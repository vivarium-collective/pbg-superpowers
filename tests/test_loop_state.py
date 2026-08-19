import viva_superpowers.loop_state as ls


def test_create_and_roundtrip(tmp_path):
    (tmp_path / "workspace.yaml").write_text("name: ws\n", encoding="utf-8")
    st = ls.create(tmp_path, "dnaa", "Does DnaA-ATP explain initiation timing?")
    assert st["schema"] == "model_build_loop/v1"
    assert st["study"] == "dnaa" and st["state"] == "AUTHOR"
    assert st["question"] == "Does DnaA-ATP explain initiation timing?"
    assert st["iteration"] == 0 and st["budget"] == {"max_iterations": 12, "spent": 0}
    assert st["locked_tests_hash"] is None and st["reopen_count"] == 0 and st["history"] == []
    p = ls.save(tmp_path, "dnaa", st)
    assert p.name == "dnaa.json" and p.parent.name == "loop"
    assert ls.load(tmp_path, "dnaa") == st


def test_load_absent_is_none(tmp_path):
    (tmp_path / "workspace.yaml").write_text("name: ws\n", encoding="utf-8")
    assert ls.load(tmp_path, "nope") is None


def test_tests_hash_is_order_and_whitespace_stable():
    a = [{"name": "t1", "pass_if": {"op": "<=", "value": 5}},
         {"name": "t2", "pass_if": {"op": ">=", "value": 1}}]
    b = list(reversed(a))
    assert ls.tests_hash(a) == ls.tests_hash(b)          # order-independent
    assert ls.tests_hash(a) != ls.tests_hash(a[:1])       # content-sensitive


def test_lock_records_hash_and_prereg():
    st = ls.create(".", "s", "q")
    tests = [{"name": "t1", "pass_if": {"op": "<=", "value": 5}}]
    st["iteration"] = 0
    st = ls.lock_tests(st, tests)
    assert st["locked_tests_hash"] == ls.tests_hash(tests)
    assert st["prereg_record"]["locked_at_iteration"] == 0
    assert st["state"] == "LOCK"


def test_advance_sets_state_and_fields():
    st = ls.advance(ls.create(".", "s", "q"), "AUDIT", audit={"overall": "within_tol"})
    assert st["state"] == "AUDIT" and st["audit"] == {"overall": "within_tol"}


def test_advance_rejects_unknown_state():
    import pytest
    with pytest.raises(ValueError):
        ls.advance(ls.create(".", "s", "q"), "NONSENSE")


def test_record_iteration_appends_history_and_spends_budget():
    st = ls.create(".", "s", "q")
    st = ls.record_iteration(st, edit="raised rate 1.3x", target="model",
                             margin_deltas={"t1": 0.03}, gate="fail")
    assert st["iteration"] == 1 and st["budget"]["spent"] == 1
    h = st["history"][-1]
    assert h["edit"] == "raised rate 1.3x" and h["target"] == "model"
    assert h["margin_deltas"] == {"t1": 0.03} and h["gate"] == "fail"
    assert "tests" not in h                                    # optional; absent by default


def test_record_iteration_carries_per_test_verdicts():
    st = ls.create(".", "s", "q")
    st = ls.record_iteration(st, edit="install thermal_death", target="model",
                             margin_deltas={"viability-cliff": 0.9}, gate="fail",
                             tests=[{"name": "viability-cliff", "verdict": "within_tol", "margin": 0.05},
                                    {"name": "viability-in-band", "verdict": "mismatch", "margin": -0.9}])
    h = st["history"][-1]
    assert [t["name"] for t in h["tests"]] == ["viability-cliff", "viability-in-band"]
    assert h["tests"][1]["verdict"] == "mismatch" and h["tests"][1]["margin"] == -0.9


def test_validate_flags_locked_test_change_without_reopen():
    tests = [{"name": "t1", "pass_if": {"op": "<=", "value": 5}}]
    st = ls.lock_tests(ls.create(".", "s", "q"), tests)
    weakened = [{"name": "t1", "pass_if": {"op": "<=", "value": 500}}]  # loosened
    viol = ls.validate(st, weakened)
    assert any("I1" in v for v in viol)                    # locked tests changed
    assert ls.validate(st, tests) == []                    # unchanged → clean
    assert ls.validate(st, weakened, is_reopen=True) == [] # reopen path allowed


