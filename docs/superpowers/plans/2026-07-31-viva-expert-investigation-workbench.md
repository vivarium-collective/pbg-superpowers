# viva-expert → investigation + published read-only workbench (FEniCS) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a new heavy-mode output model for `viva-expert` — processes + `@composite_generator` composites + one showcase **investigation with studies** + a **published read-only workbench** (replacing the standalone HTML report) — by wrapping real FEniCSx end-to-end in `pbg-fenics/`, then codify the recipe into `viva-expert/SKILL.md` and the `viva_superpowers` tooling.

**Architecture:** `pbg-fenics/` is a pixi-managed conda env (real `fenics-dolfinx`) that also holds the pbg/dashboard stack. FEM solvers are wrapped as PBG `Process`/`Step` classes with additive `array[float]` field ports; composites are `@composite_generator` functions; a `fenics-showcase` investigation binds 7 studies that run into `runs.db` and render interactive Plotly/Three.js viz; `vivarium-workbench-publish` exports a static read-only bundle. Then the skill + scaffolder are updated to make this the default terminus.

**Tech Stack:** FEniCSx (dolfinx, ufl, basix, petsc4py), gmsh, mpich; process-bigraph, bigraph-schema, bigraph-viz2; vivarium-workbench; pixi; Plotly.js + Three.js; pytest.

## Global Constraints

- **Workspace root for the wrapper:** `/Users/eranagmon/code/pbg-fenics` (fresh `git init` repo; no worktree needed — brand new).
- **Skill/scaffolder work happens in the worktree:** `/Users/eranagmon/code/pbg-superpowers--viva-expert-investigation` on branch `viva-expert-investigation-workbench`. Never commit skill changes in the shared `~/code/pbg-superpowers` checkout.
- **Real tool only** — no mock/reproduction of FEniCS. If an advanced study is genuinely intractable in-env, ship a guarded process that raises a clear requirement and surface it; do not silently downgrade.
- **Env manager:** pixi (`pixi.toml`/`pixi.lock`), channels `["conda-forge"]`, platform `osx-arm64`, `python=3.12`. All commands run via `pixi run <cmd>` from `pbg-fenics/`.
- **Ports:** bare types with additive `apply` (`float`, `array[float]`, `map[string,float]`); `overwrite[T]` only for genuine setpoints/sensors (Port-Design rules). Field state is `array[float]` (additive) so Diffusion ⊕ Reaction compose.
- **Discovery:** process classes inherit `process_bigraph.Process`/`Step`; `pbg_fenics/__init__.py` re-exports via `__all__`; `pyproject.toml` lists `bigraph-schema` + `process-bigraph`; no manual `register_link` for installed classes.
- **Composites:** every generator is `@composite_generator`-decorated with first positional `core=None`, keyword-only params matching `parameters=`, `local:RAMEmitter` (PascalCase). `composites/__init__.py` imports each submodule for side effects.
- **Emitter alias:** `local:RAMEmitter` (not `local:ram-emitter`).
- **Publish base-path:** `/pbg-fenics/dashboard`. Output bundle: `reports/published/dashboard/`.
- **Commits:** local only. NO push / gh-pages deploy until the user explicitly approves. Commit messages end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Before every commit:** `git branch --show-current` + `git rev-parse --short HEAD` sanity check in the worktree tasks.

---

## File Structure

**`pbg-fenics/` (new repo):**
- `pixi.toml`, `pixi.lock` — conda env (dolfinx + gmsh + pbg/dashboard via pip).
- `pyproject.toml` — `pbg_fenics` package metadata + discovery deps.
- `pbg_fenics/__init__.py` — re-export processes + generators.
- `pbg_fenics/fem.py` — dolfinx helpers (mesh build, function space, assemble/solve, node-array ↔ dolfinx Function conversion). Single home for the validated dolfinx API.
- `pbg_fenics/types.py` — `register_types(core)` for `fem_field` (optional).
- `pbg_fenics/processes/poisson.py` — `PoissonSolverStep`.
- `pbg_fenics/processes/diffusion.py` — `DiffusionProcess`.
- `pbg_fenics/processes/reaction.py` — `LogisticReactionProcess`.
- `pbg_fenics/processes/flow.py` — `NavierStokesProcess`.
- `pbg_fenics/processes/moving_boundary.py` — `MovingBoundaryProcess`.
- `pbg_fenics/composites/{__init__,poisson,diffusion,reaction_diffusion,convergence,flow,moving_boundary,complex_geometry}.py`.
- `pbg_fenics/viz.py` — shared interactive-viz helpers (Plotly field heatmap/animation, Three.js 3D mesh) built under the `dataviz` skill.
- `tests/test_*.py` — one per process/composite + discovery + coupling.
- `investigations/fenics-showcase/investigation.yaml` + `studies/<slug>/study.yaml` (7) + per-study `canonical_runs` scripts under `studies/<slug>/sims/`.
- `workspace.yaml`, `scripts/publish_dashboard.sh`, `.github/workflows/publish-dashboard.yml`, `scripts/lint-workspace.py`.
- `README.md`, `.gitignore`.

