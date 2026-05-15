# Workspace Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder workspace switcher in the Vivarium dashboard with a working dropdown that lists all known workspaces, shows which are running, navigates to running ones, and starts stopped ones in the background.

**Architecture:** Two new files under `~/.pbg/` form the registry — `workspaces.json` (catalog) and `servers/<name>.json` (per running dashboard). A new `pbg_superpowers.workspace_catalog` module is the single writer. The dashboard server gains five new endpoints (one GET, four POST) that read this registry and act on it; `cmd_serve` registers/unregisters on boot/exit. The dropdown in `index.html.j2` is replaced with an interactive panel.

**Tech Stack:** Python 3.10+, stdlib `subprocess`/`fcntl`/`signal`/`http.server`, pytest, vanilla JS, Jinja2 templates.

**Spec:** `docs/superpowers/specs/2026-05-15-workspace-switcher-design.md`

**Repos touched:**
- `pbg-superpowers` (this repo): Tasks 1, 2, 3
- `vivarium-dashboard` (`/Users/eranagmon/code/vivarium-dashboard/`): Tasks 4–10
- Task 11 is a manual end-to-end across two real workspaces.

**Cross-repo coordination:** Tasks 4–10 (in vivarium-dashboard) import the new `pbg_superpowers.workspace_catalog` module added in Task 1. The dashboard already declares `pbg-superpowers` as a dependency (`vivarium-dashboard/pyproject.toml`), so installing the dashboard with `pip install -e .` is enough.

---

## Task 1: `workspace_catalog` helper module

**Repo:** `pbg-superpowers`

**Files:**
- Create: `pbg_superpowers/workspace_catalog.py`
- Test: `tests/test_workspace_catalog.py`

This module is the single writer for `~/.pbg/workspaces.json` and `~/.pbg/servers/*.json`. It exposes both a Python API and a `python -m` CLI. It honors `PBG_HOME` so tests can isolate state under `tmp_path`.

- [ ] **Step 1: Create the test file with the empty-state behavior test**

```python
# tests/test_workspace_catalog.py
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
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd /Users/eranagmon/code/pbg-superpowers
pytest tests/test_workspace_catalog.py -x -v
```

Expected: `ModuleNotFoundError: No module named 'pbg_superpowers.workspace_catalog'`.

- [ ] **Step 3: Create the module skeleton with `list_workspaces` only**

```python
# pbg_superpowers/workspace_catalog.py
"""Global registry of pbg workspaces and their running dashboards.

Two files under ``$PBG_HOME`` (default ``~/.pbg``):

* ``workspaces.json``        — catalog of all known workspaces.
* ``servers/<name>.json``    — one per running dashboard (added by the
                                dashboard's ``cmd_serve`` on boot, removed
                                on exit).

Single writer surface for both. Usable as a Python API (imported by the
dashboard backend) and as a CLI (``python -m pbg_superpowers.workspace_catalog
<subcommand>``) — the CLI is what skill shims and shell scripts invoke.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def _home() -> Path:
    return Path(os.environ.get("PBG_HOME", Path.home() / ".pbg")).expanduser()


def _catalog_path() -> Path:
    return _home() / "workspaces.json"


def _servers_dir() -> Path:
    return _home() / "servers"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _load_catalog() -> dict:
    p = _catalog_path()
    if not p.is_file():
        return {"version": SCHEMA_VERSION, "workspaces": []}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("workspaces"), list):
            return {"version": SCHEMA_VERSION, "workspaces": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": SCHEMA_VERSION, "workspaces": []}


def list_workspaces() -> list[dict]:
    return _load_catalog().get("workspaces", [])
```

- [ ] **Step 4: Run the test, confirm it passes**

```bash
pytest tests/test_workspace_catalog.py::test_list_returns_empty_when_no_catalog -x -v
```

Expected: PASS.

- [ ] **Step 5: Add tests for `add` (basic insert, dedup, missing workspace.yaml)**

Append to `tests/test_workspace_catalog.py`:

```python
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
```

- [ ] **Step 6: Run the failing tests**

```bash
pytest tests/test_workspace_catalog.py -x -v
```

Expected: 3 new tests fail with `AttributeError` or `ImportError` for `add`.

- [ ] **Step 7: Implement `add` plus the file-locking helpers**

Append to `pbg_superpowers/workspace_catalog.py`:

```python
def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload)
    tmp.replace(path)


def _with_catalog_lock(fn):
    """Hold an exclusive flock on the catalog lock file while running fn."""
    _home().mkdir(parents=True, exist_ok=True)
    lock = _home() / "workspaces.json.lock"
    with lock.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def add(path, name: str | None = None, package: str | None = None) -> dict:
    """Append-or-noop. Returns the catalog entry. Raises ValueError if path is
    not a workspace (no workspace.yaml)."""
    target = _safe_resolve(path)
    if not (target / "workspace.yaml").is_file():
        raise ValueError(f"not a workspace (no workspace.yaml): {target}")

    if name is None or package is None:
        import yaml  # local import keeps the module light at import time
        data = yaml.safe_load((target / "workspace.yaml").read_text()) or {}
        name = name or data.get("name") or target.name
        package = package or data.get("package")

    def _do_add() -> dict:
        catalog = _load_catalog()
        target_str = str(target)
        for entry in catalog["workspaces"]:
            if entry.get("path") == target_str:
                return entry
        entry = {
            "name": name,
            "path": target_str,
            "package": package,
            "added_at": _now_iso(),
        }
        catalog["workspaces"].append(entry)
        catalog["version"] = SCHEMA_VERSION
        _atomic_write(_catalog_path(), json.dumps(catalog, indent=2))
        return entry

    return _with_catalog_lock(_do_add)
```

- [ ] **Step 8: Run all catalog tests, confirm pass**

```bash
pytest tests/test_workspace_catalog.py -x -v
```

Expected: 4 PASS.

- [ ] **Step 9: Add tests for `forget` (basic remove, missing entry is noop)**

Append:

```python
def test_forget_removes_entry(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import add, forget, list_workspaces
    add(workspace_dir)
    assert forget(workspace_dir) is True
    assert list_workspaces() == []


def test_forget_missing_returns_false(pbg_home, tmp_path):
    from pbg_superpowers.workspace_catalog import forget
    # path that was never added (and need not exist on disk)
    assert forget(tmp_path / "never-added") is False
```

- [ ] **Step 10: Run, confirm fail**

```bash
pytest tests/test_workspace_catalog.py -k forget -v
```

Expected: 2 fail with `AttributeError: module … has no attribute 'forget'`.

- [ ] **Step 11: Implement `forget`**

Append to `workspace_catalog.py`:

```python
def forget(path) -> bool:
    """Remove the catalog entry for ``path``. Returns True if anything was
    removed, False if no matching entry existed."""
    target_str = str(_safe_resolve(path))

    def _do_forget() -> bool:
        catalog = _load_catalog()
        before = len(catalog["workspaces"])
        catalog["workspaces"] = [
            e for e in catalog["workspaces"] if e.get("path") != target_str
        ]
        if len(catalog["workspaces"]) == before:
            return False
        _atomic_write(_catalog_path(), json.dumps(catalog, indent=2))
        return True

    return _with_catalog_lock(_do_forget)
```

- [ ] **Step 12: Run, confirm pass**

```bash
pytest tests/test_workspace_catalog.py -k forget -v
```

Expected: 2 PASS.

- [ ] **Step 13: Add tests for `register_server` / `unregister_server` / `find_running`**

Append:

