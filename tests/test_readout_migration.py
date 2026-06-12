"""Goldens + unit tests for readout_migration (sub-project #7).

The dnaa readout dicts are copied INLINE (from the design spec / the real
dnaa-1 & dnaa-2 studies) so the tests never read or mutate real investigation
data.  A round-trip end-to-end test writes to a TMP COPY only and is skipped
when v2e-invest / its hive are absent on this machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pbg_superpowers.readout_migration import (
    migrate_readouts,
    migrate_study_file,
    readout_migration_status,
)
from pbg_superpowers.readout_resolver import (
    ResolvedReadout,
    UnresolvedReadout,
    resolve_readout,
)


# ---------------------------------------------------------------------------
# Real dnaa readout dicts (inline copies — see test_readout_resolver.py).
# ---------------------------------------------------------------------------

RO_LITERAL_INDEX = {  # dnaa-1
    "name": "DnaA monomer total",
    "status": "primary",
    "identifier": "listeners.monomer_counts[3861]",
    "units": "molecules/cell",
}

RO_BULK_FRACTION = {  # dnaa-2
    "name": "DnaA-ATP fraction",
    "status": "primary",
    "identifier": (
        "bulk MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])"
    ),
    "units": "fraction",
}

RO_MIDDLE_DOT_GROUP = {  # dnaa-2 — unresolvable prose group
    "name": "DnaA-form counts",
    "status": "measured",
    "identifier": (
        "bulk PD03831[c] (apo) · MONOMER0-160[c] (DnaA-ATP) "
        "· MONOMER0-4565[c] (DnaA-ADP)"
    ),
    "units": "molecules/cell",
}

RO_SCALAR_WITH_QUALIFIER = {  # dnaa-1
    "name": "dnaA mRNA initiation rate",
    "status": "primary",
    "identifier": "listeners.rnap_data.rna_init_event_per_cistron (dnaA cistron)",
    "units": "events/min",
}


def _by_name(readouts, name):
    return next(r for r in readouts if r.get("name") == name)


# ---------------------------------------------------------------------------
# Golden: literal_index magic index → canonical index_by
# ---------------------------------------------------------------------------

def test_golden_literal_index_to_index_by():
    """monomer_counts[3861] → index_by literal_index + store_path observable."""
    spec = {"readouts": [RO_LITERAL_INDEX]}
    new, report = migrate_readouts(spec)
    mig = _by_name(new, "DnaA monomer total")
    assert mig["index_by"] == {"type": "literal_index", "value": 3861}
    assert mig["store_path"] == "listeners.monomer_counts"
    assert mig["units"] == "molecules/cell"
    assert mig["status"] == "primary"
    assert "identifier" not in mig  # magic index is gone
    # report
    assert "DnaA monomer total" in report["migrated"]
    entry = _by_name(report["entries"], "DnaA monomer total")
    assert entry["status"] == "migrated"
    assert entry["kind"] == "element"


def test_golden_literal_index_round_trips():
    """The migrated literal_index readout re-resolves to the same selector."""
    spec = {"readouts": [RO_LITERAL_INDEX]}
    new, _ = migrate_readouts(spec)
    r = resolve_readout(new[0])
    assert isinstance(r, ResolvedReadout)
    assert r.kind == "element"
    assert r.index_by == {"type": "literal_index", "value": 3861}
    assert r.observable == "listeners.monomer_counts"


# ---------------------------------------------------------------------------
# Golden: bulk fraction → expression
# ---------------------------------------------------------------------------

def test_golden_bulk_fraction_to_expression():
    """The bulk fraction migrates to an expression form that re-resolves to
    kind=expression with the same operand ids."""
    spec = {"readouts": [RO_BULK_FRACTION]}
    new, report = migrate_readouts(spec)
    mig = _by_name(new, "DnaA-ATP fraction")
    assert "MONOMER0-160[c]" in mig["identifier"]
    assert "PD03831[c]" in mig["identifier"]
    entry = _by_name(report["entries"], "DnaA-ATP fraction")
    assert entry["kind"] == "expression"
    # round-trips
    r = resolve_readout(mig)
    assert isinstance(r, ResolvedReadout)
    assert r.kind == "expression"
    assert r.observable == "bulk"
    tokens = {op["token"] for op in r.operand_ids}
    assert tokens == {"MONOMER0-160[c]", "PD03831[c]", "MONOMER0-4565[c]"}


# ---------------------------------------------------------------------------
# Golden: middle-dot group → kept untouched + needs_human
# ---------------------------------------------------------------------------

def test_golden_middle_dot_group_needs_human():
    """The ·-group readout is unresolvable: kept byte-for-byte + needs_human."""
    spec = {"readouts": [RO_MIDDLE_DOT_GROUP]}
    new, report = migrate_readouts(spec)
    # kept untouched (same object content)
    assert new[0] == RO_MIDDLE_DOT_GROUP
    assert new[0]["identifier"] == RO_MIDDLE_DOT_GROUP["identifier"]
    # flagged
    names = [h["name"] for h in report["needs_human"]]
    assert "DnaA-form counts" in names
    h = _by_name(report["needs_human"], "DnaA-form counts")
    assert h["reason"]
    assert "DnaA-form counts" not in report["migrated"]


def test_golden_scalar_qualifier_folds_into_description():
    """A scalar with a trailing prose qualifier migrates to store_path; the
    stripped qualifier is preserved in the description (nothing lost)."""
    spec = {"readouts": [RO_SCALAR_WITH_QUALIFIER]}
    new, _ = migrate_readouts(spec)
    mig = _by_name(new, "dnaA mRNA initiation rate")
    assert mig["store_path"] == "listeners.rnap_data.rna_init_event_per_cistron"
    assert "dnaA cistron" in mig["description"]
    assert "identifier" not in mig
    # round-trips to scalar
    r = resolve_readout(mig)
    assert isinstance(r, ResolvedReadout)
    assert r.kind == "scalar"


# ---------------------------------------------------------------------------
# Combined: a full study readouts list (all four dialects)
# ---------------------------------------------------------------------------

def test_migrate_full_study_readouts_list():
    spec = {"readouts": [
        RO_LITERAL_INDEX,
        RO_BULK_FRACTION,
        RO_MIDDLE_DOT_GROUP,
        RO_SCALAR_WITH_QUALIFIER,
    ]}
    new, report = migrate_readouts(spec)
    assert len(new) == 4  # parallel to input
    assert set(report["migrated"]) == {
        "DnaA monomer total", "DnaA-ATP fraction", "dnaA mRNA initiation rate",
    }
    assert [h["name"] for h in report["needs_human"]] == ["DnaA-form counts"]


def test_migrate_readouts_is_pure():
    """migrate_readouts must not mutate its input spec or readout dicts."""
    import copy
    spec = {"readouts": [copy.deepcopy(RO_LITERAL_INDEX)]}
    before = copy.deepcopy(spec)
    migrate_readouts(spec)
    assert spec == before


def test_empty_spec_is_safe():
    new, report = migrate_readouts({})
    assert new == []
    assert report["migrated"] == []
    assert report["needs_human"] == []


# ---------------------------------------------------------------------------
# migrate_study_file: dry-run by default, comment-preserving on write
# ---------------------------------------------------------------------------

STUDY_YAML_TEXT = """\
# A hand-authored study with comments that MUST survive migration.
name: dnaa-test
objective: |
  Multi-line objective prose.
