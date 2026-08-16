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