```python
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
    from pbg_superpowers.workspace_catalog import register_server, find_running
    # Use a PID that is virtually guaranteed to be dead.
    register_server(
        name="my-workspace", path=workspace_dir,
        pid=2_000_000, port=8731, url="http://127.0.0.1:8731",
    )
    assert find_running(workspace_dir) is None


def test_unregister_server_removes_file(pbg_home, workspace_dir):
    from pbg_superpowers.workspace_catalog import register_server, unregister_server, find_entry
    register_server("my-workspace", workspace_dir, os.getpid(), 8731, "http://127.0.0.1:8731")
    assert find_entry(workspace_dir) is not None
    assert unregister_server(workspace_dir) is True
    assert find_entry(workspace_dir) is None
```

- [ ] **Step 14: Run, confirm fail**

```bash
pytest tests/test_workspace_catalog.py -k "register_server or find_running or unregister_server or name_collision" -v
```

Expected: all 5 fail with AttributeError.

- [ ] **Step 15: Implement the running-server functions**

Append to `workspace_catalog.py`:

```python
def _server_filename(name: str, path: Path) -> str:
    """Pick a filename for the running-server entry for (name, path).

    Without a collision, this is ``<name>.json``. If a file already exists with
    that name and a DIFFERENT path, the new file gets a 6-char sha1(path)
    suffix to disambiguate."""
    base = f"{name}.json"
    existing = _servers_dir() / base
    if existing.is_file():
        try:
            data = json.loads(existing.read_text())
            if data.get("path") == str(path):
                return base
        except (json.JSONDecodeError, OSError):
            pass
        suffix = hashlib.sha1(str(path).encode()).hexdigest()[:6]
        return f"{name}.{suffix}.json"
    return base


def register_server(name: str, path, pid: int, port: int, url: str) -> Path:
    target = _safe_resolve(path)
    _servers_dir().mkdir(parents=True, exist_ok=True)
    fname = _server_filename(name, target)
    fpath = _servers_dir() / fname
    entry = {
        "name": name,
        "path": str(target),
        "pid": pid,
        "port": port,
        "url": url,
        "started_at": _now_iso(),
    }
    _atomic_write(fpath, json.dumps(entry, indent=2))
    return fpath


def unregister_server(path) -> bool:
    target_str = str(_safe_resolve(path))
    if not _servers_dir().is_dir():
        return False
    found = False
    for f in _servers_dir().glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("path") == target_str:
            try:
                f.unlink()
                found = True
            except FileNotFoundError:
                pass
    return found


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID owned by another user but exists → treat as alive.
        return True
    except OSError:
        return False
    return True


def find_entry(path) -> dict | None:
    """Return the running-registry entry for path (alive or stale), or None."""
    target_str = str(_safe_resolve(path))
    if not _servers_dir().is_dir():
        return None
    for f in _servers_dir().glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("path") == target_str:
            return data
    return None


def find_running(path) -> dict | None:
    """Return the running-registry entry for path if its PID is alive."""
    entry = find_entry(path)
    if entry is None:
        return None
    if _pid_alive(int(entry.get("pid", 0))):
        return entry
    return None
```

- [ ] **Step 16: Run, confirm pass**

```bash
pytest tests/test_workspace_catalog.py -v
```

Expected: all PASS (10–11 tests so far).

- [ ] **Step 17: Add concurrent-add test (flock smoke test)**

Append:

```python
def test_concurrent_add_dedups(pbg_home, tmp_path):
    """Many threads adding the same path → exactly one catalog entry."""
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
```

- [ ] **Step 18: Run, confirm pass**

```bash
pytest tests/test_workspace_catalog.py::test_concurrent_add_dedups -v
```

Expected: PASS.

- [ ] **Step 19: Add CLI subcommand test (covers `python -m`)**

Append:

```python
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
```

- [ ] **Step 20: Run, confirm fail (no `__main__`)**

```bash
pytest tests/test_workspace_catalog.py::test_cli_add_and_list -v
```

Expected: subprocess returns non-zero (no `argparse` wiring yet).

- [ ] **Step 21: Implement the CLI**

Append to `workspace_catalog.py`:

```python
def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pbg_superpowers.workspace_catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--path", required=True)
    p_add.add_argument("--name")
    p_add.add_argument("--package")

    p_forget = sub.add_parser("forget")
    p_forget.add_argument("--path", required=True)

    sub.add_parser("list")

    p_reg = sub.add_parser("register-server")
    p_reg.add_argument("--name", required=True)
    p_reg.add_argument("--path", required=True)
    p_reg.add_argument("--pid", type=int, required=True)
    p_reg.add_argument("--port", type=int, required=True)
    p_reg.add_argument("--url", required=True)

    p_unr = sub.add_parser("unregister-server")
    p_unr.add_argument("--path", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "add":
        entry = add(args.path, args.name, args.package)
        print(json.dumps(entry))
        return 0
    if args.cmd == "forget":
        ok = forget(args.path)
        return 0 if ok else 1
    if args.cmd == "list":
        print(json.dumps(list_workspaces(), indent=2))
        return 0
    if args.cmd == "register-server":
        register_server(args.name, args.path, args.pid, args.port, args.url)
        return 0
    if args.cmd == "unregister-server":
        unregister_server(args.path)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_main())
```

- [ ] **Step 22: Run, confirm pass; then run the whole catalog test file**

```bash
pytest tests/test_workspace_catalog.py -v
```

Expected: all PASS.

- [ ] **Step 23: Commit**

```bash
git add pbg_superpowers/workspace_catalog.py tests/test_workspace_catalog.py
git commit -m "feat(workspace-catalog): new module for ~/.pbg registry"
```

---

## Task 2: `/pbg-workspace` registration shim

**Repo:** `pbg-superpowers`

**Files:**
- Modify: `skills/pbg-workspace/SKILL.md`

The skill is markdown, not code. The change is a single-line addition to step 4 of the lifecycle telling the agent to invoke the catalog CLI after the bootstrap commit. No unit test (the skill content is read by the agent at runtime).

- [ ] **Step 1: Read the current step-4 text**

```bash
cd /Users/eranagmon/code/pbg-superpowers
sed -n '20,32p' skills/pbg-workspace/SKILL.md
```

Note the current block:

```
4. **Edits + commits**:
   - `python -m pbg_superpowers.scaffold workspace --name $NAME --target $TARGET`
     (clones / copies pbg-template; runs `template-init.sh` non-interactively).
   - `cd $TARGET && git init -q`
   - `uv venv .venv && source .venv/bin/activate`
   - `uv pip install -e .[dev]` (workspace's own pyproject)
   - `git add -A && git commit -m 'feat(stage-0): workspace bootstrap'`
```

- [ ] **Step 2: Add the catalog-registration step after the commit**

Edit `skills/pbg-workspace/SKILL.md`. Replace the line:

```
   - `git add -A && git commit -m 'feat(stage-0): workspace bootstrap'`
```

with:

```
   - `git add -A && git commit -m 'feat(stage-0): workspace bootstrap'`
   - `python -m pbg_superpowers.workspace_catalog add --path "$TARGET" --name "$NAME" --package "$PKG"`
     (registers the workspace in `~/.pbg/workspaces.json` so it appears in the
     dashboard's workspace switcher; idempotent — safe to re-run).
```

- [ ] **Step 3: Verify the change**

```bash
sed -n '20,32p' skills/pbg-workspace/SKILL.md
```

Expected: the new line is present immediately after the commit line.

- [ ] **Step 4: Commit**

```bash
git add skills/pbg-workspace/SKILL.md
git commit -m "feat(pbg-workspace): register new workspace in global catalog"
```

---

## Task 3: `/pbg-server` SKILL.md text update

