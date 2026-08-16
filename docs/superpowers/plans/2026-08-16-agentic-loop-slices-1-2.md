# Agentic Model-Building Loop — Slices 1-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic, unit-testable foundation of the agentic loop — the `loop_state` backbone (persisted protocol state + invariant assertions) and the `test_audit` sufficiency checks + `/viva-audit-tests` skill.

**Architecture:** Pure `viva_superpowers` helpers (no `process_bigraph`, no workbench, no AI) own the loop-state read/advance/validate and the deterministic audit checks; the `/viva-audit-tests` skill adds the AI reasoning (null-model plausibility, mechanism semantics) and assembles a graded `report_card_verdict/v2` report via the existing `TestBuilder`/`check`.

**Tech Stack:** Python 3.11+, `viva_superpowers`, pytest. Reuses `test_contract.check`/`TestBuilder`, `rigor`, `band_provenance`, `study_verdict`, `study_io.atomic_write`, `paths.workspace_dir`.

**Spec:** `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`

## Global Constraints

- **Plugin owns judgment; AI-free helpers.** `loop_state.py` and `test_audit.py` are pure stdlib + `viva_superpowers` intra-imports (no `process_bigraph`, no `vivarium_workbench`, no network). AI reasoning lives ONLY in the skill.
- **Loop-state home:** `.pbg/loop/<study>.json`, resolved via `paths.workspace_dir("pbg")` (layout-aware). Schema `model_build_loop/v1`.
- **Determinism:** no timestamps written into loop-state or the audit verdict (content only, commit-clean). Atomic writes via `study_io.atomic_write`.
- **Integrity invariants** (assert in `loop_state.validate`): I1 locked Tests immutable except via reopen; I4 no `passed` verdict the gate doesn't support. (I2/I3/I5 are driver-enforced in Slice 3; I5's history field is written here.)
- **Audit severity:** `discrimination` + `objective_coverage` axes are `severity="hard"`; `redundancy` + `discriminating_control` are `soft`. `overall = worst`; audit `fail` iff any hard axis is `mismatch`.

---

### Task 1: `loop_state` schema — create / load / save roundtrip

**Files:**
- Create: `viva_superpowers/loop_state.py`
- Test: `tests/test_loop_state.py`

**Interfaces:**
- Consumes: `paths.workspace_dir`, `study_io.atomic_write`.
- Produces: `SCHEMA = "model_build_loop/v1"`; `STATES` tuple; `loop_path(ws_root, study) -> Path`; `create(ws_root, study, question, *, max_iterations=12) -> dict`; `save(ws_root, study, state) -> Path`; `load(ws_root, study) -> dict | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_loop_state.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loop_state.py -v`
Expected: FAIL — `No module named 'viva_superpowers.loop_state'`.

- [ ] **Step 3: Write minimal implementation**

Create `viva_superpowers/loop_state.py`:

```python
"""Persisted protocol state for the agentic model-building loop.

`.pbg/loop/<study>.json` (schema model_build_loop/v1) is the loop's audit trail
AND the seam that lets a supervised in-session run become an autonomous dispatched
run — any executor reads/advances the same file. Pure: stdlib + viva_superpowers
intra-imports only (AI-free; no process_bigraph / workbench). See
docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md §3-§4.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from viva_superpowers import paths, study_io

SCHEMA = "model_build_loop/v1"
STATES = ("AUTHOR", "AUDIT", "LOCK", "BUILD", "RUN", "EVALUATE",
          "DECIDE", "NAVIGATE", "DONE", "GIVE_UP")


def loop_path(ws_root, study: str) -> Path:
    return paths.workspace_dir("pbg", root=ws_root) / "loop" / f"{study}.json"


def create(ws_root, study: str, question: str, *, max_iterations: int = 12) -> dict:
    return {
        "schema": SCHEMA,
        "study": study,
        "question": question,
        "state": "AUTHOR",
        "iteration": 0,
        "budget": {"max_iterations": int(max_iterations), "spent": 0},
        "audit": None,
        "locked_tests_hash": None,
        "prereg_record": {"locked_at_iteration": None, "prior_hashes": []},
        "reopen_count": 0,
        "last_verdict": None,
        "history": [],
    }


def save(ws_root, study: str, state: dict) -> Path:
    p = loop_path(ws_root, study)
    p.parent.mkdir(parents=True, exist_ok=True)
    study_io.atomic_write(p, json.dumps(state, indent=1, sort_keys=False) + "\n")
    return p


def load(ws_root, study: str) -> "dict | None":
    p = loop_path(ws_root, study)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_loop_state.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/loop_state.py tests/test_loop_state.py
git commit -m "loop_state: model_build_loop/v1 create/load/save"
```

