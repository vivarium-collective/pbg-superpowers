# Tests Foundation (Slice 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the pure, greenfield foundation of the Tests-as-Agent-Feedback system to `viva_superpowers`: the centralized verdict **vocabulary**, the typed **check/axis contract** (`Expected` + `check()` + `TestBuilder` → `report_card_verdict/v2`), and the cross-iteration **diff** — three self-contained, fully-tested modules that every later slice imports.

**Architecture:** Three new pure-Python modules under `viva_superpowers/` with no process-bigraph or vivarium_workbench import (so `study_audit.py` and any agent can import them). They are purely additive — they move nothing and change no existing file — so back-compat is automatic. Later slices (1b: grading move + `post_sim` rename + `TestReportStep`; 2: v2ecoli; 3: workbench) build on these.

**Tech Stack:** Python 3.12, stdlib only (`dataclasses`, `math`, `json`), pytest. Package `viva-superpowers`; tests in `tests/`, run with `pytest` (testpaths=["tests"]).

**Spec:** `docs/superpowers/specs/2026-08-15-tests-as-agent-feedback-design.md`

## Global Constraints

- **Vocabulary is immutable:** canonical verdicts are exactly `("within_tol", "drift", "mismatch", "ungraded")`. Never introduce a conflicting top-level `status`.
- **Contract lives in `viva_superpowers`/stdlib only** — these modules MUST NOT import `vivarium_workbench` or `process_bigraph` (the audit path imports them).
- **Additive `/v2`:** `report_card_verdict/v2` is `/v1` plus optional axis fields (`expected, margin, severity, units, knob, citation`); a `/v1` reader (reads only `overall` + `groups.*.verdict` + `axes.*.{id,label,verdict,value,meter,detail}`) must see `/v2` unchanged.
- **JSON safety:** non-finite floats serialize to `null`; callers use `allow_nan=False`. Provide and use a `sanitize()` helper.
- **verdict↔agent semantics:** `within_tol=pass`, `mismatch=fail`, `drift=warn/directional`, `ungraded=no-data`.
- **Severity values:** exactly `("hard", "soft", "directional")`, default `"hard"`.

---

### Task 1: `test_vocab.py` — the single home for verdict vocabulary

**Files:**
- Create: `viva_superpowers/test_vocab.py`
- Test: `tests/test_test_vocab.py`

**Interfaces:**
- Produces:
  - `CANONICAL: tuple = ("within_tol", "drift", "mismatch", "ungraded")`
  - `COLOR: dict`, `GLYPH: dict`, `RANK: dict` (severity rank; `mismatch=3 > drift=2 > within_tol=1 > ungraded=0`)
  - `SEVERITY: tuple = ("hard", "soft", "directional")`
  - `normalize_verdict(v: str | None) -> str` — maps aliases (`PASS/passed/pass/ok→within_tol`, `FAIL/failed/fail/mismatch→mismatch`, `PARTIAL/drift/warn→drift`, `SKIP/PENDING/GAP/ungraded/None/""→ungraded`), case-insensitive; unknown → `ungraded`.
  - `worst(verdicts: iterable[str]) -> str` — the max by `RANK` after normalize (empty → `ungraded`).
  - `agent_status(verdict: str) -> str` — `within_tol→"pass"`, `mismatch→"fail"`, `drift→"warn"`, `ungraded→"no-data"`.
  - `display_status(verdict: str) -> str` — four-value display: `within_tol→"met"`, `drift→"conditional-pass"`, `mismatch→"not met"`, `ungraded→"not assessable"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_vocab.py
import pytest
from viva_superpowers import test_vocab as v

def test_canonical_set_is_exact():
    assert v.CANONICAL == ("within_tol", "drift", "mismatch", "ungraded")
    assert v.SEVERITY == ("hard", "soft", "directional")

@pytest.mark.parametrize("raw,expected", [
    ("PASS", "within_tol"), ("passed", "within_tol"), ("pass", "within_tol"), ("ok", "within_tol"),
    ("FAIL", "mismatch"), ("failed", "mismatch"), ("mismatch", "mismatch"),
    ("PARTIAL", "drift"), ("drift", "drift"), ("warn", "drift"),
    ("SKIP", "ungraded"), ("PENDING", "ungraded"), ("GAP", "ungraded"),
    ("within_tol", "within_tol"), (None, "ungraded"), ("", "ungraded"), ("bogus", "ungraded"),
])
def test_normalize_verdict(raw, expected):
    assert v.normalize_verdict(raw) == expected

def test_worst():
    assert v.worst(["within_tol", "drift", "mismatch"]) == "mismatch"
    assert v.worst(["within_tol", "within_tol"]) == "within_tol"
    assert v.worst([]) == "ungraded"
    assert v.worst(["PASS", "FAIL"]) == "mismatch"   # normalizes first

def test_agent_and_display_status():
    assert v.agent_status("within_tol") == "pass"
    assert v.agent_status("mismatch") == "fail"
    assert v.agent_status("drift") == "warn"
    assert v.agent_status("ungraded") == "no-data"
    assert v.display_status("within_tol") == "met"
    assert v.display_status("mismatch") == "not met"
    assert v.display_status("drift") == "conditional-pass"
    assert v.display_status("ungraded") == "not assessable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_vocab.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'viva_superpowers.test_vocab'`