**Repo:** `pbg-superpowers`

**Files:**
- Modify: `skills/pbg-server/SKILL.md`

The current SKILL.md claims `start` writes `.pbg/server/server.pid`. With the dashboard CLI now writing the PID file itself (Task 4), and the dashboard CLI being the canonical way the user starts a workspace dashboard, the skill text needs to be updated to say so. No code change in `start-server.sh` (it stays as the report-mirror launcher per CLAUDE.md).

- [ ] **Step 1: Read the current `start` description**

```bash
sed -n '22,26p' skills/pbg-server/SKILL.md
```

- [ ] **Step 2: Update lines 23–25 to mention the dashboard CLI**

In `skills/pbg-server/SKILL.md`, replace:

```
- **`/pbg-server start`** — runs `<plugin>/server/start-server.sh <workspace>` (passes the workspace root). Writes `.pbg/server/server-info` (port, URL, content/state dirs) and `.pbg/server/server.pid`. Prints the URL.
- **`/pbg-server stop`** — reads `.pbg/server/server.pid`, sends SIGTERM, removes both `server-info` and `server.pid` once the process exits.
- **`/pbg-server status`** — prints `.pbg/server/server-info` if present (and the server is alive); otherwise reports "not running".
```

with:

```
- **`/pbg-server start`** — runs `vivarium-dashboard serve --workspace <workspace>` (the dashboard CLI from the `vivarium-dashboard` package). The dashboard writes `.pbg/server/server-info` (port, URL, content/state dirs) and `.pbg/server/server.pid` on boot, plus a global running-registry entry at `~/.pbg/servers/<name>.json`. Prints the URL.
- **`/pbg-server stop`** — reads `.pbg/server/server.pid`, sends SIGTERM. The dashboard's exit handler removes `server-info`, `server.pid`, and the global registry entry; the skill verifies the PID is gone before returning.
- **`/pbg-server status`** — prints `.pbg/server/server-info` if present (and the server is alive); otherwise reports "not running". Also reports the global registry entry under `~/.pbg/servers/` if present.
```

- [ ] **Step 3: Commit**

```bash
git add skills/pbg-server/SKILL.md
git commit -m "docs(pbg-server): describe global running-registry under ~/.pbg/servers/"
```

---

## Task 4: `cmd_serve` register/unregister + PID file

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/cli.py` (function `cmd_serve`)
- Test: `vivarium-dashboard/tests/test_workspace_switcher_cli.py` (new)

`cmd_serve` already writes `<workspace>/.pbg/server/server-info`. We extend it to:
1. Write `<workspace>/.pbg/server/server.pid` with `os.getpid()`.
2. Call `register_server(...)` on boot.
3. Install signal/atexit hooks that call `unregister_server(path)` and remove `server.pid` on exit.

- [ ] **Step 1: Switch to the dashboard repo and install the latest catalog module**

```bash
cd /Users/eranagmon/code/vivarium-dashboard
# Make sure the locally-edited pbg_superpowers is what's installed.
pip install -e /Users/eranagmon/code/pbg-superpowers
pip install -e .
```

- [ ] **Step 2: Create the failing test for `cmd_serve` registration**

```python
# vivarium-dashboard/tests/test_workspace_switcher_cli.py
"""cmd_serve must register itself in the global running registry."""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture
def pbg_home(tmp_path, monkeypatch):
    home = tmp_path / "pbg-home"
    monkeypatch.setenv("PBG_HOME", str(home))
    return home