---

### Task 2: `loop_state` — tests hash, lock, and advance

**Files:**
- Modify: `viva_superpowers/loop_state.py`
- Test: `tests/test_loop_state.py`

**Interfaces:**
- Consumes: Task 1's state dict.
- Produces: `tests_hash(tests: list) -> str`; `lock_tests(state, tests: list) -> dict`; `advance(state, to_state: str, **fields) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loop_state.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loop_state.py -k "hash or lock or advance" -v`
Expected: FAIL — `module 'viva_superpowers.loop_state' has no attribute 'tests_hash'`.

- [ ] **Step 3: Write minimal implementation**

Add to `viva_superpowers/loop_state.py`:

```python
def tests_hash(tests: list) -> str:
    """Content hash of the behavior_tests set, stable to ordering (the set is
    what's locked, not its order). Canonicalized via sorted-keys JSON."""
    canon = sorted(json.dumps(t, sort_keys=True) for t in (tests or []))
    return "sha256:" + hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()


def lock_tests(state: dict, tests: list) -> dict:
    state = dict(state)
    state["locked_tests_hash"] = tests_hash(tests)
    state["prereg_record"] = dict(state.get("prereg_record") or {})
    state["prereg_record"]["locked_at_iteration"] = state.get("iteration", 0)
    state["state"] = "LOCK"
    return state


def advance(state: dict, to_state: str, **fields) -> dict:
    if to_state not in STATES:
        raise ValueError(f"unknown loop state {to_state!r}")
    state = dict(state)
    state["state"] = to_state
    state.update(fields)
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_loop_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/loop_state.py tests/test_loop_state.py
git commit -m "loop_state: tests_hash + lock_tests + advance"
```

---

### Task 3: `loop_state` — record_iteration + invariant validation (I1, I4)

**Files:**
- Modify: `viva_superpowers/loop_state.py`
- Test: `tests/test_loop_state.py`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: `record_iteration(state, *, edit, target, margin_deltas, gate) -> dict`; `validate(state, current_tests, *, is_reopen=False) -> list[str]` (list of invariant-violation messages; empty = clean).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loop_state.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loop_state.py -k "record_iteration or validate" -v`
Expected: FAIL — `has no attribute 'record_iteration'`.

- [ ] **Step 3: Write minimal implementation**

Add to `viva_superpowers/loop_state.py`:

```python
def record_iteration(state: dict, *, edit: str, target: str,
                     margin_deltas: dict, gate: str) -> dict:
    state = dict(state)
    state["iteration"] = int(state.get("iteration", 0)) + 1
    budget = dict(state.get("budget") or {})
    budget["spent"] = int(budget.get("spent", 0)) + 1
    state["budget"] = budget
    state["history"] = list(state.get("history") or []) + [{
        "iteration": state["iteration"], "edit": edit, "target": target,
        "margin_deltas": margin_deltas or {}, "gate": gate,
    }]
    return state


def validate(state: dict, current_tests: list, *, is_reopen: bool = False) -> list:
    """Invariant violations (empty = clean). I1: after LOCK the tests are frozen
    (a change is only legal on a reopen). I4: no `passed` roll-up the gate rejects."""
    out = []
    locked = state.get("locked_tests_hash")
    if locked and not is_reopen and tests_hash(current_tests) != locked:
        out.append("I1: locked behavior_tests changed outside a re-open→AUDIT round")
    lv = state.get("last_verdict") or {}
    if str(lv.get("roll_up")) == "passed" and str(lv.get("gate")) == "fail":
        out.append("I4: roll_up 'passed' contradicts a failing severity gate")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_loop_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/loop_state.py tests/test_loop_state.py
