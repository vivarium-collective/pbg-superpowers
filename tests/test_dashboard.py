"""Tests for viva_superpowers.dashboard — Slice E of the mem3dg-readdy fix.

Covers two behavior changes the friction log called out:

  - _resolve_dashboard_cmd no longer falls through to PATH or python -m;
    the workspace venv MUST have vivarium-workbench installed. A sibling
    venv that happens to have it installed (with a different composite
    set) no longer poisons the dashboard's discovery (friction #13).

  - start() refuses to launch when reports/index.html is missing or
    still the pbg-template bootstrap placeholder. Tries auto-render
    first; falls back to a clear refusal with the manual command
    (friction #1).
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from viva_superpowers import dashboard as dash_mod


# ---------------------------------------------------------------------------
# _resolve_dashboard_cmd — strict workspace-venv-only resolution
# ---------------------------------------------------------------------------


def _make_workspace_with_venv_bin(tmp_path: Path, *, has_bin: bool) -> Path:
    """Build a minimal workspace dir; optionally seed .venv/bin/vivarium-workbench."""
    ws = tmp_path / "ws"
    (ws / ".venv" / "bin").mkdir(parents=True)
    if has_bin:
        bin_path = ws / ".venv" / "bin" / "vivarium-workbench"
        bin_path.write_text("#!/bin/sh\necho stub\n")
        bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return ws


def test_resolve_returns_venv_bin_when_present(tmp_path):
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=True)
    result = dash_mod._resolve_dashboard_cmd(ws)
    assert result is not None
    cmd, venv_workspace = result
    assert cmd[0] == str(ws / ".venv" / "bin" / "vivarium-workbench")
    assert cmd[1] == "serve"
    assert venv_workspace == ws


def test_resolve_falls_back_to_parent_worktree_venv(tmp_path):
    """When this workspace is a secondary git worktree of a main worktree
    that DOES have a usable .venv/bin/vivarium-workbench, the resolver
    reuses it. Worktrees share source so the composites resolve from this
    workspace via the dashboard's set_workspace_root() injection."""
    main = tmp_path / "main"
    (main / ".venv" / "bin").mkdir(parents=True)
    bin_path = main / ".venv" / "bin" / "vivarium-workbench"
    bin_path.write_text("#!/bin/sh\necho stub\n")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR)
    (main / ".git").mkdir()
    # Simulate the git internals for a worktree: <main>/.git/worktrees/<name>
    wt = tmp_path / "worktree-dnaa"
    wt.mkdir()
    wt_gitdir = main / ".git" / "worktrees" / "dnaa"
    wt_gitdir.mkdir(parents=True)
    # The worktree's .git is a regular file pointing at its gitdir.
    (wt / ".git").write_text(f"gitdir: {wt_gitdir}\n")
    # No local .venv in the worktree; the resolver should reach the main's.
    result = dash_mod._resolve_dashboard_cmd(wt)
    assert result is not None
    cmd, venv_workspace = result
    assert cmd[0] == str(main / ".venv" / "bin" / "vivarium-workbench")
    assert venv_workspace == main


def test_resolve_returns_none_when_venv_bin_missing(tmp_path):
    """No workspace-venv binary → None. Used to fall through to
    `which vivarium-workbench` and silently pick up a sibling venv;
    that's the foot-gun this slice closes."""
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=False)
    assert dash_mod._resolve_dashboard_cmd(ws) is None


def test_resolve_ignores_path_vivarium_workbench(tmp_path, monkeypatch):
    """Even when `which vivarium-workbench` would find one on PATH, the
    resolver must NOT use it — that's exactly the friction #13 scenario.

    We simulate by putting a fake binary on PATH and asserting the resolver
    still returns None when the workspace .venv has none."""
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=False)
    fake_bin_dir = tmp_path / "fake_path"
    fake_bin_dir.mkdir()
    fake_bin = fake_bin_dir / "vivarium-workbench"
    fake_bin.write_text("#!/bin/sh\necho sibling-venv-stub\n")
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(fake_bin_dir) + ":" + os.environ.get("PATH", ""))
    # Resolver must still return None — PATH is no longer consulted.
    assert dash_mod._resolve_dashboard_cmd(ws) is None


