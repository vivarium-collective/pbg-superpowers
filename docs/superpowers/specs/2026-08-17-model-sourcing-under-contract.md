# Model Sourcing Under Contract — Design

**Status:** approved design (2026-08-17). Extends the agentic model-build loop
([[project_agentic_model_building_loop]]) from "build a handler from a blank draft"
to "**source** a model — reuse an existing module, compose several, or build new
when justified — and audit that sourcing decision."

## Goal
Make the loop choose *where the model comes from*, and hold that choice to a contract:
- **reuse** an existing catalogued module when it already covers the task,
- **compose** several modules when the task spans their domains,
- **build-new** only when no catalogued module (or composition) fits.

Then **audit the sourcing decision** so reuse-when-you-should and build-only-when-warranted
are enforced, not just hoped for.

## Substrate (already exists)
- `vivarium_workbench/lib/analysis_tools.py`: capability matching via
  `set(requires) <= set(candidate.capabilities)`. The sourcing audit reuses this rule.
- Modules already carry capability tokens (e.g. viva-cpm declares `capabilities`).
- `viva_superpowers.loop_state` protocol states; `test_audit` det+LLM sufficiency pattern.

## Data model
A sourcing study/task declares what it needs and what it chose:
```yaml
requires: [physics_2d, rigid_body, collision]      # capability tokens the task needs
sourcing:
  decision: reuse            # reuse | compose | build-new
  modules: [viva-munk]       # chosen catalogued module(s); [] for build-new
  rationale: "2D rigid-body physics covers cell jostling"
```
Catalogued modules expose `capabilities: [tokens]` (from their describe()/registry entry).
The audit is passed a `catalog` = `{module_name: [capabilities]}` (from the workbench
catalog / registry), so it is testable without a live server.

## `viva_superpowers/module_sourcing.py` (Slice 1 — the framework)
- `match_modules(requires, catalog) -> list[str]` — modules whose capabilities ⊇ requires
  (single-module fit); `covers(requires, chosen, catalog) -> bool` — the union of the
  chosen modules' capabilities ⊇ requires (composition fit).
- `build_sourcing_report(spec, catalog) -> report_card_verdict/v2` with axes (reusing
  `test_contract.check`/TestBuilder like `test_audit`); axis IDs stable:
  - **source_fit** *(hard)* — the chosen module(s)' combined capabilities cover `requires`.
    Miss → mismatch (chose a module that doesn't actually do the job).
  - **reinvention** *(hard)* — if `decision == build-new` and some existing module (or
    composition) already satisfies `requires` → mismatch ("you reinvented viva-cpm").
  - **novelty_justified** *(soft)* — if `decision == build-new`, confirm no catalogued
    fit exists (novelty warranted); if a fit exists, drift.
  - **survey_recorded** *(soft)* — `sourcing.rationale`/candidates present (the agent
    actually surveyed, didn't blind-build).
- LLM near-miss hook: the `/viva-audit-tests` skill adds a semantic-fit judgment for
  capability tokens the manifest tags miss (mirrors the existing det+LLM split).

## `loop_state` — a SELECT phase
Add `SELECT` to `STATES` (between AUDIT and LOCK): the sourcing decision is recorded
(`state["sourcing"] = {...}`) and audited before the tests are locked. `validate` gains
no new invariant (sourcing is graded by `module_sourcing`, not the immutability contract).

## Slice 2 — the demonstration (real modules, end-to-end)
A new `model-sourcing` investigation that installs + actually runs the modules:

| Study | `requires` | Right sourcing | Audit catches if wrong |
|---|---|---|---|
| cell-jostling | physics_2d, rigid_body, collision | **reuse** viva-munk | build-new → reinvention |
| growth-and-push | growth, physics_2d | **compose** growth + viva-munk | missed composition (source_fit miss) |
| spatial-competition | spatial, fba, diffusion | **reuse** spatio-flux | wrong module → source_fit miss |
| shape-dynamics | cpm, cell_shape, adhesion | **reuse** viva-cpm | reinvention if built new |
| novel-mechanism | (tokens no module has) | **build-new** (justified) | reused a misfit → source_fit miss |
| trap | looks like viva-munk but needs a capability it lacks | reuse-misfit | source_fit miss |

Each runs the real composed model (viva-munk = pymunk, spatio-flux = spatial FBA, viva-cpm
= Rust CPM), so the demonstration is genuine. viva-cpm's Rust build is the install
bottleneck — if it can't be made runnable in the demo venv, its study degrades to a
sourcing-decision-only exhibit (clearly labelled), the others run for real.

## Slices
1. **Framework** (this repo): `module_sourcing.py` + tests; `loop_state` SELECT phase.
2. **Demonstration** (viva-meta-modelers-guide or a new workspace): install modules,
   author the 6 sourcing studies, drive the loop, run real composed models, and a report.
3. **Workbench render** (vivarium-workbench): a Sourcing sub-panel in Assurance › Audit
   showing the sourcing axes (reuses the axis renderer; IDs stable).

## Constraints
- Deterministic core (AI-free): `module_sourcing` is pure stdlib + viva_superpowers.
- Reuse the `requires ⊆ capabilities` rule; don't fork a second matching semantics.
- Axis IDs stable so the workbench audit renderer needs no branch.
