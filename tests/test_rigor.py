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
    assert sc["score"]["gap"] >= 4
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
        ],
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
                "claim_discipline", "falsifiability", "mechanism_origin"):
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
    assert study_rigor({})["score"]["total"] == 6
    assert study_rigor(None)["score"]["total"] == 6
    assert investigation_rigor(None, None)["per_study"] == {}
