"""Tests for the evidence & rigor scorecard (pbg_superpowers.rigor)."""
from pbg_superpowers.rigor import (
    study_rigor, investigation_rigor, finding_evidential_weight, GAP, WARN, OK,
)


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
    assert _sev(sc, "next_steps") == GAP             # Decide-phase: no discovery_implications
    assert sc["score"]["gap"] >= 6
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
             "hypothesis": "supplied externally -> closure fails",
             "observed": "fail-closure", "result": "PASS"},
            {"name": "self-producing", "kind": "positive",
             "hypothesis": "genuine self-production -> closure holds",
             "observed": "closure-holds", "result": "PASS"},
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
        "discovery_implications": {"followup_study_proposals": [{"id": "s2", "title": "next"}]},
    }
    sc = study_rigor(spec)
    for dim in ("replication", "negative_control", "alternatives", "claim_discipline",
                "falsifiability", "mechanism_origin", "limitations", "next_steps"):
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
              "controls": [{"kind": "negative", "observed": "fail-closure", "result": "PASS"}]}]
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
    assert study_rigor({})["score"]["total"] == 8
    assert study_rigor(None)["score"]["total"] == 8
    assert investigation_rigor(None, None)["per_study"] == {}


def test_next_steps_dimension():
    from pbg_superpowers.rigor import study_rigor, GAP, OK
    assert _sev(study_rigor({}), "next_steps") == GAP
    assert _sev(study_rigor({"follow_up_studies": ["s2"]}), "next_steps") == OK
    assert _sev(study_rigor({"discovery_implications": {"followup_study_proposals": [{"id": "x"}]}}),
                "next_steps") == OK
    # empty discovery_implications dict is still a gap
    assert _sev(study_rigor({"discovery_implications": {}}), "next_steps") == GAP


# ---------------------------------------------------------------------------
# Item 14 — replication scores AGREEMENT, not just count.
# ---------------------------------------------------------------------------

def test_replication_downgrades_on_high_cv():
    # 3 replicates but one measure has a high coefficient of variation → WARN.
    spec = {"robustness": {"n_replicates": 3, "seeds": [0, 1, 2],
                           "per_measure": [{"name": "growth_rate", "mean": 1.0, "std": 0.9}]}}
    assert _sev(study_rigor(spec), "replication") == WARN


def test_replication_downgrades_on_explicit_cv():
    spec = {"robustness": {"n_replicates": 3, "per_measure": [{"name": "g", "cv": 0.8}]}}
    assert _sev(study_rigor(spec), "replication") == WARN


def test_replication_ok_on_tight_seeds():
    # 3 replicates and a tight measure → still OK.
    spec = {"robustness": {"n_replicates": 3, "seeds": [0, 1, 2],
                           "per_measure": [{"name": "growth_rate", "mean": 1.0, "std": 0.05}]}}
    assert _sev(study_rigor(spec), "replication") == OK


def test_replication_downgrades_without_seed_majority():
    # 3 replicates but only 1 seed shows the advantage → no majority → WARN.
    spec = {"robustness": {"n_replicates": 3, "seeds_with_advantage": 1}}
    assert _sev(study_rigor(spec), "replication") == WARN


def test_replication_ok_with_seed_majority():
    spec = {"robustness": {"n_replicates": 3, "seeds_with_advantage": 2}}
    assert _sev(study_rigor(spec), "replication") == OK


def test_replication_seed_advantage_fraction():
    # A float in (0, 1] is read as a fraction directly.
    assert _sev(study_rigor({"robustness": {"n_replicates": 4, "seeds_with_advantage": 0.25}}),
                "replication") == WARN
    assert _sev(study_rigor({"robustness": {"n_replicates": 4, "seeds_with_advantage": 0.75}}),
                "replication") == OK


def test_replication_tolerant_of_malformed_robustness():
    # Missing/garbage sub-fields must not raise and must not downgrade.
    spec = {"robustness": {"n_replicates": 3,
                           "per_measure": [{"name": "x"}, "junk", {"std": None}]}}
    assert _sev(study_rigor(spec), "replication") == OK


# ---------------------------------------------------------------------------
# Item 15 — a control needs a non-empty `observed` to earn discriminating credit.
# ---------------------------------------------------------------------------

