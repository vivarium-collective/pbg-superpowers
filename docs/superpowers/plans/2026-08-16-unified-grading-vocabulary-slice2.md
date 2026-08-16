# Unified Grading Vocabulary (Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every code-graded `behavior_test` gains a signed margin + severity by grading its measured value through the shipped `test_contract.check`/`Expected` `/v2` contract — one grading grammar — without changing the `study.yaml` grammar or any PASS/FAIL consumer.

**Architecture:** `study_evaluator` keeps its measurement (`_resolve_series` + `_apply_window`) and its op-keyed grading (`_apply_op`, which stays authoritative for `result` + `measured_value`). A new pure step builds an `Expected` from `pass_if` and grades `measured_value` through `check()`, attaching the resulting `/v2` axis to the code outcome. Per-generation `measured_value` (a `{gen: value}` dict) is graded per generation and the worst generation's axis is kept.

**Tech Stack:** Python 3.11+, `viva_superpowers` package, pytest. `test_contract.check/value/band/predicate/Expected`, `test_vocab.RANK/normalize_verdict`.

**Spec:** `docs/superpowers/specs/2026-08-16-unified-grading-vocabulary-slice2-design.md`

## Global Constraints

- **Additive / non-breaking.** `study.yaml` `measure`/`pass_if` grammar unchanged. The code outcome keeps `result` / `measured_value` / `evaluated_by` / `operator` / `detail` exactly as today; it only *gains* an `axis` key. `result` and `measured_value` stay computed by `_apply_op` — the axis is added *consistently*, never re-derives `result`.
- **No new grading module.** All verdict/margin math goes through `test_contract.check`. Do not add a comparator registry.
- **Statistical comparators out of scope.** Do not touch `card_criteria` / `card_grade`; ttest/r2/pearson stay behind the `report_card_axis` workspace-evaluator seam.
- **Coverage never shrinks.** An op the map doesn't cover (or any error while building the axis) yields *no* `axis` key — the outcome is unchanged and still lands in whatever bucket it does today. Unknown kinds/ops still reach the agent bucket.
- **Determinism.** The `axis` carries no timestamp; it is content (safe to commit in `verdict.json`).
- **`severity` default `hard`** (a behavior test is an acceptance criterion); a test may set `severity: soft|directional`.

---

### Task 1: `verdict_to_result` projection helper in `test_vocab`

Adds the single documented mapping verdict → PASS/FAIL/SKIP, so the projection direction lives in one place (used by later renderers; documents §5).

**Files:**
- Modify: `viva_superpowers/test_vocab.py`
- Test: `tests/test_test_vocab.py`

**Interfaces:**
- Consumes: `normalize_verdict` (already in `test_vocab`).
- Produces: `verdict_to_result(verdict) -> "PASS" | "FAIL" | "SKIP"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_test_vocab.py` (create the file if absent, with `from viva_superpowers.test_vocab import verdict_to_result` at top):

```python
def test_verdict_to_result_maps_all_verdicts():
    from viva_superpowers.test_vocab import verdict_to_result
    assert verdict_to_result("within_tol") == "PASS"
    assert verdict_to_result("drift") == "PASS"        # a soft/directional warning still passes the gate
    assert verdict_to_result("mismatch") == "FAIL"
    assert verdict_to_result("ungraded") == "SKIP"
    assert verdict_to_result("pass") == "PASS"          # aliases normalize first
    assert verdict_to_result(None) == "SKIP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_vocab.py::test_verdict_to_result_maps_all_verdicts -v`
Expected: FAIL with `ImportError` / `cannot import name 'verdict_to_result'`.

- [ ] **Step 3: Write minimal implementation**

Add to `viva_superpowers/test_vocab.py` (after `display_status`):