**`pbg-superpowers--viva-expert-investigation/` (worktree):**
- `viva_superpowers/scaffold.py` — add `investigation-from-wrapper` subcommand + publish-asset emission (or a new `viva_superpowers/publish_assets.py` templater).
- `viva_superpowers/templates/publish_dashboard.sh.j2`, `publish-dashboard.yml.j2` — templated from `pbg-biomodels`.
- `skills/viva-expert/SKILL.md` — Phase 5 rewrite + conda/pixi path + description/deliverables/cross-links.
- `skills/viva-investigation|viva-study|viva-run|viva-workbench/SKILL.md` — see-also cross-links.
- `tests/test_scaffold_investigation_from_wrapper.py` — scaffolder test.

---

## Task 0: `pbg-fenics` repo + pixi env + dolfinx API spike

**Files:**
- Create: `pbg-fenics/pixi.toml`, `pbg-fenics/.gitignore`, `pbg-fenics/pyproject.toml`, `pbg-fenics/pbg_fenics/__init__.py`, `pbg-fenics/scratch/spike_poisson.py`

**Interfaces:**
- Produces: a working `pixi run python` with `dolfinx`, `ufl`, `gmsh`, `process_bigraph`, `bigraph_schema`, `vivarium_workbench` importable; a validated minimal Poisson solve documenting the **exact dolfinx API** (module paths, `functionspace` vs `FunctionSpace`, `LinearProblem` location, PETSc options) that all later tasks reuse via `pbg_fenics/fem.py`.

- [ ] **Step 1: Scaffold repo + pixi.toml**

```bash
mkdir -p /Users/eranagmon/code/pbg-fenics && cd /Users/eranagmon/code/pbg-fenics && git init
```

`pixi.toml`:
```toml
[workspace]
name = "pbg-fenics"
authors = ["Eran <agmon.eran@gmail.com>"]
channels = ["conda-forge"]
platforms = ["osx-arm64"]
version = "0.1.0"

[dependencies]
python = "3.12.*"
fenics-dolfinx = "*"
mpich = "*"
gmsh = "*"
python-gmsh = "*"
pip = "*"
matplotlib = "*"

[pypi-dependencies]
process-bigraph = "*"
bigraph-schema = "*"
bigraph-viz2 = "*"
vivarium-workbench = "*"
plotly = "*"
pytest = "*"
pbg-fenics = { path = ".", editable = true }
```

`.gitignore`:
```gitignore
.pixi/
.venv/
__pycache__/
*.egg-info/
dist/
build/
*.pyc
.pytest_cache/
output/
*.nc
reports/published/
scratch/*.png
.pbg/
```

- [ ] **Step 2: Install env**

Run: `cd /Users/eranagmon/code/pbg-fenics && pixi install`
Expected: solves and creates `.pixi/`. If solve fails on `python-gmsh`, drop it and use `gmsh` python bindings directly; re-run.

- [ ] **Step 3: Verify imports**

Run:
```bash
pixi run python -c "import dolfinx, ufl, basix, gmsh; from mpi4py import MPI; import process_bigraph, bigraph_schema, vivarium_workbench; print('dolfinx', dolfinx.__version__)"
```
Expected: prints a dolfinx version, no ImportError. Fix env until green.

- [ ] **Step 4: dolfinx Poisson spike (pin the API)**

