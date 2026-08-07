"""Guard: the /viva-study `migrate-readouts` subcommand + the /viva-report
canonicalize step stay wired to the readout-migration plumbing (SP2b-ii).

SP2b-ii wires the (manual-only) `readout_migration` into the workflow: the
explicit `/viva-study migrate-readouts` subcommand auto-canonicalizes the safe
`migratable` readouts via `migrate_study_file(write=True)`, drives the
`needs_human` queue to re-authoring against SP2b-i's `/api/observables`
(`/viva-study check-observables`), and `/viva-report` canonicalizes migratable
readouts before rendering. If the skills stop naming these, the wiring is
silently broken and the migration goes back to being orphaned plumbing.
"""
from pathlib import Path

STUDY_SKILL = Path(__file__).resolve().parent.parent / "skills" / "viva-study" / "SKILL.md"
REPORT_SKILL = Path(__file__).resolve().parent.parent / "skills" / "viva-report" / "SKILL.md"


def _doc(skill_md: Path) -> str:
    # A skill's documented contract is SKILL.md + its optional reference.md
    # (heavy detail is split into reference.md per the obra "supporting file"
    # pattern). Read both so content-presence checks survive the split.
    text = skill_md.read_text(encoding="utf-8")
    ref = skill_md.parent / "reference.md"
    if ref.exists():
        text += "\n" + ref.read_text(encoding="utf-8")
    return text


def test_pbg_study_documents_migrate_readouts_subcommand():
    text = _doc(STUDY_SKILL)
    assert "migrate-readouts" in text


def test_pbg_study_names_status_and_write_helpers():
    text = _doc(STUDY_SKILL)
    # Phase 2.1g thin client: the migrate-readouts subcommand drives the pure
    # status classifier + the canonicalize write via the workbench API (the
    # readout_migration compute stays server-side backing these endpoints).
    assert "/api/study-readout-migration-status" in text
    assert "/api/study-readout-migrate" in text


def test_pbg_study_drives_needs_human_reauthoring_via_check_observables():
    text = _doc(STUDY_SKILL)
    # re-authoring the needs_human queue uses SP2b-i's check-observables +
    # the real emittable set from /api/observables — never guess a selector.
    assert "check-observables" in text
    assert "/api/observables" in text


def test_pbg_report_canonicalizes_migratable_before_render():
    text = REPORT_SKILL.read_text(encoding="utf-8")
    assert "migrate_study_file" in text
    assert "needs_human" in text
