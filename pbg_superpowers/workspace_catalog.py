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