- [ ] **Step 3: Write minimal implementation**

```python
# viva_superpowers/test_vocab.py
"""Single home for the report-card / test verdict vocabulary and its mappings.

Canonical verdicts are ``within_tol | drift | mismatch | ungraded``; this module
owns them plus the alias-normalization, worst-of rollup, and the two projection
maps (agent semantics and four-value display) that were previously duplicated
across v2ecoli.library.report_card, workbench study_spec/study_page/conclusion_card.
Pure stdlib; no process_bigraph / vivarium_workbench import.
"""
from __future__ import annotations

CANONICAL = ("within_tol", "drift", "mismatch", "ungraded")
SEVERITY = ("hard", "soft", "directional")

COLOR = {"within_tol": "#1a7f37", "drift": "#ef6c00",
         "mismatch": "#c62828", "ungraded": "#757575"}
GLYPH = {"within_tol": "✓", "drift": "≈", "mismatch": "✗", "ungraded": "–"}
RANK = {"mismatch": 3, "drift": 2, "within_tol": 1, "ungraded": 0}

_ALIASES = {
    "within_tol": "within_tol", "pass": "within_tol", "passed": "within_tol",
    "ok": "within_tol", "met": "within_tol", "passing": "within_tol",
    "mismatch": "mismatch", "fail": "mismatch", "failed": "mismatch",
    "failing": "mismatch", "not met": "mismatch",
    "drift": "drift", "partial": "drift", "warn": "drift",
    "conditional-pass": "drift", "conditional_pass": "drift",
    "ungraded": "ungraded", "skip": "ungraded", "skipped": "ungraded",
    "pending": "ungraded", "gap": "ungraded", "not assessable": "ungraded",
}
_AGENT = {"within_tol": "pass", "mismatch": "fail", "drift": "warn", "ungraded": "no-data"}
_DISPLAY = {"within_tol": "met", "mismatch": "not met",
            "drift": "conditional-pass", "ungraded": "not assessable"}


def normalize_verdict(v):
    if not v:
        return "ungraded"
    return _ALIASES.get(str(v).strip().lower(), "ungraded")


def worst(verdicts):
    w = "ungraded"
    for v in verdicts:
        n = normalize_verdict(v)
        if RANK[n] > RANK[w]:
            w = n
    return w


def agent_status(verdict):
    return _AGENT[normalize_verdict(verdict)]


def display_status(verdict):
    return _DISPLAY[normalize_verdict(verdict)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_vocab.py -q`
