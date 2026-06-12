"""Tests for pbg_superpowers.needs_attention (SP5 — the "decisions needed" scan).

SP5 is a PURE, deterministic aggregator: it gathers + ranks the divergences/gaps
SP1–SP4 already compute (uncovered ACs, verdict divergence, open feedback, param
drift, stale findings, phantom observables) into one per-investigation ranked
list. It makes NO new judgment and writes NOTHING. Signals 1,2,3,5,6 are
build-free; signal 4 (phantom observable) is opt-in behind an injected
``observables_for_ref``.

Fixture style mirrors tests/test_linkage_index.py.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pbg_superpowers import study_io
from pbg_superpowers.needs_attention import scan_investigation, _stale_findings


# ---------------------------------------------------------------------------
# Workspace builders (mirrors test_linkage_index.py)
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
def tmp_inv_with_unlinked_ac(tmp_path) -> Path:
    """An investigation with one AC keyed to a study and one unlinked (the gap)."""
    root = _ws(tmp_path)
    _inv(root, "inv", {
        "studies": ["s1"],
        "acceptance_criteria": [
            {"study": "s1", "behavior": "covered-behavior"},
            {"behavior": "uncovered-behavior", "status": "failed"},  # gap
        ],
    })
    _study(root, "s1", {"tests": [{"name": "covered-behavior"}]}, inv="inv")
    return root


@pytest.fixture
def tmp_inv_with_open_feedback(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "inv", {"studies": ["s1"]})
    _study(root, "s1", {"tests": [{"name": "t"}]}, inv="inv")
    # Feedback annotation under investigations/<inv>/feedback*.yaml; no actions →
    # status == "open".
    _write(root / "investigations" / "inv" / "feedback" / "001.yaml", {
        "meta": {"report_id": "r1"},
        "annotations": {
            "study-s1": [
                {"ts": "2026-06-12T00:00:00", "author": "expert",
                 "text": "Please re-check the translation efficiency."},
            ],
        },
    })
    return root


@pytest.fixture
def tmp_inv_study_diverges(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "inv", {"studies": ["s1"]})
    _study(root, "s1", {
        "tests": [{"name": "t"}],
        "pipeline_gate": {
            "gate_evaluator": {"diverges_from_authored": True},
        },
    }, inv="inv")
    return root


@pytest.fixture
def tmp_study_findings(tmp_path) -> dict:
    return {
        "findings": [
            {"id": "F-01", "status": "novel",
             "next_action": "seed a follow-up study"},          # next_action, no seed
            {"id": "F-02", "status": "contradicts"},             # neither
            {"id": "F-03", "status": "novel",
             "next_action": "seed it", "seeded_study": "s2"},    # both → not stale
            {"id": "F-04", "status": "seeded",
             "seeded_study": "s9"},                              # terminal → excluded
        ],
    }


@pytest.fixture
def tmp_inv_run_param_drift(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "inv", {"studies": ["s1"]})
    _study(root, "s1", {
        "enforced_params": {"translation_efficiency": 1, "mrna_per_min": 1.5},
        "runs": [
            {"name": "r1", "status": "completed",
             "params": {"translation_efficiency": 20}},  # mismatch + missing mrna
        ],
    }, inv="inv")
    return root


@pytest.fixture
def tmp_inv_with_phantom_readout(tmp_path) -> Path:
    root = _ws(tmp_path)
    _inv(root, "inv", {"studies": ["s1"]})
    _study(root, "s1", {
        "conditions": {
            "baseline": {"name": "base", "composite": "comp-1"},
        },
        "readouts": [
            {"name": "phantom", "identifier": "agents.0.listeners.does_not_exist"},
        ],
    }, inv="inv")
    return root


@pytest.fixture
def tmp_inv_mixed(tmp_path) -> Path:
    """Mixed-severity investigation: an uncovered AC (high), open feedback
    (medium), a stale finding (low)."""
    root = _ws(tmp_path)
    _inv(root, "inv", {
        "studies": ["s1"],
        "acceptance_criteria": [
            {"behavior": "uncovered-behavior"},  # high gap
        ],
    })
    _study(root, "s1", {
        "tests": [{"name": "t"}],
        "findings": [{"id": "F-01", "status": "novel"}],  # low stale
    }, inv="inv")
    _write(root / "investigations" / "inv" / "feedback" / "001.yaml", {
        "annotations": {
            "study-s1": [
                {"ts": "2026-06-12T00:00:00", "author": "expert", "text": "open item"},
            ],
        },
    })
    return root


def _stub_obs(ref):  # composite emits only one leaf; readout references a phantom
    return {"leaves": ["agents.0.listeners.mass.cell_mass"], "catalogs": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_uncovered_ac_surfaces_high(tmp_inv_with_unlinked_ac):
    res = scan_investigation(tmp_inv_with_unlinked_ac, "inv")
    acs = [i for i in res["items"] if i["kind"] == "uncovered_ac"]
    assert acs and acs[0]["severity"] == "high"
    assert acs[0]["ref"] == "uncovered-behavior"
    assert acs[0]["study"] is None


def test_open_feedback_surfaces_medium(tmp_inv_with_open_feedback):
    res = scan_investigation(tmp_inv_with_open_feedback, "inv")
    assert any(i["kind"] == "open_feedback" and i["severity"] == "medium"
               and i["study"] == "s1" for i in res["items"])


def test_verdict_divergence_read_from_persisted_flag(tmp_inv_study_diverges):
    res = scan_investigation(tmp_inv_study_diverges, "inv")
    assert any(i["kind"] == "verdict_divergence" and i["study"] == "s1"
               and i["severity"] == "high" for i in res["items"])


def test_stale_finding_classifier(tmp_study_findings):
    stale = {f["id"] for f in _stale_findings(tmp_study_findings)}
    assert stale == {"F-01", "F-02"}


def test_param_drift_surfaces_when_run_violates(tmp_inv_run_param_drift):
    res = scan_investigation(tmp_inv_run_param_drift, "inv")
    drifts = [i for i in res["items"]
              if i["kind"] == "param_drift" and i["severity"] == "high"]
    assert drifts
    assert {d["ref"] for d in drifts} == {"translation_efficiency", "mrna_per_min"}


def test_scan_is_pure_no_writes(tmp_inv_with_unlinked_ac):
    before = _snapshot(tmp_inv_with_unlinked_ac)
    scan_investigation(tmp_inv_with_unlinked_ac, "inv")
    assert _snapshot(tmp_inv_with_unlinked_ac) == before


def test_scan_build_free_by_default_omits_phantom(tmp_inv_with_phantom_readout):
    res = scan_investigation(tmp_inv_with_phantom_readout, "inv")
    assert not any(i["kind"] == "phantom_observable" for i in res["items"])


def test_phantom_observable_opt_in(tmp_inv_with_phantom_readout):
    res = scan_investigation(tmp_inv_with_phantom_readout, "inv",
                             observables_for_ref=_stub_obs)
    assert any(i["kind"] == "phantom_observable" and i["severity"] == "high"
               and i["ref"] == "phantom" for i in res["items"])


def test_phantom_build_raise_is_tolerated(tmp_inv_with_phantom_readout):
    def _boom(ref):
        raise RuntimeError("composite build failed")
    res = scan_investigation(tmp_inv_with_phantom_readout, "inv",
                             observables_for_ref=_boom)
    # A build that raises skips that study; the scan still returns.
    assert not any(i["kind"] == "phantom_observable" for i in res["items"])


def test_summary_ranks_by_severity(tmp_inv_mixed):
    res = scan_investigation(tmp_inv_mixed, "inv")
    sev = [i["severity"] for i in res["items"]]
    assert sev == sorted(sev, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])
    assert res["summary"]["by_severity"]["high"] >= 1
    assert res["summary"]["total"] == len(res["items"])
    assert set(res["summary"]["by_kind"]) <= {
        "uncovered_ac", "verdict_divergence", "open_feedback",
        "param_drift", "stale_finding", "phantom_observable"}


def test_investigation_slug_echoed(tmp_inv_with_unlinked_ac):
    res = scan_investigation(tmp_inv_with_unlinked_ac, "inv")
    assert res["investigation"] == "inv"


# ---------------------------------------------------------------------------
# Golden — read-only scan over the real v2e-invest workspace (skips if absent).
# ---------------------------------------------------------------------------

_V2E_INVEST = Path("/Users/eranagmon/code/v2e-invest")


def _real_investigation_slugs() -> list[str]:
    inv_root = _V2E_INVEST / "investigations"
    if not inv_root.is_dir():
        return []
    return sorted(
        p.name for p in inv_root.iterdir()
        if p.is_dir() and (p / "investigation.yaml").is_file()
    )


@pytest.mark.skipif(not _V2E_INVEST.is_dir(),
                    reason="v2e-invest workspace not present")
def test_golden_scan_real_investigation_read_only():
    slugs = _real_investigation_slugs()
    if not slugs:
        pytest.skip("no real investigations under v2e-invest")

    # Prefer the chromosome-cycle-calibration investigation (the known SP4a
    # live gap — 5 unlinked ACs) when present, else any real slug.
    slug = ("chromosome-cycle-calibration"
            if "chromosome-cycle-calibration" in slugs else slugs[0])

    before = _snapshot(_V2E_INVEST)
    res = scan_investigation(_V2E_INVEST, slug)
    assert _snapshot(_V2E_INVEST) == before, "scan must not write to v2e-invest"

    assert res["investigation"] == slug
    assert "items" in res and "summary" in res
    assert res["summary"]["total"] == len(res["items"])

    if slug == "chromosome-cycle-calibration":
        # The known SP4a live gap: its acceptance criteria have no study link.
        acs = [i for i in res["items"]
               if i["kind"] == "uncovered_ac" and i["severity"] == "high"]
        assert acs, "expected uncovered-AC high items for the SP4a live gap"
