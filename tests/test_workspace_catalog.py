"""Tests for pbg_superpowers.workspace_catalog."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest


@pytest.fixture
def pbg_home(tmp_path, monkeypatch):
    home = tmp_path / "pbg-home"
    monkeypatch.setenv("PBG_HOME", str(home))
    return home


@pytest.fixture
def workspace_dir(tmp_path):
    """Create a minimal workspace directory with workspace.yaml."""
    ws = tmp_path / "my-workspace"
    ws.mkdir()
    (ws / "workspace.yaml").write_text(
        "name: my-workspace\npackage: pbg_myworkspace\n"
    )
    return ws


def test_list_returns_empty_when_no_catalog(pbg_home):
    from pbg_superpowers.workspace_catalog import list_workspaces
    assert list_workspaces() == []


def test_add_inserts_entry(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import add, list_workspaces
    entry = add(workspace_dir)
    assert entry["name"] == "my-workspace"
    assert entry["package"] == "pbg_myworkspace"
    assert entry["path"] == str(workspace_dir.resolve())
    assert "added_at" in entry
    assert list_workspaces() == [entry]


def test_add_is_idempotent_by_path(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import add, list_workspaces
    e1 = add(workspace_dir)
    e2 = add(workspace_dir)
    assert e1 == e2
    assert len(list_workspaces()) == 1


def test_add_rejects_non_workspace(pbg_home, tmp_path):
    from pbg_superpowers.workspace_catalog import add
    bogus = tmp_path / "not-a-workspace"
    bogus.mkdir()
    with pytest.raises(ValueError, match="no workspace.yaml"):
        add(bogus)


def test_add_explicit_name_overrides_yaml(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import add
    entry = add(workspace_dir, name="explicit", package="pbg_explicit")
    assert entry["name"] == "explicit"
    assert entry["package"] == "pbg_explicit"


def test_forget_removes_entry(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import add, forget, list_workspaces
    add(workspace_dir)
    assert forget(workspace_dir) is True
    assert list_workspaces() == []


def test_forget_missing_returns_false(pbg_home, tmp_path):
    from pbg_superpowers.workspace_catalog import forget
    # path that was never added (and need not exist on disk)
    assert forget(tmp_path / "never-added") is False


def test_register_server_writes_file(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import register_server
    fpath = register_server(
        name="my-workspace", path=workspace_dir,
        pid=os.getpid(), port=8731,
        url="http://127.0.0.1:8731",
    )
    assert fpath.exists()
    data = json.loads(fpath.read_text())
    assert data["name"] == "my-workspace"
    assert data["path"] == str(workspace_dir.resolve())
    assert data["pid"] == os.getpid()
    assert data["port"] == 8731
    assert data["url"] == "http://127.0.0.1:8731"
    assert "started_at" in data


def test_name_collision_uses_hash_suffix(pbg_home, tmp_path):
    from pbg_superpowers.workspace_catalog import register_server
    # Two workspaces with the same name but different paths.
    w1 = tmp_path / "w1" / "shared-name"; w1.mkdir(parents=True)
    w2 = tmp_path / "w2" / "shared-name"; w2.mkdir(parents=True)
    f1 = register_server("shared-name", w1, 100, 8001, "http://127.0.0.1:8001")
    f2 = register_server("shared-name", w2, 200, 8002, "http://127.0.0.1:8002")
    assert f1.name == "shared-name.json"
    assert f2.name.startswith("shared-name.") and f2.name.endswith(".json")
    assert f2.name != f1.name


def test_find_running_returns_entry_if_pid_alive(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import register_server, find_running
    register_server(
        name="my-workspace", path=workspace_dir,
        pid=os.getpid(),  # this process is alive
        port=8731, url="http://127.0.0.1:8731",
    )
    entry = find_running(workspace_dir)
    assert entry is not None
    assert entry["pid"] == os.getpid()


def test_find_running_returns_none_if_pid_dead(pbg_home, workspace_dir):
    import subprocess as _sp
    from pbg_superpowers.workspace_catalog import register_server, find_running
    # Spawn a real subprocess, wait for it to exit, then use its confirmed-dead PID.
    proc = _sp.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    dead_pid = proc.pid
    register_server(
        name="my-workspace", path=workspace_dir,
        pid=dead_pid, port=8731, url="http://127.0.0.1:8731",
    )
    assert find_running(workspace_dir) is None


def test_unregister_server_removes_file(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import register_server, unregister_server, find_entry
    register_server("my-workspace", workspace_dir, os.getpid(), 8731, "http://127.0.0.1:8731")
    assert find_entry(workspace_dir) is not None
    assert unregister_server(workspace_dir) is True
    assert find_entry(workspace_dir) is None


def test_concurrent_add_same_path_dedups(pbg_home, tmp_path):
    """Many threads adding the SAME path → exactly one catalog entry."""
    from pbg_superpowers.workspace_catalog import add, list_workspaces

    ws = tmp_path / "concurrent"
    ws.mkdir()
    (ws / "workspace.yaml").write_text("name: concurrent\npackage: pbg_concurrent\n")

    errors = []
    def worker():
        try:
            add(ws)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert errors == []
    assert len(list_workspaces()) == 1


def test_concurrent_add_different_paths_all_survive(pbg_home, tmp_path):
    """N threads each adding a distinct workspace path → all N entries land.

    Without flock, the read-modify-write race causes lost updates: a thread
    reads the catalog, another thread reads the same state, both append their
    entry to their local copy, both write back. The second write erases the
    first thread's entry. With flock, all N entries survive.
    """
    from pbg_superpowers.workspace_catalog import add, list_workspaces

    N = 12
    workspaces = []
    for i in range(N):
        ws = tmp_path / f"ws-{i}"
        ws.mkdir()
        (ws / "workspace.yaml").write_text(f"name: ws-{i}\npackage: pbg_ws_{i}\n")
        workspaces.append(ws)

    errors = []
    def worker(ws):
        try:
            add(ws)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(w,)) for w in workspaces]
    for t in threads: t.start()
    for t in threads: t.join()

    assert errors == []
    listed = list_workspaces()
    assert len(listed) == N
    paths = sorted(w["path"] for w in listed)
    expected = sorted(str(ws.resolve()) for ws in workspaces)
    assert paths == expected


def test_concurrent_register_server_same_name_different_paths(pbg_home, tmp_path):
    """Two workspaces with same name registering concurrently must end up
    with distinct files (one base, one hash-suffixed) — neither lost."""
    from pbg_superpowers.workspace_catalog import register_server

    w1 = tmp_path / "a" / "shared-name"; w1.mkdir(parents=True)
    w2 = tmp_path / "b" / "shared-name"; w2.mkdir(parents=True)

    results = {}
    errors = []
    def worker(label, ws, pid, port):
        try:
            fpath = register_server("shared-name", ws, pid, port, f"http://127.0.0.1:{port}")
            results[label] = fpath
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker, args=("w1", w1, 100, 8001))
    t2 = threading.Thread(target=worker, args=("w2", w2, 200, 8002))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert errors == []
    assert len(results) == 2
    assert results["w1"] != results["w2"]
    # Both files should still exist (neither overwritten).
    assert results["w1"].exists()
    assert results["w2"].exists()
    # And their contents should match what each thread wrote.
    d1 = json.loads(results["w1"].read_text())
    d2 = json.loads(results["w2"].read_text())
    assert d1["path"] != d2["path"]
    assert {d1["pid"], d2["pid"]} == {100, 200}


def test_cli_add_and_list(pbg_home, workspace_dir):
    env = {**os.environ, "PBG_HOME": str(pbg_home)}
    out = subprocess.check_output(
        [sys.executable, "-m", "pbg_superpowers.workspace_catalog",
         "add", "--path", str(workspace_dir)],
        env=env,
    )
    entry = json.loads(out)
    assert entry["name"] == "my-workspace"

    listed = subprocess.check_output(
        [sys.executable, "-m", "pbg_superpowers.workspace_catalog", "list"],
        env=env,
    )
    parsed = json.loads(listed)
    assert len(parsed) == 1
    assert parsed[0]["path"] == str(workspace_dir.resolve())
