"""Start / stop / status / open the interactive vivarium-dashboard server.

Distinct from ``pbg_superpowers.server`` (which manages the report-mirror
server under ``.pbg/server/``). The interactive dashboard is the
side-rail-tabbed UI served by the ``vivarium-dashboard`` pip package.

State lives at ``<workspace>/.pbg/dashboard/``:

  dashboard-info   JSON: {port, host, url, pid_file, started_at, workspace}
  dashboard.pid    text: PID of the running server process
  dashboard.log    text: stdout/stderr of the server process

The two servers can co-exist; they share neither port nor PID file.
"""
from __future__ import annotations
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from pbg_superpowers.workspace_paths import WorkspacePaths


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _state_dir(workspace: Path) -> Path:
    d = WorkspacePaths.load(workspace).pbg / "dashboard"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _info_file(workspace: Path) -> Path:
    return _state_dir(workspace) / "dashboard-info"


def _pid_file(workspace: Path) -> Path:
    return _state_dir(workspace) / "dashboard.pid"


def _log_file(workspace: Path) -> Path:
    return _state_dir(workspace) / "dashboard.log"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_free_port(preferred: int = 8765) -> int:
    """Try ``preferred`` first; if taken, ask the kernel for any free port."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", preferred))
        return preferred
    except OSError:
        s.close()
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port
    finally:
        try:
            s.close()
        except OSError:
            pass


# mem3dg-readdy friction #33: with multiple workspaces, only the first to
# launch gets the default port (8765); every subsequent workspace ends up
# on a random kernel-assigned port that shifts on each restart. Users
# can't bookmark a stable URL. Persist the first-picked port per workspace
# so `restart` reuses it instead of re-rolling.
def _preferred_port_file(workspace: Path) -> Path:
    return WorkspacePaths.load(workspace).pbg / "dashboard" / "preferred-port"


def _read_preferred_port(workspace: Path) -> int | None:
    path = _preferred_port_file(workspace)
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_preferred_port(workspace: Path, port: int) -> None:
    path = _preferred_port_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(port) + "\n")


def _is_port_free(port: int) -> bool:
    """True if we can bind to 127.0.0.1:port right now."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def _resolve_port(workspace: Path, explicit_port: int | None) -> int:
    """Decide which port to use for this workspace's dashboard.

    Precedence:
      1. ``explicit_port`` from the CLI/caller — always wins.
      2. The workspace's saved preferred-port, IF still free (so a peer
         on the same port doesn't get clobbered).
      3. 8765 if free, else any kernel-assigned port.

    The chosen port is written to ``<ws>/.pbg/dashboard/preferred-port``
    so subsequent restarts reuse it (mem3dg-readdy friction #33).
    """
    if explicit_port is not None:
        _write_preferred_port(workspace, explicit_port)
        return explicit_port
    saved = _read_preferred_port(workspace)
    if saved is not None and _is_port_free(saved):
        return saved
    chosen = _pick_free_port(8765)
    _write_preferred_port(workspace, chosen)
    return chosen


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _http_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


def _read_info(workspace: Path) -> dict | None:
    p = _info_file(workspace)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _read_pid(workspace: Path) -> int | None:
    p = _pid_file(workspace)
    if not p.is_file():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def _clear_state(workspace: Path) -> None:
    for p in (_pid_file(workspace), _info_file(workspace)):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Adopt an externally-launched server (v2ecoli friction #11)
# ---------------------------------------------------------------------------
# When someone starts the dashboard directly —
#   python -m vivarium_dashboard.server --workspace . --port 8765
# — the .pbg/dashboard/ state files are never written, so `status` used to
# report `not-running` even though the UI was live and curl-able. Probe the
# known port(s), confirm the listener really is THIS workspace's dashboard
# (so we never adopt a peer workspace's server on 8765), and write the state
# files so subsequent status/stop/restart behave.

def _listening_pid_on_port(port: int) -> int | None:
    """Return the PID listening on 127.0.0.1:<port>, via lsof. None if none."""
    try:
        r = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (r.stdout or "").split():
        try:
            return int(line)
        except ValueError:
            continue
    return None


def _proc_cmdline(pid: int) -> str:
    """Best-effort command line for `pid` (empty string if unavailable)."""
    try:
        r = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        )
        return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _proc_cwd(pid: int) -> Path | None:
    """Best-effort working directory for `pid` via lsof (None if unavailable)."""
    try:
        r = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (r.stdout or "").splitlines():
        if line.startswith("n"):  # lsof field-output: n<path>
            try:
                return Path(line[1:]).resolve()
            except (OSError, ValueError):
                return None
    return None