`scratch/spike_poisson.py` — solve `-∇²u = f` on unit square with MMS `u_exact = 1 + x² + 2y²`, `f = -6`, Dirichlet BC = `u_exact`, and print the L2 error (should be ~1e-15 for P2). Use the current dolfinx API:
```python
import numpy as np
from mpi4py import MPI
from dolfinx import mesh, fem
from dolfinx.fem.petsc import LinearProblem
import ufl

domain = mesh.create_unit_square(MPI.COMM_WORLD, 16, 16)
V = fem.functionspace(domain, ("Lagrange", 2))

def u_exact_expr(x):
    return 1 + x[0]**2 + 2*x[1]**2

uD = fem.Function(V); uD.interpolate(u_exact_expr)
tdim = domain.topology.dim
domain.topology.create_connectivity(tdim-1, tdim)
boundary_facets = mesh.exterior_facet_indices(domain.topology)
dofs = fem.locate_dofs_topological(V, tdim-1, boundary_facets)
bc = fem.dirichletbc(uD, dofs)

u = ufl.TrialFunction(V); v = ufl.TestFunction(V)
f = fem.Constant(domain, -6.0)
a = ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx
L = f * v * ufl.dx
problem = LinearProblem(a, L, bcs=[bc],
    petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
uh = problem.solve()

# L2 error
error = fem.form((uh - uD)**2 * ufl.dx)
err = np.sqrt(domain.comm.allreduce(fem.assemble_scalar(error), op=MPI.SUM))
print("L2 error:", err)
print("ndofs:", uh.x.array.size)
```

Run: `pixi run python scratch/spike_poisson.py`
Expected: `L2 error:` ~1e-14. **If any API name differs in the installed version, record the working form** — later tasks reference `fem.functionspace`, `LinearProblem` from `dolfinx.fem.petsc`, `uh.x.array`.

- [ ] **Step 5: Commit**

```bash
cd /Users/eranagmon/code/pbg-fenics
git add pixi.toml pixi.lock .gitignore pyproject.toml pbg_fenics/__init__.py scratch/spike_poisson.py
git commit -m "chore: pbg-fenics pixi env + dolfinx Poisson spike (real dolfinx validated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

`pyproject.toml` (minimal, discovery-ready):
```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "pbg-fenics"
version = "0.1.0"
description = "Process-bigraph wrapper for FEniCSx (dolfinx)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = ["bigraph-schema>=0.0.60", "process-bigraph>=0.0.66"]

[tool.hatch.build.targets.wheel]
packages = ["pbg_fenics"]
```

---

## Task 1: `fem.py` helpers + field type

**Files:**
- Create: `pbg_fenics/fem.py`, `pbg_fenics/types.py`, `tests/test_fem.py`

**Interfaces:**
- Produces:
  - `fem.build_mesh(kind, resolution) -> (domain, V)` where `kind in {"unit_square"}`, `V = functionspace(domain,("Lagrange",degree))`.
  - `fem.solve_poisson(domain, V, source_fn, bc_fn) -> np.ndarray` (nodal values, `uh.x.array` copy).
  - `fem.node_coords(V) -> np.ndarray (N,2)` — dof coordinates for viz.
  - `fem.l2_error(domain, V, uh_array, exact_fn) -> float`.
  - `register_types(core)` registering `fem_field` = `{"_inherit":"array","_data":"float64"}`.

- [ ] **Step 1: Write failing test** `tests/test_fem.py`:
```python
import numpy as np
from pbg_fenics import fem

def test_poisson_mms_converges():
    domain, V = fem.build_mesh("unit_square", 16, degree=2)
    uh = fem.solve_poisson(
        domain, V,
        source_fn=lambda x: -6.0 + 0*x[0],
        bc_fn=lambda x: 1 + x[0]**2 + 2*x[1]**2,
    )
    err = fem.l2_error(domain, V, uh, lambda x: 1 + x[0]**2 + 2*x[1]**2)
    assert err < 1e-10
    assert fem.node_coords(V).shape == (uh.size, 2)
```

- [ ] **Step 2: Run — expect fail** `pixi run pytest tests/test_fem.py -v` → ImportError/AttributeError.

- [ ] **Step 3: Implement `fem.py`** wrapping the validated spike API: `build_mesh` (create_unit_square + functionspace with `degree`), `solve_poisson` (interpolate BC, locate boundary dofs, assemble a/L, `LinearProblem(...).solve()`, return `uh.x.array.copy()`), `node_coords` (`V.tabulate_dof_coordinates()[:, :2]`), `l2_error` (interpolate exact into a Function, form `(uh-exact)**2*dx`, assemble_scalar + sqrt). `types.py` with `register_types`.

- [ ] **Step 4: Run — expect pass** `pixi run pytest tests/test_fem.py -v`.

- [ ] **Step 5: Commit** `feat(fenics): fem.py dolfinx helpers + fem_field type`.

---

## Task 2: `PoissonSolverStep` + `poisson_baseline` composite

**Files:**
- Create: `pbg_fenics/processes/poisson.py`, `pbg_fenics/composites/__init__.py`, `pbg_fenics/composites/poisson.py`, `tests/test_poisson.py`
- Modify: `pbg_fenics/__init__.py`

**Interfaces:**
- Consumes: `fem.build_mesh/solve_poisson/l2_error`.
- Produces: `PoissonSolverStep(Step)` with `config_schema={resolution:int=16, degree:int=2, source_value:float=-6.0}`; `inputs()={}` (stateless boundary from config); `outputs()={"solution":"array[float]","l2_error":"float"}`; `update(state)` solves MMS and returns nodal array + error. Generator `poisson_baseline(core=None,*,resolution=16,degree=2)`.

- [ ] **Step 1: Failing test** `tests/test_poisson.py`:
```python
from process_bigraph import Process, Step, allocate_core
from pbg_fenics.processes.poisson import PoissonSolverStep

