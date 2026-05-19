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
    """Return a status dict: alive | stale | not-running."""
    info = _read_info(workspace)
    pid = _read_pid(workspace)
    if info is None and pid is None:
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
    _open_browser(url)
    return {"action": "opened", "url": url}


def restart(workspace: Path, port: int | None = None,
            open_browser: bool = False) -> dict:
    """Default open_browser=False (mem3dg-readdy friction #32) — see start().
    `pbg-dashboard restart` is the most-common agent-driven path; pinning the
    workspace's saved port (friction #33) plus skipping the auto-open lets
    the user keep one tab and just reload it."""
    stop(workspace)
    return start(workspace, port=port, open_browser=open_browser)


def _open_browser(url: str) -> None:
    """Best-effort: open the URL in the user's browser. Silent on failure."""
    if sys.platform == "darwin":
        opener = ["open", url]
    elif sys.platform.startswith("linux"):
        opener = ["xdg-open", url]
    elif sys.platform == "win32":
        opener = ["cmd.exe", "/c", "start", "", url]
    else:
        return
    try:
        subprocess.Popen(opener, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        pass


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