Expected: PASS (10+ cases)

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_vocab.py tests/test_test_vocab.py
git commit -m "feat(vocab): centralize verdict vocabulary in viva_superpowers.test_vocab"
```

---

### Task 2: `test_contract.py` — `Expected` + `check()` (the graded axis)

**Files:**
- Create: `viva_superpowers/test_contract.py`
- Test: `tests/test_test_contract.py`

**Interfaces:**
- Consumes: `viva_superpowers.test_vocab` (`normalize_verdict`).
- Produces:
  - `@dataclass(frozen=True) Expected(kind, value=None, low=None, high=None, op="~=", tol=0.05, statement=None)` with `to_dict()`.
  - `value(target, op="~=", tol=0.05) -> Expected` (kind="value"); `band(low, high) -> Expected` (kind="band"); `predicate(statement) -> Expected` (kind="predicate").
  - `sanitize(obj)` — recursively replace non-finite floats with `None`.
  - `check(id, label, observed, expected, *, severity="hard", units=None, knob=None, cite=None, detail=None, verdict=None) -> dict` — a `report_card_verdict/v2` **axis dict**: keys `id, label, verdict, value, meter, detail, expected, margin, severity, units, knob, citation`. Computes `margin` + `verdict` per `expected.kind` (see algorithm below); `meter` is a 0..1 display clamp derived from margin; `value` = `observed`. For `kind="predicate"` or non-numeric `observed`, `margin=None` and the caller-supplied `verdict` is used (default `ungraded` if omitted).

**Margin/verdict algorithm (implement exactly):**
- `band`: `margin = min(observed - low, high - observed)`; `verdict = within_tol if margin >= 0 else mismatch`.
- `value` + `op="~="` (rel tol `t`): `margin = t*abs(target) - abs(observed - target)`; `within_tol` iff `>= 0` else `mismatch`. (If `target == 0`, use absolute tol `t`.)
- `value` + `op in {"<=","<"}`: `margin = target - observed` (for `<`, strict: fail on `== target`); `within_tol` iff pass.
- `value` + `op in {">=",">"}`: `margin = observed - target`; `within_tol` iff pass.
- `value` + `op="=="`: `margin = -abs(observed - target)`; `within_tol` iff `observed == target`.
- `severity="directional"`: never emit `mismatch`; a failing margin yields `drift` (records the gradient without gating).
- `meter`: `max(0.0, min(1.0, 0.5 + margin_scaled))` where `margin_scaled = margin / (abs(target or high or low or 1) or 1) ` clamped — a monotone display bar; exact clamp in code below.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_contract.py
import math
from viva_superpowers.test_contract import Expected, value, band, predicate, check, sanitize

def test_band_inside_edge_outside():
    a = check("flux", "Acetate flux", 3.2, band(2.5, 4.0), units="mM/h", cite="Nanchen2006")
    assert a["verdict"] == "within_tol"
    assert a["value"] == 3.2 and a["units"] == "mM/h" and a["citation"] == "Nanchen2006"
    assert math.isclose(a["margin"], 0.8)          # min(3.2-2.5, 4.0-3.2)=0.8
    edge = check("f", "f", 2.5, band(2.5, 4.0))
    assert edge["verdict"] == "within_tol" and math.isclose(edge["margin"], 0.0)
    out = check("f", "f", 5.0, band(2.5, 4.0))
    assert out["verdict"] == "mismatch" and out["margin"] < 0

def test_value_reltol():
    a = check("g", "g", 1.02, value(1.0, tol=0.05))   # |1.02-1|=0.02 <= 0.05
    assert a["verdict"] == "within_tol" and a["margin"] > 0
    b = check("g", "g", 1.10, value(1.0, tol=0.05))
    assert b["verdict"] == "mismatch"

def test_value_comparison_ops():
    assert check("n", "n", 3, value(1, op=">="))["verdict"] == "within_tol"
    assert check("n", "n", 0, value(1, op=">="))["verdict"] == "mismatch"
    assert check("n", "n", 1, value(2, op="<="))["verdict"] == "within_tol"

def test_directional_never_mismatch():
    a = check("d", "d", 5.0, band(0.0, 1.0), severity="directional")
    assert a["verdict"] == "drift" and a["margin"] < 0 and a["severity"] == "directional"

def test_predicate_uses_caller_verdict():
    a = check("p", "p", "n/a", predicate("cell divides"), verdict="within_tol")
    assert a["verdict"] == "within_tol" and a["margin"] is None
    b = check("p", "p", None, predicate("x"))
    assert b["verdict"] == "ungraded" and b["margin"] is None

def test_axis_has_all_v2_keys_and_expected_roundtrips():
    a = check("k", "K", 1.0, band(0.0, 2.0), knob=["kcat"], detail="obs")
    for key in ("id","label","verdict","value","meter","detail","expected","margin","severity","units","knob","citation"):
        assert key in a
    assert a["expected"] == {"kind":"band","value":None,"low":0.0,"high":2.0,"op":"~=","tol":0.05,"statement":None}
    assert a["knob"] == ["kcat"]

def test_sanitize_nonfinite():
    assert sanitize({"m": float("nan"), "xs": [float("inf"), 1.0]}) == {"m": None, "xs": [None, 1.0]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'viva_superpowers.test_contract'`