@pytest.fixture
def workspace_dir(tmp_path):
    ws = tmp_path / "switcher-ws"
    ws.mkdir()
    (ws / "workspace.yaml").write_text(
        "name: switcher-ws\npackage: pbg_switcher_ws\n"
    )
    # cmd_serve also wants reports/ to exist (it tries to render); we don't
    # care about render output in this test, so just make the dir.
    (ws / "reports").mkdir()
    return ws


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def test_cmd_serve_registers_on_boot(pbg_home, workspace_dir):
    """Spawning `vivarium-dashboard serve` should write ~/.pbg/servers/<name>.json
    within a few seconds, and remove it after we SIGTERM the process."""
    port = _free_port()
    env = {**os.environ, "PBG_HOME": str(pbg_home)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "vivarium_dashboard.cli",
         "serve", "--workspace", str(workspace_dir), "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        # Wait up to 8s for the global registry entry to appear.
        servers_dir = pbg_home / "servers"
        deadline = time.monotonic() + 8.0
        entry_path = None
        while time.monotonic() < deadline:
            if servers_dir.is_dir():
                cands = list(servers_dir.glob("switcher-ws*.json"))
                if cands:
                    entry_path = cands[0]
                    break
            time.sleep(0.1)
        assert entry_path is not None, "registration file never appeared"
        entry = json.loads(entry_path.read_text())
        assert entry["name"] == "switcher-ws"
        assert entry["path"] == str(workspace_dir.resolve())
        assert entry["pid"] == proc.pid
        assert entry["port"] == port
        assert entry["url"] == f"http://127.0.0.1:{port}"

        # Workspace-local PID file should also exist.
        pid_file = workspace_dir / ".pbg" / "server" / "server.pid"
        assert pid_file.is_file()
        assert int(pid_file.read_text().strip()) == proc.pid
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    # After exit, the global entry and PID file should be gone.
    assert not entry_path.exists()
    pid_file = workspace_dir / ".pbg" / "server" / "server.pid"
    assert not pid_file.exists()
```

- [ ] **Step 3: Run, confirm fail**

```bash
cd /Users/eranagmon/code/vivarium-dashboard
pytest tests/test_workspace_switcher_cli.py -x -v
```

Expected: assertion fails because the registration file never appears (registration not yet implemented). The process might also hang; if it does, the `proc.terminate()` in the test will kill it.

- [ ] **Step 4: Modify `cmd_serve` in `vivarium-dashboard/vivarium_dashboard/cli.py`**

Open `vivarium-dashboard/vivarium_dashboard/cli.py`. Locate the block at the end of `cmd_serve`:

```python
    (server_dir / "server-info").write_text(json.dumps(info))
    print(f"\nWorkspace dashboard: http://127.0.0.1:{port}")
    print("   (Ctrl-C to stop)\n")

    # Boot the HTTP server.
    from vivarium_dashboard.server import serve as serve_dashboard
    return serve_dashboard(workspace=workspace, port=port)
```

Replace with:

```python
    (server_dir / "server-info").write_text(json.dumps(info))

    # Write PID file (consumed by /pbg-server stop and the switcher's
    # cleanup-stale endpoint).
    pid_file = server_dir / "server.pid"
    pid_file.write_text(str(os.getpid()))

    # Register the running dashboard in ~/.pbg/servers/<name>.json so the
    # workspace switcher in other dashboards can see it.
    from pbg_superpowers import workspace_catalog
    ws_name = _workspace_name(workspace)
    workspace_catalog.register_server(
        name=ws_name, path=workspace,
        pid=os.getpid(), port=port,
        url=f"http://127.0.0.1:{port}",
    )

    def _unregister():
        try:
            workspace_catalog.unregister_server(workspace)
        except Exception:
            pass
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass

    import atexit
    import signal as _signal
    atexit.register(_unregister)

    def _sig_handler(signum, frame):
        _unregister()
        # Re-raise default behavior for clean exit (BaseHTTPRequestHandler
        # already handles SIGINT via KeyboardInterrupt; SIGTERM needs explicit
        # exit).
        if signum == _signal.SIGTERM:
            sys.exit(0)

    _signal.signal(_signal.SIGTERM, _sig_handler)
    # SIGINT is handled implicitly through KeyboardInterrupt in serve_dashboard;
    # atexit covers the cleanup either way.

    print(f"\nWorkspace dashboard: http://127.0.0.1:{port}")
    print("   (Ctrl-C to stop)\n")

    # Boot the HTTP server.
    from vivarium_dashboard.server import serve as serve_dashboard
    return serve_dashboard(workspace=workspace, port=port)


def _workspace_name(workspace: Path) -> str:
    """Read `name` from <workspace>/workspace.yaml, falling back to dir name."""
    try:
        data = yaml.safe_load((workspace / "workspace.yaml").read_text()) or {}
        return data.get("name") or workspace.name
    except (OSError, yaml.YAMLError):
        return workspace.name
```

- [ ] **Step 5: Run the test, confirm pass**

```bash
pytest tests/test_workspace_switcher_cli.py -x -v
```

Expected: PASS. (May take ~3–5 seconds because the test spawns a real subprocess.)

- [ ] **Step 6: Run the full dashboard test suite for regressions**

```bash
pytest -x --timeout=30
```

Expected: existing tests still PASS. If `cmd_serve` is exercised by other tests, make sure those still pass.

- [ ] **Step 7: Commit**

```bash
git add vivarium_dashboard/cli.py tests/test_workspace_switcher_cli.py
git commit -m "feat(cli): register dashboard in ~/.pbg/servers on serve"
```

---

## Task 5: `GET /api/workspaces` endpoint

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (add handler + route)
- Test: `vivarium-dashboard/tests/test_workspaces_api.py` (new)

Adds a GET endpoint that loads the catalog, joins it with `~/.pbg/servers/`, and returns the dropdown payload.

- [ ] **Step 1: Find where GET routes are added**

```bash
grep -n "self.path.startswith(\"/api/" /Users/eranagmon/code/vivarium-dashboard/vivarium_dashboard/server.py | head -25
```

The relevant `do_GET` chain starts around line 1858. We'll register a new prefix `/api/workspaces` near the other `/api/*` GET routes. The convention is: at the top of `do_GET`, after the existing aliases, add:

```python
if self.path.startswith("/api/workspaces"):
    return self._get_workspaces()
```

- [ ] **Step 2: Create the failing test**

```python
# vivarium-dashboard/tests/test_workspaces_api.py
"""Workspace switcher API: GET /api/workspaces."""
from __future__ import annotations
import json
import os
import socket
import threading
import time
from contextlib import contextmanager
from http.server import HTTPServer
from pathlib import Path

import pytest

from pbg_superpowers import workspace_catalog
from vivarium_dashboard.server import Handler, _set_runtime_state


@pytest.fixture
def pbg_home(tmp_path, monkeypatch):
    home = tmp_path / "pbg-home"
    monkeypatch.setenv("PBG_HOME", str(home))
    return home


@pytest.fixture
def workspace_dir(tmp_path):
    ws = tmp_path / "current-ws"
    ws.mkdir()
    (ws / "workspace.yaml").write_text(
        "name: current-ws\npackage: pbg_current_ws\n"
    )
    return ws


def _make_workspace(parent: Path, name: str) -> Path:
    ws = parent / name
    ws.mkdir()
    (ws / "workspace.yaml").write_text(f"name: {name}\npackage: pbg_{name.replace('-', '_')}\n")
    return ws


@contextmanager
def _ephemeral_dashboard(workspace: Path):
    """Boot the dashboard handler bound to `workspace` on a free port. Yields the URL."""
    from vivarium_dashboard.lib._root import set_workspace_root
    set_workspace_root(workspace)
    _set_runtime_state(workspace=workspace)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    httpd = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_api_workspaces_returns_empty_plus_current(pbg_home, workspace_dir):
    """Even with an empty catalog, the dashboard's own workspace is reported as 'current'."""
    import urllib.request
    with _ephemeral_dashboard(workspace_dir) as url:
        resp = urllib.request.urlopen(f"{url}/api/workspaces").read()
    data = json.loads(resp)
    assert data["current"]["name"] == "current-ws"
    assert data["current"]["path"] == str(workspace_dir.resolve())
    # Empty catalog → only the current workspace appears (auto-included).
    paths = [w["path"] for w in data["workspaces"]]
    assert str(workspace_dir.resolve()) in paths


def test_api_workspaces_marks_running_stopped_stale_missing(pbg_home, tmp_path, workspace_dir):
    import urllib.request

    running_ws = _make_workspace(tmp_path, "running-ws")
    stopped_ws = _make_workspace(tmp_path, "stopped-ws")
    stale_ws = _make_workspace(tmp_path, "stale-ws")
    missing_ws_path = tmp_path / "gone"  # never created on disk

    workspace_catalog.add(workspace_dir)
    workspace_catalog.add(running_ws)
    workspace_catalog.add(stopped_ws)
    workspace_catalog.add(stale_ws)
    # Manually add a missing entry (forge the catalog file).
    cat = pbg_home / "workspaces.json"
    cur = json.loads(cat.read_text())
    cur["workspaces"].append({
        "name": "missing-ws", "path": str(missing_ws_path),
        "package": None, "added_at": "2026-05-15T00:00:00Z",
    })
    cat.write_text(json.dumps(cur))

    # Running: register with the current process PID.
    workspace_catalog.register_server(
        "running-ws", running_ws, os.getpid(), 8001, "http://127.0.0.1:8001"
    )
    # Stale: register with a dead PID.
    workspace_catalog.register_server(
        "stale-ws", stale_ws, 2_000_000, 8002, "http://127.0.0.1:8002"
    )

    with _ephemeral_dashboard(workspace_dir) as url:
        resp = urllib.request.urlopen(f"{url}/api/workspaces").read()
    data = json.loads(resp)
    by_name = {w["name"]: w for w in data["workspaces"]}

    assert by_name["current-ws"]["status"] == "current"
    assert by_name["running-ws"]["status"] == "running"
    assert by_name["running-ws"]["url"] == "http://127.0.0.1:8001"
    assert by_name["stopped-ws"]["status"] == "stopped"
    assert by_name["stale-ws"]["status"] == "stale"
    assert by_name["missing-ws"]["status"] == "missing"
```

- [ ] **Step 3: Run, confirm fail**

```bash
pytest tests/test_workspaces_api.py -x -v
```

Expected: 404 from `/api/workspaces` → JSON parse fails, or `ImportError` for `_set_runtime_state` if it doesn't already exist.

If `_set_runtime_state` doesn't exist, find the equivalent (the dashboard tracks the bound workspace somewhere; check `lib/_root.py` and how `server.serve()` initializes module-level state). Replace the helper in the test fixture accordingly. Typical patterns:

```bash
grep -n "set_workspace_root\|WORKSPACE_ROOT\|_WORKSPACE" vivarium_dashboard/server.py | head
```

If the server reads workspace at construction via a global module variable, set that variable directly in the fixture instead of calling `_set_runtime_state`.

- [ ] **Step 4: Add the GET route registration in `do_GET`**

In `vivarium_dashboard/server.py`, find the existing `if self.path.startswith("/api/state"):` line inside `do_GET` (around line 1875) and add immediately above it:

```python
        if self.path.startswith("/api/workspaces"):
            return self._get_workspaces()
```

- [ ] **Step 5: Implement `_get_workspaces` on the Handler class**

Add a new method on the `Handler` class (search for `class Handler` and add after the existing GET handlers):

```python
    def _get_workspaces(self):
        """GET /api/workspaces — dropdown payload for the workspace switcher.

        Reads ~/.pbg/workspaces.json (catalog) and joins each entry with
        ~/.pbg/servers/<name>.json to determine status. No HTTP probes.
        Falls back to current-workspace-only on missing/corrupt catalog.
        """
        from pbg_superpowers import workspace_catalog
        from vivarium_dashboard.lib._root import get_workspace_root

        current_root = get_workspace_root()
        current_resolved = str(current_root.resolve())

        # Build the current-workspace block first; it is always present.
        current_name = self._read_workspace_name(current_root)
        result = {
            "current": {"name": current_name, "path": current_resolved},
            "workspaces": [],
        }

        try:
            catalog = workspace_catalog.list_workspaces()
        except Exception:
            catalog = []

        # Ensure the current workspace is in the listing even if the catalog
        # is empty (first-run UX).
        if not any(e.get("path") == current_resolved for e in catalog):
            catalog = [{
                "name": current_name,
                "path": current_resolved,
                "package": None,
                "added_at": None,
            }] + list(catalog)

        for entry in catalog:
            path = entry.get("path", "")
            row = {"name": entry.get("name") or Path(path).name, "path": path}
            if not Path(path).is_dir():
                row["status"] = "missing"
            elif path == current_resolved:
                row["status"] = "current"
                running = workspace_catalog.find_running(path)
                if running:
                    row["url"] = running["url"]
                    row["pid"] = running["pid"]
            else:
                running = workspace_catalog.find_running(path)
                if running:
                    row["status"] = "running"
                    row["url"] = running["url"]
                    row["pid"] = running["pid"]
                else:
                    stale = workspace_catalog.find_entry(path)
                    if stale:
                        row["status"] = "stale"
                        row["pid"] = stale.get("pid")
                    else:
                        row["status"] = "stopped"
            result["workspaces"].append(row)

        # Sort: current → running → stopped → stale → missing; alphabetical within group.
        order = {"current": 0, "running": 1, "stopped": 2, "stale": 3, "missing": 4}
        result["workspaces"].sort(key=lambda r: (order.get(r["status"], 99), r["name"]))

        self._send_json(200, result)

    def _read_workspace_name(self, root: Path) -> str:
        """Read `name` from <root>/workspace.yaml; fall back to dir basename."""
        try:
            import yaml
            data = yaml.safe_load((root / "workspace.yaml").read_text()) or {}
            return data.get("name") or root.name
        except Exception:
            return root.name
```

(If `_send_json` is not the existing helper in `Handler`, locate the existing JSON-response helper — search for `self.send_response(200)` followed by `Content-Type` — and use that pattern instead. The dashboard uses one canonical helper; reuse it. If none exists, add one at the top of the `Handler` class:)

```python
    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
```

- [ ] **Step 6: Run, confirm pass**

```bash
pytest tests/test_workspaces_api.py -x -v
```

Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): GET /api/workspaces for switcher dropdown"
```

---

## Task 6: `POST /api/workspaces/add`

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (add to `_POST_ROUTE_MAP` + handler)
- Test: `vivarium-dashboard/tests/test_workspaces_api.py` (append)

- [ ] **Step 1: Add the test**

Append to `tests/test_workspaces_api.py`:

```python
def test_post_workspaces_add(pbg_home, tmp_path, workspace_dir):
    import urllib.request, urllib.error
    new_ws = _make_workspace(tmp_path, "added-ws")

    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/add",
            data=json.dumps({"path": str(new_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req).read())
    assert resp["name"] == "added-ws"
    assert resp["path"] == str(new_ws.resolve())
    assert workspace_catalog.list_workspaces()[-1]["path"] == str(new_ws.resolve())


def test_post_workspaces_add_rejects_non_workspace(pbg_home, tmp_path, workspace_dir):
    import urllib.request, urllib.error
    bogus = tmp_path / "no-yaml-here"; bogus.mkdir()
    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/add",
            data=json.dumps({"path": str(bogus)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 400
        body = json.loads(exc.value.read())
        assert "workspace.yaml" in body["error"]
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_workspaces_api.py -k add -x -v
```

Expected: 404 because no route.

- [ ] **Step 3: Register the route and add the handler**

In `vivarium_dashboard/server.py`, locate `_POST_ROUTE_MAP` (around line 169) and add the new entries:

```python
    "/api/workspaces/add":           "_post_workspaces_add",
    "/api/workspaces/forget":        "_post_workspaces_forget",
    "/api/workspaces/cleanup-stale": "_post_workspaces_cleanup_stale",
    "/api/workspaces/start":         "_post_workspaces_start",
```

Add the handler method on `Handler` (alongside the other `_post_*` methods):

```python
    def _post_workspaces_add(self):
        body = self._read_json_body()
        path = body.get("path") if isinstance(body, dict) else None
        if not path or not isinstance(path, str) or not path.startswith("/"):
            self._send_json(400, {"error": "path must be an absolute string"})
            return
        from pbg_superpowers import workspace_catalog
        try:
            entry = workspace_catalog.add(path)
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
            return
        self._send_json(200, entry)
```

If `_read_json_body` doesn't already exist on `Handler`, search for an existing JSON-body-reading pattern (typically `int(self.headers["Content-Length"])` + `self.rfile.read(...)`). Reuse it. If none, add:

```python
    def _read_json_body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n > 0 else b""
            return json.loads(raw) if raw else {}
        except (ValueError, json.JSONDecodeError):
            return {}
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_workspaces_api.py -k add -x -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): POST /api/workspaces/add"
```

---

## Task 7: `POST /api/workspaces/forget`

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (handler — route was registered in Task 6)
- Test: `vivarium-dashboard/tests/test_workspaces_api.py` (append)

- [ ] **Step 1: Add the test**

Append to `tests/test_workspaces_api.py`:

```python
def test_post_workspaces_forget(pbg_home, tmp_path, workspace_dir):
    import urllib.request, urllib.error
    other_ws = _make_workspace(tmp_path, "to-forget")
    workspace_catalog.add(other_ws)
    assert any(w["path"] == str(other_ws.resolve()) for w in workspace_catalog.list_workspaces())

    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/forget",
            data=json.dumps({"path": str(other_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req).read())
    assert resp == {"ok": True}
    assert not any(w["path"] == str(other_ws.resolve()) for w in workspace_catalog.list_workspaces())


def test_post_workspaces_forget_refuses_running(pbg_home, tmp_path, workspace_dir):
    import urllib.request, urllib.error
    other_ws = _make_workspace(tmp_path, "running-locked")
    workspace_catalog.add(other_ws)
    workspace_catalog.register_server(
        "running-locked", other_ws, os.getpid(), 8003, "http://127.0.0.1:8003"
    )
    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/forget",
            data=json.dumps({"path": str(other_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 409
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_workspaces_api.py -k forget -x -v
```

Expected: 404 (method `_post_workspaces_forget` not on `Handler`).

- [ ] **Step 3: Implement the handler**

Add to `Handler` near the other `_post_workspaces_*` methods:

```python
    def _post_workspaces_forget(self):
        body = self._read_json_body()
        path = body.get("path") if isinstance(body, dict) else None
        if not path or not isinstance(path, str):
            self._send_json(400, {"error": "path required"})
            return
        from pbg_superpowers import workspace_catalog
        if workspace_catalog.find_running(path) is not None:
            self._send_json(409, {"error": "stop the server before forgetting"})
            return
        workspace_catalog.forget(path)
        self._send_json(200, {"ok": True})
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_workspaces_api.py -k forget -x -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): POST /api/workspaces/forget"
```

---

## Task 8: `POST /api/workspaces/cleanup-stale`

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (handler)
- Test: `vivarium-dashboard/tests/test_workspaces_api.py` (append)

- [ ] **Step 1: Add the test**

Append:

```python
def test_post_workspaces_cleanup_stale(pbg_home, tmp_path, workspace_dir):
    import urllib.request
    stale_ws = _make_workspace(tmp_path, "stale-cleanup")
    workspace_catalog.add(stale_ws)
    # Register with a dead PID.
    workspace_catalog.register_server(
        "stale-cleanup", stale_ws, 2_000_000, 8004, "http://127.0.0.1:8004"
    )
    # Also write orphan workspace-local files.
    (stale_ws / ".pbg" / "server").mkdir(parents=True)
    (stale_ws / ".pbg" / "server" / "server-info").write_text("{}")
    (stale_ws / ".pbg" / "server" / "server.pid").write_text("2000000")

    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/cleanup-stale",
            data=json.dumps({"path": str(stale_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req).read())
    assert resp == {"ok": True}
    assert workspace_catalog.find_entry(stale_ws) is None
    assert not (stale_ws / ".pbg" / "server" / "server-info").exists()
    assert not (stale_ws / ".pbg" / "server" / "server.pid").exists()


def test_post_workspaces_cleanup_stale_refuses_alive(pbg_home, tmp_path, workspace_dir):
    import urllib.request, urllib.error
    alive_ws = _make_workspace(tmp_path, "alive-locked")
    workspace_catalog.add(alive_ws)
    workspace_catalog.register_server(
        "alive-locked", alive_ws, os.getpid(), 8005, "http://127.0.0.1:8005"
    )
    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/cleanup-stale",
            data=json.dumps({"path": str(alive_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 409
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_workspaces_api.py -k cleanup -x -v
```

Expected: 404.

- [ ] **Step 3: Implement the handler**

Add to `Handler`:

```python
    def _post_workspaces_cleanup_stale(self):
        body = self._read_json_body()
        path = body.get("path") if isinstance(body, dict) else None
        if not path or not isinstance(path, str):
            self._send_json(400, {"error": "path required"})
            return
        from pbg_superpowers import workspace_catalog
        # Refuse if the PID is in fact alive.
        if workspace_catalog.find_running(path) is not None:
            self._send_json(409, {"error": "server is still running"})
            return
        # Remove the global entry.
        workspace_catalog.unregister_server(path)
        # Best-effort removal of the orphan workspace-local files.
        from pathlib import Path as _P
        sdir = _P(path).expanduser().resolve() / ".pbg" / "server"
        for fname in ("server-info", "server.pid"):
            try:
                (sdir / fname).unlink()
            except FileNotFoundError:
                pass
        self._send_json(200, {"ok": True})
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_workspaces_api.py -k cleanup -x -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): POST /api/workspaces/cleanup-stale"
```

---

## Task 9: `POST /api/workspaces/start`

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (handler)
- Test: `vivarium-dashboard/tests/test_workspaces_api.py` (append)

- [ ] **Step 1: Add the happy-path test (spawns the real dashboard CLI)**

Append:

```python
def test_post_workspaces_start_spawns_dashboard(pbg_home, tmp_path, workspace_dir):
    """Picking a stopped workspace should spawn `vivarium-dashboard serve` and
    return its URL once registered."""
    import urllib.request
    import urllib.error
    other_ws = _make_workspace(tmp_path, "start-target")
    (other_ws / "reports").mkdir()  # cmd_serve tries to render
    workspace_catalog.add(other_ws)

    spawned_pids: list[int] = []
    with _ephemeral_dashboard(workspace_dir) as url:
        try:
            req = urllib.request.Request(
                f"{url}/api/workspaces/start",
                data=json.dumps({"path": str(other_ws)}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
            assert resp["url"].startswith("http://127.0.0.1:")
            assert isinstance(resp["pid"], int) and resp["pid"] > 0
            spawned_pids.append(resp["pid"])
        finally:
            # Always tear down the child to avoid orphan processes between tests.
            for pid in spawned_pids:
                try:
                    os.kill(pid, 15)  # SIGTERM
                except ProcessLookupError:
                    pass


def test_post_workspaces_start_refuses_arbitrary_path(pbg_home, tmp_path, workspace_dir):
    """Paths not in the catalog must be refused (safety)."""
    import urllib.request, urllib.error
    not_in_catalog = _make_workspace(tmp_path, "uncatalogued")
    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/start",
            data=json.dumps({"path": str(not_in_catalog)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 400


def test_post_workspaces_start_returns_existing_url_if_live(pbg_home, tmp_path, workspace_dir):
    """If a live entry already exists for the path, return immediately."""
    import urllib.request
    other_ws = _make_workspace(tmp_path, "already-up")
    workspace_catalog.add(other_ws)
    workspace_catalog.register_server(
        "already-up", other_ws, os.getpid(), 8006, "http://127.0.0.1:8006"
    )
    with _ephemeral_dashboard(workspace_dir) as url:
        req = urllib.request.Request(
            f"{url}/api/workspaces/start",
            data=json.dumps({"path": str(other_ws)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req).read())
    assert resp["url"] == "http://127.0.0.1:8006"
    assert resp["pid"] == os.getpid()
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_workspaces_api.py -k start -x -v
```

Expected: 404 (no handler).

- [ ] **Step 3: Implement the handler**

Add to `Handler`:

```python
    def _post_workspaces_start(self):
        body = self._read_json_body()
        path = body.get("path") if isinstance(body, dict) else None
        if not path or not isinstance(path, str) or not path.startswith("/"):
            self._send_json(400, {"error": "path must be an absolute string"})
            return
        from pathlib import Path as _P
        target = _P(path).expanduser().resolve()
        if not (target / "workspace.yaml").is_file():
            self._send_json(400, {"error": "not a workspace (no workspace.yaml)"})
            return

        from pbg_superpowers import workspace_catalog
        # Must be in the catalog (safety: prevent launching arbitrary processes).
        if not any(_P(e["path"]).resolve() == target
                   for e in workspace_catalog.list_workspaces()):
            self._send_json(400, {"error": "workspace not in catalog — Add it first"})
            return

        # Idempotent: if a live entry already exists, return it.
        live = workspace_catalog.find_running(target)
        if live is not None:
            self._send_json(200, {"url": live["url"], "pid": live["pid"]})
            return

        # Spawn `vivarium-dashboard serve` detached.
        import subprocess
        import time
        log_path = target / ".pbg" / "server" / "start.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as logf:
            subprocess.Popen(
                [sys.executable, "-m", "vivarium_dashboard.cli",
                 "serve", "--workspace", str(target)],
                stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
                cwd=str(target),
            )

        # Poll for the global registry entry.
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            entry = workspace_catalog.find_running(target)
            if entry is not None:
                self._send_json(200, {"url": entry["url"], "pid": entry["pid"]})
                return
            time.sleep(0.1)

        self._send_json(504, {
            "error": "start_timeout",
            "log_path": str(log_path),
            "hint": f"tail {log_path}",
        })
```

(Add `import sys` to the top of `server.py` if not already imported; check with `grep -n "^import sys" vivarium_dashboard/server.py`.)

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_workspaces_api.py -k start -x -v --timeout=30
```

Expected: 3 PASS. The happy-path test will take a few seconds (real subprocess spawn).

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): POST /api/workspaces/start (spawn detached dashboard)"
```

---

## Task 10: Dropdown UI

**Repo:** `vivarium-dashboard`

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/templates/index.html.j2` (lines 121–123 + add CSS + add JS file include)
- Create: `vivarium-dashboard/vivarium_dashboard/static/workspace-switcher.js`
- Test: manual verification (no JS test runner is in place; the design spec opted out)

The placeholder div is replaced with a trigger + a panel rendered from the `/api/workspaces` response.

- [ ] **Step 1: Replace the placeholder div in `index.html.j2`**

In `vivarium-dashboard/vivarium_dashboard/templates/index.html.j2`, find lines 121–123:

```html
    <div class="viv-workspace-switcher viv-tooltip" data-tooltip="Other workspaces coming soon">
      <strong>{{ workspace_name }}</strong> <span class="viv-arrow">▾</span>
    </div>
```

Replace with:

```html
    <div class="viv-workspace-switcher" id="viv-workspace-switcher">
      <button class="viv-workspace-switcher-trigger" type="button"
              aria-haspopup="true" aria-expanded="false"
              id="viv-workspace-switcher-trigger">
        <span class="viv-workspace-switcher-glyph">●</span>
        <strong>{{ workspace_name }}</strong>
        <span class="viv-arrow">▾</span>
      </button>
      <div class="viv-workspace-switcher-panel" id="viv-workspace-switcher-panel" hidden>
        <div class="viv-workspace-switcher-header">Workspaces</div>
        <ul class="viv-workspace-switcher-list" id="viv-workspace-switcher-list">
          <li class="viv-workspace-switcher-loading">Loading…</li>
        </ul>
        <div class="viv-workspace-switcher-footer">
          <button class="viv-workspace-switcher-add" type="button"
                  id="viv-workspace-switcher-add">
            + Add existing workspace…
          </button>
        </div>
      </div>
    </div>
```

- [ ] **Step 2: Add CSS for the panel**

In `index.html.j2`, find the existing `<style>` block (starts around line 5). Append before `</style>`:

```css
/* Workspace switcher (top of the left rail). */
.viv-workspace-switcher { position: relative; padding: 8px 12px; }
.viv-workspace-switcher-trigger {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 6px 8px; background: #fff;
  border: 1px solid #ddd; border-radius: 4px; cursor: pointer;
  font-size: 13px;
}
.viv-workspace-switcher-trigger:hover { background: #f5f5f5; }
.viv-workspace-switcher-glyph { color: #2ea043; font-size: 14px; }
.viv-workspace-switcher-panel {
  position: absolute; top: 100%; left: 12px; right: 12px;
  background: #fff; border: 1px solid #ccc; border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  z-index: 1000; max-height: 70vh; overflow-y: auto;
}
.viv-workspace-switcher-header {
  padding: 8px 12px; border-bottom: 1px solid #eee;
  font-weight: 600; font-size: 12px; color: #666;
}
.viv-workspace-switcher-list { list-style: none; margin: 0; padding: 0; }
.viv-workspace-switcher-list li {
  padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 8px;
}
.viv-workspace-switcher-list li:last-child { border-bottom: none; }
.viv-workspace-switcher-list a {
  flex: 1; text-decoration: none; color: inherit;
  display: flex; flex-direction: column;
}
.viv-workspace-switcher-list a:hover { color: #0366d6; }
.viv-workspace-switcher-list .viv-ws-path {
  font-size: 11px; color: #888; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.viv-workspace-switcher-list .viv-ws-glyph { width: 18px; text-align: center; }
.viv-workspace-switcher-list .viv-ws-row-current { background: #f8f9fb; }
.viv-workspace-switcher-list button {
  font-size: 11px; padding: 3px 8px; cursor: pointer;
  border: 1px solid #ccc; background: #fff; border-radius: 3px;
}
.viv-workspace-switcher-list button:hover { background: #f0f0f0; }
.viv-workspace-switcher-footer {
  padding: 8px 12px; border-top: 1px solid #eee;
}
.viv-workspace-switcher-add {
  background: none; border: none; color: #0366d6;
  cursor: pointer; font-size: 12px; padding: 0;
}
.viv-glyph-running { color: #2ea043; }
.viv-glyph-stopped { color: #999; }
.viv-glyph-stale   { color: #d29922; }
.viv-glyph-missing { color: #cf222e; }
.viv-ws-error { color: #cf222e; font-size: 11px; padding: 2px 0; }
```

- [ ] **Step 3: Include the JS file**

In `index.html.j2`, find the existing `<script>` tags near the bottom of the file (search for `</body>`). Add immediately before `</body>`:

```html
<script src="/static/workspace-switcher.js"></script>
```

(If the dashboard serves `/static/` via the existing GET routing, confirm by looking at how other JS files like `study-detail.js` are referenced. Match that pattern.)

- [ ] **Step 4: Create the JS file**

Create `vivarium-dashboard/vivarium_dashboard/static/workspace-switcher.js`:

```javascript
// Workspace switcher: dropdown panel in the left rail.
//
// Reads GET /api/workspaces and renders rows by status. Click handlers:
//   running  → navigate same tab to row.url
//   stopped  → POST /api/workspaces/start, then navigate to returned url
//   stale    → POST /api/workspaces/cleanup-stale, then re-render
//   missing  → POST /api/workspaces/forget, then re-render

(function () {
  const trigger = document.getElementById('viv-workspace-switcher-trigger');
  const panel   = document.getElementById('viv-workspace-switcher-panel');
  const list    = document.getElementById('viv-workspace-switcher-list');
  const addBtn  = document.getElementById('viv-workspace-switcher-add');
  if (!trigger || !panel || !list) return;

  const GLYPH = {
    current: '●', running: '●', stopped: '○', stale: '⚠', missing: '⊘',
  };
  const GLYPH_CLASS = {
    current: 'viv-glyph-running', running: 'viv-glyph-running',
    stopped: 'viv-glyph-stopped', stale: 'viv-glyph-stale',
    missing: 'viv-glyph-missing',
  };

  function close() {
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  }
  function open() {
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    refresh();
  }

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    if (panel.hidden) open(); else close();
  });
  document.addEventListener('click', (e) => {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== trigger) close();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.hidden) close();
  });

  async function refresh() {
    list.innerHTML = '<li class="viv-workspace-switcher-loading">Loading…</li>';
    try {
      const resp = await fetch('/api/workspaces');
      const data = await resp.json();
      render(data);
    } catch (err) {
      list.innerHTML = `<li class="viv-ws-error">Failed to load: ${escapeHtml(String(err))}</li>`;
    }
  }

  function render(data) {
    list.innerHTML = '';
    data.workspaces.forEach((ws) => {
      list.appendChild(renderRow(ws, data.current));
    });
  }

  function renderRow(ws, current) {
    const li = document.createElement('li');
    if (ws.status === 'current') li.classList.add('viv-workspace-switcher-list', 'viv-ws-row-current');

    const glyph = document.createElement('span');
    glyph.className = `viv-ws-glyph ${GLYPH_CLASS[ws.status] || ''}`;
    glyph.textContent = GLYPH[ws.status] || '?';
    li.appendChild(glyph);

    if (ws.status === 'current') {
      const label = document.createElement('div');
      label.style.flex = '1';
      label.innerHTML = `<strong>${escapeHtml(ws.name)}</strong> <small>(this)</small>
                         <div class="viv-ws-path">${escapeHtml(ws.path)}</div>`;
      li.appendChild(label);
      return li;
    }

    if (ws.status === 'running') {
      const a = document.createElement('a');
      a.href = ws.url;
      a.innerHTML = `<strong>${escapeHtml(ws.name)}</strong>
                     <span class="viv-ws-path">${escapeHtml(ws.path)}</span>`;
      li.appendChild(a);
      return li;
    }

    const label = document.createElement('div');
    label.style.flex = '1';
    label.innerHTML = `<strong>${escapeHtml(ws.name)}</strong>
                       <div class="viv-ws-path">${escapeHtml(ws.path)}</div>`;
    li.appendChild(label);

    if (ws.status === 'stopped') {
      const btn = document.createElement('button');
      btn.textContent = 'Start ▸';
      btn.addEventListener('click', () => doStart(ws.path, btn, li));
      li.appendChild(btn);
    } else if (ws.status === 'stale') {
      const btn = document.createElement('button');
      btn.textContent = 'Clean up';
      btn.addEventListener('click', () => doCleanup(ws.path, btn, li));
      li.appendChild(btn);
    } else if (ws.status === 'missing') {
      const btn = document.createElement('button');
      btn.textContent = 'Forget ×';
      btn.addEventListener('click', () => doForget(ws.path, btn, li));
      li.appendChild(btn);
    }
    return li;
  }

  async function doStart(path, btn, row) {
    btn.disabled = true;
    btn.textContent = 'Starting…';
    try {
      const resp = await fetch('/api/workspaces/start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path}),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        rowError(row, body.error || `HTTP ${resp.status}`,
                 body.log_path ? `(log: ${body.log_path})` : '');
        btn.disabled = false; btn.textContent = 'Start ▸';
        return;
      }
      const data = await resp.json();
      window.location.href = data.url;
    } catch (err) {
      rowError(row, String(err));
      btn.disabled = false; btn.textContent = 'Start ▸';
    }
  }

  async function doCleanup(path, btn, row) {
    btn.disabled = true;
    try {
      const resp = await fetch('/api/workspaces/cleanup-stale', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path}),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        rowError(row, body.error || `HTTP ${resp.status}`);
        btn.disabled = false;
        return;
      }
      refresh();
    } catch (err) {
      rowError(row, String(err));
      btn.disabled = false;
    }
  }

  async function doForget(path, btn, row) {
    btn.disabled = true;
    try {
      const resp = await fetch('/api/workspaces/forget', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path}),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        rowError(row, body.error || `HTTP ${resp.status}`);
        btn.disabled = false;
        return;
      }
      refresh();
    } catch (err) {
      rowError(row, String(err));
      btn.disabled = false;
    }
  }

  function rowError(row, msg, hint) {
    const e = document.createElement('div');
    e.className = 'viv-ws-error';
    e.textContent = hint ? `${msg} ${hint}` : msg;
    row.appendChild(e);
  }

  if (addBtn) {
    addBtn.addEventListener('click', async () => {
      const p = window.prompt('Path to workspace directory:');
      if (!p) return;
      const resp = await fetch('/api/workspaces/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: p}),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        alert('Could not add: ' + (body.error || `HTTP ${resp.status}`));
        return;
      }
      refresh();
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
})();
```

- [ ] **Step 5: Confirm `/static/` serving covers the new file**

```bash
grep -n "static" /Users/eranagmon/code/vivarium-dashboard/vivarium_dashboard/server.py | head -10
```

If the server serves `/static/` from `vivarium_dashboard/static/` (it does via `force-include` in pyproject + handler logic), the new file is automatically reachable at `/static/workspace-switcher.js`. If not, follow the same registration pattern used by `study-detail.js` (search for `study-detail.js` in `server.py`).

- [ ] **Step 6: Manual smoke test in the dashboard**

In one terminal, in a real workspace:

```bash
cd /Users/eranagmon/code/v2ecoli-workspace
python -m vivarium_dashboard.cli serve --workspace .
```

In another terminal, register a couple of other workspaces:

```bash
python -m pbg_superpowers.workspace_catalog add --path /Users/eranagmon/code/pbg-biomodels
python -m pbg_superpowers.workspace_catalog add --path /Users/eranagmon/code/test-workspace
```

In a browser: open the URL printed by the dashboard. Click the workspace name in the rail; the panel should open with three rows — `v2ecoli-workspace (this)`, `pbg-biomodels` (stopped), `test-workspace` (stopped). Click `[Start ▸]` on either stopped row; within 8 s the page should navigate to the new dashboard.

- [ ] **Step 7: Commit**

```bash
git add vivarium_dashboard/templates/index.html.j2 vivarium_dashboard/static/workspace-switcher.js
git commit -m "feat(ui): workspace switcher dropdown in the left rail"
```

---

## Task 11: End-to-end verification

**Manual; no test file.**

This task is a smoke test across both repos. Before declaring the feature done, walk through the scenarios below.

- [ ] **Step 1: Fresh install both repos**

```bash
cd /Users/eranagmon/code/pbg-superpowers && pip install -e .
cd /Users/eranagmon/code/vivarium-dashboard && pip install -e .
```

- [ ] **Step 2: Clear any leftover state**

```bash
rm -rf ~/.pbg/workspaces.json ~/.pbg/servers ~/.pbg/workspaces.json.lock
```

- [ ] **Step 3: First-run UX — start a dashboard with no catalog yet**

```bash
cd /Users/eranagmon/code/v2ecoli-workspace
python -m vivarium_dashboard.cli serve --workspace .
```

Open the URL. Click the switcher. Expected: panel shows only the current workspace (auto-included even though no `add` was called). `~/.pbg/workspaces.json` does NOT need to exist for this to work.

- [ ] **Step 4: Register a second workspace via the UI**

In the panel, click `+ Add existing workspace…`. Enter `/Users/eranagmon/code/pbg-biomodels`. The row should appear with `○` and `[Start ▸]`.

- [ ] **Step 5: Start the second dashboard from the UI**

Click `[Start ▸]`. The button shows "Starting…" briefly, then the page navigates to the new dashboard URL.

- [ ] **Step 6: From the second dashboard, switch back**

In the second dashboard, click the switcher. The original workspace appears with `●` (running). Click the row; the page navigates back.

- [ ] **Step 7: Verify cleanup**

In a terminal, kill the second dashboard with SIGTERM (`kill <pid>`; the PID is in `~/.pbg/servers/pbg-biomodels.json`). Open the switcher; the row should show as stopped (no `⚠` if the exit handler ran cleanly). If the exit handler did not run (e.g., `kill -9`), the row shows `⚠` with `[Clean up]`; click it and verify the row turns to stopped.

- [ ] **Step 8: Confirm `/pbg-workspace` registers**

Create a brand-new workspace via `/pbg-workspace` (or simulate by running the new shim line manually). Verify it appears in the catalog file:

```bash
cat ~/.pbg/workspaces.json | python3 -m json.tool
```

- [ ] **Step 9: Confirm forget refuses running**

In the switcher, try to forget a running workspace (right-click → Forget, or trigger via curl). Expected: 409, row shows `stop the server before forgetting`.

- [ ] **Step 10: Wrap-up**

If all 9 steps above passed, the feature is done. Push the commits in both repos. No PR / no merge action is part of this plan — that's the engineer's call.

---

## Notes for the implementing engineer

- **Code style:** follow what's already in each repo. The dashboard uses `from __future__ import annotations` and explicit type hints; match it. The catalog module uses the same style.
- **Stay minimal:** if you find yourself wanting to add a feature not in this plan, don't. File it as a follow-up.
- **Where the launcher lives:** the canonical dashboard launcher is `vivarium-dashboard serve` (a.k.a. `python -m vivarium_dashboard.cli serve`). `pbg-superpowers/server/start-server.sh` is a *different*, report-mirror launcher and is intentionally untouched.
- **When a step refers to a helper that may not exist:** the plan says so and gives you a search command. Don't blindly add a new helper if the codebase already has one — reuse it.
- **Cross-repo commits:** each repo gets its own commits. The pbg-superpowers commits land first because vivarium-dashboard depends on the new catalog module.