git commit -m "loop_state: record_iteration + invariant validate (I1, I4)"
```

---

### Task 4: `test_audit` deterministic checks

**Files:**
- Create: `viva_superpowers/test_audit.py`
- Test: `tests/test_test_audit.py`

**Interfaces:**
- Consumes: `rigor._numeric_band_tests` (list the numeric-band tests of a spec).
- Produces: `band_too_wide(spec, *, frac=0.5) -> list[dict]` (band whose half-width > frac·|target|/|midpoint|); `redundant_paths(spec) -> list[dict]` (tests sharing a measure path); `objective_mechanisms(spec) -> list[str]` (mechanism tags from question/purpose); `uncovered_mechanisms(spec) -> list[str]` (mechanisms with no primary test citing/measuring them); `has_discriminating_control(spec) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_test_audit.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_audit.py -v`
Expected: FAIL — `No module named 'viva_superpowers.test_audit'`.

- [ ] **Step 3: Write minimal implementation**

Create `viva_superpowers/test_audit.py`:

```python
"""Deterministic test-sufficiency checks for /viva-audit-tests.

Adds the sufficiency dimensions rigor.py doesn't cover — discrimination
(trivially-wide bands), redundancy (tests on the same observable), objective
coverage (mechanisms with no test), and a discriminating control. Pure; the
skill supplies the AI reasoning (null-model plausibility, mechanism semantics)
and assembles the graded report. See the loop spec §5.
"""
from __future__ import annotations

import re

from viva_superpowers import rigor


def _tests(spec: dict) -> list:
    return [t for t in (spec.get("behavior_tests") or spec.get("expected_behavior") or [])
            if isinstance(t, dict)]


def _measure_path(t: dict) -> str:
    m = t.get("measure") or {}
    return str(m.get("path") or m.get("field") or m.get("formula") or "").strip()


def band_too_wide(spec: dict, *, frac: float = 0.5) -> list:
    """Numeric-band tests whose half-width exceeds `frac` of the band midpoint's
    magnitude — a band so wide a wrong model likely also passes."""
    out = []
    for t in rigor._numeric_band_tests(spec):
        pi = t.get("pass_if") or {}
        lo, hi = pi.get("low"), pi.get("high")
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
            continue
        mid = (lo + hi) / 2.0
        half = (hi - lo) / 2.0
        ref = abs(mid) if mid != 0 else 1.0
        if half > frac * ref:
            out.append({"name": t.get("name"), "half_width": half, "midpoint": mid})
    return out


def redundant_paths(spec: dict) -> list:
    """Groups of ≥2 tests keyed on the same measure path (a suite that looks
    broad but tests one observable)."""
    by_path: dict = {}
    for t in _tests(spec):
        p = _measure_path(t)
        if p:
            by_path.setdefault(p, []).append(str(t.get("name") or ""))
    return [{"path": p, "tests": names} for p, names in by_path.items() if len(names) > 1]


def objective_mechanisms(spec: dict) -> list:
    """Mechanism tags named in the question / purpose.mechanism / study_card —
    snake_case tokens the tests should cover. Best-effort tokenization."""
    blobs = [str(spec.get("question") or ""),
             str((spec.get("purpose") or {}).get("mechanism") or ""),
             str((spec.get("study_card") or {}).get("mechanism") or "")]
    mechs = set()
    for b in blobs:
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", b):
            if "_" in tok or tok[:1].islower() and any(c.isupper() for c in tok[1:]):
                mechs.add(tok)
    return sorted(mechs)


def uncovered_mechanisms(spec: dict) -> list:
    """Mechanisms with no PRIMARY test measuring or citing them (a deterministic
    scaffold — the skill closes the semantic gap for near-misses)."""
    tests = [t for t in _tests(spec) if str(t.get("classification", "")) == "primary"]
    haystack = " ".join(_measure_path(t) + " " + " ".join(map(str, t.get("cites") or []))
                        for t in tests).lower()
    return [m for m in objective_mechanisms(spec) if m.lower() not in haystack]


def has_discriminating_control(spec: dict) -> bool:
    """A test that acts as a negative control — the correct model should FAIL it
    if the mechanism were absent (`control: negative` or a diagnostic classification)."""
    for t in _tests(spec):
        if str(t.get("control", "")).lower() == "negative":
            return True
        if str(t.get("classification", "")) == "diagnostic":
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_audit.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_audit.py tests/test_test_audit.py
git commit -m "test_audit: deterministic sufficiency checks (band-width/redundancy/coverage/control)"
```

---

### Task 5: `build_audit_report` — assemble the graded /v2 audit

**Files:**
- Modify: `viva_superpowers/test_audit.py`
- Test: `tests/test_test_audit.py`

**Interfaces:**
- Consumes: Task 4's checks; `test_contract.TestBuilder`/`check`/`value`; `band_provenance.bands_missing_provenance`.
- Produces: `build_audit_report(spec) -> dict` — a `report_card_verdict/v2` doc (`groups`→`axes`) with `overall`, whose axes are the sufficiency dimensions. `discrimination` + `objective_coverage` are `severity="hard"`; `redundancy` + `discriminating_control` + `provenance` are `soft`. `audit_gate(report) -> "pass"|"warn"|"fail"` (fail iff any hard axis `mismatch`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_test_audit.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_audit.py -k "build_audit_report" -v`
Expected: FAIL — `has no attribute 'build_audit_report'`.