- [ ] **Step 3: Write minimal implementation**

```python
# viva_superpowers/test_contract.py
"""Typed check/axis contract for report_card_verdict/v2.

`check()` produces one v2 axis dict (v1 axis fields plus expected/margin/severity/
knob/citation) with a computed verdict + signed margin. Pure stdlib; the axis dict
is exactly what verdict_json/TestBuilder embed under groups[g]['axes'].
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict

from viva_superpowers.test_vocab import normalize_verdict


@dataclass(frozen=True)
class Expected:
    kind: str                       # "value" | "band" | "predicate"
    value: float | None = None
    low: float | None = None
    high: float | None = None
    op: str = "~="
    tol: float = 0.05
    statement: str | None = None
    def to_dict(self) -> dict:
        return asdict(self)


def value(target, op="~=", tol=0.05) -> Expected:
    return Expected(kind="value", value=float(target), op=op, tol=float(tol))

def band(low, high) -> Expected:
    return Expected(kind="band", low=float(low), high=float(high))

def predicate(statement) -> Expected:
    return Expected(kind="predicate", statement=str(statement))


def sanitize(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def _margin(observed: float, e: Expected):
    if e.kind == "band":
        return min(observed - e.low, e.high - observed)
    # kind == "value"
    t, target, op = e.tol, e.value, e.op
    if op == "~=":
        scale = abs(target) if target != 0 else 1.0
        return t * scale - abs(observed - target)
    if op in ("<=", "<"):
        return target - observed
    if op in (">=", ">"):
        return observed - target
    if op == "==":
        return -abs(observed - target)
    raise ValueError(f"unknown op {op!r}")


def _passes(margin: float, e: Expected) -> bool:
    if e.kind == "value" and e.op in ("<", ">"):
        return margin > 0          # strict
    return margin >= 0


def _meter(margin: float, e: Expected):
    ref = abs(e.value or e.high or e.low or 1.0) or 1.0
    return max(0.0, min(1.0, 0.5 + margin / (2.0 * ref)))


def check(id, label, observed, expected: Expected, *, severity="hard",
          units=None, knob=None, cite=None, detail=None, verdict=None) -> dict:
    margin = None
    meter = None
    if expected.kind != "predicate" and isinstance(observed, (int, float)):
        obs = float(observed)
        margin = _margin(obs, expected)
        passed = _passes(margin, expected)
        if passed:
            v = "within_tol"
        elif severity == "directional":
            v = "drift"
        else:
            v = "mismatch"
        meter = _meter(margin, expected)
    else:
        v = normalize_verdict(verdict)
    return {
        "id": id, "label": label, "verdict": v,
        "value": observed, "meter": meter, "detail": detail,
        "expected": expected.to_dict(), "margin": margin,
        "severity": severity, "units": units,
        "knob": list(knob) if knob else None, "citation": cite,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_contract.py tests/test_test_contract.py
git commit -m "feat(contract): Expected + check() graded v2 axis in viva_superpowers"
```

---

### Task 3: `TestBuilder` — assemble axes into a `report_card_verdict/v2` doc

**Files:**
- Modify: `viva_superpowers/test_contract.py` (append `TestBuilder`)
- Test: `tests/test_test_builder.py`

**Interfaces:**
- Consumes: `check()` axis dicts (Task 2); `viva_superpowers.test_vocab.worst`.
- Produces: `class TestBuilder(model_ref="", reference_model="", generated="")` with:
  - `.add(group: str, axis: dict) -> TestBuilder` (chainable; `axis` is a `check()` result).
  - `.build() -> dict` — a `report_card_verdict/v2` doc: `{schema:"report_card_verdict/v2", model_ref, reference_model, generated, overall, groups:{gslug:{verdict, axes:[...]}}}`. `gslug` = `group.strip().lower().replace("&","and").replace(" ","_")` (matches the existing `_slug_group`). Each group's `verdict` = `worst` of its axes; `overall` = `worst` of all axes. Output is `sanitize()`-d.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_builder.py
from viva_superpowers.test_contract import TestBuilder, check, band, value