def test_control_pass_without_observed_earns_no_credit():
    # PASS but never run (no `observed`) → no discriminating credit → WARN.
    spec = {"controls": [
        {"name": "external", "kind": "negative", "result": "PASS"},
        {"name": "self", "kind": "positive", "result": "PASS"},
    ]}
    assert _sev(study_rigor(spec), "negative_control") == WARN


def test_control_pass_with_observed_earns_credit():
    spec = {"controls": [
        {"name": "external", "kind": "negative", "observed": "fail-closure", "result": "PASS"},
        {"name": "self", "kind": "positive", "observed": "closure-holds", "result": "PASS"},
    ]}
    assert _sev(study_rigor(spec), "negative_control") == OK


def test_falsification_exposure_requires_observed_control():
    # A discriminating-negative claim with no `observed` must NOT count as
    # falsification exposure at the investigation level (item 15).
    inv = {"acceptance_criteria": [{"study": "s1", "behavior": "b"}],
           "competing_frameworks": [{"name": "active inference"}]}
    specs = [{"name": "s1", "pipeline_gate": {"gate_evaluator": {"result": "passed"}},
              "controls": [{"kind": "negative", "result": "PASS"}]}]  # no observed
    ir = investigation_rigor(inv, specs)
    assert _sev(ir, "falsification_exposure") == GAP


# ---------------------------------------------------------------------------
# Item 9 (C5) — alternatives source: DI preferred, top-level fallback.
# ---------------------------------------------------------------------------

def test_alternatives_from_discovery_implications():
    spec = {"discovery_implications": {"alternate_hypotheses": [
        {"claim": "a", "status": "excluded"}]}}
    assert _sev(study_rigor(spec), "alternatives") == OK


def test_alternatives_fallback_to_top_level():
    spec = {"alternative_hypotheses": [{"claim": "a", "status": "excluded"}]}
    assert _sev(study_rigor(spec), "alternatives") == OK


# ---------------------------------------------------------------------------
# Item 1 — could_fail_if is no longer a falsifiability source (dead field).
# ---------------------------------------------------------------------------

def test_could_fail_if_no_longer_counts_for_falsifiability():
    spec = {"behavior_tests": [{"name": "t", "could_fail_if": "x"}]}
    assert _sev(study_rigor(spec), "falsifiability") == GAP
    # study.falsifiability remains the canonical (and only) source.
    assert _sev(study_rigor({"falsifiability": "would fail if ..."}), "falsifiability") == OK


# ---------------------------------------------------------------------------
# Item 8 — per-finding evidential weight (strong / moderate / weak).
# ---------------------------------------------------------------------------

def _strong_spec():
    """A study where one finding (test=agency-advantage) can satisfy all five
    evidential dimensions when matched."""
    return {
        "name": "study-z",
        "robustness": {"n_replicates": 3, "seeds": [0, 1, 2],
                       "per_measure": [{"name": "agency-advantage", "mean": 1.0, "std": 0.05}]},
        "controls": [
            {"name": "non-sensing control for agency-advantage", "kind": "negative",
             "observed": "no-advantage", "result": "PASS"},
        ],
        "alternative_hypotheses": [
            {"claim": "plain movement to resources", "discriminated_by": "agency-advantage",
             "status": "excluded"},
        ],
        "findings": [
            {"statement": "agency in service of survival", "tier": "interpretation",
             "mechanism_origin": "emergent",
             "evidence": {"from_test": "agency-advantage"},
             "calibration_anchor": {"divergence_factor": 0.4}},
        ],
    }


def test_finding_weight_strong_when_all_dims_match():
    spec = _strong_spec()
    res = finding_evidential_weight(spec, spec["findings"][0])
    assert res["weight"] == "strong"
    assert res["n_supporting"] == 5
    assert all(res["dims"].values())
    assert set(res["dims"]) == {"replication", "effect_size", "control_strength",
                                "independence", "alternatives"}


def test_finding_weight_moderate_at_two_to_three_dims():
    # emergent (independence) + an excluded alternative (degraded study-level)
    # → 2 dims → moderate. No replication, no effect size, no control.
    spec = {
        "alternative_hypotheses": [{"claim": "alt", "status": "excluded"}],
        "findings": [{"statement": "x", "tier": "interpretation",
                      "mechanism_origin": "emergent",
                      "evidence": {"from_test": "t"}}],
    }
    res = finding_evidential_weight(spec, spec["findings"][0])
    assert res["weight"] == "moderate"
    assert res["n_supporting"] == 2
    assert res["dims"]["independence"] is True
    assert res["dims"]["alternatives"] is True
    assert res["dims"]["replication"] is False


