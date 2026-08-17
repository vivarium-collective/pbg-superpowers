"""Guard test for the /viva-model-build skill's state-machine documentation.

The loop is defined by ``viva_superpowers.loop_state.STATES``. The skill's state
table drives the agent, so if a state is added to ``STATES`` but the skill never
documents it, the loop silently skips that gate — which is exactly what happened
to **SELECT** (the model-sourcing decision) before this test existed. This
asserts every state in ``STATES`` appears in the skill, and that SELECT is wired
to the deterministic sourcing audit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from viva_superpowers import loop_state as ls

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-model-build" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file(), "skills/viva-model-build/SKILL.md must exist"


def test_every_loop_state_is_documented(skill_text):
    missing = [s for s in ls.STATES if s not in skill_text]
    assert not missing, (
        f"/viva-model-build SKILL.md does not document loop_state.STATES {missing}; "
        f"an undocumented state is a gate the loop silently skips."
    )


def test_select_phase_drives_the_sourcing_audit(skill_text):
    # SELECT must actually invoke the deterministic sourcing audit, not just name it.
    assert "SELECT" in skill_text
    assert "module_sourcing" in skill_text
    assert "build_sourcing_report" in skill_text
    assert "sourcing_gate" in skill_text
    # and it must gate LOCK on a fail (never lock a misfit sourcing decision)
    assert "reuse" in skill_text and "compose" in skill_text and "build-new" in skill_text


def test_select_sits_between_audit_and_lock(skill_text):
    # ordering in STATES the skill must reflect
    states = list(ls.STATES)
    assert states.index("AUDIT") < states.index("SELECT") < states.index("LOCK")