def test_poisson_step_update():
    core = allocate_core()
    step = PoissonSolverStep(config={"resolution": 16, "degree": 2}, core=core)
    out = step.update({})
    assert out["l2_error"] < 1e-10
    assert len(out["solution"]) > 0

def test_poisson_generator_registered():
    from viva_superpowers.composite_generator import _REGISTRY
    assert any(e.endswith(".poisson_baseline") for e in _REGISTRY)
```

- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** `PoissonSolverStep` (Step because stateless, no time-varying inputs — the Port-Design "no inputs ⇒ Step" rule); `composites/poisson.py` with `@composite_generator(name="poisson_baseline", …)` returning `{poisson:{_type:step,address:"local:PoissonSolverStep",…}, stores:{solution:[], l2_error:0.0}, emitter:{…RAMEmitter…}}`; `composites/__init__.py` `from . import poisson`; re-export in package `__init__.py`.
- [ ] **Step 4: Run — expect pass** (`pixi run pip install -e .` first so discovery sees classes).
- [ ] **Step 5: Commit** `feat(fenics): PoissonSolverStep + poisson_baseline generator`.

---

## Task 3: `DiffusionProcess` + `transient_diffusion` composite

**Files:** Create `pbg_fenics/processes/diffusion.py`, `pbg_fenics/composites/diffusion.py`, `tests/test_diffusion.py`; Modify `composites/__init__.py`, `__init__.py`.

**Interfaces:**
- Produces: `DiffusionProcess(Process)`, `config_schema={resolution:int=32, degree:int=1, D:float=0.1, dt:float=0.01, initial:string="gaussian"}`; `inputs()={"source":"array[float]"}` (additive nodal source a sibling can write); `outputs()={"solution":"array[float]","integral":"float"}`; `initial_state()` returns a gaussian bump array; `update(state, interval)` does backward-Euler diffusion steps over `interval` using real dolfinx (bilinear `(u v + dt·D·∇u·∇v)dx`, RHS `(u_n + dt·source) v dx`) and returns the **delta** field (`new - prev`) so the `array[float]` store accumulates. Generator `transient_diffusion(core=None,*,resolution=32,D=0.1,dt=0.01)`.

- [ ] **Step 1: Failing test:**
```python
from process_bigraph import allocate_core
from pbg_fenics.processes.diffusion import DiffusionProcess
import numpy as np

def test_diffusion_mass_and_smoothing():
    core = allocate_core()
    p = DiffusionProcess(config={"resolution": 32, "D": 0.1, "dt": 0.01}, core=core)
    s0 = np.array(p.initial_state()["solution"])
    delta = p.update({"source": np.zeros_like(s0), "solution": s0}, interval=0.05)
    s1 = s0 + np.array(delta["solution"])
    assert s1.max() < s0.max()            # peak diffuses down
    assert abs(s1.sum() - s0.sum()) / s0.sum() < 0.05   # ~mass conserved (no-flux/decay)
