"""End-to-end test: server can start, serve a static report, and stop cleanly."""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


PBG_TEMPLATE = Path(os.environ.get("PBG_TEMPLATE", "~/code/pbg-template")).expanduser().resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


# macOS GHA runners are noticeably slower at cold subprocess Python
# startup; the 30s budget that worked locally and on Ubuntu times out
# there. 60s is comfortably above the Ubuntu wall-clock.
@pytest.mark.timeout(60)
def test_server_serves_workspace_report(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    # Scaffold workspace
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", "demo", "--target", str(ws),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    # Render the static dashboard once so the server has something to serve
    subprocess.run(
        [sys.executable, "-c",
         f"from pathlib import Path; "
         f"from pbg_superpowers.report import render_workspace_report; "
         f"render_workspace_report(Path(r'{ws}'), today='2026-05-09')"],
        check=True, cwd=plugin_root,
    )

    # Start the server
    out = subprocess.check_output(
        [str(plugin_root / "server" / "start-server.sh"), str(ws)],
        text=True,
    ).strip()
    info = json.loads(out)
    pid_file = ws / ".pbg" / "server" / "server.pid"
    pid = int(pid_file.read_text().strip())

    try:
        # Poll until /api/state is reachable
        for _ in range(40):
            try:
                r = urllib.request.urlopen(f"http://localhost:{info['port']}/api/state", timeout=1)
                assert r.status == 200
                state = json.loads(r.read())
                assert state["name"] == "demo"
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.fail("server never came up on /api/state")

        # Index page returns the rendered report HTML
        r = urllib.request.urlopen(f"http://localhost:{info['port']}/", timeout=2)
        body = r.read().decode()
        assert "demo" in body
        assert "Workspace dashboard" in body

        # Static asset path resolves
        r = urllib.request.urlopen(f"http://localhost:{info['port']}/assets/style.css", timeout=2)
        assert r.status == 200
        css = r.read().decode()
        assert ":root" in css

        # /api/guidance with no content returns 204
        try:
            r = urllib.request.urlopen(f"http://localhost:{info['port']}/api/guidance", timeout=2)
            # urlopen treats 204 as a non-error; status code accessible directly
            assert r.status == 204
        except urllib.error.HTTPError as e:
            # Some Python versions raise on non-2xx codes; 204 itself is 2xx
            # but we accept either path here.
            assert e.code == 204

    finally:
        # Stop the server cleanly
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for it to exit (best-effort, no assertion)
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