- [ ] **Step 3: Write minimal implementation**

Add to `viva_superpowers/test_audit.py` (add the imports at module top):

```python
from viva_superpowers.test_contract import TestBuilder, check, value
from viva_superpowers import band_provenance


def _axis(id, label, ok: bool, severity, detail):
    # A boolean sufficiency dimension → a predicate-style axis: within_tol when ok,
    # else mismatch (hard) / drift (soft), carrying a human detail.
    verdict = "within_tol" if ok else ("mismatch" if severity == "hard" else "drift")
    return check(id, label, None, value(1.0, op=">="), severity=severity,
                 verdict=verdict, detail=detail)


def build_audit_report(spec: dict) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    wide = band_too_wide(spec)
    uncovered = uncovered_mechanisms(spec)
    dupes = redundant_paths(spec)
    missing_prov = band_provenance.bands_missing_provenance(spec)
    tb = TestBuilder(model_ref=str(spec.get("name") or ""))
    tb.add("sufficiency", _axis(
        "discrimination", "Discrimination (bands not trivially wide)",
        not wide, "hard", {"wide_bands": wide}))
    tb.add("sufficiency", _axis(
        "objective_coverage", "Objective coverage (mechanisms tested)",
        not uncovered, "hard", {"uncovered_mechanisms": uncovered}))
    tb.add("sufficiency", _axis(
        "redundancy", "Independence (tests on distinct observables)",
        not dupes, "soft", {"shared_paths": dupes}))
    tb.add("sufficiency", _axis(
        "discriminating_control", "Discriminating control present",
        has_discriminating_control(spec), "soft", {}))
    tb.add("provenance", _axis(
        "band_provenance", "Bands carry citation/provenance",
        not missing_prov, "soft", {"missing": missing_prov}))
    return tb.build()


def audit_gate(report: dict) -> str:
    hard_mismatch = soft_issue = False
    for g in (report.get("groups") or {}).values():
        for ax in g.get("axes") or []:
            v, sev = ax.get("verdict"), ax.get("severity", "hard")
            if v == "mismatch" and sev == "hard":
                hard_mismatch = True
            elif v in ("mismatch", "drift"):
                soft_issue = True
    return "fail" if hard_mismatch else ("warn" if soft_issue else "pass")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_test_audit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/test_audit.py tests/test_test_audit.py
git commit -m "test_audit: build_audit_report (/v2 graded sufficiency) + audit_gate"
```

---

### Task 6: `/viva-audit-tests` skill + catalog guards

**Files:**
- Create: `skills/viva-audit-tests/SKILL.md`
- Modify: `tests/test_skill_manifests.py`, `docs/skills.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `test_audit.build_audit_report`/`audit_gate` (deterministic), plus the skill's own AI reasoning (null-model plausibility, mechanism semantics).
- Produces: the `/viva-audit-tests <study>` user-invocable skill; writes the audit as `viz/report_card/test-audit.{verdict.json,html}` and prints the gate + the insufficient dimensions.

- [ ] **Step 1: Determine the current skill count**

Run: `grep -rEno "[0-9]+ user-facing skills" docs/skills.md README.md CLAUDE.md AGENTS.md`
Note the current N (it was 15 at #256; confirm the live value). The new skill makes it **N+1**.

- [ ] **Step 2: Write the failing manifest test expectation**

In `tests/test_skill_manifests.py`, add `"viva-audit-tests"` to the pinned user-invocable set, and bump the asserted "N user-facing skills" count to N+1.

Run: `pytest tests/test_skill_manifests.py -v`
Expected: FAIL (skill dir + doc counts not yet present).

- [ ] **Step 3: Create the skill**

Create `skills/viva-audit-tests/SKILL.md`:

```markdown
---
name: viva-audit-tests
description: Use before locking a study's acceptance-criteria Tests for an autonomous model-building loop — audits whether the Tests are SUFFICIENT (discriminating, covering the question, independent, with a discriminating control) so a wrong model can't pass them. Gates the pre-registration lock.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <study-slug>
---

