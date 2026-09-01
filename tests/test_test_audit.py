import viva_superpowers.test_audit as ta


def _spec(tests, question="", purpose=None, controls=None):
    s = {"question": question, "behavior_tests": tests}
    if purpose:
        s["purpose"] = purpose
    if controls:
        s["controls"] = controls
    return s


def test_band_too_wide_flags_trivially_wide_band():
    narrow = {"name": "n", "measure": {"path": "a"},
              "pass_if": {"op": "in_range", "low": 0.9, "high": 1.1}}   # ±10% of ~1
    wide = {"name": "w", "measure": {"path": "b"},
            "pass_if": {"op": "in_range", "low": 0.1, "high": 10.0}}    # half-width >> mid
    flags = ta.band_too_wide(_spec([narrow, wide]))
    names = {f["name"] for f in flags}
    assert "w" in names and "n" not in names


def test_redundant_paths_flags_shared_observable():
    t1 = {"name": "t1", "measure": {"path": "mass.growth"}, "pass_if": {"op": "<=", "value": 1}}
    t2 = {"name": "t2", "measure": {"path": "mass.growth"}, "pass_if": {"op": ">=", "value": 0}}
    t3 = {"name": "t3", "measure": {"path": "dnaa.atp"}, "pass_if": {"op": "<=", "value": 1}}
    dupes = ta.redundant_paths(_spec([t1, t2, t3]))
    assert dupes and dupes[0]["path"] == "mass.growth" and set(dupes[0]["tests"]) == {"t1", "t2"}


def test_uncovered_mechanisms_when_no_test_touches_a_mechanism():
    spec = _spec(
        [{"name": "growth", "classification": "primary", "measure": {"path": "mass.growth"}}],
        purpose={"mechanism": "dnaA_atp_titration"})
    assert "dnaA_atp_titration" in ta.uncovered_mechanisms(spec)


def test_has_discriminating_control():
    assert ta.has_discriminating_control(_spec(
        [{"name": "c", "classification": "diagnostic",
          "control": "negative", "measure": {"path": "x"}}])) is True
    assert ta.has_discriminating_control(_spec(
        [{"name": "p", "classification": "primary", "measure": {"path": "x"}}])) is False


def test_build_audit_report_fails_on_wide_band_and_uncovered_mechanism():
    spec = _spec(
        [{"name": "w", "classification": "primary", "measure": {"path": "b"},
          "pass_if": {"op": "in_range", "low": 0.1, "high": 10.0}}],
        purpose={"mechanism": "dnaA_atp_titration"})
    rep = ta.build_audit_report(spec)
    assert rep["schema"] == "report_card_verdict/v2"
    axes = {ax["id"]: ax for g in rep["groups"].values() for ax in g["axes"]}
    assert axes["discrimination"]["verdict"] == "mismatch"       # wide band
    assert axes["objective_coverage"]["verdict"] == "mismatch"   # uncovered mechanism
    assert ta.audit_gate(rep) == "fail"                          # a hard axis mismatched


def test_build_audit_report_passes_a_sound_suite():
    spec = _spec(
        [{"name": "atp", "classification": "primary",
          "measure": {"path": "dnaA_atp_titration.fraction"}, "cites": ["Kurokawa1999"],
          "pass_if": {"op": "in_range", "low": 0.6, "high": 0.8,
                      "provenance": {"kind": "literature"}}},
         {"name": "ctl", "classification": "diagnostic", "control": "negative",
          "measure": {"path": "dnaA_atp_titration.knockout"},
          "pass_if": {"op": "<=", "value": 0.1, "provenance": {"kind": "first_principles"}}}],
        purpose={"mechanism": "dnaA_atp_titration"})
    rep = ta.build_audit_report(spec)
    assert ta.audit_gate(rep) in ("pass", "warn")


def test_tests_section_not_blind_spot_for_redundancy_and_coverage():
    # Study authored under `tests:` (not `behavior_tests:`) — band_too_wide
    # already sees it via rigor._numeric_band_tests/_study_test_entries; this
    # regression-tests that redundant_paths/uncovered_mechanisms/
    # has_discriminating_control see it too (previously a false hard-fail of
    # objective_coverage since _tests() only read behavior_tests/expected_behavior).
    spec = {
        "question": "",
        "purpose": {"mechanism": "dnaA_atp_titration"},
        "tests": [
            {"name": "atp", "classification": "primary",
             "measure": {"path": "dnaA_atp_titration.fraction"},
             "pass_if": {"op": "in_range", "low": 0.6, "high": 0.8}},
            {"name": "atp2", "classification": "primary",
             "measure": {"path": "dnaA_atp_titration.fraction"},
             "pass_if": {"op": "in_range", "low": 0.5, "high": 0.9}},
        ],
    }
    dupes = ta.redundant_paths(spec)
    assert dupes and dupes[0]["path"] == "dnaA_atp_titration.fraction"
    assert set(dupes[0]["tests"]) == {"atp", "atp2"}
    assert ta.uncovered_mechanisms(spec) == []
    rep = ta.build_audit_report(spec)
    axes = {ax["id"]: ax for g in rep["groups"].values() for ax in g["axes"]}
    assert axes["objective_coverage"]["verdict"] == "within_tol"


