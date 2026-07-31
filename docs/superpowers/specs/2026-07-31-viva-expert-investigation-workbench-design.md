# viva-expert → investigation + published read-only workbench

**Date:** 2026-07-31
**Status:** Approved (design)
**Author:** Eran Agmon (+ Claude)
**Branch:** `viva-expert-investigation-workbench` (worktree of `viva-superpowers`)

## Problem

The `viva-expert` skill's heavy mode terminates at a standalone
`demo/report.html` per wrapper repo. That artifact is disconnected from the
investigation/study/workbench substrate the ecosystem has since standardized
on. We want heavy-mode wrappers to instead terminate at:

- **processes + `@composite_generator` composites** (already produced today), plus
- **one showcase investigation** containing several **studies** that reference
  the real composites, run into `runs.db`, and carry **beautiful interactive
  visualizations**, and
- a **published read-only workbench** (static bundle → `gh-pages:dashboard/`)
  that replaces the standalone HTML report.

We prove the new flow by wrapping **FEniCSx** (modern FEniCS) end-to-end, then
codify the proven recipe back into the skill and smooth the surrounding
`viva-superpowers` tooling.

## Non-goals

- No push / gh-pages deploy without explicit user approval (skill safety rule).
- No mock/reproduction of FEniCS — real dolfinx bridge (user opted in).
- No refactor of unrelated skills; changes are scoped to the flow above.

## Decisions (locked)

1. **Sequencing:** FEniCS-first, then codify. Build `pbg-fenics/` working, then
   extract the recipe into `viva-expert/SKILL.md` and the scaffolder.
2. **FEniCS install:** real `fenics-dolfinx` from conda-forge, managed with
   **pixi** (`pixi.toml`/`pixi.lock`), mirroring `pbg-compucell3d`. One pixi env
   holds the solver **and** the pbg/dashboard stack; `pixi run` drives tests,
   dashboard, and publish. (`fenics-dolfinx` has no PyPI wheel; verified pip
   resolve fails. `micromamba`/`mamba`/`pixi` are present on this machine.)
3. **Showcase investigation:** reaction-diffusion coupling as the headline, plus
   validation/convergence and the advanced set (Navier-Stokes, moving boundary,
   complex geometry) — 7 studies total.
4. **Skill-update scope:** rewrite `viva-expert` terminal phase + add a
   `viva_superpowers` scaffolder helper + emit publish assets from the
   `pbg-biomodels` template + cross-link sibling skills.

## Contracts (verified)

- **Investigation:** `investigations/<slug>/investigation.yaml`
  (`schema_version: 2`): `name/title/question/hypothesis`, `studies: [slugs]`
  (membership list — the join), `executive:{…}` + `scientific_argument:{…}`
  spine, `acceptance_criteria:[{study, behavior}]` → a member's
  `expected_behavior[i].name`.
- **Study:** `investigations/<inv>/studies/<slug>/study.yaml` with
  `investigation:` back-ref. Key fields: `baseline:[{name, composite, params}]`
  (composite = **real registered composite id**), `variants:[{name,
  base_composite, parameter_overrides}]`, `expected_behavior:[{name, observable,
  condition, rationale}]`, `behavior_tests[]`, `parent_studies:[{study,
  condition, relation}]` (the DAG edges), `canonical_runs:[{name, script,
  args[], label, default}]`, `visualizations:[{name, chart, render}]`.
- **Execution:** `/viva-study run-script [--entry N]` shells out
  `python <script> <args>` from `canonical_runs`; results land in
  `studies/<slug>/runs.db` (SQLite `runs_meta`) and/or `parquet-runs/<run>/`.
  Charts render to `studies/<slug>/viz/<name>.html` (+ `.meta.json` sidecars).