def test_validate_flags_unsupported_pass_verdict():
    st = ls.create(".", "s", "q")
    st["last_verdict"] = {"roll_up": "passed", "gate": "fail"}   # I4 violation
    assert any("I4" in v for v in ls.validate(st, []))


# --- reopen trail (anti-gaming visibility, spec §7) ---

def test_relock_records_reopen_trail():
    t1 = [{"name": "t", "pass_if": {"op": "<=", "value": 5}}]
    t2 = [{"name": "t", "pass_if": {"op": "<=", "value": 500}}]   # weakened
    st = ls.lock_tests(ls.create(".", "s", "q"), t1)
    assert st["reopen_count"] == 0 and st["prereg_record"]["prior_hashes"] == []
    st = ls.lock_tests(st, t2)                                     # re-lock a changed set
    assert st["reopen_count"] == 1
    assert st["prereg_record"]["prior_hashes"] == [ls.tests_hash(t1)]   # prior retained
    assert st["locked_tests_hash"] == ls.tests_hash(t2)


def test_relock_same_tests_is_not_a_reopen():
    t1 = [{"name": "t", "pass_if": {"op": "<=", "value": 5}}]
    st = ls.lock_tests(ls.lock_tests(ls.create(".", "s", "q"), t1), t1)   # lock twice, same
    assert st["reopen_count"] == 0 and st["prereg_record"]["prior_hashes"] == []


def test_validate_flags_tampered_reopen_trail():
    st = ls.lock_tests(ls.create(".", "s", "q"), [{"name": "t", "pass_if": {"op": "<=", "value": 5}}])
    st["reopen_count"] = 2                        # claims 2 reopens but no prior hashes
    assert any("I1b" in v for v in ls.validate(st, [{"name": "t", "pass_if": {"op": "<=", "value": 5}}]))


# --- SPIKE: feasibility spike before locking (closed-loop review §3a) ---

def test_spike_is_a_state_and_record_spike_sets_it():
    assert "SPIKE" in ls.STATES
    st = ls.create(".", "s", "q")
    assert st["spike"] is None                                   # present, empty by default
    st = ls.record_spike(st, expressible=True, artifact={"mcs": 100, "trend": "up"},
                         note="occupancy gradient present at low bg")
    assert st["state"] == "SPIKE"
    assert st["spike"]["expressible"] is True
    assert st["spike"]["artifact"]["mcs"] == 100


def test_locking_after_nonexpressible_spike_is_flagged():
    # the contract was locked even though the feasibility probe showed the engine
    # cannot express the phenomenon — the exact failure the spike exists to prevent
    st = ls.record_spike(ls.create(".", "s", "q"), expressible=False,
                         artifact={}, note="engine has no occupancy operator")
    st = ls.lock_tests(st, [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}])
    viol = ls.validate(st, [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}])
    assert any("I0" in v for v in viol)
    # an expressible spike locks clean
    st2 = ls.record_spike(ls.create(".", "s", "q"), expressible=True, artifact={})
    st2 = ls.lock_tests(st2, [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}])
    assert not any("I0" in v for v in ls.validate(st2, [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}]))


def test_legacy_state_without_spike_is_not_flagged():
    # back-compat: a pre-existing loop file has no spike key; absence is never a violation
    st = ls.lock_tests(ls.create(".", "s", "q"), [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}])
    st.pop("spike", None)
    assert not any("I0" in v for v in ls.validate(st, [{"name": "t", "pass_if": {"op": ">=", "value": 0.5}}]))


# --- typed NAVIGATE actions + diagnosis-before-MODIFY (closed-loop review §3b) ---

def test_record_iteration_carries_typed_action_and_diagnosis():
    st = ls.create(".", "s", "q")
    diag = {"hypotheses": ["receptor saturation", "adaptation too slow"],
            "discriminating_measure": "high-background threshold scan"}
    st = ls.record_iteration(st, edit="add adaptive kd", target="model",
                             margin_deltas={"recruits_high": 0.4}, gate="fail",
                             action="MODIFY", diagnosis=diag)
    h = st["history"][-1]
    assert h["action"] == "MODIFY" and h["diagnosis"]["discriminating_measure"] == "high-background threshold scan"


def test_record_iteration_rejects_unknown_action():
    import pytest
    with pytest.raises(ValueError):
        ls.record_iteration(ls.create(".", "s", "q"), edit="x", target="model",
                            margin_deltas={}, gate="fail", action="FROB")


