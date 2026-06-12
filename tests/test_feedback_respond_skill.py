"""Structural guard: the pbg-study skill documents the feedback-respond
subcommand and references the SP3b primitives by name (the AI-free split).
"""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "pbg-study" / "SKILL.md"


def test_skill_names_feedback_respond_and_primitives():
    text = SKILL.read_text()
    assert "feedback-respond" in text, "subcommand not documented"
    assert "study_feedback_actions" in text, "aggregator primitive not referenced"
    assert "apply_feedback_action" in text, "apply primitive not referenced"
    assert "record_feedback_action" in text, "record helper not referenced"


def test_skill_argument_hint_lists_feedback_respond():
    text = SKILL.read_text()
    # The front-matter argument-hint should advertise the new subcommand.
    hint_line = next(
        (ln for ln in text.splitlines() if ln.startswith("argument-hint:")), ""
    )
    assert "feedback-respond" in hint_line, "feedback-respond missing from argument-hint"


def test_skill_documents_ai_free_split_and_no_silent_mutation():
    text = SKILL.read_text()
    # The judgment is the agent's; the primitives are deterministic.
    assert "AI-free" in text or "AI-free split" in text
    # design-edit must never silently mutate design.
    assert "design-edit" in text
    assert "next_action" in text