- **Publish (read-only workbench):** `vivarium-workbench-publish --workspace .
  --out ./reports/published/dashboard --base-path /pbg-fenics/dashboard
  --interactive-url <repo>` (entry point `vivarium_workbench.publish:main`,
  verified). Produces a self-contained static bundle (`index.html`,
  `studies/<slug>/index.html`, `assets/`, `api/*.json`, `config.json`
  `mode:"snapshot"`). Deploy is `scripts/publish_dashboard.sh` +
  `.github/workflows/publish-dashboard.yml` copying the bundle into
  `gh-pages:dashboard/`. NOTE: `vivarium-workbench add-dashboard` is **not** a
  real subcommand — the publish assets are templated files (source of truth:
  `pbg-biomodels`). Our scaffolder emits them.

## Part A — `pbg-fenics/` reference build

### Environment
`pixi.toml` (channels `conda-forge`; platform `osx-arm64`): `fenics-dolfinx`,
`mpich`, `gmsh`, `python-gmsh`, `pyvista` (optional), `python=3.12`, `pip`.
`[pypi-dependencies]` or a pixi `pip` task installs `process-bigraph`,
`bigraph-schema`, `vivarium-workbench`, `bigraph-viz2`, and `-e .` (pbg_fenics).
`pyproject.toml` lists `bigraph-schema`/`process-bigraph` for discovery.

### Processes (`pbg_fenics/processes/`)
- `PoissonSolverStep(Step)` — steady `-∇²u = f`. Inputs: `source`, boundary.
  Outputs: `solution` (`array[float]`), `l2_error`.
- `DiffusionProcess(Process)` — transient `u_t = D∇²u + source`, real per-interval
  FEM step. Inputs: `source` (additive `array[float]` delta), boundary. Outputs:
  `solution` delta, `integral`.
- `StokesProcess` / `NavierStokesProcess(Process)` — incompressible flow;
  outputs `velocity`, `pressure` fields; config `reynolds`, `dt`.
- `LogisticReactionProcess(Process)` — pure-numpy per-node reaction writing
  `source` deltas to the shared field store (Fisher-KPP coupling partner).
- `types.py` — optional `fem_field` type (`array[float]` + mesh metadata); bare
  types otherwise. Ports follow Port-Design rules: bare `float`/`array` deltas,
  `overwrite[T]` only for genuine setpoints.

### Composites (`pbg_fenics/composites/`, all `@composite_generator`)
`poisson_baseline`, `mesh_convergence` (param `resolution`),
`transient_diffusion`, `reaction_diffusion` (Diffusion ⊕ Reaction — the coupling
showcase), `navier_stokes` (param `reynolds`), `moving_boundary` (ALE/deforming
mesh), `complex_geometry` (gmsh obstacle/L-shape/annulus). `composites/__init__.py`
imports each submodule for decorator side-effects.

### Investigation `investigations/fenics-showcase/`
Question: *"Can modern FEniCSx be wrapped as composable pbg processes that
reproduce canonical FEM results and enable bigraph coupling?"* Studies:

| Study | Capability | Interactive viz | Behavior test |
|---|---|---|---|
| `poisson-validation` | correctness vs analytic (MMS) | numeric vs exact + error heatmap | L2 error < tol |
| `mesh-convergence` | FEM rigor | log-log error∝hᵖ + mesh overlays | rate ≈ p |
| `transient-diffusion` | time-stepping | animated field (time slider) + decay curve | mass/decay |
| `reaction-diffusion` (headline) | **bigraph coupling** → Fisher-KPP | animated wavefront + bigraph-viz2 coupling diagram | wave speed |
| `navier-stokes` | fluid dynamics | streamlines + speed heatmap + pressure (slider) | steady/Re trend |
| `moving-boundary` | ALE / deforming domain | animated moving mesh | boundary tracks |
| `complex-geometry` | gmsh meshes | field on obstacle/L-shape; 3D via Three.js | solves on domain |

`parent_studies` DAG: validation → convergence → transient → reaction-diffusion;
validation → navier-stokes → moving-boundary → complex-geometry. Each study has
`canonical_runs` scripts so `/viva-study run-script` records `runs.db`;
`acceptance_criteria` links studies → behaviors. Charts use **Plotly** (2D
fields/animation) and **Three.js** (3D), built under the `dataviz` skill for
palette/design consistency.

