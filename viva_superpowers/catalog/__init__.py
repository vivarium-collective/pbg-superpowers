"""Canonical module registry — single source of truth for the dashboard's
"available modules" catalog (the Registry tab + `/api/catalog-install`).

Before this, every workspace vendored a full copy at
``scripts/_catalog/modules.json``, so curating the list (e.g. removing an
unauthorized module) meant editing N drifting copies across every workspace
and clone. Now the curated list ships HERE as a package resource; the
dashboard reads it via :func:`load_registry`, merging an optional
per-workspace ``scripts/_catalog/overlay.json`` for local-only modules.

To add/remove a module from the ecosystem registry, edit ``modules.json`` in
this package and release — every workspace's dashboard picks it up.
"""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

# Per-workspace overlay: a list of module dicts (same shape as the canonical
# entries) for modules that should appear only in that workspace's registry.
_OVERLAY_REL = ("scripts", "_catalog", "overlay.json")


def canonical_registry() -> list[dict]:
    """The curated available-modules list.

    Ownership of the ecosystem registry has moved to the dedicated
    ``viva-marketplace`` repo/package — read it from there when it's installed so
    there's a single source of truth. The copy shipped here is a fallback kept
    for standalone / offline use (e.g. viva-marketplace not installed)."""
    try:
        import viva_marketplace  # noqa: PLC0415
        mods = viva_marketplace.load_modules()
        if mods:
            return mods
    except Exception:  # noqa: BLE001 — any import/read failure falls back to the local copy
        pass
    text = (files(__package__) / "modules.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return data if isinstance(data, list) else []


def _load_overlay(workspace_root: Path | str) -> list[dict]:
    p = Path(workspace_root).joinpath(*_OVERLAY_REL)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def load_registry(workspace_root: Path | str | None = None) -> list[dict]:
    """Canonical registry, with an optional per-workspace overlay merged on top.

    Overlay entries are keyed by ``name``: an entry whose name is new is
    appended after the canonical modules; one matching a canonical name
    overrides it in place. This lets a workspace add local-only modules (or
    pin a variant) without forking the whole list.
    """
    merged: dict[str, dict] = {
        m["name"]: m for m in canonical_registry() if isinstance(m, dict) and m.get("name")
    }
    if workspace_root is not None:
        for m in _load_overlay(workspace_root):
            if isinstance(m, dict) and m.get("name"):
                merged[m["name"]] = m
    return list(merged.values())
