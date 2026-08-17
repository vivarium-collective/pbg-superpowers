"""Guard test for the /viva-audit-tests skill's sourcing near-miss hook.

The skill mirrors its deterministic+LLM split for TEST sufficiency onto the
model-SOURCING decision: it runs the deterministic module_sourcing audit and
adds an LLM near-miss judgment for capability tokens the manifest tags miss.
This asserts that hook is documented and wired to the real audit, so it can't
silently regress to test-only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-audit-tests" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file()


def test_deterministic_sourcing_audit_wired(skill_text):
    # runs the real deterministic sourcing grading
    assert "module_sourcing" in skill_text
    assert "build_sourcing_report" in skill_text
    assert "sourcing_gate" in skill_text


def test_near_miss_judgment_documented(skill_text):
    lowered = skill_text.lower()
    assert "near-miss" in lowered
    # the two failure modes the token match can't see
    assert "missing_capabilities" in skill_text          # semantic fit under a different token
    assert "semantically hollow" in lowered              # exact token match that isn't real
    # a tagging-gap near-miss is a warn (fix the manifest), not a hard fail
    assert "manifest" in lowered and "warn" in lowered


def test_gate_contract_folds_in_sourcing(skill_text):
    # fail path names the sourcing hard axes; the overall gate is the worse of the two
    assert "source_fit" in skill_text and "reinvention" in skill_text
    assert "worse of" in skill_text.lower()


def test_module_sourcing_axes_are_real():
    # the axis IDs the skill names must exist in the deterministic report
    from viva_superpowers import module_sourcing as ms
    catalog = {"m": ["a", "b"]}
    spec = {"name": "t", "requires": ["a"], "sourcing": {"decision": "reuse", "modules": ["m"]}}
    rep = ms.build_sourcing_report(spec, catalog)
    ids = {ax["id"] for g in rep["groups"].values() for ax in g["axes"]}
    assert {"source_fit", "reinvention", "novelty_justified", "survey_recorded"} <= ids
    assert ms.sourcing_gate(rep) in ("pass", "warn", "fail")