def test_one_sided_loose_primary_flags_discrimination_drift_not_silent_pass():
    # A primary test with a trivially-loose one-sided threshold has no stated
    # band, so band_too_wide can't grade it — but a silent "pass" on a
    # gameable suite is exactly what the discrimination axis must not do.
    spec = _spec(
        [{"name": "loose", "classification": "primary", "measure": {"path": "x"},
          "pass_if": {"op": "<=", "value": 1e12}}])
    flags = ta.one_sided_loose_primary(spec)
    assert flags and flags[0]["name"] == "loose"
    rep = ta.build_audit_report(spec)
    axes = {ax["id"]: ax for g in rep["groups"].values() for ax in g["axes"]}
    assert axes["discrimination"]["verdict"] == "drift"
    assert ta.audit_gate(rep) == "warn"                          # not a silent pass


def test_band_too_wide_sees_expected_behavior_section():
    # A study authored under expected_behavior: (scaffold.py's default section
    # name) must not escape the discrimination check.
    spec = {
        "question": "",
        "expected_behavior": [
            {"name": "wide_eb", "classification": "primary", "measure": {"path": "z"},
             "pass_if": {"op": "in_range", "low": 0.1, "high": 10.0}},
        ],
    }
    flags = ta.band_too_wide(spec)
    assert flags and flags[0]["name"] == "wide_eb"
    rep = ta.build_audit_report(spec)
    axes = {ax["id"]: ax for g in rep["groups"].values() for ax in g["axes"]}
    assert axes["discrimination"]["verdict"] == "mismatch"


def test_pass_if_provenance_counts_as_provenance():
    # A band with pass_if.provenance but NO cites is NOT missing provenance
    # (band_provenance flags it on cites; the audit accepts provenance too).
    spec = _spec([{"name": "ctl", "classification": "diagnostic", "control": "negative",
                   "measure": {"path": "x.ko"},
                   "pass_if": {"op": "<=", "value": 0.1, "provenance": {"kind": "first_principles"}}}])
    assert ta._bands_missing_provenance(spec) == []
    rep = ta.build_audit_report(spec)
    axes = {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}
    assert axes["band_provenance"]["verdict"] == "within_tol"     # not flagged


# ── comparison studies (graded against an external reference) ─────────────────

def _comparison_spec(uncovered_card=False):
    """A vs-reference study: report_card tests + a comparison block. If
    uncovered_card, a declared card has no test (a genuine coverage gap)."""
    cards = ["statistical", "trajectory"]
    tests = [{"name": f"{c}-vs-ref", "kind": "report_card", "card": c,
              "classification": "primary"} for c in cards]
    if uncovered_card:
        cards = cards + ["metabolism"]   # declared but not tested
    return {"name": "basal", "question": "Does v2ecoli reproduce vEcoli on basal?",
            "comparison": {"seeds": 4}, "report_card_refs": {"vs": "…/verdict.json"},
            "report_cards": [f"viz/report_card/{c}.html" for c in cards],
            "tests": tests}


def test_comparison_study_is_detected():
    assert ta.is_comparison_study(_comparison_spec()) is True
    # a model-building study (behavior_tests, no comparison markers) is NOT
    assert ta.is_comparison_study(
        {"behavior_tests": [{"name": "x", "measure": {"path": "v"},
                             "pass_if": {"op": ">=", "value": 1.0}}]}) is False


def test_comparison_audit_does_not_misread_reference_name_as_a_mechanism():
    """The bug: "vEcoli" tokenized from the question was flagged as an uncovered
    mechanism → false objective_coverage mismatch. Comparison coverage keys off
    the compared CARDS, not question tokens, so a covered suite passes."""
    spec = _comparison_spec()
    assert ta.uncovered_comparison_axes(spec) == []
    rep = ta.build_audit_report(spec)
    axes = {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}
    assert axes["objective_coverage"]["verdict"] == "within_tol"
    assert axes["discriminating_control"]["verdict"] == "within_tol"  # reference is the discriminator
    assert ta.audit_gate(rep) == "pass"


def test_comparison_coverage_still_bites_on_an_untested_card():
    """Coverage is not a rubber stamp: a declared card with no test is a real gap."""
    spec = _comparison_spec(uncovered_card=True)
    assert "metabolism" in ta.uncovered_comparison_axes(spec)
    rep = ta.build_audit_report(spec)
    axes = {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}
    assert axes["objective_coverage"]["verdict"] == "mismatch"        # hard → gate fail
    assert ta.audit_gate(rep) == "fail"


def test_no_tests_is_not_a_vacuous_pass():
    # A study with no tests must NOT earn green 'within_tol' on sufficiency
    # checks — every axis is 'ungraded' (not assessable) and the gate is
    # 'incomplete', not 'pass'.
    spec = {"name": "diffusion-demo", "question": "how do particles spread"}
    rep = ta.build_audit_report(spec)
    axes = {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}
    assert all(ax["verdict"] == "ungraded" for ax in axes.values()), axes
    for ax in axes.values():
        assert (ax.get("detail") or {}).get("reason")   # each says WHY
    assert ta.audit_gate(rep) == "incomplete"


def test_declared_mechanism_but_no_test_is_not_met():
    # Objective coverage is assessable (a mechanism is named) but uncovered →
    # 'mismatch' (not met), not a vacuous pass.
    spec = {"name": "x", "question": "does dnaA_ATP gate initiation",
            "purpose": {"mechanism": "dnaA_ATP hydrolysis controls initiation"}}
    rep = ta.build_audit_report(spec)
    axes = {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}
    assert axes["objective_coverage"]["verdict"] == "mismatch"