def _proc_is_workspace_dashboard(pid: int, workspace: Path) -> bool:
    """True iff `pid` is a vivarium-dashboard server bound to `workspace`.

    Identity check (so we never adopt a different workspace's server that
    happens to hold the default port):
      - the command line must look like the dashboard server, AND
      - either the resolved `--workspace <path>` arg, or the process cwd,
        must equal `workspace`.
    """
    cmd = _proc_cmdline(pid)
    if "vivarium_dashboard" not in cmd and "vivarium-dashboard" not in cmd:
        return False
    ws = workspace.resolve()
    # Explicit `--workspace <path>` form.
    toks = cmd.split()
    for i, tok in enumerate(toks):
        if tok == "--workspace" and i + 1 < len(toks):
            try:
                if Path(toks[i + 1]).resolve() == ws:
                    return True
            except (OSError, ValueError):
                pass
        elif tok.startswith("--workspace="):
            try:
                if Path(tok.split("=", 1)[1]).resolve() == ws:
                    return True
            except (OSError, ValueError):
                pass
    # Fallback: launched from the workspace dir (e.g. `--workspace .`).
    cwd = _proc_cwd(pid)
    return cwd is not None and cwd == ws


def _candidate_ports(workspace: Path) -> list[int]:
    """Ports worth probing: the saved preferred-port, then the 8765 default."""
    ports: list[int] = []
    saved = _read_preferred_port(workspace)
    if saved is not None:
        ports.append(saved)
    if 8765 not in ports:
        ports.append(8765)
    return ports


def _adopt_running_server(workspace: Path) -> dict | None:
    """Probe known ports for a live dashboard bound to `workspace`; adopt it.

    On a confirmed match, write `.pbg/dashboard/{dashboard-info,dashboard.pid}`
    so future status/stop/restart see it, and return the info dict. Returns
    None when nothing adoptable is found.
    """
    for port in _candidate_ports(workspace):
        url = f"http://localhost:{port}"
        if not _http_ok(url):
            continue
        pid = _listening_pid_on_port(port)
        if pid is None or not _proc_is_workspace_dashboard(pid, workspace):
            continue
        info = {
            "host": "127.0.0.1",
            "port": port,
            "url": url,
            "pid": pid,
            "workspace": str(workspace.resolve()),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "adopted": True,  # marks a server we discovered, didn't launch
        }
        try:
            _info_file(workspace).write_text(json.dumps(info, indent=2))
            _pid_file(workspace).write_text(str(pid))
        except OSError:
            # Couldn't persist (read-only fs?) — still report it as alive.
            pass
        return info
    return None


def _find_main_worktree(workspace: Path) -> Path | None:
    """For git worktrees, return the main (primary) worktree's path.

    A git worktree has a ``.git`` *file* (not directory) of the form
    ``gitdir: <main>/.git/worktrees/<name>``. The main worktree itself has
    a ``.git`` directory. Returns the main worktree's root path when
    ``workspace`` is a secondary worktree; returns ``workspace`` when it
    IS the main worktree; returns ``None`` when ``.git`` is missing
    entirely.

    Used by ``_resolve_dashboard_cmd`` to fall back to a sibling
    worktree's ``.venv`` — safe because all worktrees of the same repo
    share the same source code (composites resolve identically via the
    workspace_root sys.path injection the dashboard already does).
    """
    git_path = workspace / ".git"
    if git_path.is_dir():
        return workspace
    if not git_path.is_file():
        return None
    try:
        content = git_path.read_text().strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not content.startswith(prefix):
        return None
    gitdir = Path(content[len(prefix):].strip())
    if not gitdir.is_absolute():
        gitdir = (workspace / gitdir).resolve()
    # Expected shape: <main>/.git/worktrees/<name>
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return None