# ---------------------------------------------------------------------------
# Placeholder detection + refusal-to-start
# ---------------------------------------------------------------------------


def test_is_placeholder_true_when_missing(tmp_path):
    assert dash_mod._is_placeholder_or_missing(tmp_path / "reports" / "index.html") is True


def test_is_placeholder_true_when_bootstrap_stub(tmp_path):
    p = tmp_path / "reports" / "index.html"
    p.parent.mkdir(parents=True)
    p.write_text(
        "<!doctype html><html><body>"
        "<p>No models registered yet. Run /pbg-add-model name to begin.</p>"
        "</body></html>"
    )
    assert dash_mod._is_placeholder_or_missing(p) is True


def test_is_placeholder_true_when_pbg_report_stub(tmp_path):
    """`/pbg-report` writes a workspace-level stub via
    viva_superpowers.report.render_workspace_report() to the SAME path
    the SPA uses. Body says 'No models yet' (note: shorter than the
    pbg-template bootstrap stub's 'No models registered yet').
    Without this marker, /pbg-report silently overwrites the SPA.
    """
    p = tmp_path / "reports" / "index.html"
    p.parent.mkdir(parents=True)
    p.write_text(
        "<!doctype html><html><body>"
        "<header><h1>v2ecoli</h1>"
        "<p class='subtitle'>Workspace dashboard · regenerated 2026-05-28</p></header>"
        "<div class='panel'><h2>Models</h2>"
        "<p>No models yet. <code>/pbg-add-model &lt;name&gt;</code></p></div>"
        "</body></html>"
    )
    assert dash_mod._is_placeholder_or_missing(p) is True


def test_is_placeholder_false_when_real_spa(tmp_path):
    p = tmp_path / "reports" / "index.html"
    p.parent.mkdir(parents=True)
    p.write_text(
        "<!doctype html><html><body>"
        "<div id='app'><h1>Workspace dashboard</h1>"
        "<div>3 models · 2 investigations · 6 studies</div></div>"
        "</body></html>"
    )
    assert dash_mod._is_placeholder_or_missing(p) is False


def test_start_refuses_when_no_venv_bin(tmp_path, monkeypatch):
    """When workspace .venv has no vivarium-workbench, start() must raise
    with an actionable install command — NOT fall through to PATH."""
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=False)
    # Make sure no PATH-installed vivarium-workbench sneaks in either.
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError) as ei:
        dash_mod.start(ws, open_browser=False)
    msg = str(ei.value)
    assert "vivarium-workbench is not installed in the workspace venv" in msg
    assert "uv pip install" in msg
    # Sibling-WORKSPACE fallback (different repo, different composites) is
    # still off — only sibling git-worktree fallback (same source) is allowed.
    assert "Sibling-WORKSPACE venvs are still off-limits" in msg
    assert "friction log #13" in msg


def _block_vivarium_workbench_imports(monkeypatch):
    """Clear every cached vivarium_workbench.* submodule so the next
    `from vivarium_workbench.lib.report import render_dashboard` fails
    fresh. Setting sys.modules['vivarium_workbench'] to None alone isn't
    enough — Python honors cached submodules even when the parent is None.
    Cross-test pollution from earlier integration tests that DO import
    vivarium-workbench is the reason this helper exists."""
    import sys
    for key in list(sys.modules):
        if key == "vivarium_workbench" or key.startswith("vivarium_workbench."):
            monkeypatch.delitem(sys.modules, key, raising=False)
    monkeypatch.setitem(sys.modules, "vivarium_workbench", None)


