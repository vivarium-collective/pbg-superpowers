# Tests Foundation (Slice 1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The viva_superpowers-only unification pieces of the Tests system: rename `ReportCardStep→TestStep` (with back-compat aliases), make the package `__init__` import the heavy `post_sim` names lazily (so the pure contract is importable without the process-bigraph stack), and add `TestReportStep` — the Evaluate-tail Step that writes the run's aggregate `report.json` + cross-iteration `diff.json`.

**Architecture:** Builds on Slice 1a (`test_vocab`, `test_contract`, `test_diff`, all merged on this branch). All three tasks live in `viva_superpowers/` and touch no other repo. Renames are additive-with-aliases (nothing downstream breaks on the same commit). The grading *move* (`grade_card`/renderers) and the severity-aware `study_verdict` gate are deliberately **deferred** — the move to Slice 2 (v2ecoli de-dup, since it relocates v2ecoli code), the gate to its own slice (it reconciles the `tests[]`-outcome path with the axis-severity path).

**Tech Stack:** Python 3.12, `process_bigraph.composite.Step`/`SyncUpdate`, stdlib, pytest. Package `viva-superpowers`; tests in `tests/`, run with `.venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-08-15-tests-as-agent-feedback-design.md`

## Global Constraints

- **Back-compat on the same commit:** every renamed public symbol keeps a working alias; alias use emits `DeprecationWarning`. v2ecoli's cards (`tests`, `vs_literature`, `vs_vecoli`) subclass `ReportCardStep` and workbench imports `ReportCardStep`/`REPORT_CARD_REGISTRY`/`write_card` — all must keep working.
- **`TestStep` keeps the exact runtime contract** of today's `ReportCardStep`: `inputs()->{"study":"tree"}`, `outputs()->{"view":"string","data":"tree"}`, `applies(study)->bool`, `build(study)->(verdict_dict, html)|None`, guarded `invoke()`. `build` may return a `report_card_verdict/v2` doc OR the legacy `(dict, html)` tuple; `update()` normalizes both.
- **On-disk layout unchanged:** cards still write `<study>/viz/report_card/<name>.{html,verdict.json}`. `TestReportStep`'s new artifacts (`report.json`, `diff.json`, `history/`) are siblings under `<study>/viz/tests/`.
- **Determinism:** `TestReportStep` never generates timestamps/ids internally — they arrive via config/state (workflow-engine `Date.now()`-free rule).
- **JSON safety:** verdicts written `allow_nan=False`, sanitized via `viva_superpowers.test_contract.sanitize`.
- **`overall` vocabulary immutable:** `{within_tol, drift, mismatch, ungraded}` (use `viva_superpowers.test_vocab`).

---

### Task 1: Rename `ReportCardStep → TestStep` with back-compat aliases

**Files:**
- Modify: `viva_superpowers/post_sim.py` (the `ReportCardStep` class ~442-497, `REPORT_CARD_REGISTRY` ~65, `write_card` ~535, `applicable` ~566, `register_post_sim` kind, `__init_subclass__` ~463)
- Modify: `viva_superpowers/__init__.py` (export `TestStep`, `TEST_REGISTRY`, `write_test` alongside the old names)
- Test: `tests/test_teststep_rename.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TestStep` (canonical), `TEST_REGISTRY` (canonical dict), `write_test(ctx, name, verdict, html) -> Path`. Aliases: `ReportCardStep = TestStep`, `REPORT_CARD_REGISTRY` bound to the SAME dict object as `TEST_REGISTRY`, `write_card(...)` = a `DeprecationWarning` shim delegating to `write_test`. `register_post_sim`/`__init_subclass__` tag kind `"test"`; `iter_post_sim("report_card")` maps to `"test"`.