def _resolve_dashboard_cmd(workspace: Path) -> tuple[list[str], Path] | None:
    """Pick the vivarium-dashboard launcher to use.

    Returns ``(cmd, venv_root)`` where ``cmd`` is the launcher prefix and
    ``venv_root`` is the workspace the venv came from (for diagnostics).

    Resolution order:

      1. **Local ``<workspace>/.venv/bin/vivarium-dashboard``** — the canonical
         case. Composites resolve from local site-packages exactly as
         intended.
      2. **Parent git-worktree's ``.venv/bin/vivarium-dashboard``** — when
         this workspace is a secondary git worktree (``.git`` is a file
         pointing at ``<main>/.git/worktrees/<name>``) and the main
         worktree has a usable venv. Safe because worktrees share source;
         the dashboard's ``set_workspace_root()`` + sys.path injection
         ensures the **local** workspace's v2ecoli/ takes precedence over
         the venv's editable install.

         This avoids forcing a per-worktree ``uv sync`` (~5 min) for what
         is effectively the same source tree.

    F-friction #13 (mem3dg-readdy log) — SIBLING workspace fallback is
    still off. Different repos must each install their own dashboard, or
    the discovered composites are wrong.
    """
    local_bin = workspace / ".venv" / "bin" / "vivarium-dashboard"
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return ([str(local_bin), "serve"], workspace)
    main = _find_main_worktree(workspace)
    if main is not None and main.resolve() != workspace.resolve():
        main_bin = main / ".venv" / "bin" / "vivarium-dashboard"
        if main_bin.is_file() and os.access(main_bin, os.X_OK):
            return ([str(main_bin), "serve"], main)
    return None


def prepare_investigation(workspace: Path | str, *,
                          investigation: str | None = None,
                          study: str | None = None,
                          steps: int | None = None,
                          render_only: bool = False,
                          param_set: str | None = None,
                          dashboard_url: str | None = None) -> int:
    """Prepare an investigation's coordinated generation.

    Thin wrapper over ``vivarium-dashboard prepare-investigation`` — that
    command lives in the vivarium-dashboard package (co-located with the run
    API + comparative_viz it drives), and this is how the framework invokes it.
    Requires a running dashboard for the workspace. Runs in the foreground
    (streams progress); returns the subprocess exit code.
    """
    workspace = Path(workspace)
    venv_bin = workspace / ".venv" / "bin" / "vivarium-dashboard"
    if not (venv_bin.is_file() and os.access(venv_bin, os.X_OK)):
        raise FileNotFoundError(
            f"vivarium-dashboard not found in {workspace}/.venv/bin — install "
            "it into the workspace venv first.")
    cmd = [str(venv_bin), "prepare-investigation", "--workspace", str(workspace)]
    if investigation:
        cmd += ["--investigation", investigation]
    if study:
        cmd += ["--study", study]
    if steps is not None:
        cmd += ["--steps", str(steps)]
    if render_only:
        cmd += ["--render-only"]
    if param_set:
        cmd += ["--param-set", str(param_set)]
    if dashboard_url:
        cmd += ["--dashboard-url", dashboard_url]
    return subprocess.run(cmd, cwd=str(workspace)).returncode


# Placeholder bodies that overwrite reports/index.html with something OTHER
# than the rich vivarium-dashboard SPA. Detecting any of these lets
# `start()` decide whether to auto-render the real SPA before the user
# sees an empty page at the dashboard URL.
#
#   1. "No models registered yet" — pbg-template's bootstrap stub (the
#      Jinja-rendered reports/index.html.j2 ships this body before
#      /pbg-report or render_dashboard() populates the SPA).
#   2. "No models yet" — pbg_superpowers.report.render_workspace_report()
#      stub. /pbg-report invokes that helper, which writes a
#      workspace-level dashboard (Models / Findings index / Recent
#      decisions panels) to the SAME path the SPA uses. Without this
#      marker, /pbg-report silently overwrites the SPA and the next
#      `pbg-dashboard start` doesn't notice (mock 2026-05-28: the user
#      sees a 4-line stub page until manually re-rendered).
_REPORTS_PLACEHOLDER_MARKERS = (
    "No models registered yet",
    "No models yet",
)


def _reports_index(workspace: Path) -> Path:
    return WorkspacePaths.load(workspace).reports / "index.html"


def _is_placeholder_or_missing(reports_path: Path) -> bool:
    """True if reports/index.html is absent OR still a known stub."""
    if not reports_path.is_file():
        return True
    try:
        body = reports_path.read_text(errors="replace")
    except OSError:
        return True
    return any(marker in body for marker in _REPORTS_PLACEHOLDER_MARKERS)


def _try_render_dashboard(workspace: Path) -> tuple[bool, str | None]:
    """Try to render the workspace SPA before serving. Returns (rendered,
    error_msg). When vivarium-dashboard isn't importable from THIS Python,
    rendered=False and error_msg names the install command — the caller
    decides whether to refuse-to-start or proceed with the placeholder."""
    try:
        from vivarium_dashboard.lib.report import render_dashboard
    except ImportError as e:
        return False, (
            f"vivarium-dashboard not importable from {sys.executable}: {e}. "
            f"Run `{workspace}/.venv/bin/python scripts/render-dashboard.py` "
            "to render the SPA, then re-run dashboard start."
        )
    try:
        render_dashboard(workspace)
    except Exception as e:  # noqa: BLE001 — render errors must surface
        return False, f"render_dashboard({workspace}) raised: {type(e).__name__}: {e}"
    return True, None