def test_start_refuses_when_placeholder_and_render_unavailable(tmp_path, monkeypatch):
    """Workspace has a .venv/bin/vivarium-workbench, but reports/index.html
    is the bootstrap placeholder AND vivarium-workbench isn't importable
    from this Python (so auto-render can't run). start() must refuse with
    a clear hint rather than serving the stub."""
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=True)
    reports = ws / "reports"
    reports.mkdir()
    (reports / "index.html").write_text(
        "<html><p>No models registered yet. Run /pbg-add-model</p></html>"
    )
    _block_vivarium_workbench_imports(monkeypatch)

    with pytest.raises(RuntimeError) as ei:
        dash_mod.start(ws, open_browser=False)
    msg = str(ei.value)
    assert "placeholder" in msg
    assert "Refusing to start" in msg


def test_try_render_dashboard_handles_missing_import(monkeypatch, tmp_path):
    """The fallback path (when vivarium_workbench isn't importable) must
    return a clean (False, error_msg) tuple — not raise."""
    _block_vivarium_workbench_imports(monkeypatch)
    rendered, err = dash_mod._try_render_dashboard(tmp_path)
    assert rendered is False
    assert err is not None
    assert "not importable" in err


# ---------------------------------------------------------------------------
# Preferred-port persistence (mem3dg-readdy friction #33)
# ---------------------------------------------------------------------------


def test_resolve_port_writes_explicit_port_to_disk(tmp_path):
    """Explicit --port overrides everything AND becomes the new saved
    preferred port for subsequent restarts."""
    ws = tmp_path / "ws"
    ws.mkdir()
    assert dash_mod._resolve_port(ws, 9999) == 9999
    assert dash_mod._read_preferred_port(ws) == 9999


def test_resolve_port_reuses_saved_port_when_free(tmp_path, monkeypatch):
    """Subsequent restarts read the saved port and reuse it — that's the
    whole friction #33 fix; bookmarkable URLs across restarts."""
    ws = tmp_path / "ws"
    ws.mkdir()
    dash_mod._write_preferred_port(ws, 8777)
    # Force the "is this port free?" probe to return True regardless of
    # actual socket state — the test must work whether or not 8777 happens
    # to be in use on the dev machine.
    monkeypatch.setattr(dash_mod, "_is_port_free", lambda p: True)
    assert dash_mod._resolve_port(ws, None) == 8777


def test_resolve_port_rerolls_when_saved_port_taken(tmp_path, monkeypatch):
    """If the saved port is now occupied (e.g. a peer workspace grabbed
    it after a kernel restart), pick a fresh one and persist that. The
    user gets a new bookmarkable URL; no clobbering the peer."""
    ws = tmp_path / "ws"
    ws.mkdir()
    dash_mod._write_preferred_port(ws, 8777)
    monkeypatch.setattr(dash_mod, "_is_port_free", lambda p: False)
    monkeypatch.setattr(dash_mod, "_pick_free_port", lambda preferred=8765: 8800)
    assert dash_mod._resolve_port(ws, None) == 8800
    assert dash_mod._read_preferred_port(ws) == 8800


def test_resolve_port_picks_default_then_writes(tmp_path, monkeypatch):
    """Fresh workspace with no saved port and no explicit port → picks
    via _pick_free_port (8765 if free, else any) AND writes the result."""
    ws = tmp_path / "ws"
    ws.mkdir()
    assert dash_mod._read_preferred_port(ws) is None
    monkeypatch.setattr(dash_mod, "_pick_free_port", lambda preferred=8765: 8765)
    assert dash_mod._resolve_port(ws, None) == 8765
    assert dash_mod._read_preferred_port(ws) == 8765


def test_browser_default_is_off_in_start(tmp_path, monkeypatch):
    """start() defaults to open_browser=False — the agentic case where
    the user is already on a tab. Verify by inspecting the signature
    (don't actually start a subprocess)."""
    import inspect
    sig = inspect.signature(dash_mod.start)
    assert sig.parameters["open_browser"].default is False
    # restart() should match — it composes stop + start.
    sig_r = inspect.signature(dash_mod.restart)
    assert sig_r.parameters["open_browser"].default is False


