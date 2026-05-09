"""Helpers to introspect a process-bigraph core's registries.

These adapt to whatever public API the running version of process-bigraph
exposes (list_processes / registered_links / etc.) — they fail loudly if
no introspection method is available.
"""
from __future__ import annotations
from typing import Any, Iterable


def _try(core: Any, *attrs: str) -> Iterable[str] | None:
    for a in attrs:
        m = getattr(core, a, None)
        if callable(m):
            return list(m())
        if isinstance(m, dict):
            return list(m.keys())
    return None


def list_processes(core: Any) -> list[str]:
    res = _try(core, "list_processes", "registered_links", "_links")
    if res is None:
        raise RuntimeError("core has no inspectable process registry")
    return sorted(res)


def list_types(core: Any) -> list[str]:
    res = _try(core, "list_types", "_types", "registered_types")
    if res is None:
        raise RuntimeError("core has no inspectable type registry")
    return sorted(res)


def registry_snapshot(core: Any) -> dict:
    return {"processes": list_processes(core), "types": list_types(core)}