# ---------------------------------------------------------------------------
# Public ops
# ---------------------------------------------------------------------------

def status(workspace: Path) -> dict:
    """Return a status dict: alive | stale | not-running.

    v2ecoli friction #11: when our own state files are absent we don't
    immediately conclude not-running — a dashboard may have been launched
    directly (``python -m vivarium_dashboard.server …``) without writing
    them. Probe the known port(s) and adopt a live server that's confirmed
    to be THIS workspace's, writing the state files so later commands work.
    """
    info = _read_info(workspace)
    pid = _read_pid(workspace)
    if info is None and pid is None:
        adopted = _adopt_running_server(workspace)
        if adopted is not None:
            return {"state": "alive", "info": adopted, "pid": adopted["pid"],
                    "note": "adopted externally-launched server"}
        return {"state": "not-running"}
    if pid is None or not _pid_alive(pid):
        return {"state": "stale", "info": info, "pid": pid}
    url = (info or {}).get("url") or ""
    if url and not _http_ok(url):
        return {"state": "stale", "info": info, "pid": pid,
                "note": "PID alive but HTTP probe failed"}
    return {"state": "alive", "info": info, "pid": pid}


def start(workspace: Path, port: int | None = None,
          open_browser: bool = False,
          investigation: str | None = None) -> dict:
    """Start the dashboard server in the background. Returns the info dict.

    Default open_browser=False (mem3dg-readdy friction #32). The agent-
    driven case is the more common one — the user is already on a tab and
    auto-opening a new tab on every restart is friction-by-default. CLI
    users get the URL in stdout and can click it; pass --browser to opt
    in to auto-open.

    ``investigation`` (when set, requires ``open_browser=True``): after
    opening / focusing the dashboard URL, inject a JS call to switch the
    SPA to the named investigation's detail view. Bypasses the SPA's
    branch-name-based auto-pick, which only matches branches of the form
    ``investigation/<slug>`` and otherwise falls back to the alphabetically-
    first investigation.
    """
    workspace = workspace.resolve()
    s = status(workspace)
    if s["state"] == "alive":
        if open_browser and s.get("info", {}).get("url"):
            _open_browser(s["info"]["url"])
            if investigation:
                _switch_investigation_in_browser(investigation)
        return {"action": "already-running", **s["info"]}
    if s["state"] == "stale":
        _clear_state(workspace)

    resolved = _resolve_dashboard_cmd(workspace)
    if resolved is None:
        raise RuntimeError(
            "vivarium-dashboard is not installed in the workspace venv at "
            f"{workspace}/.venv/, and no parent git-worktree's venv has it "
            "either. Install it before starting the dashboard:\n"
            f"  uv pip install --python {workspace}/.venv/bin/python -e "
            "/path/to/vivarium-dashboard\n"
            "OR, if this is a secondary git worktree, install vivarium-dashboard "
            "into the MAIN worktree's .venv (this skill will reuse it via "
            "git-worktree-aware fallback — safe because worktrees share "
            "source). Sibling-WORKSPACE venvs are still off-limits because "
            "the discovered composites would come from the wrong site-packages "
            "(see mem3dg-readdy friction log #13)."
        )
    cmd_prefix, venv_workspace = resolved

    # F-friction #1: ensure reports/index.html is the rendered SPA, not the
    # pbg-template bootstrap placeholder. The vivarium-dashboard server happily
    # serves whatever's at that path — and the placeholder "No models
    # registered yet" body is always a bug for an end user to see. Try to
    # render now; if vivarium-dashboard isn't importable from this Python,
    # refuse-to-start with the manual command instead of serving the stub.
    reports = _reports_index(workspace)
    if _is_placeholder_or_missing(reports):
        rendered, err = _try_render_dashboard(workspace)
        if not rendered:
            raise RuntimeError(
                f"reports/index.html is still the bootstrap placeholder "
                f"(or missing) and auto-render failed.\n  {err}\n"
                "Refusing to start: serving the placeholder would show an "
                "empty 'No models registered yet' page at the dashboard URL."
            )

    # mem3dg-readdy friction #33: prefer the workspace's saved port over
    # re-rolling, so the user can bookmark a stable URL across restarts.
    chosen_port = _resolve_port(workspace, port)
    cmd = cmd_prefix + ["--workspace", str(workspace), "--port", str(chosen_port)]

    log = _log_file(workspace)
    log.parent.mkdir(parents=True, exist_ok=True)
    # Force Python UTF-8 mode in the detached server. Without this, a server
    # launched from a process whose locale resolves to ascii/C makes open()
    # default to ascii — so any unguarded read of a study.yaml / chart / .meta
    # containing unicode (τ, →, ⇌, ×, ⁷, …) raises UnicodeDecodeError, e.g.
    # /api/study-charts returning {error: 'ascii' codec...} → reports with no
    # figures. PYTHONUTF8=1 makes open() default to utf-8 regardless of locale.
    server_env = {**os.environ, "PYTHONUTF8": "1"}
    with log.open("ab") as logf:
        proc = subprocess.Popen(
            cmd, cwd=str(workspace),
            stdout=logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach from caller's process group
            env=server_env,
        )

    info = {
        "host": "127.0.0.1",
        "port": chosen_port,
        "url": f"http://localhost:{chosen_port}",
        "pid": proc.pid,
        "workspace": str(workspace),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "log_file": str(log.relative_to(workspace)),
    }
    # Mark when we used a parent worktree's venv as a fallback so
    # status/diagnostics can surface it.
    if venv_workspace.resolve() != workspace.resolve():
        info["venv_workspace"] = str(venv_workspace.resolve())
    _info_file(workspace).write_text(json.dumps(info, indent=2))
    _pid_file(workspace).write_text(str(proc.pid))

    # Wait briefly for the server to bind. If it crashes on import, surface
    # the log tail so users don't see a silent failure.
    for _ in range(40):  # up to ~4 s
        if _http_ok(info["url"]):
            break
        if proc.poll() is not None:
            tail = log.read_text()[-1500:] if log.is_file() else "(no log)"
            _clear_state(workspace)
            raise RuntimeError(
                f"vivarium-dashboard exited immediately. Last log lines:\n{tail}"
            )
        time.sleep(0.1)
    else:
        # Process is still alive but HTTP probe never succeeded — leave it
        # running; status() will report stale if the user comes back.
        info["note"] = "process alive; HTTP probe did not respond within 4s"

    if open_browser:
        _open_browser(info["url"])
        if investigation:
            _switch_investigation_in_browser(investigation)
    return {"action": "started", **info}


