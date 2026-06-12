"""Guard: the /pbg-study `migrate-readouts` subcommand + the /pbg-report
canonicalize step stay wired to the readout-migration plumbing (SP2b-ii).

SP2b-ii wires the (manual-only) `readout_migration` into the workflow: the
explicit `/pbg-study migrate-readouts` subcommand auto-canonicalizes the safe
`migratable` readouts via `migrate_study_file(write=True)`, drives the
`needs_human` queue to re-authoring against SP2b-i's `/api/observables`
(`/pbg-study check-observables`), and `/pbg-report` canonicalizes migratable
readouts before rendering. If the skills stop naming these, the wiring is
silently broken and the migration goes back to being orphaned plumbing.
"""
from pathlib import Path

STUDY_SKILL = Path(__file__).resolve().parent.parent / "skills" / "pbg-study" / "SKILL.md"
REPORT_SKILL = Path(__file__).resolve().parent.parent / "skills" / "pbg-report" / "SKILL.md"


def test_pbg_study_documents_migrate_readouts_subcommand():
    text = STUDY_SKILL.read_text(encoding="utf-8")
    assert "migrate-readouts" in text


def test_pbg_study_names_status_and_write_helpers():
    text = STUDY_SKILL.read_text(encoding="utf-8")
    # the pure status classifier + the write helper that does the canonicalize
    assert "readout_migration_status" in text
    assert "migrate_study_file" in text


def test_pbg_study_drives_needs_human_reauthoring_via_check_observables():
    text = STUDY_SKILL.read_text(encoding="utf-8")
    # re-authoring the needs_human queue uses SP2b-i's check-observables +
    # the real emittable set from /api/observables — never guess a selector.
    assert "check-observables" in text
    assert "/api/observables" in text


def test_pbg_report_canonicalizes_migratable_before_render():
    text = REPORT_SKILL.read_text(encoding="utf-8")
    assert "migrate_study_file" in text
    assert "needs_human" in text
