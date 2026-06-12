"""SP4a golden: the linkage index/queries on the real v2e-invest workspace.

READ-ONLY. Skipped when v2e-invest is not checked out next to this repo.
Asserts the live gaps + resolutions that motivate SP4a:

- ``chromosome-cycle-calibration`` has 5 acceptance criteria with NO ``study:``
  link → 5 flagged gaps.
- ``dnaa-replication``'s AC matrix resolves every criterion to a study + result.
- ``studies_for_source`` inverts a real bib_key.
- The whole derive is PURE (no writes); v2e-invest is left byte-identical.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pbg_superpowers.linkage_index import (
    build_index,
    ac_gating_matrix,
    studies_for_source,
    study_dag,
)

_V2E = Path("/Users/eranagmon/code/v2e-invest")

pytestmark = pytest.mark.skipif(
    not (_V2E / "workspace.yaml").is_file(),
    reason="v2e-invest workspace not present",
)


def _snapshot(root: Path) -> dict:
    snap: dict = {}
    # Snapshot only the YAML the index reads — cheap + sufficient to prove the
    # derive never writes (the heavy out/*.db artifacts are irrelevant + huge).
    for p in sorted(root.rglob("*.yaml")):
        if p.is_file():
            try:
                snap[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                pass
    return snap


def test_chromosome_cycle_shows_five_unkeyed_ac_gaps():
    m = ac_gating_matrix(_V2E, "chromosome-cycle-calibration")
    assert len(m["criteria"]) == 5
    assert len(m["gaps"]) == 5
    assert all(r["gap"] and not r["covered_by"] for r in m["criteria"])


def test_dnaa_replication_ac_matrix_resolves_studies():
    m = ac_gating_matrix(_V2E, "dnaa-replication")
    assert m["criteria"], "dnaa-replication should have acceptance criteria"
    assert not m["gaps"], "every dnaa-replication criterion should link a study"
    for r in m["criteria"]:
        assert r["covered_by"], f"criterion {r['behavior']} should name a study"
        assert r["result"], f"criterion {r['behavior']} should resolve a result"


def test_studies_for_source_inverts_real_bib_key():
    studies = studies_for_source(_V2E, "dnaa-abundance-jb-1991")
    assert "dnaa-01-expression-dynamics" in studies


def test_study_dag_has_prerequisite_edges():
    dag = study_dag(_V2E, "dnaa-replication")
    assert any(e["from"] and e["to"] for e in dag["edges"])


def test_build_index_pure_on_v2e_invest():
    before = _snapshot(_V2E)
    build_index(_V2E)
    ac_gating_matrix(_V2E, "chromosome-cycle-calibration")
    ac_gating_matrix(_V2E, "dnaa-replication")
    studies_for_source(_V2E, "dnaa-abundance-jb-1991")
    study_dag(_V2E, "dnaa-replication")
    assert _snapshot(_V2E) == before  # v2e-invest untouched