def stop(workspace: Path, timeout_s: float = 5.0) -> dict:
    """Send SIGTERM to the running dashboard. Returns an action dict."""
    pid = _read_pid(workspace)
    info = _read_info(workspace)
    if pid is None:
        _clear_state(workspace)
        return {"action": "not-running"}
    if not _pid_alive(pid):
        _clear_state(workspace)
        return {"action": "cleared-stale", "pid": pid}

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_state(workspace)
        return {"action": "cleared-stale", "pid": pid}

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_alive(pid):
            _clear_state(workspace)
            return {"action": "stopped", "pid": pid, "url": (info or {}).get("url")}
        time.sleep(0.1)
    # Last resort: SIGKILL.
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _clear_state(workspace)
    return {"action": "killed", "pid": pid}


def open_url(workspace: Path, investigation: str | None = None) -> dict:
    """Open the running dashboard's URL in the user's default browser.

    Starts the server first if it isn't running. When ``investigation`` is
    given, additionally calls ``_openInvestigationDetail(<slug>)`` in the
    focused tab so the SPA switches to that investigation's detail view.
    """
    s = status(workspace)
    if s["state"] != "alive":
        return start(workspace, open_browser=True, investigation=investigation)
    url = s["info"]["url"]
    how = _open_browser(url)
    action = "focused" if how == "focused" else "opened"
    out = {"action": action, "url": url}
    if investigation:
        switched = _switch_investigation_in_browser(investigation)
        out["investigation_switched"] = switched
        out["investigation"] = investigation
    return out


