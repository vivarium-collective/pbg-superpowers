---
name: pbg-baseline
description: Build the minimal end-to-end Composite for a model. Dispatches /pbg-composer for wiring, runs a short baseline simulation, persists the registry snapshot, and validates against the expert-input acceptance subset.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep Agent
argument-hint: <model-name>
---

# pbg-baseline

Stage 7 of the canonical PR flow. Operates in the model repo (the submodule).

## Prerequisites

- `stages.pull_processes.status` is `complete`
- `stages.data.status` is `complete`
- `stages.expert_input.status` is `complete`
- Working tree clean in the model submodule

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if any prerequisite stage is not complete.
2. **Branch** — `stage/7-baseline` in the model repo.
3. **Dispatch `/pbg-composer <model> <pbg-tools...>`** (Agent tool, general-purpose subagent_type). The composer skill produces the wiring table, adapters, stubs, and a `pbg-composite-<model>` repo. When the dispatch returns, adopt the produced wiring back into:
   - `models/<name>/pbg_<slug>/wiring.py` ← from the composite's wiring
   - `models/<name>/pbg_<slug>/adapters.py` ← copy adapters
   - `models/<name>/pbg_<slug>/stubs.py` ← copy stubs
   - `models/<name>/pbg_<slug>/document.py` ← update `build_document()` to consume the wiring
4. **Run pytest:**
   - `tests/test_assembly.py` — `build_document()` returns a dict
   - `tests/test_run.py` — short baseline run smoke
   - `tests/test_core_integration.py` — `build_core()` registers expected processes; types accessible
   All three MUST pass before proceeding.
5. **Persist registry snapshot:**
   ```bash
   python -c "import json; \
              from pbg_<slug>.core import build_core; \
              from pbg_superpowers.core_introspection import registry_snapshot; \
              open('tests/registry-snapshot.json','w').write(json.dumps(registry_snapshot(build_core())))"
   ```
   This unlocks the drift-detector test on subsequent phase implementations.
6. **Run expert-input acceptance subset** — load `expert/acceptance.yaml`, filter to baseline-relevant tests (those with `id` starting with `baseline.`), execute each, record pass/fail. All MUST pass.
7. **Generate baseline plots and PBG document tree** under `reports/assets/`. (Stub for v0.1.0; full implementation arrives with `/pbg-report` in Task 20-21.)
8. **Update workspace.yaml** — `models.<name>.stages.baseline.status = complete`.
9. **PR_BODY.md** — list registered processes, types, adapters, stubs, baseline acceptance results, and links to plots.
10. **Report refresh** — `/pbg-report` produces the per-model deep dive (deferred until Task 21).
11. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## External models (external: true)

For in-place imports (`workspace.yaml.models.<name>.external == true`):
- The composer dispatch operates against the existing model repo's structure.
- The registry snapshot is written to `models/<name>/tests/registry-snapshot.json`
  AS IS (no convention-rewriting in upstream). If the upstream has no `tests/`
  directory, write to `models-overlay/<name>/tests/registry-snapshot.json`
  instead — the workspace owns this overlay path.
- Baseline plots / PBG document tree write to `models-overlay/<name>/reports/assets/`
  rather than into the upstream repo, keeping it clean.
- The PR_BODY targets the upstream remote.

## Sub-skill rollback

If `/pbg-composer` fails:
- Revert any partial changes to `wiring.py`/`adapters.py`/`stubs.py`/`document.py` (`git checkout -- <files>`)
- Append a decision entry to `docs/decisions.yaml`
- Surface in PR_BODY
- Mark `stages.baseline.status: in_progress` (NOT `complete`)

## Idempotency

Re-running on a complete `stages.baseline` is treated as a re-baseline — useful when a wrapper version bump or new stub changes the registry. Re-running:
- Re-runs the composer dispatch (with current wrapper set)
- Re-writes `tests/registry-snapshot.json` (the drift detector now compares against the new baseline)
- Re-runs the baseline acceptance subset
- Updates the deep-dive panel
