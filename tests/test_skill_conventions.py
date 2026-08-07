# tests/test_skill_conventions.py
"""Skill-authoring conventions, enforced (obra/superpowers `writing-skills` lessons).

Complements test_skill_manifests.py (which pins the *set* of skills). This file
pins the *quality* of each SKILL.md so the gateway (viva-orient) can trust that:

  * descriptions are triggers ("Use when ..."), not workflow summaries, and stay
    within the frontmatter budget an agent actually reads (<=500 chars);
  * the H1 title matches the skill name and command form;
  * the pbg->viva rebrand stays finished — no `pbg-` command/skill/title leaks
    (legit ecosystem repo names live in bodies, not titles/descriptions);
  * internal program vocabulary ("spine stage #N", "SP4a") never reaches a
    user-facing description.

Why descriptions matter most: obra's testing shows an agent follows a
workflow-summarizing description *instead of* reading the skill body. The
description is When-To-Use, third person, and nothing else.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DESCRIPTION_MAX = 500

# `pbg-` tokens that are legitimate *ecosystem* identifiers (sibling repos /
# published dists). They may appear in skill *bodies*, but never in a title or
# description. Titles/descriptions forbid `pbg-` outright, so this allowlist is
# only consulted for the (looser) body scans if we add them later.
_PBG_TITLE_DESC = re.compile(r"pbg-")
_INTERNAL_JARGON = re.compile(r"spine stage|\bSP\d|stage #\d", re.IGNORECASE)


def _split(text: str) -> tuple[dict, str]:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.find("\n---\n", 4)
    assert end != -1, "SKILL.md frontmatter not closed"
    fm = yaml.safe_load(text[4:end]) or {}
    body = text[end + 5 :]
    return fm, body


def _first_h1(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line
    return None


def _skill_files(plugin_root: Path) -> list[Path]:
    return sorted((plugin_root / "skills").glob("*/SKILL.md"))


def pytest_generate_tests(metafunc):
    if "skill_path" in metafunc.fixturenames:
        root = Path(__file__).resolve().parents[1]
        metafunc.parametrize(
            "skill_path", _skill_files(root), ids=lambda p: p.parent.name
        )


def test_name_matches_dir(skill_path):
    fm, _ = _split(skill_path.read_text())
    assert fm.get("name") == skill_path.parent.name, (
        f"{skill_path.parent.name}: frontmatter name {fm.get('name')!r} "
        f"must equal directory name"
    )


def test_description_within_budget(skill_path):
    fm, _ = _split(skill_path.read_text())
    desc = (fm.get("description") or "").strip()
    assert 0 < len(desc) <= DESCRIPTION_MAX, (
        f"{skill_path.parent.name}: description is {len(desc)} chars "
        f"(budget {DESCRIPTION_MAX}). Move workflow/deliverable detail into the "
        f"body; the description is When-To-Use only."
    )


def test_user_invocable_description_is_a_trigger(skill_path):
    fm, _ = _split(skill_path.read_text())
    if fm.get("user-invocable") is not True:
        pytest.skip("not user-invocable")
    desc = (fm.get("description") or "").strip()
    assert desc.startswith("Use when"), (
        f"{skill_path.parent.name}: user-invocable description must start with "
        f"'Use when ...' (trigger, not a summary of what the skill does). "
        f"Got: {desc[:60]!r}"
    )


def test_no_internal_jargon_in_description(skill_path):
    fm, _ = _split(skill_path.read_text())
    desc = fm.get("description") or ""
    m = _INTERNAL_JARGON.search(desc)
    assert not m, (
        f"{skill_path.parent.name}: description leaks internal vocabulary "
        f"{m.group(0)!r}. Keep 'spine stage #N' / 'SP4a' in the body, not the "
        f"user-facing trigger."
    )


def test_no_pbg_in_description(skill_path):
    fm, _ = _split(skill_path.read_text())
    desc = fm.get("description") or ""
    assert not _PBG_TITLE_DESC.search(desc), (
        f"{skill_path.parent.name}: description contains a 'pbg-' token. The "
        f"rebrand is finished — use the viva-* name (ecosystem repo names like "
        f"pbg-emitters belong in the body, not the trigger)."
    )


def test_h1_matches_name_and_has_no_pbg(skill_path):
    fm, body = _split(skill_path.read_text())
    name = skill_path.parent.name
    h1 = _first_h1(body)
    assert h1 is not None, f"{name}: no H1 (`# ...`) title found"
    assert "pbg-" not in h1, (
        f"{name}: H1 still says {h1!r} — stale pbg- title, should be /{name}"
    )
    # Non-user-invocable skills (viva-orient, viva-suggest) may use a prose H1.
    if fm.get("user-invocable") is True:
        assert re.match(rf"^#\s+/?{re.escape(name)}\b", h1), (
            f"{name}: H1 {h1!r} must start with '# /{name}' (command form)"
        )
