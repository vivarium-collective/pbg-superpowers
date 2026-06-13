"""Tests for the evidence & rigor scorecard (pbg_superpowers.rigor)."""
from pbg_superpowers.rigor import study_rigor, investigation_rigor, GAP, WARN, OK


def _sev(scorecard, dim_id):
    return next(d["severity"] for d in scorecard["dimensions"] if d["id"] == dim_id)


# ---------------------------------------------------------------------------
# A minimal study (the common case the reviewer critiqued) flags every gap.
# ---------------------------------------------------------------------------

def test_minimal_study_flags_the_reviewer_gaps():
    spec = {
        "name": "study-x",
        "runs": [{"name": "r1"}],  # single run
        "findings": [{"statement": "It works."}],  # untiered, no evidence link
    }
    sc = study_rigor(spec)
    assert _sev(sc, "replication") == GAP            # C4 single run
    assert _sev(sc, "negative_control") == GAP       # C1/C2 no control
    assert _sev(sc, "alternatives") == GAP           # C6 no alternatives
    assert _sev(sc, "claim_discipline") == WARN      # C3 untiered findings
    assert _sev(sc, "falsifiability") == GAP         # C5 no falsifiability note
    assert _sev(sc, "limitations") == GAP            # C8/C11 no limitations
    assert sc["score"]["gap"] >= 5
    assert "rigor dimensions addressed" in sc["summary"]


# ---------------------------------------------------------------------------
# A fully-defended study turns the dimensions green.
# ---------------------------------------------------------------------------

def test_well_defended_study_is_ok():
    spec = {
        "name": "study-y",
        "robustness": {"n_replicates": 5, "seeds": [0, 1, 2, 3, 4], "parameter_sweep": True},
        "controls": [
            {"name": "external-membrane", "kind": "negative",
             "hypothesis": "supplied externally -> closure fails", "result": "PASS"},
            {"name": "self-producing", "kind": "positive",
             "hypothesis": "genuine self-production -> closure holds", "result": "PASS"},
        ],
        "limitations": "Only the geometric-boundary aspect of the membrane is modelled.",
        "alternative_hypotheses": [
            {"claim": "plain movement to resources", "discriminated_by": "non-sensing control",
             "status": "excluded"},
        ],
        "findings": [
            {"statement": "sensing improves survival", "tier": "observation",
             "evidence": {"from_test": "survival"}},
            {"statement": "agency in service of survival", "tier": "interpretation",
             "mechanism_origin": "emergent", "evidence": {"from_test": "agency-advantage"}},
        ],
        "falsifiability": "Survival advantage would vanish if the non-sensing control matched it.",
    }
    sc = study_rigor(spec)
    for dim in ("replication", "negative_control", "alternatives",
                "claim_discipline", "falsifiability", "mechanism_origin", "limitations"):
        assert _sev(sc, dim) == OK, f"{dim} should be OK"
    assert sc["score"]["gap"] == 0


def test_replication_warn_at_two_seeds():
    sc = study_rigor({"robustness": {"seeds": [0, 1]}})
    assert _sev(sc, "replication") == WARN


def test_replication_counts_simulation_set_seeds():
    sc = study_rigor({"simulation_set": [{"seeds": [0, 1, 2]}]})
    assert _sev(sc, "replication") == OK


def test_interpretation_without_origin_warns():
    spec = {
        "findings": [{"statement": "x", "tier": "interpretation", "evidence": {"from_test": "t"}}],
        "alternative_hypotheses": [{"claim": "a", "status": "excluded"}],
    }
    assert _sev(study_rigor(spec), "mechanism_origin") == WARN  # C7


# ---------------------------------------------------------------------------
# Investigation roll-up: adversarial coverage + methodology headline.
# ---------------------------------------------------------------------------

def test_controls_negative_only_warns_calibration():
    # A negative control discriminates, but without a passing/borderline case the
    # metric isn't calibrated across its range (review-2 C4).
    sc = study_rigor({"controls": [{"name": "x", "kind": "negative", "result": "PASS"}]})
    assert _sev(sc, "negative_control") == WARN


def test_limitations_ok_when_declared():
    assert _sev(study_rigor({"limitations": "does not model transport"}), "limitations") == OK
    assert _sev(study_rigor({"does_not_show": ["transport", "signalling"]}), "limitations") == OK


def test_investigation_falsification_and_comparative_gaps():
    inv = {"acceptance_criteria": [{"study": "s1", "behavior": "b"}]}
    specs = [{"name": "s1", "pipeline_gate": {"gate_evaluator": {"result": "passed"}}}]
    ir = investigation_rigor(inv, specs)
    assert _sev(ir, "falsification_exposure") == GAP   # C1 all-pass, nothing failed
    assert _sev(ir, "comparative_framing") == GAP      # C13 no competing frameworks


def test_discriminating_control_and_competing_frameworks_flip_to_ok():
    inv = {"acceptance_criteria": [{"study": "s1", "behavior": "b"}],
           "competing_frameworks": [{"name": "active inference"}]}
    specs = [{"name": "s1", "pipeline_gate": {"gate_evaluator": {"result": "passed"}},
              "controls": [{"kind": "negative", "result": "PASS"}]}]
    ir = investigation_rigor(inv, specs)
    assert _sev(ir, "falsification_exposure") == OK    # a system was shown to fail
    assert _sev(ir, "comparative_framing") == OK


def test_investigation_flags_missing_adversarial_study():
    inv = {"acceptance_criteria": [{"study": "s1", "behavior": "b"}]}
    specs = [{"name": "s1", "pipeline_gate": {}, "runs": [{}]}]
    ir = investigation_rigor(inv, specs)
    assert _sev(ir, "adversarial_coverage") == GAP   # C10
    assert _sev(ir, "methodology") == OK             # C9
    assert "s1" in ir["per_study"]


def test_investigation_recognizes_adversarial_study():
    inv = {"acceptance_criteria": [{"study": "s1", "behavior": "b"}]}
    specs = [
        {"name": "s1", "pipeline_gate": {}},
        {"name": "s2-break", "kind": "adversarial", "pipeline_gate": {}},
    ]
    ir = investigation_rigor(inv, specs)
    assert _sev(ir, "adversarial_coverage") == OK


def test_pure_no_mutation_and_tolerant_of_empty():
    # Empty / None specs must not raise.
    assert study_rigor({})["score"]["total"] == 7
    assert study_rigor(None)["score"]["total"] == 7
    assert investigation_rigor(None, None)["per_study"] == {}