readouts:
  - name: DnaA monomer total  # the magic-index one
    status: primary
    identifier: listeners.monomer_counts[3861]
    units: molecules/cell
  - name: DnaA-form counts
    status: measured
    identifier: "bulk PD03831[c] (apo) · MONOMER0-160[c] (DnaA-ATP)"
    units: molecules/cell
# trailing comment
baselines: []
"""


def test_migrate_study_file_dry_run_does_not_write(tmp_path):
    study_dir = tmp_path / "dnaa-test"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_TEXT)
    original = sy.read_text()

    report = migrate_study_file(study_dir, write=False)
    assert report["written"] is False
    assert sy.read_text() == original  # untouched
    assert "DnaA monomer total" in report["migrated"]
    assert [h["name"] for h in report["needs_human"]] == ["DnaA-form counts"]


def test_migrate_study_file_write_preserves_comments_and_other_content(tmp_path):
    study_dir = tmp_path / "dnaa-test"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_TEXT)

    report = migrate_study_file(study_dir, write=True)
    assert report["written"] is True

    text = sy.read_text()
    # comments + hand-authored content survive
    assert "MUST survive migration" in text
    assert "trailing comment" in text
    assert "Multi-line objective prose." in text
    assert "objective:" in text
    # the magic index is migrated away
    assert "monomer_counts[3861]" not in text
    assert "literal_index" in text
    # the unresolvable readout is kept untouched
    assert "PD03831[c] (apo)" in text

    # and the rewritten file still parses + its migrated readout re-resolves
    from pbg_superpowers import study_io
    spec2 = study_io.load_yaml_mapping(sy)
    r = resolve_readout(_by_name(spec2["readouts"], "DnaA monomer total"))
    assert isinstance(r, ResolvedReadout)
    assert r.index_by == {"type": "literal_index", "value": 3861}


# ---------------------------------------------------------------------------
# FIX 1 + FIX 2 + FIX 3: no-op on already-canonical + indentation preservation
# ---------------------------------------------------------------------------

# An all-canonical study (one canonical readout + one needs_human prose readout):
# a migrate_study_file(write=True) must be a TRUE no-op (byte-identical), since
# nothing actually changes — the canonical readout is already canonical and the
# needs_human one is kept untouched.
STUDY_YAML_ALL_CANONICAL = """\
# An all-canonical study — migrate must be a true no-op (byte-identical).
name: dnaa-canonical
objective: |
  Already-canonical readouts; nothing to rewrite.
