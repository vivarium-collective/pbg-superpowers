"""Guard: the /viva-study `check-observables` subcommand wires in the
never-fabricate observable guard.

SP2b-i wires the (otherwise orphaned) `readout_validation` into a live path.
If the skill stops naming the validation endpoints or the never-fabricate
status, the guard silently stops guiding re-authoring and agents can author
phantom observables again. Keep the wiring named in SKILL.md.
"""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "viva-study" / "SKILL.md"


def _doc(skill_md: Path) -> str:
    # SKILL.md + optional reference.md (heavy detail is split out per the obra
    # "supporting file" pattern) — read both so content checks survive the split.
    text = skill_md.read_text(encoding="utf-8")
    ref = skill_md.parent / "reference.md"
    if ref.exists():
        text += "\n" + ref.read_text(encoding="utf-8")
    return text


def test_skill_documents_check_observables_subcommand():
    text = _doc(SKILL)
    assert "check-observables" in text


def test_skill_mentions_validation_endpoints():
    text = _doc(SKILL)
    assert "study-observable-check" in text
    assert "/api/observables" in text


def test_skill_mentions_never_fabricate_status():
    text = _doc(SKILL)
    assert "not_in_structure" in text
