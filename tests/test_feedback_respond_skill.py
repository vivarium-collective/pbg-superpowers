"""Structural guard: the viva-study skill documents the feedback-respond
subcommand and references the SP3b primitives by name (the AI-free split).
"""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-study" / "SKILL.md"


def _doc(skill_md: Path) -> str:
    # SKILL.md + optional reference.md (heavy detail is split out per the obra
    # "supporting file" pattern) — read both so content checks survive the split.
    text = skill_md.read_text()
    ref = skill_md.parent / "reference.md"
    if ref.exists():
        text += "\n" + ref.read_text()
    return text


def test_skill_names_feedback_respond_and_primitives():
    text = _doc(SKILL)
    assert "feedback-respond" in text, "subcommand not documented"
    # Phase 2.1g thin client: the record/apply primitives are called via the
    # workbench API (the feedback_actions compute stays server-side backing
    # these endpoints); open items are read from the study-detail payload.
    assert "/api/feedback-record-action" in text, "record endpoint not referenced"
    assert "/api/feedback-apply-action" in text, "apply endpoint not referenced"
    assert "/api/study/" in text, "open-item read endpoint not referenced"


def test_skill_index_lists_feedback_respond():
    # argument-hints are now compact pointers (token budget — see
    # test_skill_conventions.test_argument_hint_within_budget); the SKILL.md
    # subcommand index is where subcommands are advertised.
    skill_text = SKILL.read_text()
    assert "feedback-respond" in skill_text, (
        "feedback-respond missing from viva-study SKILL.md subcommand index"
    )


def test_skill_documents_ai_free_split_and_no_silent_mutation():
    text = _doc(SKILL)
    # The judgment is the agent's; the primitives are deterministic.
    assert "AI-free" in text or "AI-free split" in text
    # design-edit must never silently mutate design.
    assert "design-edit" in text
    assert "next_action" in text
