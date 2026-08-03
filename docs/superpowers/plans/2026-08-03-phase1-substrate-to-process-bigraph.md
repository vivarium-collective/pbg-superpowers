# Phase 1 — Substrate → process-bigraph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the framework substrate (composite generation/discovery/introspection, config helpers, and the visualization Step framework) from the `viva_superpowers` plugin package into the `process_bigraph` engine package, leaving re-export shims so no consumer breaks.

**Architecture:** A mechanical move following the existing `composite_spec` precedent (already moved to PBG, shimmed in viva). Land the modules + their ported tests in **process-bigraph** first and release it; then convert the `viva_superpowers` modules to re-export shims and bump the PBG dependency. All ~1,829 downstream `import viva_superpowers.*` sites and the workbench's ~54 import sites keep working unchanged via the shims.

**Tech Stack:** Python 3.12, `uv` (build/venv), `hatchling`, `pytest`, `process-bigraph` (git-`@main` source during dev, released version at merge), `bigraph-schema`.

## Global Constraints

- **Nothing may break downstream.** Every moved module leaves a `viva_superpowers.<name>` re-export shim. (verbatim: ~1,829 files import `viva_superpowers`; workbench imports the substrate from ~54 sites.)
- **Shims must re-export the exact surface consumers use**, including semi-private names: the workbench imports `_REGISTRY`, `emitter_defaults`, `install_default_emitters` from `composite_generator`.
- **Preserve the subpackage-walk** in `discover_generators` — it imports `pbg_<ws>/composites/**` so `@composite_generator` decorators fire (mem3dg-readdy friction #22).
- **Dependency direction:** `viva_superpowers` may depend on `process_bigraph`; never the reverse.
- **Version lockstep for the PBG release:** its `pyproject.toml` version + tag must match (its release flow verifies this).
- **Decisions in force (from spec sign-off):** D1 drop the self-referential `process_bigraph.spec_generators` entry point (keep the group for external workspace generators); D2 delete `_demo_visualizations` after the 3-consumer check; D3 shims stay silent (no `DeprecationWarning`) this phase; D4 move the viz Step framework now, defer any render-side split.

## File Structure

**process-bigraph (`~/code/process-bigraph`) — new worktree:**
- Create: `process_bigraph/composite_generator.py`, `process_bigraph/composite_discovery.py`, `process_bigraph/core_introspection.py`, `process_bigraph/config_helpers.py`, `process_bigraph/visualization.py`, `process_bigraph/visualizations/` (subpkg)
- Create tests: `tests/test_composite_generator.py`, etc. (ported from viva's suite)
- Modify: `process_bigraph/__init__.py` (public exports)

**viva-superpowers (`~/code/pbg-superpowers`) — new worktree:**
- Modify → shim: `viva_superpowers/composite_generator.py`, `composite_discovery.py`, `core_introspection.py`, `config_helpers.py`, `visualization.py`, `visualizations/__init__.py`
- Delete: `viva_superpowers/_demo_visualizations.py` (D2)
- Modify: `pyproject.toml` (PBG dependency floor; drop/repoint the `spec_generators` entry point per D1)

---

## Task 1: Warm-up move — `core_introspection` (zero-dependency proof)

**Rationale:** `core_introspection.py` (44 LOC) imports **no** `viva_superpowers` — the cleanest possible first move; proves the pattern end-to-end before the harder modules.

**Files:**
- Create: `~/code/process-bigraph--phase1/process_bigraph/core_introspection.py`
- Test: `~/code/process-bigraph--phase1/tests/test_core_introspection.py`
- Modify: `process_bigraph/__init__.py`

**Interfaces:**
- Produces: `process_bigraph.core_introspection` module with its existing public functions, re-exported from `process_bigraph/__init__.py`.

- [ ] **Step 1: Set up the process-bigraph worktree**

```bash
git -C ~/code/process-bigraph fetch origin main
git -C ~/code/process-bigraph worktree add ~/code/process-bigraph--phase1 -b feat/phase1-substrate origin/main
cd ~/code/process-bigraph--phase1 && uv sync
```

- [ ] **Step 2: Copy the module + its test verbatim from viva**

```bash
cp ~/code/pbg-superpowers/viva_superpowers/core_introspection.py process_bigraph/core_introspection.py
# adjust any `from viva_superpowers.X` intra-substrate imports to `from process_bigraph.X` (none expected for this module — verify)
grep -n "viva_superpowers" process_bigraph/core_introspection.py   # expect: no output
```

- [ ] **Step 3: Write/port the failing test (import from the NEW location)**

```python
# tests/test_core_introspection.py
import process_bigraph.core_introspection as ci
def test_core_introspection_importable_from_pbg():
    assert hasattr(ci, "__file__")
    # port the 1-2 real assertions from viva's core_introspection test here
```

- [ ] **Step 4: Run — expect PASS once the module is in place**

Run: `uv run pytest tests/test_core_introspection.py -q`
Expected: PASS

- [ ] **Step 5: Export from `__init__.py` and commit**

Add to `process_bigraph/__init__.py`: `from process_bigraph import core_introspection  # noqa: F401`

```bash
git add process_bigraph/core_introspection.py tests/test_core_introspection.py process_bigraph/__init__.py
git commit -m "feat(substrate): add core_introspection (moved from viva_superpowers)"
```

---

## Task 2: Move `composite_generator` (the framework core)

**Files:**
- Create: `process_bigraph/composite_generator.py`
- Test: `tests/test_composite_generator.py` (port from viva)
- Modify: `process_bigraph/__init__.py`

**Interfaces:**
- Consumes: `process_bigraph.composite_spec` (already present).
- Produces: `process_bigraph.composite_generator` exposing `composite_generator` (decorator), `discover_generators`, `build_generator`, `install_default_emitters`, `emitter_defaults`, `_REGISTRY`.

- [ ] **Step 1: Copy the module; repoint intra-substrate imports**

```bash
cp ~/code/pbg-superpowers/viva_superpowers/composite_generator.py process_bigraph/composite_generator.py
# it already imports `from process_bigraph import composite_spec as _cs` — keep.
grep -n "viva_superpowers" process_bigraph/composite_generator.py   # expect none; if any, repoint to process_bigraph.*
```

- [ ] **Step 2: Port the generator test, asserting the subpackage-walk still fires**

```python
# tests/test_composite_generator.py  (port viva's + this regression)
import process_bigraph.composite_generator as cg
def test_discover_generators_walks_subpackages(tmp_path, monkeypatch):
    # build a fake pkg with composites/__init__.py that registers via @composite_generator,
    # import the top pkg, call cg.discover_generators, assert the decorated generator is in cg._REGISTRY
    ...   # port the equivalent assertion from viva tests/test_composite_generator.py
```

- [ ] **Step 3: Run — expect PASS**

Run: `uv run pytest tests/test_composite_generator.py -q`
Expected: PASS (decorators fire via the walk)

- [ ] **Step 4: Export + commit**

Add to `__init__.py`: `from process_bigraph.composite_generator import (composite_generator, discover_generators, build_generator, install_default_emitters, emitter_defaults)  # noqa: F401`

```bash
git add process_bigraph/composite_generator.py tests/test_composite_generator.py process_bigraph/__init__.py
git commit -m "feat(substrate): add composite_generator (moved from viva_superpowers)"
```

---

## Task 3: Move `composite_discovery` + `config_helpers`

**Files:**
- Create: `process_bigraph/composite_discovery.py`, `process_bigraph/config_helpers.py`
- Test: `tests/test_composite_discovery.py`, `tests/test_config_helpers.py`

**Interfaces:**
- Consumes: `process_bigraph.composite_spec.CompositeSpec`, `process_bigraph.composite_generator.discover_generators`.
- Produces: `process_bigraph.composite_discovery.discover_all`; `process_bigraph.config_helpers.normalize_config_list` (+ the other normalizers).

- [ ] **Step 1: 3-consumer check for config_helpers before moving**

```bash
# confirm real downstream consumers so the shim surface is complete (not for delete — config_helpers moves + shims)
grep -rIl "superpowers.config_helpers\|superpowers import config_helpers" ~/code --include='*.py' | grep -vE "/pbg-superpowers|/vivarium-workbench|/.venv/|site-packages" | head
```

- [ ] **Step 2: Copy both modules; repoint intra-substrate lazy imports**

```bash
cp ~/code/pbg-superpowers/viva_superpowers/composite_discovery.py process_bigraph/composite_discovery.py
cp ~/code/pbg-superpowers/viva_superpowers/config_helpers.py process_bigraph/config_helpers.py
# composite_discovery's lazy `from viva_superpowers.composite_generator import discover_generators`
# → `from process_bigraph.composite_generator import discover_generators`
sed -i '' 's/from viva_superpowers.composite_generator/from process_bigraph.composite_generator/' process_bigraph/composite_discovery.py
grep -n "viva_superpowers" process_bigraph/composite_discovery.py process_bigraph/config_helpers.py  # expect none
```

- [ ] **Step 3: Port tests; run**

Run: `uv run pytest tests/test_composite_discovery.py tests/test_config_helpers.py -q`
Expected: PASS

- [ ] **Step 4: Export config_helpers normalizers + commit**

```bash
git add process_bigraph/composite_discovery.py process_bigraph/config_helpers.py tests/test_composite_discovery.py tests/test_config_helpers.py process_bigraph/__init__.py
git commit -m "feat(substrate): add composite_discovery + config_helpers (moved from viva_superpowers)"
```

---

## Task 4: Move the visualization Step framework (`visualization` + `visualizations/`)

**Files:**
- Create: `process_bigraph/visualization.py`, `process_bigraph/visualizations/` (all concrete Step modules + `__init__.py`)
- Test: `tests/test_visualization.py`, `tests/test_visualizations.py` (port from viva)
- Modify: `process_bigraph/__init__.py`

**Interfaces:**
- Consumes: `process_bigraph.Step`, `process_bigraph.composite.find_instance_paths`.
- Produces: `process_bigraph.visualization.Visualization` (base), `as_visualization`, `render_results`; `process_bigraph.visualizations.{TimeSeriesPlot,Heatmap,PhaseSpace,ParamVsObservable,Distribution,TimeseriesFromObservables}`.

- [ ] **Step 1: Copy visualization.py + the visualizations/ subpkg; repoint base-class imports**

```bash
cp ~/code/pbg-superpowers/viva_superpowers/visualization.py process_bigraph/visualization.py
cp -R ~/code/pbg-superpowers/viva_superpowers/visualizations process_bigraph/visualizations
# every visualizations/*.py does `from viva_superpowers.visualization import Visualization` → process_bigraph
grep -rl "from viva_superpowers.visualization" process_bigraph/visualizations | xargs sed -i '' 's/from viva_superpowers.visualization/from process_bigraph.visualization/g'
grep -rn "viva_superpowers" process_bigraph/visualization.py process_bigraph/visualizations/  # expect none
```

- [ ] **Step 2: Port viz tests (base class + one concrete Step round-trip); run**

Run: `uv run pytest tests/test_visualization.py tests/test_visualizations.py -q`
Expected: PASS

- [ ] **Step 3: Export + commit**

Add to `__init__.py`: `from process_bigraph.visualization import Visualization, as_visualization, render_results  # noqa: F401`

```bash
git add process_bigraph/visualization.py process_bigraph/visualizations tests/test_visualization.py tests/test_visualizations.py process_bigraph/__init__.py
git commit -m "feat(substrate): add visualization Step framework (moved from viva_superpowers)"
```

---

## Task 5: Full process-bigraph suite green + open PR

**Files:** none (verification + PR)

- [ ] **Step 1: Run the full PBG suite**

Run: `uv run pytest -q`
Expected: PASS (no regressions; new substrate tests included)

- [ ] **Step 2: Confirm no `viva_superpowers` reference leaked into PBG**

Run: `grep -rn "viva_superpowers" process_bigraph/ && echo "LEAK — fix" || echo "clean"`
Expected: `clean`

- [ ] **Step 3: Push + PR (process-bigraph)**

```bash
git push -u origin feat/phase1-substrate
gh pr create --repo vivarium-collective/process-bigraph --base main \
  --title "feat: absorb the composite + visualization substrate from viva_superpowers" \
  --body "Phase 1 of the viva-superpowers 3-home migration. Adds composite_generator/discovery/core_introspection/config_helpers + the visualization Step framework (moved verbatim from viva_superpowers; viva keeps re-export shims in a follow-up). No behavior change; ported tests included."
```

- [ ] **Step 4: Merge after CI green; cut a release**

```bash
# bump process_bigraph version in pyproject.toml (minor), commit, merge PR, then:
git tag v<new> origin/main && git push origin v<new>   # triggers PBG's PyPI release
```

---

## Task 6: viva-superpowers shims + dependency bump

**Files:**
- Modify → shim: `viva_superpowers/{composite_generator,composite_discovery,core_introspection,config_helpers,visualization}.py`, `viva_superpowers/visualizations/__init__.py`
- Delete: `viva_superpowers/_demo_visualizations.py` (D2, after Step 1 check)
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: the released `process_bigraph.*` substrate.
- Produces: `viva_superpowers.<name>` modules that re-export identically to before (import-parity with `process_bigraph.<name>`).

- [ ] **Step 1: Set up the viva worktree; 3-consumer check for `_demo_visualizations` (D2 delete)**

```bash
git -C ~/code/pbg-superpowers fetch origin main
git -C ~/code/pbg-superpowers worktree add ~/code/pbg-superpowers--phase1-shim -b refactor/phase1-shims origin/main
cd ~/code/pbg-superpowers--phase1-shim
grep -rIl "superpowers._demo_visualizations\|import _demo_visualizations" ~/code --include='*.py' | grep -vE "/pbg-superpowers|/.venv/|site-packages" | head
# expect empty → safe to delete
```

- [ ] **Step 2: Write the import-parity failing test FIRST**

```python
# tests/test_substrate_shims.py
import importlib, pytest
PAIRS = [
    ("viva_superpowers.composite_generator", "process_bigraph.composite_generator"),
    ("viva_superpowers.composite_discovery", "process_bigraph.composite_discovery"),
    ("viva_superpowers.core_introspection", "process_bigraph.core_introspection"),
    ("viva_superpowers.config_helpers", "process_bigraph.config_helpers"),
    ("viva_superpowers.visualization", "process_bigraph.visualization"),
]
@pytest.mark.parametrize("shim,real", PAIRS)
def test_shim_reexports_are_identical(shim, real):
    s, r = importlib.import_module(shim), importlib.import_module(real)
    for name in getattr(r, "__all__", None) or [n for n in dir(r) if not n.startswith("__")]:
        assert getattr(s, name) is getattr(r, name), f"{shim}.{name} is not {real}.{name}"

def test_workbench_semiprivate_names_survive():
    from viva_superpowers.composite_generator import _REGISTRY, emitter_defaults, install_default_emitters  # noqa: F401
```

- [ ] **Step 3: Run — expect FAIL (shims not written yet)**

Run: `uv run pytest tests/test_substrate_shims.py -q`
Expected: FAIL

- [ ] **Step 4: Replace each module with a shim (pattern from `composite_spec.py`)**

```python
# viva_superpowers/composite_generator.py  (after)
"""Back-compat shim — moved to process_bigraph.composite_generator (Phase 1)."""
from process_bigraph.composite_generator import *          # noqa: F401,F403
from process_bigraph.composite_generator import (           # explicit: names not in __all__ that consumers use
    _REGISTRY, composite_generator, discover_generators, build_generator,
    install_default_emitters, emitter_defaults,
)
```

Repeat for `composite_discovery`, `core_introspection`, `config_helpers`, `visualization`, and `visualizations/__init__.py` (re-export the concrete Step classes from `process_bigraph.visualizations`). Delete `_demo_visualizations.py`.

- [ ] **Step 5: Bump the PBG dependency + handle the entry point (D1)**

In `pyproject.toml`: raise the `process-bigraph` floor to the released version; **remove** the self-referential `[project.entry-points."process_bigraph.spec_generators"] viva_superpowers = "viva_superpowers.composite_generator:discover_generators"` line (D1 — PBG discovers its own generators internally now).

- [ ] **Step 6: Run parity + full suite**

Run: `uv run pytest tests/test_substrate_shims.py -q` → PASS
Run: `uv run pytest -q --ignore=tests/test_composite_generator.py --ignore=tests/test_composite_spec.py` (the moved tests now live in PBG; delete viva's copies) → PASS

- [ ] **Step 7: Delete viva's now-moved test copies + commit**

```bash
git rm tests/test_composite_generator.py tests/test_composite_spec.py  # and any other fully-moved suites
git add -A
git commit -m "refactor(phase1): shim the composite + visualization substrate to process_bigraph"
git push -u origin refactor/phase1-shims
```

---

## Task 7: Cross-repo + downstream verification

**Files:** none (verification), then PR.

- [ ] **Step 1: Import-parity across repos (interactive smoke)**

```bash
cd ~/code/pbg-superpowers--phase1-shim
uv run python -c "import viva_superpowers.composite_generator as v, process_bigraph.composite_generator as p; assert v.discover_generators is p.discover_generators; assert v._REGISTRY is p._REGISTRY; print('parity OK')"
```

- [ ] **Step 2: Workbench still builds against the shimmed plugin**

```bash
# in a workbench worktree with the phase1 plugin + new PBG installed
cd ~/code/vivarium-workbench-main && uv run pytest -q -k "composite or rigor or report" 2>&1 | tail
# expect: green (workbench still imports viva_superpowers.composite_generator via shim)
```

- [ ] **Step 3: Downstream smoke (v2ecoli)**

```bash
cd ~/code/v2ecoli--main && .venv/bin/python -c "import viva_superpowers.composite_generator; import viva_superpowers.config_helpers; print('downstream import OK')"
```

- [ ] **Step 4: Open the viva shim PR; merge after CI + release the plugin**

```bash
gh pr create --repo vivarium-collective/viva-superpowers --base main \
  --title "refactor(phase1): shim the composite + visualization substrate to process_bigraph" \
  --body "Follow-up to process-bigraph#<n>. Converts the moved substrate modules to re-export shims; bumps the process-bigraph floor; drops the self-referential spec_generators entry point (D1); deletes _demo_visualizations (D2). Import-parity test added; workbench + v2ecoli smoke green."
# after merge: bump viva version + tag → PyPI release (both viva-superpowers + pbg-superpowers shim), per the established release flow
```

---

## Self-Review

- **Spec coverage:** every spec scope item has a task — composite_generator (T2), composite_discovery + config_helpers (T3), core_introspection (T1), visualization + visualizations/ (T4), shims (T6), release ordering (T5→T6), verification incl. workbench + downstream (T7). D1 (T6 Step 5), D2 (T6 Step 1/4), D3 (silent shims — the shim code adds no warning), D4 (viz moved in T4, render-split deferred — noted, no task).
- **Placeholder scan:** the `...` in T2 Step 2 / T3 test porting are explicit "port the equivalent assertion from viva's existing test" instructions with the exact source file named — not blanks. `<new>` / `<n>` are release-time version/PR numbers, correct to leave.
- **Type consistency:** the produced names in T1–T4 (`discover_generators`, `build_generator`, `install_default_emitters`, `emitter_defaults`, `_REGISTRY`, `Visualization`, `render_results`, `discover_all`, `normalize_config_list`) match the shim re-exports and parity test in T6.