```python
_RESULT = {"within_tol": "PASS", "drift": "PASS", "mismatch": "FAIL", "ungraded": "SKIP"}


def verdict_to_result(verdict) -> str:
    """Project a canonical verdict to the PASS/FAIL/SKIP a study test carries.
    ``drift`` (a soft/directional warning) still PASSES the gate; ``ungraded``
    (no gradable data) is SKIP."""
    return _RESULT[normalize_verdict(verdict)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_vocab.py::test_verdict_to_result_maps_all_verdicts -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_vocab.py tests/test_test_vocab.py
git commit -m "test_vocab: verdict_to_result (verdict -> PASS/FAIL/SKIP projection)"
```

---

### Task 2: `_expected_from_pass_if` — the pass_if → Expected map

The heart of the unification: translate a `pass_if` block into a `test_contract.Expected`, or `None` when the op has no scalar expectation.

**Files:**
- Modify: `viva_superpowers/study_evaluator.py`
- Test: `tests/test_grading_axis.py` (new)

**Interfaces:**
- Consumes: `test_contract.value`, `test_contract.band`, `test_contract.predicate`, `test_contract.Expected`.
- Produces: `_expected_from_pass_if(pass_if: dict, op: str) -> Expected | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grading_axis.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grading_axis.py -v`
Expected: FAIL with `cannot import name '_expected_from_pass_if'`.

- [ ] **Step 3: Write minimal implementation**

Add near the top of `viva_superpowers/study_evaluator.py` (after the imports; add the import line if `test_contract` is not already imported):

```python
from viva_superpowers.test_contract import Expected, band, predicate, value


def _num(pass_if: dict, *keys):
    """First present numeric among keys, or None."""
    for k in keys:
        v = pass_if.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _expected_from_pass_if(pass_if: dict, op: str) -> Expected | None:
    """Map a pass_if block to a test_contract.Expected, or None when the op has
    no scalar expectation this slice grades (it then yields no /v2 axis).

    Pure synonyms are folded in: at_most->'<=', at_least->'>=', and the
    ``operator: greater-than/less-than`` spelling. Aliases that need a new
    *measure* (e.g. ratio_at_most) are intentionally unmapped -> None."""
    o = (op or "").strip()
    # band
    if o in ("range", "in_range", "in_range_every_generation", "generation_average_in_range"):
        lo, hi = _num(pass_if, "low"), _num(pass_if, "high")
        return band(lo, hi) if lo is not None and hi is not None else None
    # comparators (+ extrema + pure synonyms + operator spelling)
    _LE = {"<=", "max_le", "at_most", "less-than-or-equal"}
    _LT = {"<", "max_lt", "less-than"}
    _GE = {">=", "min_ge", "at_least", "greater-than-or-equal"}
    _GT = {">", "min_gt", "greater-than"}
    spelled = pass_if.get("operator")
    if o in _LE or spelled in _LE:
        t = _num(pass_if, "value", "threshold")
        return value(t, op="<=") if t is not None else None
    if o in _LT or spelled in _LT:
        t = _num(pass_if, "value", "threshold")
        return value(t, op="<") if t is not None else None
    if o in _GE or spelled in _GE:
        t = _num(pass_if, "value", "threshold")
        return value(t, op=">=") if t is not None else None
    if o in _GT or spelled in _GT:
        t = _num(pass_if, "value", "threshold")
        return value(t, op=">") if t is not None else None
    # approx / tolerance
    if o in ("==", "eq", "equals"):
        t = _num(pass_if, "value", "target")
        tol = _num(pass_if, "tolerance")
        return value(t, op="~=", tol=tol if tol is not None else 0.05) if t is not None else None
    if o == "median_within_tolerance":
        t, tol = _num(pass_if, "target", "value"), _num(pass_if, "tolerance_fraction", "tolerance")
        return value(t, op="~=", tol=tol if tol is not None else 0.05) if t is not None else None
    if o == "periodic_doubling_every_generation":
        tol = _num(pass_if, "tolerance")
        return value(2.0, op="~=", tol=tol if tol is not None else 0.05)
    if o == "cv_below":
        t = _num(pass_if, "cv_threshold", "value")
        return value(t, op="<=") if t is not None else None
    if o == "rises_within_cycle":
        t = _num(pass_if, "min_fraction")
        return value(t, op=">=") if t is not None else None
    # categorical -> predicate (verdict only, no numeric margin)
    if o in ("in_set", "!=", "exactly_one_initiation_per_generation"):
        return predicate(o)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_grading_axis.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/study_evaluator.py tests/test_grading_axis.py
git commit -m "study_evaluator: _expected_from_pass_if (pass_if -> Expected map)"
```