def test_finding_weight_weak_when_unsupported():
    spec = {"findings": [{"statement": "It works.", "evidence": {"from_test": "t"}}]}
    res = finding_evidential_weight(spec, spec["findings"][0])
    assert res["weight"] == "weak"
    assert res["n_supporting"] <= 1


def test_finding_weight_effect_size_reads_divergence_factor():
    spec = {"findings": [{"statement": "x", "evidence": {"from_test": "t"},
                          "calibration_anchor": {"divergence_factor": 0.3}}]}
    res = finding_evidential_weight(spec, spec["findings"][0])
    assert res["dims"]["effect_size"] is True
    # zero divergence is not a meaningful effect size
    spec0 = {"findings": [{"statement": "x", "evidence": {"from_test": "t"},
                           "calibration_anchor": {"divergence_factor": 0.0}}]}
    assert finding_evidential_weight(spec0, spec0["findings"][0])["dims"]["effect_size"] is False


def test_finding_weight_control_degrades_to_study_level():
    # The discriminating control does NOT name the finding's test, so the
    # tolerant matcher degrades to the study-level "any discriminating control".
    spec = {
        "controls": [{"name": "external-membrane", "kind": "negative",
                      "observed": "fail-closure", "result": "PASS"}],
        "findings": [{"statement": "x", "evidence": {"from_test": "unrelated-test"}}],
    }
    res = finding_evidential_weight(spec, spec["findings"][0])
    assert res["dims"]["control_strength"] is True


def test_finding_weight_control_pass_without_observed_no_credit():
    spec = {
        "controls": [{"name": "external", "kind": "negative", "result": "PASS"}],  # no observed
        "findings": [{"statement": "x", "evidence": {"from_test": "t"}}],
    }
    assert finding_evidential_weight(spec, spec["findings"][0])["dims"]["control_strength"] is False


def test_finding_weight_replication_restricted_to_finding_measure():
    # The finding's OWN measure is tight (agreement OK) even though another
    # measure in the study is noisy → restricted replication is True.
    spec = {
        "robustness": {"n_replicates": 3, "seeds": [0, 1, 2], "per_measure": [
            {"name": "mine", "mean": 1.0, "std": 0.02},
            {"name": "other", "mean": 1.0, "std": 0.9},  # noisy, but not this finding's
        ]},
        "findings": [{"statement": "x", "evidence": {"from_test": "mine"}}],
    }
    assert finding_evidential_weight(spec, spec["findings"][0])["dims"]["replication"] is True


def test_finding_weight_tolerant_of_empty():
    res = finding_evidential_weight({}, {})
    assert res["weight"] == "weak"
    assert res["n_supporting"] == 0
    assert finding_evidential_weight(None, None)["weight"] == "weak"


# ---------------------------------------------------------------------------
# Wave 3a — _study_type, exploratory falsification, confirmatory dim,
# intent label, and framework_metrics (critiques #10, #18, #1, #26)
# ---------------------------------------------------------------------------

from pbg_superpowers.rigor import _study_type, framework_metrics


def _dim_ids(scorecard):
    return {d["id"] for d in scorecard["dimensions"]}


def test_study_type_reads_field_and_aliases():
    assert _study_type({"study_type": "exploratory"}) == "exploratory"
    # legacy kind / study_kind aliases still resolve
    assert _study_type({"kind": "adversarial"}) == "adversarial"
    assert _study_type({"study_kind": "confirmatory"}) == "confirmatory"
    # study_type wins over the alias
    assert _study_type({"study_type": "diagnostic", "kind": "adversarial"}) == "diagnostic"
    # unknown / unset → standard
    assert _study_type({"kind": "whatever"}) == "standard"
    assert _study_type({}) == "standard"
    assert _study_type(None) == "standard"