**Implementation notes (apply, do not paste verbatim without reading the file):**
- Rename the class `ReportCardStep` → `TestStep`; in its `__init_subclass__`, register into `TEST_REGISTRY` and `register_post_sim(cls, "test")`.
- Add module-level `TEST_REGISTRY = {}`; make `REPORT_CARD_REGISTRY = TEST_REGISTRY` (same object, so old readers see new registrations).
- Rename `write_card` → `write_test`; keep `write_card` as: `def write_card(ctx, name, verdict, html): warnings.warn("write_card is renamed to write_test", DeprecationWarning, stacklevel=2); return write_test(ctx, name, verdict, html)`.
- Add `ReportCardStep = TestStep` after the class.
- In `register_post_sim` and `iter_post_sim`, accept the legacy kind string: normalize `"report_card" -> "test"` on input so `iter_post_sim("report_card")` returns test-kind entries.
- `applicable()` iterates `TEST_REGISTRY` (== `REPORT_CARD_REGISTRY`) — no change needed beyond the rename of the name it reads.
- Export in `__init__.py`: add `TestStep, TEST_REGISTRY, write_test` to the `from viva_superpowers.post_sim import (...)` list (keep `ReportCardStep, REPORT_CARD_REGISTRY, write_card`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teststep_rename.py
import warnings
import viva_superpowers as vsp
from viva_superpowers import post_sim

def test_teststep_and_aliases_exist():
    assert vsp.TestStep is post_sim.TestStep
    assert vsp.ReportCardStep is vsp.TestStep            # alias
    assert vsp.REPORT_CARD_REGISTRY is vsp.TEST_REGISTRY  # same dict object

def test_subclassing_either_name_registers_in_test_registry():
    class _MyCardViaAlias(vsp.ReportCardStep):
        name = "unit_alias_card"
        def build(self, study): return ({"overall": "within_tol"}, "<html></html>")
    class _MyTestViaNew(vsp.TestStep):
        name = "unit_new_test"
        def build(self, study): return ({"overall": "within_tol"}, "<html></html>")
    assert vsp.TEST_REGISTRY["unit_alias_card"] is _MyCardViaAlias
    assert vsp.TEST_REGISTRY["unit_new_test"] is _MyTestViaNew
    # kind-tagged as "test" in the unified registry
    kinds = {nm: e["kind"] for nm, e in vsp.POST_SIM_REGISTRY.items()}
    assert kinds["unit_alias_card"] == "test"

def test_iter_post_sim_accepts_legacy_kind():
    names_new = {nm for nm, _ in vsp.iter_post_sim("test")}
    names_legacy = {nm for nm, _ in vsp.iter_post_sim("report_card")}
    assert names_new == names_legacy
    assert "unit_new_test" in names_new

def test_write_card_deprecated_but_works(tmp_path):
    ctx = post_sim.StudyContext(study_name="s", study_dir=tmp_path, spec={}, ws_root=tmp_path)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        p = vsp.write_card(ctx, "c1", {"overall": "within_tol"}, "<html>ok</html>")
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert p.exists()
    assert (p.parent / "c1.verdict.json").exists()
    # write_test writes identically, no warning
    p2 = vsp.write_test(ctx, "c2", {"overall": "mismatch"}, "<html>x</html>")
    assert p2.exists() and (p2.parent / "c2.verdict.json").exists()

def test_legacy_tuple_build_still_yields_view_data():
    class _T(vsp.TestStep):
        name = "unit_legacy_tuple"
        def applies(self, study): return True
        def build(self, study): return ({"overall": "drift"}, "<html>h</html>")
    step = _T({}, None) if False else _T.__new__(_T)   # construct minimally
    step.config = {}
    out = step.update({"study": {"any": 1}})
    assert out == {"view": "<html>h</html>", "data": {"overall": "drift"}}
```

Note: if `TestStep.__init__` requires args that make `_T.__new__` insufficient, construct it the way the other post_sim tests in this repo construct a Step (grep `tests/` for an existing `ReportCardStep`/`Step` instantiation and mirror it); the assertion on `update()` is the point.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_teststep_rename.py -q`
Expected: FAIL — `AttributeError: module 'viva_superpowers' has no attribute 'TestStep'`

- [ ] **Step 3: Write minimal implementation**

Apply the renames + aliases per the Implementation notes above in `viva_superpowers/post_sim.py` (add `import warnings` if absent) and add the three new exports in `viva_superpowers/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_teststep_rename.py -q`
Expected: PASS. Also run the existing post_sim tests to confirm no regression: `.venv/bin/python -m pytest tests/ -k "post_sim or report_card or analysis" -q`

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/post_sim.py viva_superpowers/__init__.py tests/test_teststep_rename.py
git commit -m "refactor(post_sim): ReportCardStep->TestStep + write_test/TEST_REGISTRY with back-compat aliases"
```

---

### Task 2: Lazy `__init__` — pure contract importable without the process-bigraph stack

**Files:**
- Modify: `viva_superpowers/__init__.py`
- Test: `tests/test_lazy_post_sim_import.py`

**Interfaces:**
- Consumes: the post_sim names (Task 1) + the test_contract/test_diff/test_vocab names (Slice 1a).
- Produces: `import viva_superpowers` no longer eagerly imports `viva_superpowers.post_sim` (hence not `process_bigraph`). Heavy post_sim names (`TestStep`, `ReportCardStep`, `ResultsStep`, `ResultsHandle`, `AnalysisStep`, `Analysis`, `VisualizationStep`, `TEST_REGISTRY`, `REPORT_CARD_REGISTRY`, `POST_SIM_REGISTRY`, `VISUALIZATION_REGISTRY`, `ANALYSIS_REGISTRY`, `ANALYSIS_SCALES`, `KINDS`, `StudyContext`, `write_test`, `write_card`, `prune`, `applicable`, `iter_post_sim`, `register_post_sim`) resolve via a module-level PEP-562 `__getattr__` that imports `post_sim` on first access. The light contract names (`check`, `band`, `value`, `predicate`, `Expected`, `TestBuilder`, `sanitize`, `diff_reports`, `test_vocab`) stay eagerly imported (they're cheap and import-safe).

**Implementation (PEP 562):**

```python
# viva_superpowers/__init__.py — replace the eager `from viva_superpowers.post_sim import (...)` block

# Light, import-safe contract (no process_bigraph): eager.
from viva_superpowers.test_contract import (  # noqa: F401
    Expected, value, band, predicate, check, TestBuilder, sanitize,
)
from viva_superpowers.test_diff import diff_reports  # noqa: F401
from viva_superpowers import test_vocab  # noqa: F401

# Heavy post_sim family (pulls process_bigraph): lazy, so a pure consumer
# (e.g. study_audit importing `check`) doesn't drag the simulation stack in.
_POST_SIM_NAMES = frozenset({
    "TestStep", "ReportCardStep", "ResultsStep", "ResultsHandle",
    "AnalysisStep", "Analysis", "VisualizationStep",
    "TEST_REGISTRY", "REPORT_CARD_REGISTRY", "POST_SIM_REGISTRY",
    "VISUALIZATION_REGISTRY", "ANALYSIS_REGISTRY", "ANALYSIS_SCALES", "KINDS",
    "StudyContext", "write_test", "write_card", "prune", "applicable",
    "iter_post_sim", "register_post_sim",
})


def __getattr__(name):
    if name in _POST_SIM_NAMES:
        from viva_superpowers import post_sim
        return getattr(post_sim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _POST_SIM_NAMES)
```

Remove the old eager `from viva_superpowers.post_sim import (...)` statement. Keep any other existing eager imports in `__init__` that are NOT process_bigraph-backed as-is; if another eager import transitively pulls `post_sim`/`process_bigraph`, note it in the report (it would defeat the lazy goal, but is out of this task's scope to fix).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lazy_post_sim_import.py
import subprocess, sys, textwrap

def test_importing_package_does_not_eager_import_post_sim():
    # Fresh interpreter: importing viva_superpowers must NOT import post_sim.
    code = textwrap.dedent("""
        import sys, viva_superpowers
        assert "viva_superpowers.post_sim" not in sys.modules, "post_sim eagerly imported"
        # pure contract is available eagerly
        from viva_superpowers import check, band, diff_reports, TestBuilder  # noqa
        assert "viva_superpowers.post_sim" not in sys.modules
        # accessing a heavy name triggers the lazy import
        _ = viva_superpowers.TestStep
        assert "viva_superpowers.post_sim" in sys.modules
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout

def test_from_import_heavy_name_still_works():
    from viva_superpowers import ReportCardStep, ResultsStep  # triggers __getattr__
    assert ReportCardStep is not None and ResultsStep is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lazy_post_sim_import.py -q`
Expected: FAIL on `test_importing_package_does_not_eager_import_post_sim` — `AssertionError: post_sim eagerly imported`.

- [ ] **Step 3: Write minimal implementation**

Apply the PEP-562 `__init__.py` change above.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_lazy_post_sim_import.py tests/test_teststep_rename.py tests/test_tests_foundation_exports.py -q`
Expected: PASS (the foundation-exports test's heavy-import guard still holds; if that test did `import viva_superpowers` then asserted `vivarium_workbench not in sys.modules`, it still passes — and now `post_sim` isn't eager either).

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/__init__.py tests/test_lazy_post_sim_import.py
git commit -m "perf(pkg): lazy post_sim re-exports (PEP 562) so the pure test contract imports without process_bigraph"
```

---

### Task 3: `TestReportStep` — aggregate `report.json` + cross-iteration `diff.json`

**Files:**
- Modify: `viva_superpowers/post_sim.py` (append `TestReportStep` + a `write_report` helper + `tests_dir`/`history_dir` on `StudyContext` or as helpers)
- Modify: `viva_superpowers/__init__.py` (add `TestReportStep`, `write_report` to `_POST_SIM_NAMES` + the export list)
- Test: `tests/test_test_report_step.py`

**Interfaces:**
- Consumes: `viva_superpowers.test_contract.sanitize`, `viva_superpowers.test_vocab.worst`, `viva_superpowers.test_diff.diff_reports`, `StudyContext` (Task 1 / existing). The per-test verdict docs arrive as the `data` outputs of upstream `TestStep`s, wired into this Step's `state`.
- Produces:
  - `tests_dir(ctx) -> Path` = `ctx.study_dir / "viz" / "tests"`; `history_dir(ctx) -> Path` = `tests_dir(ctx) / "history"`.
  - `build_report(study_name, run_id, cards: dict[str, dict]) -> dict` — a `test_report/v1` doc: `{schema:"test_report/v1", study, run_id, overall, counts:{cards, axes, within_tol, drift, mismatch, ungraded, hard_mismatch}, cards:<the {name: verdict_doc} map>}`. `overall` = `worst` over every card's `overall`.
  - `write_report(ctx, report) -> Path` — writes `tests_dir(ctx)/report.json` (sanitized, `allow_nan=False`); returns the path.
  - `class TestReportStep(Step)`: `config_schema={}`, `inputs()->{"cards":"tree","run_id":"tree"}`, `outputs()->{"report":"tree","diff":"tree","gate":"string"}`. `update(state)`:
    1. `cards = state.get("cards") or self.config.get("cards") or {}` (a `{name: verdict_doc}` map).
    2. `report = build_report(ctx.study_name, run_id, cards)`; `write_report(ctx, report)`.
    3. Load previous report from `history_dir(ctx)/<newest>.json` (if any) → `prev_cards = prev["cards"]`; `diff = diff_reports(prev_cards, cards)`; write `tests_dir(ctx)/diff.json`.
    4. Rotate: copy the just-written `report.json` into `history_dir(ctx)/<run_id or seq>.json`, keeping at most `HISTORY_KEEP = 10` (delete oldest by name).
    5. Return `{"report": report, "diff": diff, "gate": report["overall"]}`.
  - `ctx` is built from config: `StudyContext.load(Path(self.config["ws_root"]), self.config["study_name"])` when those config keys are present, else a `StudyContext` passed via `state["study"]`. `run_id` comes from `state`/`config` — never generated here.
  - Guarded `invoke()` verbatim like the other bases (catch → empty update).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_test_report_step.py
import json
from pathlib import Path
from viva_superpowers.post_sim import (
    TestReportStep, StudyContext, build_report, write_report, tests_dir, history_dir,
)

def _doc(overall, axes):  # axes: list[(id, verdict, margin)]
    return {"schema": "report_card_verdict/v2", "overall": overall,
            "groups": {"g": {"verdict": overall,
                             "axes": [{"id": i, "verdict": v, "margin": m} for i, v, m in axes]}}}

def _ctx(tmp_path):
    sd = tmp_path / "studies" / "demo"
    sd.mkdir(parents=True)
    return StudyContext(study_name="demo", study_dir=sd, spec={}, ws_root=tmp_path)

def test_build_report_overall_and_counts():
    cards = {"c1": _doc("within_tol", [("a", "within_tol", 0.2)]),
             "c2": _doc("mismatch", [("b", "mismatch", -0.1)])}
    rep = build_report("demo", "run1", cards)
    assert rep["schema"] == "test_report/v1"
    assert rep["overall"] == "mismatch"       # worst of the two cards
    assert rep["counts"]["cards"] == 2 and rep["counts"]["axes"] == 2
    assert rep["counts"]["mismatch"] == 1 and rep["counts"]["within_tol"] == 1
    assert rep["cards"]["c1"]["overall"] == "within_tol"

def test_write_report_and_step_writes_report_and_diff(tmp_path):
    ctx = _ctx(tmp_path)
    # seed a prior report into history so the diff has a baseline
    history_dir(ctx).mkdir(parents=True, exist_ok=True)
    prev = build_report("demo", "run0",
                        {"c1": _doc("mismatch", [("a", "mismatch", -0.5)])})
    (history_dir(ctx) / "run0.json").write_text(json.dumps(prev))
    # run the step on a curr where 'a' is now fixed
    step = TestReportStep.__new__(TestReportStep)
    step.config = {"ws_root": str(tmp_path), "study_name": "demo", "run_id": "run1",
                   "cards": {"c1": _doc("within_tol", [("a", "within_tol", 0.3)])}}
    out = step.update({})
    assert out["gate"] == "within_tol"
    assert (tests_dir(ctx) / "report.json").exists()
    diff = json.loads((tests_dir(ctx) / "diff.json").read_text())
    entry = next(p for p in diff["per"] if p["id"] == "a")
    assert entry["change"] == "fixed"
    # history rotated: run1 present
    assert (history_dir(ctx) / "run1.json").exists()

def test_step_no_prior_history_diff_all_new(tmp_path):
    ctx = _ctx(tmp_path)
    step = TestReportStep.__new__(TestReportStep)
    step.config = {"ws_root": str(tmp_path), "study_name": "demo", "run_id": "r1",
                   "cards": {"c1": _doc("within_tol", [("a", "within_tol", 0.1)])}}
    out = step.update({})
    diff = json.loads((tests_dir(ctx) / "diff.json").read_text())
    assert diff["rollup"]["new"] == 1 and diff["per"][0]["change"] == "new"
```

Note: if `TestReportStep.__new__(...)` + manual `.config` set is not how this repo constructs a Step for tests, mirror the existing post_sim Step-construction pattern (grep `tests/` for an existing Step test). The behavioral assertions are the point.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_test_report_step.py -q`
Expected: FAIL — `ImportError: cannot import name 'TestReportStep'`

- [ ] **Step 3: Write minimal implementation**

Append to `viva_superpowers/post_sim.py`:

```python
from viva_superpowers.test_vocab import worst as _worst
from viva_superpowers.test_diff import diff_reports as _diff_reports
from viva_superpowers.test_contract import sanitize as _sanitize

HISTORY_KEEP = 10


def tests_dir(ctx) -> Path:
    return ctx.study_dir / "viz" / "tests"


def history_dir(ctx) -> Path:
    return tests_dir(ctx) / "history"


def build_report(study_name: str, run_id, cards: dict) -> dict:
    counts = {"cards": len(cards), "axes": 0, "within_tol": 0, "drift": 0,
              "mismatch": 0, "ungraded": 0, "hard_mismatch": 0}
    overalls = []
    for doc in cards.values():
        overalls.append(doc.get("overall", "ungraded"))
        for grp in (doc.get("groups") or {}).values():
            for ax in grp.get("axes") or []:
                counts["axes"] += 1
                v = ax.get("verdict", "ungraded")
                if v in counts:
                    counts[v] += 1
                if v == "mismatch" and ax.get("severity", "hard") == "hard":
                    counts["hard_mismatch"] += 1
    return _sanitize({
        "schema": "test_report/v1", "study": study_name, "run_id": run_id,
        "overall": _worst(overalls), "counts": counts, "cards": cards,
    })


def write_report(ctx, report: dict) -> Path:
    d = tests_dir(ctx)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "report.json"
    p.write_text(json.dumps(_sanitize(report), indent=1, allow_nan=False) + "\n",
                 encoding="utf-8")
    return p


def _latest_history(ctx):
    hd = history_dir(ctx)
    if not hd.is_dir():
        return None
    files = sorted(hd.glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _rotate_history(ctx, report, run_id):
    hd = history_dir(ctx)
    hd.mkdir(parents=True, exist_ok=True)
    name = f"{run_id}.json" if run_id else f"{len(list(hd.glob('*.json'))):06d}.json"
    (hd / name).write_text(json.dumps(_sanitize(report), allow_nan=False), encoding="utf-8")
    files = sorted(hd.glob("*.json"))
    for old in files[:-HISTORY_KEEP]:
        old.unlink()


class TestReportStep(Step):
    """Evaluate-tail Step: aggregate the run's TestStep verdicts into report.json
    and diff against the previous run (diff.json). Emits {report, diff, gate}."""

    config_schema: dict = {}

    def _ctx(self, state):
        if self.config.get("ws_root") and self.config.get("study_name"):
            return StudyContext.load(Path(self.config["ws_root"]), self.config["study_name"])
        return state.get("study")

    def inputs(self):
        return {"cards": "tree", "run_id": "tree"}

    def outputs(self):
        return {"report": "tree", "diff": "tree", "gate": "string"}

    def update(self, state, interval=None):
        ctx = self._ctx(state)
        cards = state.get("cards") or self.config.get("cards") or {}
        run_id = state.get("run_id") or self.config.get("run_id")
        report = build_report(getattr(ctx, "study_name", ""), run_id, cards)
        write_report(ctx, report)
        prev = _latest_history(ctx)
        prev_cards = (prev or {}).get("cards") or {}
        diff = _diff_reports(prev_cards, cards)
        (tests_dir(ctx) / "diff.json").write_text(
            json.dumps(_sanitize(diff), indent=1, allow_nan=False) + "\n", encoding="utf-8")
        _rotate_history(ctx, report, run_id)
        return {"report": report, "diff": diff, "gate": report["overall"]}

    def invoke(self, state, interval=None):
        try:
            update = self.update(state)
        except Exception:
            update = {}
        return SyncUpdate(update)
```

Add `TestReportStep`, `write_report`, `build_report`, `tests_dir`, `history_dir` to `__init__.py`'s `_POST_SIM_NAMES` and to whatever it exports.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_test_report_step.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/post_sim.py viva_superpowers/__init__.py tests/test_test_report_step.py
git commit -m "feat(post_sim): TestReportStep writes run report.json + cross-iteration diff.json"
```

---

## Self-Review

**Spec coverage (Slice 1b portion of §5.1, §6, §8, §9):**
- §6 `ReportCardStep→TestStep` + `write_card→write_test` + `REPORT_CARD_REGISTRY→TEST_REGISTRY` + aliases → Task 1. ✓
- §5.1 "importable anywhere" / the 1a-review-deferred lazy `__init__` → Task 2. ✓
- §8/§9 `TestReportStep` writing `report.json` + `diff.json` + history → Task 3. ✓
- **Deferred (noted, out of this plan):** the grading *move* (`grade_card`/`verdict_json`/renderers into viva_superpowers) → Slice 2 (v2ecoli de-dup, since it relocates v2ecoli code + `card_criteria`); the severity-aware `study_verdict.roll_up_verdict` gate → its own slice (reconciles the `tests[]`-outcome path with axis severity — `counts.hard_mismatch` from Task 3 is the seam it will consume).

**Placeholder scan:** none. The two "mirror the existing Step-construction pattern if `__new__` is insufficient" notes are explicit fallbacks with a concrete grep target, not vague hand-waves — the behavioral assertion is fully specified either way.

**Type consistency:** `TestStep`/`TEST_REGISTRY`/`write_test` names match across Tasks 1–3 and `__init__`; `_POST_SIM_NAMES` in Task 2 is extended by Task 3 (both list the same symbol names); `build_report`→`test_report/v1` `cards` map is exactly the `{name: verdict_doc}` shape `diff_reports` (Slice 1a) consumes; `worst`/`sanitize`/`diff_reports` imports match Slice 1a's exports.

## Execution Handoff

Slice 1b is viva_superpowers-only and back-compat. Slice 2 (v2ecoli de-dup: re-export the viva bases, move `grade_card`/`card_criteria`/renderers, `SimGateCard→SimGateTest`, wire `TestReportStep`) and Slice 3 (workbench render) follow; the severity-gate slice consumes `counts.hard_mismatch`.