def test_modify_without_diagnosis_is_flagged():
    # a structural edit (MODIFY) must be justified by a diagnosis: >=2 competing
    # hypotheses + the MEASURE that discriminates them — else it is a reflexive edit
    st = ls.record_iteration(ls.create(".", "s", "q"), edit="swapped mechanism",
                             target="model", margin_deltas={}, gate="fail", action="MODIFY")
    assert any("I6" in v for v in ls.validate(st, []))
    # a one-hypothesis "diagnosis" is not discriminating → still flagged
    st2 = ls.record_iteration(ls.create(".", "s", "q"), edit="swapped mechanism",
                              target="model", margin_deltas={}, gate="fail", action="MODIFY",
                              diagnosis={"hypotheses": ["only one"], "discriminating_measure": "m"})
    assert any("I6" in v for v in ls.validate(st2, []))
    # a proper diagnosis clears it
    st3 = ls.record_iteration(ls.create(".", "s", "q"), edit="swapped mechanism",
                              target="model", margin_deltas={}, gate="fail", action="MODIFY",
                              diagnosis={"hypotheses": ["a", "b"], "discriminating_measure": "scan"})
    assert not any("I6" in v for v in ls.validate(st3, []))


def test_tune_and_legacy_iterations_do_not_require_diagnosis():
    # TUNE (parameter calibration) is not a structural edit → no diagnosis required
    st = ls.record_iteration(ls.create(".", "s", "q"), edit="raised rate", target="model",
                             margin_deltas={}, gate="fail", action="TUNE")
    assert not any("I6" in v for v in ls.validate(st, []))
    # legacy history entries carry no action → exempt (back-compat)
    st2 = ls.record_iteration(ls.create(".", "s", "q"), edit="old-style", target="model",
                              margin_deltas={}, gate="fail")
    assert not any("I6" in v for v in ls.validate(st2, []))


# --- one Investigation State: ledger folded in + trajectory as a derived render
#     (closed-loop streamlining #1: collapse the redundant persistence layers) ---

def test_record_note_folds_the_ledger_into_the_state():
    st = ls.create(".", "s", "q")
    assert st["log"] == []                                        # present, empty
    st = ls.record_note(st, kind="ruling", text="deferred push to user",
                        refs=["PR#28"])
    st = ls.record_note(st, kind="commit", text="feat: mechanism ladder", refs=["abc123"])
    kinds = [n["kind"] for n in st["log"]]
    assert kinds == ["ruling", "commit"]
    assert st["log"][0]["text"] == "deferred push to user" and st["log"][0]["refs"] == ["PR#28"]
    assert st["log"][0]["at_iteration"] == 0                      # stamped with the iteration
    import pytest
    with pytest.raises(ValueError):
        ls.record_note(st, kind="bogus", text="x")               # typed: unknown kind rejected


def test_to_trajectory_is_derived_from_the_state():
    st = ls.create(".", "adaptive", "Does it recruit across backgrounds?")
    tests = [{"name": "recruits_high", "pass_if": {"op": "in_range", "low": 0.35, "high": 1.0}}]
    st = ls.record_spike(st, expressible=True, artifact={"n_steps": 100})
    st = ls.advance(st, "AUDIT", audit={"gate": "pass"})
    st = ls.lock_tests(st, tests)
    st = ls.record_iteration(st, edit="install adaptive", target="model",
                             margin_deltas={"recruits_high": 0.4}, gate="pass",
                             action="MODIFY",
                             diagnosis={"hypotheses": ["saturation", "slow adaptation"],
                                        "discriminating_measure": "bg scan"})
    st = ls.record_note(st, kind="ruling", text="bands from measured numbers")
    traj = ls.to_trajectory(st)
    assert traj["schema"] == "model_build_trajectory/v2"
    assert traj["study"] == "adaptive" and traj["question"].startswith("Does it recruit")
    assert traj["spike"]["expressible"] is True
    assert traj["lock"]["tests_hash"] == ls.tests_hash(tests)
    assert traj["iterations"][0]["action"] == "MODIFY"           # history is the iteration log
    assert traj["log"][0]["kind"] == "ruling"
    # derived, not separately captured: rebuilding from the same state is identical
    assert ls.to_trajectory(st) == traj