### Publish
Scaffolder emits `scripts/publish_dashboard.sh` +
`.github/workflows/publish-dashboard.yml` (base-path `/pbg-fenics/dashboard`)
from the `pbg-biomodels` template. Run `vivarium-workbench-publish … --out
./reports/published/dashboard`, verify the bundle locally, open it. **Local
commit only; no push.** gh-pages deploy is opt-in on explicit approval.

### Workspace promotion
`workspace.yaml` (schema_version 2) + `viva_superpowers.workspace_catalog add`
registration + `scripts/lint-workspace.py` green, per existing convention.

## Part B — rewrite `viva-expert/SKILL.md`

- Replace **Phase 5 "Demo Report (`demo/report.html`)"** with **"Phase 5:
  Showcase Investigation + Published Read-only Workbench"**: build one
  investigation of 2–4+ studies referencing the `@composite_generator`s, author
  `canonical_runs`, run into `runs.db`, scaffold publish assets, export the
  read-only bundle, open it. Interactive viz lives in study `viz/` pages.
- Add a **conda/pixi install path** (conda-only tools like FEniCS/CompuCell3D)
  alongside the uv `.venv` path.
- Update frontmatter `description`, top-of-file intent, deliverables checklist,
  README requirements (link the published dashboard, not `demo/report.html`),
  Final Validation. Explicit hand-offs to `viva-investigation` / `viva-study` /
  `viva-run`. Composite mode gets the same terminus. Lightweight mode unchanged.

## Part C — smooth `viva-superpowers`

- **Scaffolder:** `python -m viva_superpowers.scaffold investigation-from-wrapper
  --name <slug> --studies <gen1,gen2,…> [--workspace .]` → emits
  `investigations/<slug>/investigation.yaml` + skeleton
  `studies/<slug>/study.yaml` (baseline referencing each generator id,
  `canonical_runs` + `expected_behavior` stubs, linear `parent_studies`).
- **Publish helper:** emit `scripts/publish_dashboard.sh` +
  `publish-dashboard.yml` from the `pbg-biomodels` template (fills the phantom
  `add-dashboard` gap).
- **Cross-link** sibling skills (see-also) so viva-expert → investigation →
  study → run → publish is discoverable.

## Build tiers (parallelizable)

1. **Core** (sequential foundation): env/pixi, `PoissonSolverStep`,
   `DiffusionProcess`, `LogisticReactionProcess`, `poisson_baseline`,
   `mesh_convergence`, `transient_diffusion`, `reaction_diffusion` + their
   studies/tests/viz. Establishes the field type + coupling pattern.
2. **Advanced** (parallel agents, independent studies): `navier_stokes`,
   `moving_boundary`, `complex_geometry` — each its own process/composite/study/
   viz. Built in isolated worktrees to avoid file collisions.
3. **Codify:** Part B skill rewrite + Part C scaffolder/publish helper +
   cross-links.

## Risks

- Navier-Stokes, moving-boundary (ALE), gmsh complex-geometry are each
  substantial real-FEM work; the dolfinx conda env is a heavy install. If an
  advanced study proves genuinely intractable in this environment, surface it
  explicitly (guarded process that raises a clear requirement) — never silently
  downgrade to a mock.
- Field-as-`array[float]` coupling must preserve additive apply semantics; verify
  the Diffusion ⊕ Reaction shared store composes correctly.
- pixi env must expose `vivarium-workbench` so the dashboard/publish run inside
  the same env that has dolfinx.

## Success criteria

- `pbg-fenics` installs via pixi; `pytest` (behavior tests) green under `pixi run`.
- All 7 composites discoverable (`discover_generators()`), all 7 studies run into
  `runs.db` with committed interactive `viz/*.html`.
- `vivarium-workbench-publish` produces a static bundle that opens and renders
  every study's viz read-only.
- `viva-expert/SKILL.md` rewritten to this terminus; scaffolder + publish helper
  land in `viva_superpowers`; sibling skills cross-linked.
- Local commits only; no push until approved.
