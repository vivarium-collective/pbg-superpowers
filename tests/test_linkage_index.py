"""Tests for pbg_superpowers.linkage_index (SP4a).

The linkage index is a derived, EPHEMERAL knowledge graph over the workspace
YAML — studies ↔ composites ↔ observables ↔ sources ↔ findings ↔ acceptance ↔
study-DAG — plus the cheap reverse queries that today need grep. Pure derive,
no writes.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pbg_superpowers import study_io
from pbg_superpowers.linkage_index import (
    build_index,
    ac_gating_matrix,
    studies_for_source,
    findings_for_observable,
    study_dag,
)


# ---------------------------------------------------------------------------
# Workspace builders
# ---------------------------------------------------------------------------

def _write(path: Path, spec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    study_io.save_yaml_atomic(path, spec)


def _ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "workspace.yaml", {"name": "ws", "package_path": "pbg_ws"})
    return root


def _inv(root: Path, slug: str, spec: dict) -> None:
    spec = {"name": slug, **spec}
    _write(root / "investigations" / slug / "investigation.yaml", spec)


def _study(root: Path, slug: str, spec: dict, inv: str | None = None) -> None:
    spec = {"name": slug, **spec}
    if inv:
        spec.setdefault("investigation", inv)
    _write(root / "studies" / slug / "study.yaml", spec)


def _snapshot(root: Path) -> dict:
    snap: dict = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_inv_mixed_ac(tmp_path) -> Path:
    """One investigation: one AC keyed to a study (with a result), one AC with
    NO study: link (the gap)."""
    root = _ws(tmp_path)
    _inv(root, "the-inv", {
        "studies": ["s1"],
        "acceptance_criteria": [
            {"study": "s1", "behavior": "b1"},     # keyed
            {"behavior": "b2", "status": "failed"},  # unkeyed → gap
        ],
    })
    _study(root, "s1", {
        "tests": [{"name": "b1"}],
        "runs": [{"name": "r1", "status": "completed",
                  "outcomes": {"b1": {"result": "PASS"}}}],
    }, inv="the-inv")
    return root


@pytest.fixture
def tmp_ws_two_studies_cite_X(tmp_path) -> Path:
    root = _ws(tmp_path)
    _study(root, "s1", {"cites": ["bib-key-X", "other"]})
    _study(root, "s2", {
        "tests": [{"name": "t", "cites": ["bib-key-X"]}],
    })
    _study(root, "s3", {"cites": ["unrelated"]})
    return root


@pytest.fixture
def tmp_ws_finding_measures_obs(tmp_path) -> Path:
    root = _ws(tmp_path)
    _study(root, "s1", {
        "tests": [{
            "name": "mass-test",
            "measure": {"path": "listeners.mass.cell_mass"},
        }],
        "findings": [{
            "id": "F-01",
            "evidence": {"from_test": "mass-test"},
        }],
    })
    return root


@pytest.fixture
def tmp_ws_dag(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "the-inv", {"studies": ["a", "b"]})
    _study(root, "a", {"pipeline_gate": {"prerequisites": [], "enables": ["b"]}},
           inv="the-inv")
    _study(root, "b", {"pipeline_gate": {"prerequisites": ["a"], "enables": []}},
           inv="the-inv")
    return root


@pytest.fixture
def tmp_ws(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "the-inv", {
        "studies": ["s1"],
        "acceptance_criteria": [{"study": "s1", "behavior": "b1"}],
        "references": [{"path": "paper.pdf"}],
    })
    _study(root, "s1", {
        "cites": ["k1"],
        "tests": [{"name": "b1", "measure": {"path": "x.y"}}],
        "readouts": [{"name": "ro", "identifier": "x.y"}],
        "findings": [{"id": "F", "evidence": {"from_test": "b1"}}],
        "conditions": {"baseline": {"composite": "base"}},
        "pipeline_gate": {"prerequisites": [], "enables": []},
    }, inv="the-inv")
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ac_gating_matrix_flags_unkeyed_criteria(tmp_inv_mixed_ac):
    m = ac_gating_matrix(tmp_inv_mixed_ac, "the-inv")
    assert any(r["covered_by"] for r in m["criteria"])  # keyed AC → a study
    assert any(r["gap"] is True and not r["covered_by"] for r in m["criteria"])


def test_studies_for_source_inverts_cites(tmp_ws_two_studies_cite_X):
    assert set(studies_for_source(tmp_ws_two_studies_cite_X, "bib-key-X")) == {"s1", "s2"}


def test_findings_for_observable(tmp_ws_finding_measures_obs):
    found = findings_for_observable(tmp_ws_finding_measures_obs, "listeners.mass.cell_mass")
    assert "F-01" in [f["finding"] for f in found]


def test_study_dag_edges(tmp_ws_dag):
    dag = study_dag(tmp_ws_dag, "the-inv")
    assert any(e["from"] and e["to"] for e in dag["edges"])


def test_build_index_shape(tmp_ws):
    idx = build_index(tmp_ws)
    assert "nodes" in idx and "edges" in idx
    types = {n["type"] for n in idx["nodes"]}
    assert {"study", "composite", "observable", "source"} <= types


def test_build_index_pure_read(tmp_ws):
    before = _snapshot(tmp_ws)
    build_index(tmp_ws)
    ac_gating_matrix(tmp_ws, "the-inv")
    studies_for_source(tmp_ws, "k1")
    findings_for_observable(tmp_ws, "x.y")
    study_dag(tmp_ws, "the-inv")
    assert _snapshot(tmp_ws) == before  # no writes
