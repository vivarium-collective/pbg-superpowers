"""Guard: the /pbg-study `check-observables` subcommand wires in the
never-fabricate observable guard.

SP2b-i wires the (otherwise orphaned) `readout_validation` into a live path.
If the skill stops naming the validation endpoints or the never-fabricate
status, the guard silently stops guiding re-authoring and agents can author
phantom observables again. Keep the wiring named in SKILL.md.
"""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "pbg-study" / "SKILL.md"


def test_skill_documents_check_observables_subcommand():
    text = SKILL.read_text(encoding="utf-8")
    assert "check-observables" in text


def test_skill_mentions_validation_endpoints():
    text = SKILL.read_text(encoding="utf-8")
    assert "study-observable-check" in text
    assert "/api/observables" in text


def test_skill_mentions_never_fabricate_status():
    text = SKILL.read_text(encoding="utf-8")
    assert "not_in_structure" in text