---

### Task 3: `_grade_axis_from_outcome` — reduce measured_value + build the /v2 axis

Grades the code outcome's `measured_value` through `check()`. Scalar → graded directly; a per-generation `{gen: value}` dict → each generation graded, the **worst** (highest verdict rank, then smallest margin) kept with the full per-gen breakdown in `detail`.

**Files:**
- Modify: `viva_superpowers/study_evaluator.py`
- Test: `tests/test_grading_axis.py`

**Interfaces:**
- Consumes: `_expected_from_pass_if` (Task 2); `test_contract.check`; `test_vocab.RANK`.
- Produces: `_grade_axis_from_outcome(test: dict, pass_if: dict, op: str, outcome: dict) -> dict | None` (a `/v2` axis dict, or `None`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grading_axis.py`:

```python
from viva_superpowers.study_evaluator import _grade_axis_from_outcome


def _outcome(result, measured_value):
    return {"result": result, "measured_value": measured_value, "evaluated_by": "code"}


def test_scalar_band_axis_has_signed_margin():
    test = {"name": "atp", "description": "ATP fraction", "cites": ["Kurokawa 1999"],
            "measure": {"units": "fraction"}}
    ax = _grade_axis_from_outcome(test, {"op": "in_range", "low": 0.6, "high": 0.8}, "in_range",
                                  _outcome("FAIL", 0.54))
    assert ax["verdict"] == "mismatch"
    assert ax["margin"] == -0.06 or abs(ax["margin"] - (-0.06)) < 1e-9   # 0.54 - 0.6
    assert ax["severity"] == "hard" and ax["citation"] == "Kurokawa 1999"
    assert ax["units"] == "fraction" and ax["value"] == 0.54


def test_per_generation_keeps_worst_generation():
    test = {"name": "band_every_gen"}
    ax = _grade_axis_from_outcome(test, {"op": "in_range_every_generation", "low": 0.6, "high": 0.8},
                                  "in_range_every_generation",
                                  _outcome("FAIL", {"0": 0.7, "1": 0.5, "2": 0.72}))
    assert ax["verdict"] == "mismatch"                 # gen 1 (0.5) fails
    assert ax["value"] == 0.5                           # worst generation's value
    assert ax["detail"]["per_generation"] == {"0": 0.7, "1": 0.5, "2": 0.72}
    assert ax["detail"]["worst_generation"] == "1"


def test_predicate_axis_verdict_from_result():
    test = {"name": "seeds"}
    ok = _grade_axis_from_outcome(test, {"op": "in_set", "set": [4]}, "in_set", _outcome("PASS", 4))
    assert ok["verdict"] == "within_tol" and ok["margin"] is None
    bad = _grade_axis_from_outcome(test, {"op": "in_set", "set": [4]}, "in_set", _outcome("FAIL", 3))
    assert bad["verdict"] == "mismatch"


def test_soft_severity_flows_through():
    test = {"name": "s", "severity": "soft"}
    ax = _grade_axis_from_outcome(test, {"op": "<=", "value": 5}, "<=", _outcome("PASS", 3))
    assert ax["severity"] == "soft" and ax["verdict"] == "within_tol"


def test_unmapped_op_yields_no_axis():
    assert _grade_axis_from_outcome({"name": "x"}, {"op": "ratio_at_most", "value": 1},
                                    "ratio_at_most", _outcome("PASS", 0.5)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grading_axis.py -v -k grade_axis_from_outcome or worst or predicate_axis or soft_severity or unmapped`
Expected: FAIL with `cannot import name '_grade_axis_from_outcome'`.

- [ ] **Step 3: Write minimal implementation**

Add to `viva_superpowers/study_evaluator.py` (after `_expected_from_pass_if`; add `from viva_superpowers.test_contract import check` and `from viva_superpowers.test_vocab import RANK` to the imports):

```python
def _grade_axis_from_outcome(test: dict, pass_if: dict, op: str, outcome: dict) -> dict | None:
    """Build a report_card_verdict/v2 axis from a code outcome by grading its
    measured_value through test_contract.check. Returns None when the op has no
    scalar expectation (Task 2) — the outcome then simply carries no axis."""
    expected = _expected_from_pass_if(pass_if, op)
    if expected is None:
        return None
    name = test.get("name", "test")
    label = test.get("description") or name
    cites = test.get("cites") or []
    cite = "; ".join(str(c) for c in cites) or None
    units = (test.get("measure") or {}).get("units")
    common = dict(severity=test.get("severity", "hard"), cite=cite, units=units)
    mv = outcome.get("measured_value")

    if expected.kind == "predicate":
        # categorical: verdict comes from the code result, no numeric margin.
        v = "within_tol" if outcome.get("result") == "PASS" else "mismatch"
        return check(name, label, mv, expected, verdict=v, **common)

    if isinstance(mv, dict):
        # per-generation: grade each generation, keep the worst.
        graded = [(g, check(name, label, val, expected, **common))
                  for g, val in mv.items() if isinstance(val, (int, float))]
        if not graded:
            return None

        def _severity_key(ga):
            ax = ga[1]
            m = ax.get("margin")
            return (RANK.get(ax.get("verdict", "ungraded"), 0), -(m if m is not None else 0.0))

        g_worst, ax = max(graded, key=_severity_key)
        ax = dict(ax)
        ax["detail"] = {"per_generation": mv, "worst_generation": g_worst}
        return ax

    if isinstance(mv, (int, float)):
        return check(name, label, mv, expected, **common)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_grading_axis.py -v`
Expected: PASS (all Task 2 + Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/study_evaluator.py tests/test_grading_axis.py
git commit -m "study_evaluator: _grade_axis_from_outcome (measured_value -> /v2 axis)"
```

---

### Task 4: Attach the axis in `evaluate_test`

Wire the axis onto every code outcome, best-effort, without changing any other field.

**Files:**
- Modify: `viva_superpowers/study_evaluator.py` (the `evaluate_test` step-10 region, ~line 470-477)
- Test: `tests/test_grading_axis.py`

**Interfaces:**
- Consumes: `_grade_axis_from_outcome` (Task 3), the existing `_apply_op`.
- Produces: code outcomes from `evaluate_test` now carry an `axis` key when the op is mapped; every other field is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grading_axis.py` (uses the existing test suite's synthetic reader helpers; import the same `RunReader` stub the sibling `test_study_evaluator*` tests use — check `tests/conftest.py` / those tests for the fixture name and reuse it):

```python
def test_evaluate_test_attaches_axis_and_preserves_result(monkeypatch):
    import viva_superpowers.study_evaluator as se

    # Stub the measurement layer so the test is pure: _apply_op returns a known
    # code outcome; evaluate_test must attach the axis and keep result/measured_value.
    def fake_apply_op(windowed, pass_if, kind, op, config=None):
        return se._code_outcome("FAIL", 0.54, "derived/in_range", "0.54 below [0.6,0.8]")

    monkeypatch.setattr(se, "_resolve_series", lambda path, reader: object())
    monkeypatch.setattr(se, "_apply_window", lambda series, w: ("flat", object()))
    monkeypatch.setattr(se, "_is_empty_window", lambda windowed: False)
    monkeypatch.setattr(se, "_validate_window", lambda w: None)
    monkeypatch.setattr(se, "_apply_op", fake_apply_op)

    test = {"name": "atp", "description": "ATP fraction",
            "measure": {"kind": "derived", "formula": "x", "window": "full_lineage_from_gen_0"},
            "pass_if": {"op": "in_range", "low": 0.6, "high": 0.8}, "cites": ["Kurokawa 1999"]}
    out = se.evaluate_test(test, reader=object())
    assert out["result"] == "FAIL" and out["measured_value"] == 0.54   # unchanged
    assert out["evaluated_by"] == "code"
    assert out["axis"]["verdict"] == "mismatch"
    assert abs(out["axis"]["margin"] - (-0.06)) < 1e-9


def test_agent_bucket_has_no_axis(monkeypatch):
    import viva_superpowers.study_evaluator as se
    out = se.evaluate_test({"measure": {"kind": "totally_unknown"}}, reader=object())
    assert out["evaluated_by"] == "agent" and "axis" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grading_axis.py::test_evaluate_test_attaches_axis_and_preserves_result -v`
Expected: FAIL with `KeyError: 'axis'`.

- [ ] **Step 3: Write minimal implementation**

In `evaluate_test`, replace the step-10 block:

```python
    # 10. Reduce + predicate → outcome
    try:
        return _apply_op(windowed, pass_if, kind, op, config=config)
    except Exception as exc:  # noqa: BLE001
        return _agent(f"evaluation error: {exc}")
```

with:

```python
    # 10. Reduce + predicate → outcome, then attach the /v2 axis (best-effort).
    try:
        outcome = _apply_op(windowed, pass_if, kind, op, config=config)
    except Exception as exc:  # noqa: BLE001
        return _agent(f"evaluation error: {exc}")
    if outcome.get("evaluated_by") == "code":
        try:
            axis = _grade_axis_from_outcome(test, pass_if, op, outcome)
            if axis is not None:
                outcome["axis"] = axis
        except Exception:  # noqa: BLE001 — grading is enrichment; never fail the test on it
            pass
    return outcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_grading_axis.py -v`
Expected: PASS.

- [ ] **Step 5: Run the regression suites**

Run: `pytest tests/test_study_evaluator.py tests/test_evaluator_structural_ops.py tests/test_computed_outcomes.py -q` (run whichever of these exist; discover with `ls tests/ | grep -E 'study_evaluator|computed_outcomes|structural_ops'`).
Expected: PASS — `result` / `measured_value` unchanged; the new `axis` key is additive.

- [ ] **Step 6: Commit**

```bash
git add viva_superpowers/study_evaluator.py tests/test_grading_axis.py
git commit -m "study_evaluator: attach /v2 axis to code outcomes (margin + severity)"
```

---

### Task 5: Document the graded ops in the grammar doc

Records which `pass_if` ops now produce a `/v2` margin vs remain agent-bucket, so authors know which tests get graded feedback.

**Files:**
- Modify: `docs/concepts/expected-behavior-grammar.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the graded-ops note**

Add a subsection to `docs/concepts/expected-behavior-grammar.md` (near the `pass_if` op list):

```markdown
### Graded feedback (report_card_verdict/v2)

Ops in the closed set now grade to a **signed margin + severity** (a `/v2` axis
attached to the outcome as `axis`), not just PASS/FAIL — an agent sees *how far*
a test is from passing. Band + comparator + tolerance ops (`in_range`, `<=`,
`>=`, `==`, `max_le`, `min_ge`, `cv_below`, `median_within_tolerance`,
`periodic_doubling_every_generation`, `rises_within_cycle`) carry a numeric
margin; categorical ops (`in_set`, `!=`, `exactly_one_initiation_per_generation`)
carry a verdict only (`margin: null`). Per-generation ops report the **worst
generation's** margin, with the per-generation breakdown under `axis.detail`.

Ops/kinds outside the closed set (e.g. `ratio_at_most`, `xy_correlation`) still
fall to the agent bucket and carry no `axis` — implementing them is a later
(measurement-layer) slice.
```

- [ ] **Step 2: Commit**

```bash
git add docs/concepts/expected-behavior-grammar.md
git commit -m "docs: note graded /v2 feedback for the closed pass_if op set"
```

---

### Task 6: Persist the axis in `runs[].outcomes` (vivarium-workbench)

`study_evaluator` now produces an `axis`, but the dashboard's outcome writer
cherry-picks a fixed set of fields, so the axis is dropped before it reaches
`runs[].outcomes`. Add `axis` to the persisted set so the margin survives to the
consumers (and a later margin-bar render). **This task is in the `vivarium-workbench`
repo, and depends on a viva-superpowers release that includes Tasks 1-4** (re-lock
its `viva-superpowers` pin first — both the `viva-superpowers` and `pbg-superpowers`
git sources share the URL, so `uv lock --upgrade-package viva-superpowers
--upgrade-package pbg-superpowers`).

**Files:**
- Modify: `vivarium_workbench/lib/auto_evaluate.py` (the `_write_outcomes` field loop, ~line 54)
- Test: `vivarium-workbench` `tests/test_behavior_test_card.py` or a new `tests/test_auto_evaluate_axis.py`

**Interfaces:**
- Consumes: the `axis` key produced by `study_evaluator.evaluate_test` (Tasks 3-4).
- Produces: `runs[].outcomes[name]["axis"]` persisted when present.

- [ ] **Step 1: Write the failing test**

Create `vivarium-workbench/tests/test_auto_evaluate_axis.py`:

```python
from vivarium_workbench.lib.auto_evaluate import _build_outcome_entry  # the entry builder near line 40


def test_outcome_entry_preserves_axis():
    raw = {"result": "FAIL", "measured_value": 0.54, "evaluated_by": "code",
           "detail": "below band", "axis": {"verdict": "mismatch", "margin": -0.06}}
    entry = _build_outcome_entry(raw, existing=None)   # match the real builder's name/signature
    assert entry["result"] == "FAIL"
    assert entry["axis"] == {"verdict": "mismatch", "margin": -0.06}
```

(Adjust the imported function name/signature to the actual builder in
`auto_evaluate.py` — the function around line 40 that assembles `entry` and loops
over `("measured_value", "detail", "operator", "evaluated_by")`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_evaluate_axis.py -v`
Expected: FAIL — `axis` not in `entry`.

- [ ] **Step 3: Write minimal implementation**

In `vivarium_workbench/lib/auto_evaluate.py`, add `"axis"` to the preserved-field tuple:

```python
    for key in ("measured_value", "detail", "operator", "evaluated_by", "axis"):
        if raw_map.get(key) is not None:
            entry[key] = raw_map[key]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auto_evaluate_axis.py -v`
Expected: PASS.

- [ ] **Step 5: Run the outcome-writer regression**

Run: `pytest tests/test_behavior_test_card.py tests/ -k "auto_evaluate or outcomes" -q`
Expected: PASS (axis is additive; existing fields unchanged).

- [ ] **Step 6: Commit**

```bash
git add vivarium_workbench/lib/auto_evaluate.py tests/test_auto_evaluate_axis.py
git commit -m "auto_evaluate: persist the /v2 axis in runs[].outcomes"
```

---

## Notes for the executor

**This plan spans two repos.** Tasks 1-5 are in `viva-superpowers`
(`/Users/eranagmon/code/viva-superpowers--grading-vocab`); Task 6 is in
`vivarium-workbench` and depends on a merged+released Tasks 1-4. Execute 1-5,
merge, then re-lock vivarium-workbench onto the new viva-superpowers rev and do
Task 6.

- **Run tests with a full venv.** `study_evaluator` transitively imports
  `viva_workspace` (via `study_outcomes`) and `process_bigraph`/`viva_emitters`
  (via `post_sim`, only if imported). Use a venv that has them, e.g.
  `/Users/eranagmon/code/v2ecoli/.venv/bin/python` with
  `PYTHONPATH=<worktree>:/Users/eranagmon/code/viva-workspace` prepended, or the
  CI environment. `test_contract` / `test_vocab` themselves are stdlib-only.
- **`_apply_op` internals are out of scope.** Do not change how `result` or
  `measured_value` are computed — only read them. If a per-gen op returns a
  `measured_value` that is NOT a `{gen: value}` dict, `_grade_axis_from_outcome`
  grades it as a scalar (or returns `None`); that is correct and safe.
- **Import placement:** put the `test_contract` / `test_vocab` imports at module
  top with the other `viva_superpowers.*` imports; they are light (no
  `process_bigraph`).
