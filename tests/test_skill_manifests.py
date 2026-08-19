# tests/test_skill_manifests.py
"""Every SKILL.md has required frontmatter; only well-formed skill dirs exist.

Also guards against the drift this file is named for: the plugin manifests
must agree with pyproject on version, and the set of user-invocable skills
must stay pinned (so adding/removing a skill forces a conscious docs update).
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pytest
import yaml


# The skills that ship with `user-invocable: true`.
#
# `_VIVA_CORE`: the core `/viva-*` skills (incl. `/viva-init` machine setup;
# `/viva-suggest` is an internal dashboard callback, deliberately NOT invocable).
# `_VIVA_EXTRA`: skills added after the core set.
# The pbg→viva rebrand is complete — the legacy `pbg-*` alias skills were removed,
# so the invocable set is now viva-only. `/viva-server` (the report-mirror server)
# was retired; report viewing is served by the vivarium-workbench (`/viva-workbench`).
# The v0.10 skill-surface leanness pass folded 4 overlapping skills into 3 hosts
# as subcommands/aspects and removed their standalone dirs:
#   viva-audit-tests   -> viva-tests   "### Subcommand: audit"
#   viva-cite-bands    -> viva-tests   "### Subcommand: cite-bands"
#   viva-status        -> viva-navigate "### Subcommand: status"
#   viva-biology-forward -> viva-harden-investigation "### Aspect: biology-forward"
# Keep in sync with docs/skills.md + README/CLAUDE counts — the test below fails on drift.
_VIVA_CORE = {
    "viva-catalog", "viva-expert",
    "viva-init", "viva-investigation", "viva-navigate",
    "viva-report", "viva-run", "viva-study", "viva-tests",
    "viva-viz", "viva-workbench", "viva-workspace",
}
_VIVA_EXTRA = {"viva-harden-investigation", "viva-model-build", "viva-benchmark"}
_VIVA_INVOCABLE = _VIVA_CORE | _VIVA_EXTRA
USER_INVOCABLE_SKILLS = _VIVA_INVOCABLE


REQUIRED_FIELDS = {"name", "description"}
SKILL_NAME_RE = re.compile(r"^viva-[a-z][a-z0-9-]*$")


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
    assert not bad, f"skill dirs with bad names: {bad} (expected viva-<kebab>)"


def pytest_generate_tests(metafunc):
    if "skill_path" in metafunc.fixturenames:
        plugin_root = Path(__file__).resolve().parents[1]
        metafunc.parametrize("skill_path", _skill_files(plugin_root),
                             ids=lambda p: p.parent.name)


def test_skill_has_valid_frontmatter(skill_path):
    fm = _frontmatter(skill_path.read_text())
    missing = REQUIRED_FIELDS - fm.keys()
    assert not missing, f"{skill_path.parent.name} missing fields: {missing}"


def test_user_invocable_set_is_pinned(plugin_root):
    """The user-invocable skills must match USER_INVOCABLE_SKILLS exactly.

    Drift here means docs/skills.md + the README/CLAUDE.md counts are now wrong.
    Update both the docs and this set together.
    """
    actual = set()
    for p in _skill_files(plugin_root):
        fm = _frontmatter(p.read_text())
        if fm.get("user-invocable") is True:
            actual.add(p.parent.name)
    assert actual == USER_INVOCABLE_SKILLS, (
        f"user-invocable skills drifted.\n"
        f"  unexpected: {sorted(actual - USER_INVOCABLE_SKILLS)}\n"
        f"  missing:    {sorted(USER_INVOCABLE_SKILLS - actual)}"
    )


def test_docs_skill_count_matches(plugin_root):
    """docs/skills.md, README.md, CLAUDE.md must all cite the live count."""
    n = len(_VIVA_INVOCABLE) - 1  # exclude viva-init (machine setup)
    skills_md = (plugin_root / "docs" / "skills.md").read_text()
    assert f"{n} user-facing skills" in skills_md, (
        f"docs/skills.md should say '{n} user-facing skills'")
    readme = (plugin_root / "README.md").read_text()
    assert f"Ships {n} `/viva-*` skills" in readme, (
        f"README.md should say 'Ships {n} `/viva-*` skills'")
    claude = (plugin_root / "CLAUDE.md").read_text()
    assert f"all {n} user-invocable" in claude, (
        f"CLAUDE.md should say 'all {n} user-invocable'")


def test_manifest_version_matches_pyproject(plugin_root):
    """plugin.json + marketplace.json must agree with pyproject on version."""
    pyproject = (plugin_root / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m, "could not find version in pyproject.toml"
    version = m.group(1)

    plugin = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == version, (
        f"plugin.json version {plugin['version']!r} != pyproject {version!r}")

    market = json.loads((plugin_root / ".claude-plugin" / "marketplace.json").read_text())
    # marketplace.json nests the version under the plugin entry; find it anywhere.
    blob = json.dumps(market)
    assert f'"version": "{version}"' in blob, (
        f"marketplace.json has no version matching pyproject {version!r}")