```

- [ ] **Step 2–4:** run-fail → implement (persist `self._u_n` between calls; rebuild mesh/forms lazily; emit delta) → run-pass.
- [ ] **Step 5: Commit** `feat(fenics): DiffusionProcess + transient_diffusion generator`.

---

## Task 4: `LogisticReactionProcess` + `reaction_diffusion` coupling composite

**Files:** Create `pbg_fenics/processes/reaction.py`, `pbg_fenics/composites/reaction_diffusion.py`, `tests/test_reaction_diffusion.py`; Modify `composites/__init__.py`, `__init__.py`.

**Interfaces:**
- Produces: `LogisticReactionProcess(Process)`, pure-numpy, `config_schema={r:float=1.0, K:float=1.0}`; `inputs()={"solution":"array[float]"}`; `outputs()={"source":"array[float]"}`; `update(state, interval)` returns `r·u·(1 - u/K)·interval` as the `source` delta. Generator `reaction_diffusion(core=None,*,resolution=32,D=0.05,r=1.0,dt=0.01)` wiring **DiffusionProcess.source ← shared `source` store ← LogisticReactionProcess.source** and **both read shared `field` store** → Fisher-KPP by composition.

- [ ] **Step 1: Failing test** — build the composite, run a few steps, assert the field develops a growing/advancing front (max increases toward K where diffusion spreads it):
```python
from process_bigraph import Composite, allocate_core, gather_emitter_results
from pbg_fenics.composites.reaction_diffusion import reaction_diffusion

def test_fisher_kpp_front_grows():
    core = allocate_core()
    doc = reaction_diffusion(core, resolution=24, D=0.05, r=2.0, dt=0.01)
    sim = Composite({"state": doc}, core=core); sim.run(0.2)
    res = gather_emitter_results(sim)[("emitter",)]
    first, last = res[0]["integral"], res[-1]["integral"]
    assert last > first          # reaction grows total; diffusion spreads it
```

- [ ] **Step 2–4:** run-fail → implement process + generator (shared `field` store wired to Diffusion `solution` in/out and Reaction `solution` in; shared `source` store wired Reaction-out → Diffusion-in) → run-pass. This is the **headline composability proof** — verify additive `array[float]` apply merges the two writers.
- [ ] **Step 5: Commit** `feat(fenics): Fisher-KPP via Diffusion⊕Reaction coupling generator`.

---

## Task 5: `mesh_convergence` composite + convergence test

**Files:** Create `pbg_fenics/composites/convergence.py`, `tests/test_convergence.py`; Modify `composites/__init__.py`.

**Interfaces:**
- Produces: `mesh_convergence(core=None,*,resolution=16,degree=1)` — a composite wrapping `PoissonSolverStep` at a given resolution (its `l2_error` is the readout). The convergence *sweep* is expressed as study variants over `resolution`.

- [ ] **Step 1: Failing test** — assert error halves at the expected rate across resolutions (rate ≈ degree+1):
```python
import numpy as np
from process_bigraph import allocate_core
from pbg_fenics.processes.poisson import PoissonSolverStep

def test_convergence_rate():
    core = allocate_core()
    errs = []
    for n in (8, 16, 32):
        e = PoissonSolverStep(config={"resolution": n, "degree": 1}, core=core).update({})["l2_error"]
        errs.append(e)
    rates = [np.log2(errs[i]/errs[i+1]) for i in range(len(errs)-1)]
    assert min(rates) > 1.7   # P1 → O(h^2)
```

- [ ] **Step 2–4:** run-fail → implement generator → run-pass.
- [ ] **Step 5: Commit** `feat(fenics): mesh_convergence generator + convergence rate test`.

---

## Task 6: Interactive viz helpers

**Files:** Create `pbg_fenics/viz.py`, `tests/test_viz.py`.

**Interfaces:**
- Produces (build under the **dataviz** skill — invoke it before writing chart code):
  - `viz.field_heatmap_html(coords, values, title) -> str` — Plotly triangulated/heatmap of a scalar field.
  - `viz.field_animation_html(coords, frames, times, title) -> str` — Plotly with a time slider over `frames` (list of nodal arrays).
  - `viz.convergence_loglog_html(h, errors) -> str` — log-log with fitted slope annotation.
  - `viz.quiver_streamlines_html(coords, u, v, speed, title) -> str` — velocity field.
  - `viz.mesh3d_html(coords3, cells, values, times=None) -> str` — Three.js 3D mesh viewer (orbit, slider, sequential colormap) for complex/3D geometry.
- Each returns a self-contained HTML fragment (CDN Plotly/Three.js) suitable for `studies/<slug>/viz/<name>.html`.

- [ ] **Step 1: Failing test** — assert each returns non-empty HTML containing the expected library tag and a data payload:
```python
import numpy as np
from pbg_fenics import viz

def test_field_heatmap_html():
    html = viz.field_heatmap_html(np.random.rand(20,2), np.random.rand(20), "t")
    assert "plotly" in html.lower() and len(html) > 500

def test_convergence_loglog_html():
    html = viz.convergence_loglog_html([1/8,1/16,1/32],[1e-2,2.5e-3,6e-4])
    assert "plotly" in html.lower()