def restart(workspace: Path, port: int | None = None,
            open_browser: bool = False,
            investigation: str | None = None) -> dict:
    """Default open_browser=False (mem3dg-readdy friction #32) — see start().
    `pbg-dashboard restart` is the most-common agent-driven path; pinning the
    workspace's saved port (friction #33) plus skipping the auto-open lets
    the user keep one tab and just reload it.

    v2ecoli friction #9: pre-check the venv BEFORE stopping. The earlier
    behavior (stop, then start, fail start) killed the running dashboard
    and left the user with nothing — they had a working server before the
    restart and no working server after. Refuse-up-front when the venv
    can't supply vivarium-dashboard, so the running dashboard keeps
    running.
    """
    if _resolve_dashboard_cmd(workspace) is None:
        raise RuntimeError(
            "vivarium-dashboard is not installed in the workspace venv at "
            f"{workspace}/.venv/ and no parent git-worktree's venv has it "
            "either. Refusing to restart — the running dashboard would be "
            "stopped and unable to restart. Install vivarium-dashboard "
            "into the workspace venv first:\n"
            f"  uv pip install --python {workspace}/.venv/bin/python -e "
            "/path/to/vivarium-dashboard\n"
            "If you only want to STOP the running dashboard, run "
            "`pbg-dashboard stop` instead (stop is venv-agnostic — it "
            "only needs the PID file)."
        )
    stop(workspace)
    return start(workspace, port=port, open_browser=open_browser,
                 investigation=investigation)


# NOTE on AppleScript dictionaries: when ``tell application appName`` uses a
# variable, AppleScript can't resolve terminology like ``URL of t`` or
# ``active tab index of w`` at compile time. We wrap each call in
# ``using terms from application "<concrete>"`` so the right dictionary is
# loaded — Chrome's terms for the Chromium family (active tab index, tabs
# of window), Safari's for the WebKit family (current tab, tabs of window).
_FOCUS_TAB_APPLESCRIPT = r'''
on tabMatches(tabURL, targetURL)
    if tabURL is targetURL then return true
    if tabURL is (targetURL & "/") then return true
    if tabURL starts with (targetURL & "/") then return true
    if tabURL starts with (targetURL & "?") then return true
    if tabURL starts with (targetURL & "#") then return true
    return false
end tabMatches

on chromeFind(appName, targetURL)
    tell application "System Events"
        if not (exists process appName) then return "skip"
    end tell
    using terms from application "Google Chrome"
        try
            tell application appName
                set winIdx to 0
                repeat with w in windows
                    set winIdx to winIdx + 1
                    set tabIdx to 0
                    repeat with t in tabs of w
                        set tabIdx to tabIdx + 1
                        if my tabMatches((URL of t) as string, targetURL) then
                            set active tab index of w to tabIdx
                            set index of w to 1
                            activate
                            return "found"
                        end if
                    end repeat
                end repeat
            end tell
        on error
            return "skip"
        end try
    end using terms from
    return "notfound"
end chromeFind

on safariFind(appName, targetURL)
    tell application "System Events"
        if not (exists process appName) then return "skip"
    end tell
    using terms from application "Safari"
        try
            tell application appName
                repeat with w in windows
                    repeat with t in tabs of w
                        if my tabMatches((URL of t) as string, targetURL) then
                            set current tab of w to t
                            set index of w to 1
                            activate
                            return "found"
                        end if
                    end repeat
                end repeat
            end tell
        on error
            return "skip"
        end try
    end using terms from
    return "notfound"
end safariFind

on run argv
    set targetURL to item 1 of argv
    set chromeApps to {"Google Chrome", "Google Chrome Canary", "Brave Browser", "Microsoft Edge", "Arc", "Vivaldi"}
    repeat with appName in chromeApps
        set r to chromeFind(appName as string, targetURL)
        if r is "found" then return "found"
    end repeat
    set safariApps to {"Safari", "Safari Technology Preview"}
    repeat with appName in safariApps
        set r to safariFind(appName as string, targetURL)
        if r is "found" then return "found"
    end repeat
    return "notfound"
end run
'''


# AppleScript to execute a JS snippet in the focused tab. Used to call
# `_openInvestigationDetail(<slug>)` so the dashboard UI navigates to a
# specific investigation instead of defaulting to the alphabetically-first
# one (the SPA's auto-pick only honors a branch named `investigation/<slug>`,
# which most workspace branches don't match).
_EXEC_JS_IN_FRONT_TAB_APPLESCRIPT = r'''
on chromeJS(appName, js)
    tell application "System Events"
        if not (exists process appName) then return "skip"
    end tell
    using terms from application "Google Chrome"
        try
            tell application appName
                tell front window
                    execute active tab javascript js
                end tell
            end tell
            return "ok"
        on error
            return "err"
        end try
    end using terms from
end chromeJS

on safariJS(appName, js)
    tell application "System Events"
        if not (exists process appName) then return "skip"
    end tell
    using terms from application "Safari"
        try
            tell application appName
                tell front window
                    do JavaScript js in current tab
                end tell
            end tell
            return "ok"
        on error
            return "err"
        end try
    end using terms from
end safariJS

on run argv
    set js to item 1 of argv
    set chromeApps to {"Google Chrome", "Google Chrome Canary", "Brave Browser", "Microsoft Edge", "Arc", "Vivaldi"}
    repeat with appName in chromeApps
        set r to chromeJS(appName as string, js)
        if r is "ok" then return "ok"
    end repeat
    set safariApps to {"Safari", "Safari Technology Preview"}
    repeat with appName in safariApps
        set r to safariJS(appName as string, js)
        if r is "ok" then return "ok"
    end repeat
    return "notfound"
end run
'''


