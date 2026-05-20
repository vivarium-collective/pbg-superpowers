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


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _state_dir(workspace: Path) -> Path:
    d = workspace / ".pbg" / "dashboard"
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
    return workspace / ".pbg" / "dashboard" / "preferred-port"


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


def _resolve_dashboard_cmd(workspace: Path) -> list[str] | None:
    """Pick the vivarium-dashboard launcher to use.

    F-friction #13 (mem3dg-readdy log) bit a user when the resolution
    order fell through to `which vivarium-dashboard` and silently picked
    up a SIBLING venv that had `pbg-compucell3d` installed. The dashboard
    then discovered composites from THAT venv's site-packages and showed
    the wrong simulators. Silent cross-venv resolution is the worst-case
    UX, so we drop both the PATH-search and the `python -m` fallback.

    Workspace .venv MUST contain vivarium-dashboard. If it doesn't,
    return None and let `start()` print a clear install command. The user
    can always set up a venv manually and re-run.
    """
    venv_bin = workspace / ".venv" / "bin" / "vivarium-dashboard"
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return [str(venv_bin), "serve"]
    return None


# Placeholder body shipped by pbg-template's reports/index.html.j2 before
# /pbg-report (or render_dashboard()) populates the SPA. Detecting this
# string lets `start()` decide whether to auto-render or refuse-with-hint
# before the user sees the bootstrap stub at the dashboard URL.
_REPORTS_PLACEHOLDER_MARKER = "No models registered yet"


def _reports_index(workspace: Path) -> Path:
    return workspace / "reports" / "index.html"


def _is_placeholder_or_missing(reports_path: Path) -> bool:
    """True if reports/index.html is absent OR still the pbg-template stub."""
    if not reports_path.is_file():
        return True
    try:
        return _REPORTS_PLACEHOLDER_MARKER in reports_path.read_text(errors="replace")
    except OSError:
        return True


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
          open_browser: bool = False) -> dict:
    """Start the dashboard server in the background. Returns the info dict.

    Default open_browser=False (mem3dg-readdy friction #32). The agent-
    driven case is the more common one — the user is already on a tab and
    auto-opening a new tab on every restart is friction-by-default. CLI
    users get the URL in stdout and can click it; pass --browser to opt
    in to auto-open.
    """
    workspace = workspace.resolve()
    s = status(workspace)
    if s["state"] == "alive":
        if open_browser and s.get("info", {}).get("url"):
            _open_browser(s["info"]["url"])
        return {"action": "already-running", **s["info"]}
    if s["state"] == "stale":
        _clear_state(workspace)

    cmd_prefix = _resolve_dashboard_cmd(workspace)
    if cmd_prefix is None:
        raise RuntimeError(
            "vivarium-dashboard is not installed in the workspace venv at "
            f"{workspace}/.venv/. Install it before starting the dashboard:\n"
            f"  uv pip install --python {workspace}/.venv/bin/python -e "
            "/path/to/vivarium-dashboard\n"
            "Cross-venv fallback is intentionally disabled — a sibling "
            "venv's vivarium-dashboard would discover composites from THAT "
            "venv's site-packages, not this workspace's. See mem3dg-readdy "
            "friction log #13."
        )

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
    with log.open("ab") as logf:
        proc = subprocess.Popen(
            cmd, cwd=str(workspace),
            stdout=logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach from caller's process group
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


def open_url(workspace: Path) -> dict:
    """Open the running dashboard's URL in the user's default browser.

    Starts the server first if it isn't running.
    """
    s = status(workspace)
    if s["state"] != "alive":
        return start(workspace, open_browser=True)
    url = s["info"]["url"]
    how = _open_browser(url)
    action = "focused" if how == "focused" else "opened"
    return {"action": action, "url": url}


def restart(workspace: Path, port: int | None = None,
            open_browser: bool = False) -> dict:
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
            f"{workspace}/.venv/. Refusing to restart — the running "
            "dashboard would be stopped and unable to restart. Install "
            "vivarium-dashboard in the workspace venv first:\n"
            f"  uv pip install --python {workspace}/.venv/bin/python -e "
            "/path/to/vivarium-dashboard\n"
            "If you only want to STOP the running dashboard, run "
            "`pbg-dashboard stop` instead (stop is venv-agnostic — it "
            "only needs the PID file)."
        )
    stop(workspace)
    return start(workspace, port=port, open_browser=open_browser)


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
    args = p.parse_args(argv)

    ws = args.workspace.resolve()
    # `--browser` is the new opt-in; `--no-browser` is kept as a recognized
    # but redundant flag so existing skill invocations don't error.
    open_b = bool(args.browser) and not args.no_browser
    try:
        if args.subcommand == "start":
            r = start(ws, port=args.port, open_browser=open_b)
        elif args.subcommand == "stop":
            r = stop(ws)
        elif args.subcommand == "status":
            r = status(ws)
        elif args.subcommand == "open":
            r = open_url(ws)
        elif args.subcommand == "restart":
            r = restart(ws, port=args.port, open_browser=open_b)
        else:
            raise SystemExit(2)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