```

- [ ] **Step 2: Invoke dataviz skill**, then Steps 3–4 implement + pass. Palette from `dataviz` references; light/dark aware.
- [ ] **Step 5: Commit** `feat(fenics): interactive Plotly/Three.js viz helpers`.

---

## Task 7: Workspace promotion + `fenics-showcase` investigation (core studies)

**Files:** Create `pbg-fenics/workspace.yaml`, `investigations/fenics-showcase/investigation.yaml`, `investigations/fenics-showcase/studies/{poisson-validation,mesh-convergence,transient-diffusion,reaction-diffusion}/study.yaml` + `sims/run.py` each; `scripts/lint-workspace.py`.

**Interfaces:**
- Consumes: the 5 core generators (`poisson_baseline`, `mesh_convergence`, `transient_diffusion`, `reaction_diffusion`) by registry id.
- Produces: a lint-clean workspace with an investigation binding the 4 core studies, each with `baseline[].composite` = real generator id, `expected_behavior`, `behavior_tests`, `parent_studies` DAG, `canonical_runs:[{name,script:sims/run.py,default:true}]`, and `visualizations`.

- [ ] **Step 1:** `pixi run python -m viva_superpowers.scaffold workspace --in-place --name fenics --target . --package pbg_fenics --branch main` then `viva_superpowers.workspace_catalog add --path "$(pwd)" --name fenics --package pbg_fenics`.
- [ ] **Step 2:** Hand-author `investigation.yaml` (schema_version 2) with `executive`/`scientific_argument` spine, `studies: [poisson-validation, mesh-convergence, transient-diffusion, reaction-diffusion]`, `acceptance_criteria` linking each study to a `behavior` name.
- [ ] **Step 3:** Author each `study.yaml` (baseline composite id, `expected_behavior[].name` matching acceptance_criteria, `parent_studies` = linear DAG, `canonical_runs`, `visualizations`) and a `sims/run.py` that builds the composite, runs it, writes `runs.db` (ParquetEmitter or the study run harness) and renders `viz/<name>.html` via `pbg_fenics.viz`.
- [ ] **Step 4:** `pixi run python scripts/lint-workspace.py` → "workspace lint: OK"; `pixi run pytest` green.
- [ ] **Step 5: Commit** `feat(fenics): workspace + fenics-showcase investigation (4 core studies)`.

---

## Task 8: Run core studies → `runs.db` + committed interactive viz

**Files:** Modify each core `studies/<slug>/` (adds `runs.db`, `viz/*.html`, `*.meta.json`).

- [ ] **Step 1:** For each core study run its canonical script:
```bash
cd /Users/eranagmon/code/pbg-fenics
for s in poisson-validation mesh-convergence transient-diffusion reaction-diffusion; do
  pixi run python investigations/fenics-showcase/studies/$s/sims/run.py
done
```
- [ ] **Step 2:** Verify `runs.db` exists per study and `viz/*.html` render (open one).
- [ ] **Step 3:** Run behavior tests (`/viva-study`-style pytest under `studies/<slug>/tests/` if authored, else the process tests already cover the behaviors).
- [ ] **Step 4:** Confirm outcomes recorded.
- [ ] **Step 5: Commit** `feat(fenics): run core studies → runs.db + interactive viz`.

---

## Task 9 (Tier 2, parallel): Navier-Stokes study

**Files:** Create `pbg_fenics/processes/flow.py` (`NavierStokesProcess`), `pbg_fenics/composites/flow.py` (`navier_stokes(core=None,*,reynolds=100,resolution=32,dt=0.01)`), `investigations/fenics-showcase/studies/navier-stokes/{study.yaml,sims/run.py}`, `tests/test_flow.py`.

**Interfaces:** `NavierStokesProcess(Process)` — incompressible NS (IPCS splitting or Stokes for low Re) on a lid-driven cavity or channel; `inputs()={"body_force":"array[float]"}`; `outputs()={"velocity":"array[float]","pressure":"array[float]","speed_integral":"float"}`. Viz: `viz.quiver_streamlines_html`.

- [ ] Steps: failing test (steady velocity is non-trivial and divergence≈0; speed increases with lid velocity/Re trend) → implement real dolfinx NS → pass → author study.yaml (baseline `navier_stokes`, variants sweep `reynolds`, parent `poisson-validation`) + `sims/run.py` (runs.db + streamlines viz) → run → commit `feat(fenics): Navier-Stokes process + study + streamline viz`.
- [ ] **Isolation:** build in a git worktree of `pbg-fenics` (`pbg-fenics--ns`) to avoid file collisions with Tasks 10–11; cherry-pick/merge onto current HEAD before combining.

---

## Task 10 (Tier 2, parallel): Moving-boundary study

**Files:** Create `pbg_fenics/processes/moving_boundary.py` (`MovingBoundaryProcess`), `pbg_fenics/composites/moving_boundary.py` (`moving_boundary(core=None,*,resolution=32,speed=0.1,dt=0.01)`), `investigations/.../studies/moving-boundary/{study.yaml,sims/run.py}`, `tests/test_moving_boundary.py`.

**Interfaces:** `MovingBoundaryProcess(Process)` — ALE / deforming domain (e.g. a growing or oscillating boundary via mesh coordinate update + solve on the deformed mesh); `outputs()={"solution":"array[float]","domain_measure":"float","boundary_position":"float"}`. Viz: `viz.field_animation_html` over the moving mesh.

- [ ] Steps: failing test (`boundary_position` / `domain_measure` changes monotonically with `speed`; solve stays finite) → implement real ALE update → pass → study.yaml (variants sweep `speed`, parent `navier-stokes`) + run.py → run → commit. **If ALE proves intractable in the installed dolfinx**, ship the process guarded with a clear `RuntimeError` describing the missing capability and mark the study `design_pivot_required` — surface to user, do not mock. Worktree `pbg-fenics--mb`.

---

## Task 11 (Tier 2, parallel): Complex-geometry study (gmsh)

**Files:** Create `pbg_fenics/composites/complex_geometry.py` (`complex_geometry(core=None,*,geometry="obstacle",resolution=32)`), `pbg_fenics/fem_gmsh.py` (gmsh→dolfinx mesh import), `investigations/.../studies/complex-geometry/{study.yaml,sims/run.py}`, `tests/test_complex_geometry.py`.

**Interfaces:** gmsh builds an obstacle/L-shape/annulus mesh imported via `dolfinx.io.gmshio`; reuse `DiffusionProcess`/`PoissonSolverStep` on the imported mesh (generalize `fem.build_mesh` to accept a gmsh mesh). Viz: `viz.field_heatmap_html` on the non-trivial domain + `viz.mesh3d_html` for a 3D variant.

- [ ] Steps: failing test (mesh imports with expected #cells; Poisson solves on it, error finite) → implement gmsh import + generator → pass → study.yaml (variants over `geometry`, parent `poisson-validation`) + run.py → run → commit. Worktree `pbg-fenics--cg`.

---

## Task 12 (Tier 3): merge advanced studies + wire investigation to 7 studies

**Files:** Modify `investigations/fenics-showcase/investigation.yaml` (`studies:` → all 7; extend `acceptance_criteria`), `pbg_fenics/composites/__init__.py`, `pbg_fenics/__init__.py`.

- [ ] Cherry-pick/merge the three Tier-2 worktrees onto `pbg-fenics` HEAD (verify no foreign commits). Update `investigation.yaml` `studies` list + `acceptance_criteria` for ns/moving-boundary/complex-geometry. `pixi run pytest` all green; `discover_generators()` shows all 7. Commit `feat(fenics): integrate 7-study showcase investigation`.

---

## Task 13 (Tier 3): `viva_superpowers` publish-asset templater

**Files (worktree):** Create `viva_superpowers/publish_assets.py`, `viva_superpowers/templates/publish_dashboard.sh.j2`, `viva_superpowers/templates/publish-dashboard.yml.j2`, `tests/test_publish_assets.py`. Templates copied/parameterized from `pbg-biomodels/scripts/publish_dashboard.sh` + `.github/workflows/publish-dashboard.yml`.

**Interfaces:** `publish_assets.emit(workspace_dir, name, base_path=None, interactive_url=None)` writes `scripts/publish_dashboard.sh` (chmod +x) + `.github/workflows/publish-dashboard.yml` with `base_path` defaulting to `/pbg-<name>/dashboard`.

- [ ] Failing test (emit into tmp dir, assert both files exist, contain the base-path and `vivarium-workbench-publish`, script is executable) → implement (read `.j2`, substitute, write) → pass → commit `feat(viva): publish-asset templater (fills add-dashboard gap)`.

---

## Task 14 (Tier 3): `investigation-from-wrapper` scaffolder

**Files (worktree):** Modify `viva_superpowers/scaffold.py` (add subcommand); Create `tests/test_scaffold_investigation_from_wrapper.py`.

**Interfaces:** `python -m viva_superpowers.scaffold investigation-from-wrapper --name <slug> --studies <gen1,gen2,…> [--workspace .]` → writes `investigations/<slug>/investigation.yaml` (schema_version 2, `studies:` = one slug per generator, executive/scientific_argument stubs, acceptance_criteria stubs) + per-generator `studies/<slug>/study.yaml` (baseline `composite:` = generator id, `expected_behavior` stub, `canonical_runs:[{name,script:sims/run.py,default:true}]`, linear `parent_studies`).

- [ ] Failing test (run subcommand into a tmp workspace with 2 fake generator ids, assert investigation.yaml lists 2 studies and each study.yaml has the right baseline composite id + canonical_runs) → implement → pass → commit `feat(viva): scaffold investigation-from-wrapper`.

---

## Task 15 (Tier 3): rewrite `viva-expert/SKILL.md`

**Files (worktree):** Modify `skills/viva-expert/SKILL.md`.

- [ ] Replace **Phase 5 "Demo Report"** section with **"Phase 5: Showcase Investigation + Published Read-only Workbench"**: (a) `investigation-from-wrapper` scaffold from the repo's generators; (b) author `expected_behavior`/`behavior_tests`/`canonical_runs` + interactive viz per study (invoke `dataviz`); (c) run studies → `runs.db`; (d) `publish_assets.emit` + `vivarium-workbench-publish --workspace . --out reports/published/dashboard --base-path /pbg-<tool>/dashboard`; (e) open the bundle. Interactive viz lives in study `viz/`, not `demo/report.html`.
- [ ] Add a **conda/pixi install path** subsection (for conda-only tools: pixi.toml on conda-forge, one env holding solver + pbg/dashboard, all commands via `pixi run`) next to the uv `.venv` path; reference `pbg-compucell3d` + `pbg-fenics`.
- [ ] Update frontmatter `description`, top-of-file "The Default"/intent, **Deliverables** checklist (investigation+studies+published dashboard replace demo report; keep processes+generators+workspace), **README Requirements** (link published dashboard), **Final Validation** (run studies + publish + lint), and the **Start** dispatch text. Mirror the same terminus into **Composite Mode**. Lightweight mode unchanged.
- [ ] Commit `docs(viva-expert): terminate heavy mode at investigation + read-only workbench`.

---

## Task 16 (Tier 3): cross-link sibling skills + local publish verify

**Files (worktree):** Modify `skills/viva-investigation|viva-study|viva-run|viva-workbench/SKILL.md` (see-also block linking the viva-expert → investigation → study → run → publish chain). **In `pbg-fenics`:** emit publish assets + produce the bundle.

- [ ] `pixi run python -c "from viva_superpowers.publish_assets import emit; emit('.', 'fenics', base_path='/pbg-fenics/dashboard', interactive_url='https://github.com/vivarium-collective/pbg-fenics')"` (from `pbg-fenics`, with the worktree package importable), then `pixi run vivarium-workbench-publish --workspace . --out reports/published/dashboard --base-path /pbg-fenics/dashboard`; open `reports/published/dashboard/index.html`, click into each of the 7 studies, confirm interactive viz renders read-only.
- [ ] Add see-also cross-links in the 4 sibling skills.
- [ ] Commit skills in worktree (`docs(viva): cross-link investigation/study/run/publish chain`) and `pbg-fenics` bundle/README (`feat(fenics): published read-only workbench bundle + README`).
- [ ] **STOP — no push.** Report to user: local commits on `pbg-fenics` (main) + worktree branch `viva-expert-investigation-workbench`; offer gh-pages deploy + PRs only on explicit approval.

---

## Self-Review

**Spec coverage:** Part A env→pixi (T0), processes (T1–T5, T9–T11), composites (T2–T5, T9–T11), investigation+studies (T7, T12), runs+viz (T6, T8), publish (T13, T16), workspace promotion (T7). Part B skill rewrite (T15). Part C scaffolder (T14) + publish templater (T13) + cross-links (T16). All 7 studies covered. ✓

**Placeholder scan:** each code task carries real test assertions + concrete dolfinx/generator skeletons; advanced tasks reference the exact FEM method and a real behavior assertion. dolfinx API pinned in T0 and reused via `fem.py`. ✓

**Type consistency:** field state is `array[float]` everywhere; `solution`/`source`/`integral`/`l2_error` port names consistent across Diffusion/Reaction/Poisson; generator names match investigation `baseline[].composite` ids; `publish_assets.emit(...)` and `investigation-from-wrapper` signatures reused verbatim in T15/T16. ✓