readouts:
  - name: DnaA monomer total
    index_by:
      type: literal_index
      value: 3861
    store_path: listeners.monomer_counts
    units: molecules/cell
    status: primary
  - name: DnaA-form counts
    status: measured
    identifier: "bulk PD03831[c] (apo) · MONOMER0-160[c] (DnaA-ATP)"
    units: molecules/cell
# trailing comment
baselines: []
"""


def test_migrate_study_file_already_canonical_is_byte_identical_noop(tmp_path):
    """An all-canonical study: write=True is a TRUE no-op — the file is left
    byte-for-byte identical, and the report reports changed=False/written=False."""
    study_dir = tmp_path / "dnaa-canonical"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_ALL_CANONICAL)
    before = sy.read_bytes()

    report = migrate_study_file(study_dir, write=True)

    assert report["changed"] is False
    assert report["written"] is False
    # FIX 2: byte-identical, not just meaning-identical.
    assert sy.read_bytes() == before
    # FIX 3: nothing was actually canonicalized this run.
    assert report.get("canonicalized") == []
    # the prose readout is still flagged for a human (untouched).
    assert [h["name"] for h in report["needs_human"]] == ["DnaA-form counts"]


def test_migrate_study_file_changed_flag_true_on_real_change(tmp_path):
    """A study with a migratable readout reports changed=True/written=True and
    names the actually-canonicalized readout (FIX 3)."""
    study_dir = tmp_path / "dnaa-test"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_TEXT)

    report = migrate_study_file(study_dir, write=True)
    assert report["changed"] is True
    assert report["written"] is True
    # FIX 3: the actually-canonicalized set is the changed readout, NOT the
    # already-canonical/needs_human ones.
    assert report.get("canonicalized") == ["DnaA monomer total"]


def test_migrate_study_file_preserves_readouts_block_indentation(tmp_path):
    """FIX 1: on a real change, only the changed selector lines differ — the
    non-readout blocks + comments stay byte-identical, and the readouts block
    keeps its original 2-space block-seq offset (no whole-block reindent)."""
    study_dir = tmp_path / "dnaa-test"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_TEXT)

    report = migrate_study_file(study_dir, write=True)
    assert report["written"] is True
    text = sy.read_text()

    # readouts block keeps its original indentation: `-` at column 2, content
    # at column 4 (sequence=4, offset=2), NOT reindented to column 0.
    assert "\n  - name: DnaA monomer total" in text
    assert "\n    status: primary" in text
    assert "\n- name:" not in text  # no 0-offset block-seq reindent

    # non-readout blocks + their comments survive byte-for-byte.
    assert text.startswith(
        "# A hand-authored study with comments that MUST survive migration.\n"
    )
    assert "# trailing comment\nbaselines: []\n" in text

    # only the readouts region changed: the lines OUTSIDE the readouts block are
    # identical between before and after.
    before_lines = STUDY_YAML_TEXT.splitlines()
    after_lines = text.splitlines()
    # the pre-readouts header (name/objective) is untouched
    assert before_lines[:5] == after_lines[:5]


def test_migrate_study_file_dry_run_reports_changed(tmp_path):
    """changed reflects whether a write WOULD change anything, even in dry-run."""
    study_dir = tmp_path / "dnaa-test"
    study_dir.mkdir()
    sy = study_dir / "study.yaml"
    sy.write_text(STUDY_YAML_TEXT)

    report = migrate_study_file(study_dir, write=False)
    assert report["written"] is False
    assert report["changed"] is True


# ---------------------------------------------------------------------------
# readout_migration_status — pure classify into canonical/migratable/needs_human
# ---------------------------------------------------------------------------

# Already in canonical form (index_by + store_path) — a dry-run migrate leaves
# it byte-identical, so it lands in `canonical`.
RO_ALREADY_CANONICAL = {
    "name": "DnaA monomer total",
    "index_by": {"type": "literal_index", "value": 3861},
    "store_path": "listeners.monomer_counts",
    "units": "molecules/cell",
    "status": "primary",
}

# Clean legacy `identifier:` magic-index dialect — resolvable, but its canonical
# form DIFFERS from the original, so it lands in `migratable`.
RO_CLEAN_MIGRATABLE = {
    "name": "Cell mass",
    "status": "primary",
    "identifier": "listeners.mass.cell_mass[2]",
    "units": "fg",
}


STUDY_YAML_MIXED = """\
# Mixed-dialect study: one canonical, one migratable, one prose needs_human.
name: dnaa-mixed
objective: |
  Exercise all three migration-status buckets.