def _switch_investigation_in_browser(slug: str) -> bool:
    """Call ``_openInvestigationDetail(slug)`` in whatever tab is in focus.

    Best-effort. Requires macOS, an osascript-capable browser, and
    AppleScript→browser permission. Returns False on every other path —
    the caller still gets the dashboard open at the URL, just at the
    default investigation.

    The injected JS polls for ``_openInvestigationDetail`` to be defined
    (up to 8 s) so it works whether the tab is just-opened (SPA still
    loading) or already loaded.
    """
    if sys.platform != "darwin":
        return False
    if shutil.which("osascript") is None:
        return False
    # JSON-encode the slug so the JS literal is safe. Self-polling so the
    # SPA's _loadInvestigationSets() has time to populate _isetIndex.
    slug_json = json.dumps(slug)
    js = (
        "(function(){var s=" + slug_json + ";var d=Date.now()+8000;"
        "function t(){if(typeof window._openInvestigationDetail==='function'){"
        "window._openInvestigationDetail(s);}else if(Date.now()<d){"
        "setTimeout(t,200);}}t();})()"
    )
    try:
        result = subprocess.run(
            ["osascript", "-", js],
            input=_EXEC_JS_IN_FRONT_TAB_APPLESCRIPT,
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return result.stdout.strip() == "ok"


def _list_workspace_investigations(workspace: Path) -> list[str]:
    """Slugs of every investigation present in ``<workspace>/investigations/``."""
    root = WorkspacePaths.load(workspace).investigations
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "investigation.yaml").is_file()
    )