# /viva-audit-tests

Judge whether a study's `behavior_tests[]` are rigorous enough to VALIDATE a
model — not too weak, not gameable — BEFORE they are pre-registered/locked and
the model-iteration loop begins. This is the AUDIT gate of the agentic
model-building loop (spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`).

## What it checks

Deterministic (from `viva_superpowers.test_audit.build_audit_report`):
- **discrimination** (hard) — no trivially-wide band a wrong model would also pass.
- **objective coverage** (hard) — every mechanism the `question`/`purpose.mechanism` names has a primary Test.
- **redundancy** (soft) — Tests key on distinct observables.
- **discriminating control** (soft) — a Test the correct model should FAIL absent the mechanism.
- **band provenance** (soft) — numeric bands carry `cites`/`provenance`.

AI reasoning you add on top (the deterministic scaffold can't):
- **null-model plausibility** — for each primary Test, reason whether a scrambled/knockout/null model (mechanism removed) would ALSO satisfy the band. If yes, the Test is insufficient even if its band is narrow — say so and downgrade `discrimination`.
- **semantic coverage** — the mechanism-token scaffold flags literal misses; confirm real coverage (a Test may cover a mechanism the tokenizer didn't match, or vice-versa).

## Run

```bash
STUDY="${1:?usage: /viva-audit-tests <study-slug>}"
python - "$STUDY" <<'PY'
import sys, json, yaml
from pathlib import Path
from viva_superpowers import paths, test_audit
ws = paths.workspace_root()
sf = paths.workspace_dir("studies", root=ws) / sys.argv[1] / "study.yaml"
spec = yaml.safe_load(sf.read_text()) if sf.is_file() else {}
rep = test_audit.build_audit_report(spec)
gate = test_audit.audit_gate(rep)
print("audit gate:", gate)
for g in rep["groups"].values():
    for ax in g["axes"]:
        if ax["verdict"] != "within_tol":
            print(f"  {ax['verdict']:9} {ax['id']}  {json.dumps(ax.get('detail') or {})}")
print(json.dumps(rep))  # for the caller / to write test-audit.verdict.json
PY
```

Then apply the AI-reasoning dimensions (null-model, semantic coverage): if either
finds an insufficiency the deterministic pass missed, treat the audit as **fail**
and report which Tests to strengthen. On `fail`, the loop returns to AUTHOR; only a
`pass`/`warn` audit may proceed to the pre-registration lock.

## Gate contract

- `fail` → a hard dimension (discrimination / objective_coverage) is a mismatch, OR your null-model/semantic reasoning found one. Do NOT lock; strengthen the Tests.
- `warn` → only soft dimensions flagged (redundancy / control / provenance). Lockable, but note the gaps.
- `pass` → sufficient. Proceed to lock.
```

- [ ] **Step 4: Update the catalog docs**

Add a `/viva-audit-tests` row to `docs/skills.md`, the skill list in `README.md`, the routing table in `AGENTS.md`, and `CLAUDE.md`'s skills catalog; bump each "N user-facing skills" count to N+1.

- [ ] **Step 5: Run the manifest + cross-harness tests**

Run: `pytest tests/test_skill_manifests.py -v` (and `tests/test_cross_harness.py` if present)
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/viva-audit-tests/SKILL.md tests/test_skill_manifests.py docs/skills.md README.md AGENTS.md CLAUDE.md
git commit -m "skill: /viva-audit-tests (test-sufficiency audit gate)"
```

---

## Notes for the executor

- **Test venv:** `loop_state`/`test_audit` import only light `viva_superpowers` modules (`paths`, `study_io`, `rigor`, `band_provenance`, `test_contract`, `study_verdict`) — all stdlib-backed; a plain `viva-superpowers` editable install runs the tests. If `rigor`/`band_provenance` transitively pull `viva_workspace`, prepend `/Users/eranagmon/code/viva-workspace` to `PYTHONPATH` (as the other suites do).
- **Do NOT** import `process_bigraph` or `vivarium_workbench` in `loop_state.py`/`test_audit.py` — the AI-free/one-way-dep rule is a hard constraint (a `test_no_workbench_import`-style guard exists).
- Slice 3 (the `/viva-model-build` driver skill) and Slice 4 (fixture harness) are a separate follow-on plan; do not build them here.