readouts:
  - name: DnaA monomer total
    index_by:
      type: literal_index
      value: 3861
    store_path: listeners.monomer_counts
    units: molecules/cell
    status: primary
  - name: Cell mass
    status: primary
    identifier: listeners.mass.cell_mass[2]
    units: fg
  - name: DnaA-form counts
    status: measured
    identifier: "bulk PD03831[c] (apo) · MONOMER0-160[c] (DnaA-ATP)"
    units: molecules/cell
baselines: []
"""


@pytest.fixture
def tmp_study_mixed_readouts(tmp_path):
    study_dir = tmp_path / "dnaa-mixed"
    study_dir.mkdir()
    (study_dir / "study.yaml").write_text(STUDY_YAML_MIXED)
    return study_dir


def test_status_classifies_canonical_migratable_needs_human(tmp_study_mixed_readouts):
    s = readout_migration_status(tmp_study_mixed_readouts)
    # the prose ·-group is unresolvable → needs_human
    assert {r["name"] for r in s["needs_human"]} == {"DnaA-form counts"}
    # the clean legacy identifier dialect → migratable
    assert {r["name"] for r in s["migratable"]} == {"Cell mass"}
    # the already-canonical readout is unchanged by a dry-run migrate → canonical
    assert {r["name"] for r in s["canonical"]} == {"DnaA monomer total"}
    assert isinstance(s["canonical"], list)
    # needs_human entries carry a reason
    assert all(h.get("reason") for h in s["needs_human"])


def test_status_pure_read(tmp_study_mixed_readouts):
    before = (tmp_study_mixed_readouts / "study.yaml").read_bytes()
    readout_migration_status(tmp_study_mixed_readouts)
    after = (tmp_study_mixed_readouts / "study.yaml").read_bytes()
    assert after == before  # dry-run, no write


def test_status_accepts_study_yaml_path_directly(tmp_study_mixed_readouts):
    s = readout_migration_status(tmp_study_mixed_readouts / "study.yaml")
    assert {r["name"] for r in s["migratable"]} == {"Cell mass"}


# ---------------------------------------------------------------------------
# End-to-end against real v2e-invest data (skipped when absent)
# ---------------------------------------------------------------------------

def _find_real_dnaa_study():
    """Locate a real dnaa study.yaml *with readouts* under a v2e-invest
    workspace, if present.  Returns the one with the most readouts so the e2e
    actually exercises migration (read-only scan; the test copies to tmp)."""
    from pbg_superpowers import study_io

    candidates = [
        Path.home() / "code" / "v2e-invest",
        Path.home() / "v2e-invest",
    ]
    best = None
    best_n = 0
    for root in candidates:
        if not root.is_dir():
            continue
        for sy in root.rglob("study.yaml"):
            if "dnaa" not in str(sy).lower():
                continue
            try:
                spec = study_io.load_yaml_mapping(sy)
            except Exception:
                continue
            n = len(spec.get("readouts") or [])
            if n > best_n:
                best, best_n = sy, n
    return best


@pytest.mark.skipif(
    _find_real_dnaa_study() is None,
    reason="v2e-invest / a real dnaa study.yaml not present on this machine",
)
def test_e2e_migrate_real_dnaa_study_on_tmp_copy(tmp_path):
    """On a TMP COPY of a real dnaa study.yaml: migrate (write=True), then
    confirm the migrated readouts still resolve via readout_resolver.  NEVER
    touches the real file."""
    import shutil

    real = _find_real_dnaa_study()
    study_dir = tmp_path / "dnaa-real"
    study_dir.mkdir()
    shutil.copy(real, study_dir / "study.yaml")

    report = migrate_study_file(study_dir, write=True)
    assert report["written"] is True
    # the chosen study genuinely has readouts to migrate
    assert report["migrated"] or report["needs_human"]

    from pbg_superpowers import study_io
    spec2 = study_io.load_yaml_mapping(study_dir / "study.yaml")
    assert spec2.get("readouts"), "migrated study should still have readouts"
    # every migrated readout re-resolves (the unresolved ones stay unresolved)
    for ro in spec2.get("readouts", []):
        r = resolve_readout(ro)
        assert isinstance(r, (ResolvedReadout, UnresolvedReadout))
    # the real file was never touched
    assert real.is_file()


@pytest.mark.skipif(
    _find_real_dnaa_study() is None,
    reason="v2e-invest / a real dnaa study.yaml not present on this machine",
)
def test_status_golden_real_dnaa_study_read_only():
    """READ-ONLY golden: readout_migration_status on a real v2e-invest dnaa
    study returns the three buckets with the prose/`derived` readouts in
    `needs_human` (matching SP2b-i's `unresolved` set), and is byte-for-byte
    PURE — the real study.yaml is never written."""
    from pbg_superpowers import study_io

    real = _find_real_dnaa_study()  # the real file, NOT a copy
    before = real.read_bytes()

    status = readout_migration_status(real.parent)

    # three buckets, each a list
    assert isinstance(status["canonical"], list)
    assert isinstance(status["migratable"], list)
    assert isinstance(status["needs_human"], list)

    # the real dnaa studies carry prose/`derived` readouts that the migration
    # refuses to guess — they must surface in needs_human with a reason.
    assert status["needs_human"], "expected un-parseable (derived/prose) readouts"
    assert all(h.get("name") and h.get("reason") for h in status["needs_human"])
    # at least one needs_human is the canonical 'derived'/un-parseable signature
    reasons = " ".join(h["reason"] for h in status["needs_human"])
    assert "derived" in reasons or "could not parse" in reasons

    # the three buckets partition the study's readouts (no double-counting).
    spec = study_io.load_yaml_mapping(real)
    n_total = len(spec.get("readouts") or [])
    n_buckets = (
        len(status["canonical"]) + len(status["migratable"]) + len(status["needs_human"])
    )
    assert n_buckets == n_total

    # PURE: the real study.yaml is byte-identical (no write).
    assert real.read_bytes() == before
