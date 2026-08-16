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
