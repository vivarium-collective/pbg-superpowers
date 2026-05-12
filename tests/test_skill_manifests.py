# tests/test_skill_manifests.py
"""Every SKILL.md has required frontmatter; only well-formed skill dirs exist."""
from __future__ import annotations
import re
from pathlib import Path

import pytest
import yaml


REQUIRED_FIELDS = {"name", "description"}
SKILL_NAME_RE = re.compile(r"^pbg-[a-z][a-z0-9-]*$")


def _frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise AssertionError("SKILL.md frontmatter not closed")
    return yaml.safe_load(text[4:end]) or {}


def _skill_files(plugin_root: Path) -> list[Path]:
    return sorted((plugin_root / "skills").glob("*/SKILL.md"))


def test_at_least_one_skill_present(plugin_root):
    found = {p.parent.name for p in _skill_files(plugin_root)}
    assert found, "no skills found under skills/*/SKILL.md"


def test_skill_dir_names_well_formed(plugin_root):
    bad = [p.parent.name for p in _skill_files(plugin_root)
           if not SKILL_NAME_RE.match(p.parent.name)]
    assert not bad, f"skill dirs with bad names: {bad} (expected pbg-<kebab>)"


def pytest_generate_tests(metafunc):
    if "skill_path" in metafunc.fixturenames:
        plugin_root = Path(__file__).resolve().parents[1]
        metafunc.parametrize("skill_path", _skill_files(plugin_root),
                             ids=lambda p: p.parent.name)


def test_skill_has_valid_frontmatter(skill_path):
    fm = _frontmatter(skill_path.read_text())
    missing = REQUIRED_FIELDS - fm.keys()
    assert not missing, f"{skill_path.parent.name} missing fields: {missing}"
