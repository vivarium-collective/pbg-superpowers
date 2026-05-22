"""Tests for pbg_superpowers.study_status (derive-on-read status, friction #2)."""
from pbg_superpowers.study_status import (
    derive_simulation_status, derive_evaluation_status,
    derive_status, status_disagreements,
)


def _runs(*statuses):
    return [{"status": s, "started_at": i} for i, s in enumerate(statuses)]


def test_simulation_status_not_run_when_no_runs():
    assert derive_simulation_status([]) == "not_run"
    assert derive_simulation_status(None) == "not_run"


def test_simulation_status_ran_when_any_complete():
    assert derive_simulation_status(_runs("running", "complete")) == "ran"
    assert derive_simulation_status(_runs("ran")) == "ran"          # legacy marker
    assert derive_simulation_status(_runs("completed")) == "ran"


def test_simulation_status_running_when_only_in_progress():
    assert derive_simulation_status(_runs("running")) == "running"


def test_simulation_status_failed_only_is_not_run():
    # A failed/orphaned attempt is not a clean completion.
    assert derive_simulation_status(_runs("failed", "orphaned")) == "not_run"


def test_evaluation_status_needs_completed_run():
    spec = {"conclusion_verdicts": [{"test": "a", "verdict": "pass"}]}
    assert derive_evaluation_status(spec, _runs("running")) == "not_evaluated"
    assert derive_evaluation_status(spec, _runs("complete")) == "evaluated"


def test_evaluation_status_needs_verdicts():
    assert derive_evaluation_status({}, _runs("complete")) == "not_evaluated"
    assert derive_evaluation_status(
        {"findings": [{"id": "f1"}]}, _runs("complete")) == "evaluated"


def test_evaluation_status_explicit_has_verdicts_override():
    assert derive_evaluation_status({}, _runs("complete"), has_verdicts=True) == "evaluated"
    assert derive_evaluation_status(
        {"conclusion_verdicts": [1]}, _runs("complete"), has_verdicts=False) == "not_evaluated"


def test_derive_status_shape_and_source():
    d = derive_status({"findings": [{"id": "x"}]}, _runs("complete", "complete"))
    assert d["simulation_status"] == {"value": "ran", "source": "2 completed run(s)"}
    assert d["evaluation_status"]["value"] == "evaluated"


def test_derive_status_no_runs():
    d = derive_status({}, [])
    assert d["simulation_status"]["value"] == "not_run"
    assert d["evaluation_status"]["value"] == "not_evaluated"


def test_no_disagreement_when_stored_matches_derived():
    spec = {"simulation_status": "ran", "findings": [{"id": "x"}],
            "evaluation_status": "evaluated"}
    assert status_disagreements(spec, _runs("complete")) == []


def test_disagreement_stored_axis_contradicts_runs():
    spec = {"simulation_status": "not_run"}
    out = status_disagreements(spec, _runs("complete"))
    assert len(out) == 1
    assert out[0]["axis"] == "simulation_status"
    assert out[0]["stored"] == "not_run"
    assert out[0]["derived"] == "ran"


def test_disagreement_legacy_planning_headline_after_runs():
    """Round-2 friction #2: 'planning-with-baseline-confirmed' headline on a
    study that has completed runs."""
    spec = {"status": "planning-with-baseline-confirmed"}
    out = status_disagreements(spec, _runs("complete"))
    msgs = [v["message"] for v in out]
    assert any("still says planning" in m for m in msgs)


def test_legacy_planning_not_flagged_when_not_run():
    spec = {"status": "planning"}
    assert status_disagreements(spec, _runs("running")) == []


def test_no_disagreement_when_stored_absent():
    # Absent stored axes are derived-on-read, not contradictions.
    assert status_disagreements({}, _runs("complete")) == []