# ---------------------------------------------------------------------------
# v2ecoli friction #9: restart pre-checks venv before killing the running
# dashboard. Stop is unaffected — it's already venv-agnostic.
# ---------------------------------------------------------------------------


def test_restart_refuses_when_venv_bin_missing(tmp_path, monkeypatch):
    """If start() would fail the venv check, restart() refuses BEFORE
    calling stop. The running dashboard is preserved."""
    ws = _make_workspace_with_venv_bin(tmp_path, has_bin=False)
    monkeypatch.setenv("PATH", "")
    # Seed a fake PID file so stop would have something to kill if it ran.
    pid_file = ws / ".pbg" / "dashboard" / "dashboard.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("99999\n")

    with pytest.raises(RuntimeError) as ei:
        dash_mod.restart(ws, open_browser=False)
    msg = str(ei.value)
    assert "Refusing to restart" in msg
    assert "stop is venv-agnostic" in msg
    # The pid file must still be there — stop was not called.
    assert pid_file.is_file()


def test_stop_is_venv_agnostic_when_no_pid(tmp_path):
    """Stop with no running dashboard returns not-running cleanly. The
    function never consults the venv — it only needs the PID file."""
    ws = tmp_path / "ws"
    ws.mkdir()
    # No .venv at all in the workspace.
    out = dash_mod.stop(ws)
    assert out["action"] == "not-running"


# ---------------------------------------------------------------------------
# Adopt an externally-launched server (v2ecoli friction #11)
# ---------------------------------------------------------------------------