def test_study_rigor_reports_study_type_and_no_extra_dim_for_standard():
    sc = study_rigor({"name": "s", "runs": [{"name": "r"}]})
    assert sc["study_type"] == "standard"
    # back-compat: standard studies do NOT get the confirmatory preregistration dim
    assert "preregistration" not in _dim_ids(sc)


def test_confirmatory_pass_on_posthoc_criteria_warns():
    spec = {
        "name": "c1",
        "study_type": "confirmatory",
        "behavior_tests": [{"name": "t1", "pass_if": {"low": 1}}],
        "runs": [{"name": "r1", "status": "complete", "timestamp": "2026-01-02",
                  "outcomes": {"t1": {"result": "pass"}}}],
        "gate_status": "passed",
        # no preregistered block → can't show criteria predate the run
    }
    sc = study_rigor(spec)
    assert "preregistration" in _dim_ids(sc)
    assert _sev(sc, "preregistration") == WARN


def test_confirmatory_preregistered_before_run_is_ok():
    spec = {
        "name": "c2",
        "study_type": "confirmatory",
        "behavior_tests": [{"name": "t1", "pass_if": {"low": 1}}],
        "runs": [{"name": "r1", "status": "complete", "timestamp": "2026-05-01",
                  "started_at": "2026-05-01", "outcomes": {"t1": {"result": "pass"}}}],
        "gate_status": "passed",
        "preregistered": {"registered_at": "2026-01-01",
                          "thresholds": {"t1": {"low": 1}}},
    }
    sc = study_rigor(spec)
    assert _sev(sc, "preregistration") == OK


def test_exploratory_pass_not_counted_toward_falsification_exposure():
    # A single exploratory study that passes everything is NOT falsification
    # exposure (it observed, it didn't test a hypothesis).
    explor = {"name": "e1", "study_type": "exploratory", "gate_status": "passed"}
    inv = investigation_rigor({}, [explor])
    fe = next(d for d in inv["dimensions"] if d["id"] == "falsification_exposure")
    assert fe["severity"] == GAP

    # A non-exploratory study that did NOT pass DOES expose falsification.
    failed = {"name": "f1", "study_type": "standard", "gate_status": "failed"}
    inv2 = investigation_rigor({}, [failed])
    fe2 = next(d for d in inv2["dimensions"] if d["id"] == "falsification_exposure")
    assert fe2["severity"] == OK


def test_investigation_rigor_exposes_method_intent():
    inv = investigation_rigor({}, [{"name": "s"}])
    assert "intent" in inv
    assert "METHOD" in inv["intent"]


def test_framework_metrics_aggregates_existing_fields():
    studies = [
        {  # discriminating control + emergent interp + 3 seeds + excluded alt
            "name": "s1",
            "robustness": {"n_replicates": 3},
            "controls": [{"kind": "negative", "result": "PASS", "observed": "fail"}],
            "findings": [{"tier": "interpretation", "mechanism_origin": "emergent"}],
            "alternative_hypotheses": [{"claim": "x", "status": "excluded"}],
            "behavior_tests": [{"name": "t", "pass_if": {"low": 1}, "cites": ["k"]}],
            "gate_status": "passed",
        },
        {  # no control, missing mechanism_origin, 1 seed, uncited band
            "name": "s2",
            "findings": [{"tier": "interpretation"}],
            "behavior_tests": [{"name": "t2", "pass_if": {"low": 1}}],
            "gate_status": "failed",
        },
    ]
    invs = [{"acceptance_criteria": [{"behavior": "a", "study": "s1"},
                                     {"behavior": "b"}]}]
    m = framework_metrics(studies, invs)
    assert m["n_studies"] == 2
    assert m["n_investigations"] == 1
    assert m["discriminating_controls"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["emergent_interpretations"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["missing_mechanism_origin"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["threshold_provenance"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["replication_coverage"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["ac_coverage"] == {"fraction": 0.5, "count": 1, "total": 2}
    assert m["alternatives_excluded"] == {"fraction": 0.5, "count": 1, "total": 2}
    # s2 failed (non-exploratory) → falsification exposure
    assert m["falsification_exposure"]["count"] == 2  # s1 has disc control, s2 failed


def test_framework_metrics_tolerant_of_empty():
    m = framework_metrics([], [])
    assert m["n_studies"] == 0
    assert m["discriminating_controls"]["fraction"] is None
    assert framework_metrics(None, None)["n_studies"] == 0