def test_builder_groups_and_overall():
    doc = (TestBuilder(model_ref="m@abc")
           .add("Exchange fluxes", check("ac", "Acetate", 3.2, band(2.5, 4.0)))
           .add("Exchange fluxes", check("glc", "Glucose", 9.0, value(10.0, tol=0.05)))  # |9-10|=1 > 0.5 -> mismatch
           .add("Growth", check("mu", "Growth rate", 0.6, band(0.5, 0.9)))
           .build())
    assert doc["schema"] == "report_card_verdict/v2"
    assert doc["model_ref"] == "m@abc"
    assert set(doc["groups"]) == {"exchange_fluxes", "growth"}
    assert doc["groups"]["exchange_fluxes"]["verdict"] == "mismatch"   # worst of {within_tol, mismatch}
    assert doc["groups"]["growth"]["verdict"] == "within_tol"
    assert doc["overall"] == "mismatch"
    assert len(doc["groups"]["exchange_fluxes"]["axes"]) == 2
    assert doc["groups"]["exchange_fluxes"]["axes"][0]["id"] == "ac"

def test_builder_v1_reader_compatibility():
    # A v1 reader only touches overall + groups[g].verdict + axes[i].{id,label,verdict,value,meter,detail}
    doc = TestBuilder().add("G", check("a", "A", 1.0, band(0.0, 2.0))).build()
    ax = doc["groups"]["g"]["axes"][0]
    for k in ("id", "label", "verdict", "value", "meter", "detail"):
        assert k in ax
    assert doc["overall"] in ("within_tol", "drift", "mismatch", "ungraded")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_builder.py -q`
Expected: FAIL — `ImportError: cannot import name 'TestBuilder'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to viva_superpowers/test_contract.py
from viva_superpowers.test_vocab import worst as _worst


def _slug_group(label: str) -> str:
    return (label or "ungrouped").strip().lower().replace("&", "and").replace(" ", "_")


