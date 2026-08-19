"""Guard test for the /viva-tests skill.

Asserts the SKILL.md exists, carries valid user-invocable front-matter, and
covers the graded-Test contract the skill is *for*: `check()`/`TestBuilder`,
a signed `margin`, the cross-iteration diff, `TestStep`, and the three verbs
(author/enrich/run). It also guards the two disciplines that make the signal
useful to an agent — graded bands over magic numbers, and only `hard` axes gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-tests" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file(), "skills/viva-tests/SKILL.md must exist"


def test_frontmatter_is_user_invocable(skill_text):
    assert skill_text.startswith("---"), "SKILL.md must open with YAML front-matter"
    fm = skill_text.split("---", 2)[1]
    assert "name: viva-tests" in fm
    assert "user-invocable: true" in fm
    assert "description:" in fm
    assert "argument-hint:" in fm


def test_covers_the_graded_contract(skill_text):
    for token in ("TestStep", "check(", "TestBuilder", "margin",
                  "report_card_verdict/v2", "band(", "severity"):
        assert token in skill_text, f"skill must document {token!r}"


def test_covers_the_three_verbs_and_the_diff(skill_text):
    for verb in ("author", "enrich", "run"):
        assert f"## {verb} " in skill_text, f"skill must document the '{verb}' verb"
    # the cross-iteration signal an agent reads
    assert "test_diff" in skill_text
    assert "report.json" in skill_text


def test_guards_the_disciplines(skill_text):
    # bands over magic numbers; only hard axes gate
    assert "bands over magic numbers" in skill_text.lower() \
        or "over magic numbers" in skill_text.lower()
    assert "hard" in skill_text and "directional" in skill_text
    # points at the cite-bands subcommand for the acceptance-band + citation authoring path
    assert "cite-bands" in skill_text
