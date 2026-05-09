# tests/test_skill_manifests.py
"""Every SKILL.md has required frontmatter."""
from __future__ import annotations
from pathlib import Path

import pytest
import yaml


REQUIRED_FIELDS = {"name", "description"}
EXPECTED_SKILLS = {
    "pbg-workspace", "pbg-server", "pbg-report", "pbg-phase",
    "pbg-expert", "pbg-composer",
}


def _frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise AssertionError("SKILL.md frontmatter not closed")
    return yaml.safe_load(text[4:end]) or {}


def _skill_files(plugin_root: Path) -> list[Path]:
    return sorted((plugin_root / "skills").glob("*/SKILL.md"))


def test_all_expected_skills_present(plugin_root):
    found = {p.parent.name for p in _skill_files(plugin_root)}
    missing = EXPECTED_SKILLS - found
    extra = found - EXPECTED_SKILLS
    assert not missing, f"missing skills: {sorted(missing)}"
    assert not extra, f"unexpected skills: {sorted(extra)}"


def pytest_generate_tests(metafunc):
    if "skill_path" in metafunc.fixturenames:
        plugin_root = Path(__file__).resolve().parents[1]
        files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        metafunc.parametrize("skill_path", files, ids=lambda p: p.parent.name)


def test_each_skill_frontmatter(skill_path):
    fm = _frontmatter(skill_path.read_text())
    missing = REQUIRED_FIELDS - set(fm.keys())
    assert not missing, f"{skill_path}: missing {missing}"
    assert fm["name"] == skill_path.parent.name, "name field must match dir name"
