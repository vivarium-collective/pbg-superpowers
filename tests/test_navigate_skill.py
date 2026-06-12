"""Guard test for the /pbg-navigate skill (SP4a).

Asserts the SKILL.md documents the four read-only subcommands and references the
deterministic linkage backend (linkage_index / /api/linkage-index).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "pbg-navigate" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file(), "skills/pbg-navigate/SKILL.md must exist"


def test_subcommands_documented(skill_text):
    for sub in ("ac-gaps", "source", "finding-by-observable", "dag",
                "observable", "composite"):
        assert sub in skill_text, f"subcommand {sub!r} not documented"


def test_references_linkage_backend(skill_text):
    assert "linkage_index" in skill_text
    assert "/api/linkage-index" in skill_text


def test_read_only_no_ai(skill_text):
    # The skill must call the deterministic query helpers.
    for fn in ("ac_gating_matrix", "studies_for_source",
               "findings_for_observable", "study_dag",
               "studies_for_observable", "composite_emits"):
        assert fn in skill_text, f"helper {fn!r} not referenced"
