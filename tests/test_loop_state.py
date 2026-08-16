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
