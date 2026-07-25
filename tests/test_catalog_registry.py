"""Tests for the canonical module registry (viva_superpowers.catalog)."""
from __future__ import annotations

import json

from viva_superpowers.catalog import (
    canonical_registry,
    load_registry,
)


def test_canonical_registry_loads_as_package_resource():
    reg = canonical_registry()
    assert isinstance(reg, list) and len(reg) > 10
    # every entry has the catalog shape
    for m in reg:
        assert isinstance(m, dict) and m.get("name")


def test_canonical_registry_has_no_pbg_physicell():
    names = {m["name"] for m in canonical_registry()}
    assert "pbg-physicell" not in names
    # a couple of expected curated modules are present
    assert "v2ecoli" in names
    assert "spatio-flux" in names


def test_load_registry_without_workspace_is_canonical():
    assert load_registry() == canonical_registry()
    assert load_registry(None) == canonical_registry()


def test_overlay_appends_new_module(tmp_path):
    (tmp_path / "scripts" / "_catalog").mkdir(parents=True)
    (tmp_path / "scripts" / "_catalog" / "overlay.json").write_text(
        json.dumps([{"name": "pbg-localonly", "description": "local"}])
    )
    names = {m["name"] for m in load_registry(tmp_path)}
    assert "pbg-localonly" in names
    assert names >= {m["name"] for m in canonical_registry()}


def test_overlay_overrides_canonical_entry_in_place(tmp_path):
    canon = canonical_registry()
    target = canon[0]["name"]
    (tmp_path / "scripts" / "_catalog").mkdir(parents=True)
    (tmp_path / "scripts" / "_catalog" / "overlay.json").write_text(
        json.dumps([{"name": target, "description": "OVERRIDDEN"}])
    )
    merged = load_registry(tmp_path)
    # same count (override, not append) and the entry is replaced
    assert len(merged) == len(canon)
    hit = next(m for m in merged if m["name"] == target)
    assert hit["description"] == "OVERRIDDEN"


def test_malformed_overlay_is_ignored(tmp_path):
    (tmp_path / "scripts" / "_catalog").mkdir(parents=True)
    (tmp_path / "scripts" / "_catalog" / "overlay.json").write_text("{ not json")
    assert load_registry(tmp_path) == canonical_registry()
