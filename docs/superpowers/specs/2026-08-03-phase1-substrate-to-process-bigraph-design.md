# Phase 1 — Migrate the framework substrate to process-bigraph

*Design doc · 2026-08-03 · part of the viva-superpowers 3-home re-architecture*

## Context

The end-state (locked with the maintainer): **three homes.**

| Home | Owns |
|---|---|
| **process-bigraph** (engine) | the framework substrate — composite generation/spec/discovery + the visualization Step framework |
| **vivarium-workbench** (server) | all compute — rendering, rigor/evaluation, study derivations, run tracking |
| **viva-superpowers** (plugin) | pure agent skills (SKILL.md) that drive the workbench API + process-bigraph |

**Phase 1** is the first real cross-repo *move*: relocate the framework substrate out of the `viva_superpowers` Python package and into `process_bigraph`. It is the maintainer's explicit ask ("the process-bigraph framework substrate should be migrated to process-bigraph") and it directly reduces the workbench's reliance on the plugin (the workbench's #1 plugin import is `composite_generator`).

**Non-negotiable constraint:** ~1,829 files across ~39 repos still `import viva_superpowers`, and the workbench imports these substrate modules from ~54 sites. Nothing may break. Every moved module leaves a re-export shim in `viva_superpowers`; consumers migrate over a deprecation window. This is the exact playbook used for the pbg→viva rebrand.

## Precedent — this move has already been done once here

`process_bigraph/composite_spec.py` **already exists**, and `viva_superpowers/composite_spec.py` is **already a thin re-export shim** of it:

```python
# viva_superpowers/composite_spec.py
from process_bigraph.composite_spec import (  # noqa: F401  (re-export)
    ...
)
```

Phase 1 generalizes that proven pattern to the rest of the substrate. `process_bigraph/__init__.py` already exports the generator-registration API (`discover_specs`, `register_spec_generator`, `regenerate_default_state`) and `CompositeSpec`, `Composite`, `Emitter`. There are **no name collisions** with the modules we are about to move.

## Scope

### Modules that MOVE (viva_superpowers → process_bigraph), leaving shims

| Module | LOC | Notes |
|---|---|---|
| `composite_generator` | 594 | The `@composite_generator` registry + `discover_generators`, `build_generator`, `install_default_emitters`, `emitter_defaults`, `_REGISTRY`. Already registered into PBG via the `process_bigraph.spec_generators` entry point; already imports `process_bigraph.composite_spec`. |
| `composite_discovery` | 135 | `discover_all` composite index. Imports `process_bigraph.composite_spec.CompositeSpec` + (lazy) `composite_generator.discover_generators`. |
| `core_introspection` | 44 | Pure PBG core introspection. **Zero** `viva_superpowers` imports — cleanest of all. |
| `config_helpers` | 98 | Config-value normalizers for process `initialize()` bodies (the `[low,high]` / `{0:…}` / `{"low":…}` tolerance). Consumed by generated process wrappers downstream. A process-authoring helper → belongs with the substrate. |
| `visualization` | 393 | The `Visualization` Step base class (`process_bigraph.Step` subclass) + `as_visualization` + `render_results`. |
| `visualizations/` (subpkg) | 647 | Concrete viz Steps (`TimeSeriesPlot`, `Heatmap`, `PhaseSpace`, …), each `from viva_superpowers.visualization import Visualization`. Moves as a unit with `visualization`. |
| `_demo_visualizations` | 209 | Example-only viz Steps. **Candidate to drop, not move** — verify no downstream import first (survey flagged it orphan-in-repo). |

`composite_spec` is **already moved** (shim in place) — no action beyond confirming the shim still points at PBG.

### What does NOT move in Phase 1
- All compute (rigor, evaluation, report rendering, study derivations, run tracking) — that's **Phase 2** (→ workbench).
- The skill-only clusters (feedback/guidance judgment, scaffold, calibration, migrations).
- No downstream import rewrites — shims cover every consumer.

### Entanglement analysis (why this is a clean cut)
The substrate modules depend on `process_bigraph` and on **each other**, **not** on the heavy investigation-science modules. The only cross-links are lazy and resolve trivially once co-located in `process_bigraph`:
- `composite_spec` → (lazy) `composite_generator.install_default_emitters`
- `composite_discovery` → (lazy) `composite_generator.discover_generators`
- `visualizations/*` → `visualization.Visualization` (base class)

The one behavior to preserve: `discover_generators` **walks subpackages** so `@composite_generator` decorators fire (`pbg_<ws>/composites/__init__.py`). That walk logic moves verbatim into PBG.

## Target design

### In `process_bigraph`
Add the modules as `process_bigraph/<name>.py` (+ `process_bigraph/visualizations/`). Export the public API from `process_bigraph/__init__.py` alongside the existing composite_spec exports:

```python
# process_bigraph/__init__.py (additions)
from process_bigraph.composite_generator import (
    composite_generator, discover_generators, build_generator,
    install_default_emitters, emitter_defaults,
)
from process_bigraph.visualization import Visualization, as_visualization, render_results
```

The `process_bigraph.spec_generators` entry point that currently targets `viva_superpowers.composite_generator:discover_generators` is updated to `process_bigraph.composite_generator:discover_generators` (or dropped — once the impl is in PBG, self-discovery no longer needs an entry point). **Decision D1 (below).**

### In `viva_superpowers` (shims)
Each moved module becomes a re-export shim, identical in spirit to today's `composite_spec.py`:

```python
# viva_superpowers/composite_generator.py  (after)
"""Back-compat shim: moved to process_bigraph.composite_generator."""
from process_bigraph.composite_generator import *   # noqa: F401,F403
from process_bigraph.composite_generator import (    # explicit for private/underscore names skills use
    _REGISTRY, discover_generators, build_generator,
    install_default_emitters, emitter_defaults,
)
```

Shims must re-export the **exact** public + semi-private surface today's consumers use (e.g. the workbench imports `_REGISTRY`, `emitter_defaults`, `install_default_emitters`). The shim inventory is derived from the coupling maps (workbench 54 sites; skills `-m`/imports; downstream).

## Sequencing (PR-by-PR)

1. **process-bigraph PR** — add the modules + `__init__` exports + entry-point update; port the substrate's own tests. CI green.
2. **process-bigraph release** — version bump + tag (its existing release flow). viva-superpowers will pin `process-bigraph >= <new>`.
3. **viva-superpowers PR** — replace the six moved modules with re-export shims; bump the `process-bigraph` dependency; keep `viva_superpowers.composite_spec` as-is. Update the entry point. CI green.
4. **Verify downstream** — smoke-test that a representative consumer (v2ecoli) still does `import viva_superpowers.composite_generator` and `from process_bigraph import composite_generator` interchangeably; run the workbench test suite against the shimmed plugin.

Steps 1–2 are prerequisites for 3 (the shim can't point at PBG until PBG ships it). This is the same ordering the dist-name rename used.

## Blast radius & back-compat
- **~1,829 downstream `import viva_superpowers.*` sites** keep working via shims — unchanged, no rewrites required this phase.
- **Workbench (~54 sites)** keeps importing `viva_superpowers.composite_generator` etc. via shims; a follow-up (Phase 2-adjacent) repoints the workbench to `process_bigraph.*` directly to actually shed the plugin dependency. **Phase 1 makes it *possible*; it doesn't force the workbench rewrite.**
- Deprecation window: shims emit no warning initially (avoid log spam across 1,829 sites); a `DeprecationWarning` can be added once the major consumers (workbench, v2ecoli) are repointed.

## Non-goals
- Moving any compute (Phase 2).
- Rewriting downstream or workbench imports to `process_bigraph.*` (a later, separate, mechanical sweep).
- Deleting `viva_superpowers` modules outright (shims stay for the deprecation window).
- Touching `.pbg/` on-disk conventions.

## Verification plan
- **process-bigraph**: the moved modules' ported unit tests pass; `discover_generators` still fires `@composite_generator` decorators via the subpackage walk (regression test).
- **viva-superpowers**: `from viva_superpowers.composite_generator import _REGISTRY, discover_generators, build_generator` etc. all resolve through the shims; existing plugin tests green; `test_manifest_version_matches_pyproject` still green.
- **Cross-repo smoke**: build a workspace, run a composite through the workbench against the shimmed plugin + new PBG; confirm composites still discover, build, run, and render.
- **Downstream smoke**: in a v2ecoli checkout, `import viva_superpowers.composite_generator` and `import process_bigraph.composite_generator` both succeed and are the same objects.

## Risks & mitigations
- **R1 — the `spec_generators` entry point / self-discovery loop.** `composite_generator.discover_generators` is the entry-point target; moving the impl into PBG while PBG's `__init__` also participates in discovery risks an import cycle. *Mitigation:* keep discovery lazy (as today); land + test in the process-bigraph PR in isolation before shimming viva.
- **R2 — incomplete shim surface.** A consumer imports a name the shim forgot to re-export → ImportError downstream. *Mitigation:* derive the re-export list from the coupling maps (workbench `_REGISTRY`/`emitter_defaults`/`install_default_emitters`, skills, downstream) + `import *` + explicit underscore names; CI a shim-surface test.
- **R3 — process-bigraph release cadence.** viva can't ship its shims until PBG releases. *Mitigation:* during dev, pin the plugin to the PBG git branch (as the pyproject already does for pbg-emitters); switch to the released version at merge.
- **R4 — `_demo_visualizations` / `config_helpers` classification.** If either has an unseen downstream consumer, dropping/moving it breaks them. *Mitigation:* the same three-consumer verification used in Phase 0 (plugin + workbench + real downstream repos, excluding sibling worktrees) before finalizing.

## Open decisions (for maintainer sign-off)
- **D1 — entry point.** Once `composite_generator` lives in PBG, does PBG still need the `process_bigraph.spec_generators` entry point pointing at itself, or is it dropped in favor of direct import in PBG's discovery? (Leaning: drop the self-referential entry point; keep the group for *external* workspace generators.)
- **D2 — `_demo_visualizations`.** Move to PBG, or drop as example-only? (Leaning: drop after the three-consumer check.)
- **D3 — shim warnings.** Silent shims now, add `DeprecationWarning` only after workbench + v2ecoli are repointed? (Leaning: yes, silent now.)
- **D4 — viz home confirmation.** Confirmed in scoping: `visualization` + `visualizations/` go to PBG in this phase (they're `Step` subclasses). The *render* side (`render_results`) is engine-adjacent but dashboard-facing — flagged for a possible later split, not this phase.
