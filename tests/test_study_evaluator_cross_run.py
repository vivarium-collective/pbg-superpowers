"""Stage 2 (issue #98): cross-run assertions (run_delta + given.compare_to)."""
from __future__ import annotations

import polars as pl

from viva_superpowers import study_evaluator as se


class FakeReader:
    def __init__(self, data: dict[str, pl.DataFrame]):
        self._data = data

    def series(self, name: str) -> pl.DataFrame:
        if name not in self._data:
            raise KeyError(name)
        return self._data[name]

    def observables(self) -> list[str]:
        return sorted(self._data)


def _series(times: list[float], values: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"generation": 0, "time": float(t), "abs_time": float(t), "value": float(v)}
         for t, v in zip(times, values)],
        schema={"generation": pl.Int64, "time": pl.Float64,
                "abs_time": pl.Float64, "value": pl.Float64},
    )


# ── _run_delta (pure computation) ────────────────────────────────────────────

def test_run_delta_identical_is_zero():
    a = _series([0, 1, 2, 3], [1, 2, 3, 4])
    assert se._run_delta(a, a, "time", "max_abs_diff") == 0.0


def test_run_delta_constant_offset_max():
    a = _series([0, 1, 2, 3], [1, 2, 3, 4])
    b = _series([0, 1, 2, 3], [1.1, 2.1, 3.1, 4.1])
    assert abs(se._run_delta(a, b, "time", "max_abs_diff") - 0.1) < 1e-9


def test_run_delta_time_align_interpolates_onto_shared_grid():
    # both lie on value == abs_time; compare is coarser but interpolates exactly
    a = _series([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    b = _series([0, 2, 4], [0, 2, 4])
    assert se._run_delta(a, b, "time", "max_abs_diff") < 1e-9


def test_run_delta_metrics():
    a = _series([0, 1, 2], [0, 0, 0])
    b = _series([0, 1, 2], [0, 3, 4])   # diffs: 0, 3, 4
    assert se._run_delta(a, b, "index", "max_abs_diff") == 4.0
    assert se._run_delta(a, b, "index", "final_abs_diff") == 4.0
    assert abs(se._run_delta(a, b, "index", "mean_abs_diff") - (7 / 3)) < 1e-9
    assert abs(se._run_delta(a, b, "index", "rmse") - (25 / 3) ** 0.5) < 1e-9


def test_run_delta_non_overlapping_time_is_none():
    a = _series([0, 1, 2], [1, 1, 1])
    b = _series([10, 11, 12], [1, 1, 1])
    assert se._run_delta(a, b, "time", "max_abs_diff") is None


# ── _evaluate_run_delta via evaluate_test ────────────────────────────────────

def _xrun_test(metric="max_abs_diff", tol=0.05):
    return {
        "name": "do-converges",
        "given": {"compare_to": {"run": "baseline"}},
        "measure": {"kind": "run_delta", "of": {"readout": "obs.do"},
                    "align": "time", "metric": metric},
        "pass_if": {"op": "<", "value": tol},
    }


def test_run_delta_evaluate_pass():
    primary = FakeReader({"obs.do": _series([0, 1, 2], [5.0, 5.0, 5.0])})
    compare = FakeReader({"obs.do": _series([0, 1, 2], [5.0, 5.01, 4.99])})
    out = se.evaluate_test(_xrun_test(), primary, run_opener=lambda sel: compare)
    assert out["result"] == "PASS" and out["evaluated_by"] == "code"


def test_run_delta_evaluate_fail():
    primary = FakeReader({"obs.do": _series([0, 1, 2], [5.0, 5.0, 5.0])})
    compare = FakeReader({"obs.do": _series([0, 1, 2], [5.0, 5.2, 4.8])})
    out = se.evaluate_test(_xrun_test(), primary, run_opener=lambda sel: compare)
    assert out["result"] == "FAIL"


def test_run_delta_without_opener_needs_rerun():
    primary = FakeReader({"obs.do": _series([0, 1], [1, 1])})
    out = se.evaluate_test(_xrun_test(), primary, run_opener=None)
    assert out["evaluated_by"] == "needs_rerun"


def test_run_delta_without_compare_to_routes_to_agent():
    primary = FakeReader({"obs.do": _series([0, 1], [1, 1])})
    test = _xrun_test()
    test["given"] = {}
    out = se.evaluate_test(test, primary, run_opener=lambda sel: primary)
    assert out["evaluated_by"] == "agent"


def test_run_delta_unresolvable_compare_routes_to_agent():
    primary = FakeReader({"obs.do": _series([0, 1], [1, 1])})
    out = se.evaluate_test(_xrun_test(), primary, run_opener=lambda sel: None)
    assert out["evaluated_by"] == "agent"