def _current_branch(workspace: Path) -> str | None:
    """Best-effort: ``git rev-parse --abbrev-ref HEAD`` from ``workspace``."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace),
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    branch = (r.stdout or "").strip()
    return branch or None


def _infer_investigation_from_branch(workspace: Path) -> str | None:
    """Infer the investigation slug from the workspace's current git branch.

    The pbg-template convention is one branch per investigation; this picks
    the matching investigation slug so callers like ``pbg-dashboard open``
    can default to the current session's investigation instead of the
    alphabetically-first one.

    Resolution order:
      1. Branch is exactly an investigation slug (e.g. ``colonies``).
      2. Branch matches the SPA's canonical ``investigation/<slug>`` pattern.
      3. Branch contains a known investigation slug as a substring (longest
         match wins so ``dnaa-replication`` beats ``dnaa``). Common feat-
         and mock-investigation prefixes are tolerated implicitly via
         substring matching.
      4. Exactly one investigation exists in the workspace — use it.
      5. Otherwise return ``None`` and let the caller pick the default.
    """
    slugs = _list_workspace_investigations(workspace)
    if not slugs:
        return None
    branch = _current_branch(workspace)
    if branch is None:
        return slugs[0] if len(slugs) == 1 else None
    if branch in slugs:
        return branch
    # Canonical SPA pattern: investigation/<slug>
    if branch.startswith("investigation/"):
        candidate = branch.split("/", 1)[1]
        if candidate in slugs:
            return candidate
    # Token-overlap scoring. Tokenize on /, -, _. Score each slug by what
    # FRACTION of its tokens appear in the branch tokens. Highest score
    # wins; ties broken by token-count then alphabetical. Pure substring
    # is a subset of this (every token of the slug is a substring), but
    # this also catches `feat/dnaa-biology` → `dnaa-replication` (shared
    # token: 'dnaa', 1/2 = 0.5 — wins over colonies' 0/1 = 0.0).
    import re
    def _tokens(s: str) -> list[str]:
        return [t for t in re.split(r"[/_-]+", s) if t]
    branch_tokens = set(_tokens(branch))
    scored: list[tuple[float, int, str]] = []
    for slug in slugs:
        slug_tokens = _tokens(slug)
        if not slug_tokens:
            continue
        hits = sum(1 for t in slug_tokens if t in branch_tokens)
        if hits == 0:
            continue
        score = hits / len(slug_tokens)
        scored.append((score, len(slug_tokens), slug))
    if scored:
        # Sort: highest score, then most-specific (longest slug), then alphabetical
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return scored[0][2]
    if len(slugs) == 1:
        return slugs[0]
    return None


def _focus_existing_tab(url: str) -> bool:
    """Try to focus a running browser's existing tab at ``url``.

    Returns True iff one of the supported browsers (Chrome family +
    Safari family) is running, has a tab whose URL matches, and was
    activated. Returns False on every other path: non-macOS, osascript
    missing, no match, AppleScript Automation permission denied, etc.

    mem3dg-readdy friction: ``pbg-dashboard open`` always opened a fresh
    tab, churning the browser even when the user already had the
    dashboard up. With multiple workspaces (each on its own port) the
    pile of duplicate tabs got out of hand fast.
    """
    if sys.platform != "darwin":
        return False
    if shutil.which("osascript") is None:
        return False
    try:
        result = subprocess.run(
            ["osascript", "-", url],
            input=_FOCUS_TAB_APPLESCRIPT,
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return result.stdout.strip() == "found"


def _open_browser(url: str) -> str:
    """Best-effort: focus the URL in an existing browser tab, else open new.

    On macOS, scans running Chrome-family and Safari-family browsers via
    AppleScript for a tab whose URL matches ``url``; if found, activates
    that tab and returns "focused". Otherwise falls back to ``open
    <url>`` (default browser, new tab) and returns "opened-new". Returns
    "skipped" if no opener applies / fails silently.
    """
    if sys.platform == "darwin":
        if _focus_existing_tab(url):
            return "focused"
        opener = ["open", url]
    elif sys.platform.startswith("linux"):
        opener = ["xdg-open", url]
    elif sys.platform == "win32":
        opener = ["cmd.exe", "/c", "start", "", url]
    else:
        return "skipped"
    try:
        subprocess.Popen(opener, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return "opened-new"
    except (FileNotFoundError, OSError):
        return "skipped"


# ---------------------------------------------------------------------------
# CLI entry point (so the skill SKILL.md can ``python -m`` it)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="pbg-dashboard",
                                description="Manage the interactive vivarium-dashboard server.")
    p.add_argument("subcommand", choices=("start", "stop", "status", "open", "restart"))
    p.add_argument("--workspace", default=".", type=Path,
                   help="Workspace root (default: cwd).")
    p.add_argument("--port", type=int, default=None,
                   help="Preferred port (default: workspace's saved port, then 8765, then any free port).")
    p.add_argument("--browser", action="store_true",
                   help="Open the dashboard URL in the user's default browser. Default: off (the URL is printed to stdout). The off-by-default matches the agentic case where the user is already on a tab; pre-2026-05-19 behavior was on-by-default and churned tabs on every restart.")
    p.add_argument("--no-browser", action="store_true",
                   help="DEPRECATED — auto-open is now off by default. Pass --browser to opt in.")
    p.add_argument("--investigation", default=None,
                   help="When the dashboard URL is opened/focused, switch the SPA to this investigation slug. "
                   "Implies --browser. Without this flag the dashboard auto-picks the alphabetically-first "
                   "investigation when the workspace branch doesn't match the pattern 'investigation/<slug>'.")
    args = p.parse_args(argv)

    ws = args.workspace.resolve()
    # `--browser` is the new opt-in; `--no-browser` is kept as a recognized
    # but redundant flag so existing skill invocations don't error.
    # --investigation always implies the user wants the browser to land on
    # that investigation, so it implicitly enables --browser.
    open_b = (bool(args.browser) and not args.no_browser) or bool(args.investigation)
    # `open` is inherently a browser-opener — auto-infer the investigation
    # even without --browser. start/restart only infer when --browser was
    # explicitly requested (otherwise they're headless / agent-driven and
    # tabs shouldn't open).
    will_show_browser = open_b or args.subcommand == "open"
    investigation = args.investigation
    if investigation is None and will_show_browser:
        investigation = _infer_investigation_from_branch(ws)
    try:
        if args.subcommand == "start":
            r = start(ws, port=args.port, open_browser=open_b,
                      investigation=investigation)
        elif args.subcommand == "stop":
            r = stop(ws)
        elif args.subcommand == "status":
            r = status(ws)
        elif args.subcommand == "open":
            r = open_url(ws, investigation=investigation)
        elif args.subcommand == "restart":
            r = restart(ws, port=args.port, open_browser=open_b,
                        investigation=investigation)
        else:
            raise SystemExit(2)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