class TestBuilder:
    """Accumulate check() axes into a report_card_verdict/v2 document."""

    def __init__(self, model_ref="", reference_model="", generated=""):
        self.model_ref = model_ref
        self.reference_model = reference_model
        self.generated = generated
        self._groups: dict[str, list] = {}

    def add(self, group: str, axis: dict) -> "TestBuilder":
        self._groups.setdefault(_slug_group(group), []).append(axis)
        return self

    def build(self) -> dict:
        groups = {}
        all_verdicts = []
        for gslug, axes in self._groups.items():
            vs = [a.get("verdict", "ungraded") for a in axes]
            groups[gslug] = {"verdict": _worst(vs), "axes": axes}
            all_verdicts.extend(vs)
        return sanitize({
            "schema": "report_card_verdict/v2",
            "model_ref": self.model_ref,
            "reference_model": self.reference_model,
            "generated": self.generated,
            "overall": _worst(all_verdicts),
            "groups": groups,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_builder.py tests/test_test_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_contract.py tests/test_test_builder.py
git commit -m "feat(contract): TestBuilder assembles check() axes into report_card_verdict/v2"
```

---

### Task 4: `test_diff.py` — cross-iteration diff (the iteration signal)

**Files:**
- Create: `viva_superpowers/test_diff.py`
- Test: `tests/test_test_diff.py`

**Interfaces:**
- Consumes: `viva_superpowers.test_vocab` (`normalize_verdict`); axis dicts carrying `verdict` + `margin` (Task 2/3 output).
- Produces:
  - `diff_reports(prev: dict, curr: dict) -> dict` where `prev`/`curr` are **card maps** `{card_name: verdict_doc}` (each `verdict_doc` a `report_card_verdict/v1|v2` doc with `groups[g].axes[]`). Returns:
    `{schema:"test_diff/v1", per:[{card, group, id, prev, curr, change, margin_delta}], rollup:{fixed, broke, improved, regressed, new, gone, unchanged}}`.
  - `change` per keyed axis `(card, group, id)`:
    - not in prev → `"new"`; not in curr → `"gone"`;
    - `mismatch → within_tol` = `"fixed"`; `within_tol → mismatch` = `"broke"`;
    - same normalized verdict, `margin` increased = `"improved"`, decreased = `"regressed"`, equal/unknown = `"unchanged"`;
    - any other verdict transition uses margin sign if available else `"unchanged"`.
  - `margin_delta = curr.margin - prev.margin` when both numeric, else `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_diff.py
from viva_superpowers.test_diff import diff_reports

def _doc(axes):  # axes: list of (group, id, verdict, margin)
    groups = {}
    for g, i, v, m in axes:
        groups.setdefault(g, {"verdict": v, "axes": []})["axes"].append(
            {"id": i, "label": i, "verdict": v, "margin": m})
    return {"schema": "report_card_verdict/v2", "overall": "ungraded", "groups": groups}

def test_diff_transitions():
    prev = {"card": _doc([
        ("g", "a", "mismatch", -1.0),   # will fix
        ("g", "b", "within_tol", 0.2),  # will break
        ("g", "c", "within_tol", 0.1),  # will improve
        ("g", "d", "within_tol", 0.5),  # will regress
        ("g", "e", "within_tol", 0.3),  # will go away
    ])}
    curr = {"card": _doc([
        ("g", "a", "within_tol", 0.4),
        ("g", "b", "mismatch", -0.2),
        ("g", "c", "within_tol", 0.6),
        ("g", "d", "within_tol", 0.2),
        ("g", "f", "within_tol", 0.9),  # new
    ])}
    d = diff_reports(prev, curr)
    got = {(p["id"]): p["change"] for p in d["per"]}
    assert got == {"a": "fixed", "b": "broke", "c": "improved",
                   "d": "regressed", "e": "gone", "f": "new"}
    assert d["rollup"] == {"fixed": 1, "broke": 1, "improved": 1,
                           "regressed": 1, "new": 1, "gone": 1, "unchanged": 0}
    a = next(p for p in d["per"] if p["id"] == "a")
    assert a["margin_delta"] == 1.4   # 0.4 - (-1.0)

def test_diff_empty_prev():
    curr = {"card": _doc([("g", "a", "within_tol", 0.1)])}
    d = diff_reports({}, curr)
    assert d["per"][0]["change"] == "new" and d["rollup"]["new"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_diff.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'viva_superpowers.test_diff'`

- [ ] **Step 3: Write minimal implementation**

```python
# viva_superpowers/test_diff.py
"""Cross-iteration diff of two card-maps ({card_name: verdict_doc}).

The iteration signal a model-building agent reads: for each keyed axis
(card, group, id) it reports fixed/broke/improved/regressed/new/gone/unchanged
plus the signed margin delta. Pure stdlib.
"""
from __future__ import annotations

from viva_superpowers.test_vocab import normalize_verdict

_CHANGES = ("fixed", "broke", "improved", "regressed", "new", "gone", "unchanged")


def _index(card_map):
    """(card, group, id) -> {'verdict','margin'} over a {card: verdict_doc} map."""
    out = {}
    for card, doc in (card_map or {}).items():
        for gslug, grp in (doc.get("groups") or {}).items():
            for ax in grp.get("axes") or []:
                out[(card, gslug, ax.get("id"))] = {
                    "verdict": normalize_verdict(ax.get("verdict")),
                    "margin": ax.get("margin"),
                }
    return out


def _classify(prev, curr):
    if prev is None:
        return "new"
    if curr is None:
        return "gone"
    pv, cv = prev["verdict"], curr["verdict"]
    if pv == "mismatch" and cv == "within_tol":
        return "fixed"
    if pv == "within_tol" and cv == "mismatch":
        return "broke"
    pm, cm = prev["margin"], curr["margin"]
    if isinstance(pm, (int, float)) and isinstance(cm, (int, float)):
        if cm > pm:
            return "improved"
        if cm < pm:
            return "regressed"
    return "unchanged"


def diff_reports(prev: dict, curr: dict) -> dict:
    pi, ci = _index(prev), _index(curr)
    rollup = {k: 0 for k in _CHANGES}
    per = []
    for key in sorted(set(pi) | set(ci)):
        p, c = pi.get(key), ci.get(key)
        change = _classify(p, c)
        rollup[change] += 1
        md = None
        if p and c and isinstance(p["margin"], (int, float)) and isinstance(c["margin"], (int, float)):
            md = c["margin"] - p["margin"]
        card, group, aid = key
        per.append({"card": card, "group": group, "id": aid,
                    "prev": p["verdict"] if p else None,
                    "curr": c["verdict"] if c else None,
                    "change": change, "margin_delta": md})
    return {"schema": "test_diff/v1", "per": per, "rollup": rollup}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_diff.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_diff.py tests/test_test_diff.py
git commit -m "feat(diff): diff_reports cross-iteration test signal in viva_superpowers"
```

---

### Task 5: Export the foundation from `viva_superpowers/__init__.py`

**Files:**
- Modify: `viva_superpowers/__init__.py`
- Test: `tests/test_tests_foundation_exports.py`

**Interfaces:**
- Produces: top-level re-exports so downstream imports `from viva_superpowers import check, band, value, predicate, TestBuilder, Expected, diff_reports` and the `test_vocab` names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tests_foundation_exports.py
def test_foundation_reexports():
    import viva_superpowers as vsp
    for name in ("Expected", "value", "band", "predicate", "check",
                 "TestBuilder", "diff_reports"):
        assert hasattr(vsp, name), name
    # vocab still reachable via submodule
    from viva_superpowers import test_vocab
    assert test_vocab.CANONICAL[0] == "within_tol"

def test_foundation_has_no_heavy_imports():
    # the contract must be importable without process_bigraph / vivarium_workbench
    import sys, importlib
    for mod in ("viva_superpowers.test_vocab", "viva_superpowers.test_contract",
                "viva_superpowers.test_diff"):
        importlib.import_module(mod)
    # importing the pure modules must not have pulled workbench in
    assert "vivarium_workbench" not in sys.modules
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tests_foundation_exports.py -q`
Expected: FAIL — `AttributeError: module 'viva_superpowers' has no attribute 'check'` (or the heavy-import assertion, if `__init__` eagerly imports post_sim)

Note: if `viva_superpowers/__init__` already imports `process_bigraph`-backed modules eagerly (e.g. `post_sim`), the second test guards only against `vivarium_workbench`; keep it as written — `process_bigraph` is an allowed dependency of the package, `vivarium_workbench` is not.

- [ ] **Step 3: Write minimal implementation**

```python
# add to viva_superpowers/__init__.py (near the existing post_sim re-exports)
from viva_superpowers.test_contract import (  # noqa: F401
    Expected, value, band, predicate, check, TestBuilder, sanitize,
)
from viva_superpowers.test_diff import diff_reports  # noqa: F401
from viva_superpowers import test_vocab  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tests_foundation_exports.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/__init__.py tests/test_tests_foundation_exports.py
git commit -m "feat: re-export the tests foundation (contract/diff/vocab) from viva_superpowers"
```

---

## Self-Review

**Spec coverage (Slice 1a portion of §5, §8, §11):**
- §11 centralized vocabulary → Task 1 (`test_vocab`). ✓
- §5 `Expected`/`check()`/graded v2 axis (margin/severity/knob/citation) → Task 2. ✓
- §5.1 `TestBuilder` → `report_card_verdict/v2` → Task 3. ✓
- §8 `diff_reports` / `test_diff/v1` → Task 4. ✓
- Export surface for later slices → Task 5. ✓
- **Deferred to Slice 1b (out of this plan, by design):** moving `grade_card`/`verdict_json`/renderers into viva_superpowers (needs `card_criteria` handling); `post_sim` `ReportCardStep→TestStep` rename + aliases; `TestReportStep`; severity-aware `study_verdict.roll_up_verdict`. Noted in the handoff.

**Placeholder scan:** none — every step has runnable code or an exact command.

**Type consistency:** the axis dict keys produced by `check()` (Task 2) are consumed unchanged by `TestBuilder` (Task 3) and `diff_reports` (Task 4: reads `verdict`/`margin`/`id`); `worst`/`normalize_verdict` names match `test_vocab` (Task 1); `report_card_verdict/v2` group/axis shape matches the spec §5 and the existing `verdict_json/v1` shape (`groups[gslug].axes[].{id,label,verdict,value,meter,detail}`) so a v1 reader is unaffected (asserted in Task 3).

## Execution Handoff

Slice 1a is the additive, dependency-free foundation. Slice 1b (grading move + `post_sim` rename + `TestReportStep` + severity gate) is the next plan and depends on these modules; it requires reading `v2ecoli/library/card_criteria.py`, the `report_card.py` renderers, and `viva_superpowers/study_verdict.py` internals before it can be written without placeholders.
