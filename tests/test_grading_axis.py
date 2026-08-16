from viva_superpowers.study_evaluator import _expected_from_pass_if


def test_band_ops_map_to_band():
    for op in ("range", "in_range", "in_range_every_generation", "generation_average_in_range"):
        e = _expected_from_pass_if({"op": op, "low": 0.6, "high": 0.8}, op)
        assert e.kind == "band" and e.low == 0.6 and e.high == 0.8


def test_comparator_ops_map_to_value():
    assert _expected_from_pass_if({"op": "<=", "value": 5}, "<=") == \
        __import__("viva_superpowers.test_contract", fromlist=["value"]).value(5, op="<=")
    assert _expected_from_pass_if({"op": "max_le", "value": 5}, "max_le").op == "<="
    assert _expected_from_pass_if({"op": "min_ge", "threshold": 2}, "min_ge").op == ">="
    assert _expected_from_pass_if({"op": "at_most", "value": 5}, "at_most").op == "<="
    assert _expected_from_pass_if({"operator": "greater-than", "threshold": 2}, "greater-than").op == ">="


def test_tolerance_ops_map_to_value_approx():
    e = _expected_from_pass_if({"op": "==", "value": 2.0, "tolerance": 0.1}, "==")
    assert e.kind == "value" and e.op == "~=" and e.value == 2.0 and e.tol == 0.1
    m = _expected_from_pass_if({"op": "median_within_tolerance", "target": 60, "tolerance_fraction": 0.1},
                               "median_within_tolerance")
    assert m.op == "~=" and m.value == 60 and m.tol == 0.1
    cv = _expected_from_pass_if({"op": "cv_below", "cv_threshold": 0.2}, "cv_below")
    assert cv.op == "<=" and cv.value == 0.2


def test_categorical_ops_map_to_predicate():
    assert _expected_from_pass_if({"op": "in_set", "set": [1, 2]}, "in_set").kind == "predicate"
    assert _expected_from_pass_if({"op": "!=", "value": 0}, "!=").kind == "predicate"
    assert _expected_from_pass_if({"op": "exactly_one_initiation_per_generation"},
                                  "exactly_one_initiation_per_generation").kind == "predicate"


def test_unknown_op_returns_none():
    assert _expected_from_pass_if({"op": "ratio_at_most", "value": 1}, "ratio_at_most") is None