def test_status_not_running_when_no_state_and_no_live_server(tmp_path, monkeypatch):
    """No state files AND no adoptable server → honest not-running."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(dash_mod, "_http_ok", lambda url, timeout=1.0: False)
    assert dash_mod.status(ws) == {"state": "not-running"}


def test_status_adopts_externally_launched_server(tmp_path, monkeypatch):
    """A live dashboard on the known port, launched directly (no state files),
    is discovered, confirmed as THIS workspace's, and adopted — status reports
    alive and the state files get written so stop/restart work afterward."""
    ws = tmp_path / "ws"
    ws.mkdir()
    dash_mod._write_preferred_port(ws, 8765)

    monkeypatch.setattr(dash_mod, "_http_ok", lambda url, timeout=1.0: True)
    monkeypatch.setattr(dash_mod, "_listening_pid_on_port", lambda port: 4242)
    monkeypatch.setattr(dash_mod, "_proc_is_workspace_dashboard",
                        lambda pid, workspace: True)

    out = dash_mod.status(ws)
    assert out["state"] == "alive"
    assert out["pid"] == 4242
    assert out["note"] == "adopted externally-launched server"
    assert out["info"]["adopted"] is True
    assert out["info"]["port"] == 8765
    # State files were written so subsequent status() reads them directly.
    assert dash_mod._read_pid(ws) == 4242
    assert dash_mod._read_info(ws)["adopted"] is True


def test_status_does_not_adopt_other_workspaces_server(tmp_path, monkeypatch):
    """A live server on 8765 that belongs to a DIFFERENT workspace must NOT
    be adopted — the identity check fails, status stays not-running."""
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(dash_mod, "_http_ok", lambda url, timeout=1.0: True)
    monkeypatch.setattr(dash_mod, "_listening_pid_on_port", lambda port: 4242)
    # The listener is a dashboard, but for some OTHER workspace.
    monkeypatch.setattr(dash_mod, "_proc_is_workspace_dashboard",
                        lambda pid, workspace: False)
    assert dash_mod.status(ws) == {"state": "not-running"}
    # Nothing was written.
    assert dash_mod._read_pid(ws) is None


def test_proc_is_workspace_dashboard_matches_workspace_arg(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    cmd = f"python -m vivarium_workbench.cli serve --workspace {ws} --port 8765"
    monkeypatch.setattr(dash_mod, "_proc_cmdline", lambda pid: cmd)
    monkeypatch.setattr(dash_mod, "_proc_cwd", lambda pid: None)
    assert dash_mod._proc_is_workspace_dashboard(4242, ws) is True


def test_proc_is_workspace_dashboard_matches_cwd_fallback(tmp_path, monkeypatch):
    """`--workspace .` form: the arg isn't an absolute path, so fall back to
    matching the process cwd."""
    ws = tmp_path / "ws"
    ws.mkdir()
    cmd = "python -m vivarium_workbench.cli serve --workspace . --port 8765"
    monkeypatch.setattr(dash_mod, "_proc_cmdline", lambda pid: cmd)
    monkeypatch.setattr(dash_mod, "_proc_cwd", lambda pid: ws.resolve())
    assert dash_mod._proc_is_workspace_dashboard(4242, ws) is True


def test_proc_is_workspace_dashboard_rejects_non_dashboard(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(dash_mod, "_proc_cmdline",
                        lambda pid: "python -m http.server 8765")
    monkeypatch.setattr(dash_mod, "_proc_cwd", lambda pid: ws.resolve())
    assert dash_mod._proc_is_workspace_dashboard(4242, ws) is False


def test_proc_is_workspace_dashboard_rejects_other_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    cmd = f"python -m vivarium_workbench.cli serve --workspace {other} --port 8765"
    monkeypatch.setattr(dash_mod, "_proc_cmdline", lambda pid: cmd)
    monkeypatch.setattr(dash_mod, "_proc_cwd", lambda pid: other.resolve())
    assert dash_mod._proc_is_workspace_dashboard(4242, ws) is False


# ---------------------------------------------------------------------------
# _infer_investigation_from_branch — current-branch → investigation default
# ---------------------------------------------------------------------------


def _make_ws_with_investigations(tmp_path: Path, slugs: list[str]) -> Path:
    ws = tmp_path / "ws"
    inv_root = ws / "investigations"
    inv_root.mkdir(parents=True)
    for slug in slugs:
        d = inv_root / slug
        d.mkdir()
        (d / "investigation.yaml").write_text(f"name: {slug}\n")
    return ws


def test_infer_returns_exact_branch_match(tmp_path, monkeypatch):
    ws = _make_ws_with_investigations(tmp_path, ["colonies", "dnaa-replication"])
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "colonies")
    assert dash_mod._infer_investigation_from_branch(ws) == "colonies"


def test_infer_handles_canonical_investigation_prefix(tmp_path, monkeypatch):
    ws = _make_ws_with_investigations(tmp_path, ["colonies", "dnaa-replication"])
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "investigation/dnaa-replication")
    assert dash_mod._infer_investigation_from_branch(ws) == "dnaa-replication"


def test_infer_via_token_overlap(tmp_path, monkeypatch):
    """`feat/dnaa-biology` shares the token 'dnaa' with `dnaa-replication`
    (1/2 of slug tokens) but nothing with `colonies` (0/1). dnaa-replication
    wins."""
    ws = _make_ws_with_investigations(tmp_path, ["colonies", "dnaa-replication"])
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "feat/dnaa-biology")
    assert dash_mod._infer_investigation_from_branch(ws) == "dnaa-replication"


def test_infer_falls_back_to_single_investigation(tmp_path, monkeypatch):
    """When the branch matches no investigation and exactly one exists,
    that one is unambiguous."""
    ws = _make_ws_with_investigations(tmp_path, ["colonies"])
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "feat/unrelated")
    assert dash_mod._infer_investigation_from_branch(ws) == "colonies"


def test_infer_returns_none_when_ambiguous(tmp_path, monkeypatch):
    """No token overlap + multiple investigations → no safe default."""
    ws = _make_ws_with_investigations(tmp_path, ["aaa", "bbb"])
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "feat/unrelated")
    assert dash_mod._infer_investigation_from_branch(ws) is None


def test_infer_returns_none_when_no_investigations(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(dash_mod, "_current_branch", lambda w: "any")
    assert dash_mod._infer_investigation_from_branch(ws) is None
