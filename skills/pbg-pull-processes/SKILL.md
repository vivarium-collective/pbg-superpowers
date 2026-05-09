---
name: pbg-pull-processes
description: Identify pbg-* wrappers needed by a model, install existing ones into the workspace venv, and dispatch /pbg-expert for any missing wrapper. Updates workspace.yaml.models.<name>.pbg_processes and the model's core.py registrations.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep Agent
argument-hint: <model-name>
---

# pbg-pull-processes

Stage 3 of the canonical PR flow. Operates inside `models/<name>/` (the submodule).

## Prerequisites

- Model exists in `workspace.yaml.models`.
- `stages.add_model.status` is `complete`.
- Working tree clean inside the model submodule.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if prerequisites unmet or working tree dirty.
2. **Branch** — `stage/3-pull-processes` in the model repo.
3. **Walkthrough** — for each tool the model needs:
   - Probe `${PBG_WORKSPACE:-$HOME/code}/pbg-<tool>/`. Exists?
     - Yes: add `-e <path>` install to model's `pyproject.toml` deps (or `uv pip install -e <path>` directly into the workspace venv).
     - No: **dispatch** `/pbg-expert <tool>` (Agent tool, general-purpose subagent_type). When sub-skill returns, install the new wrapper editably and continue.
   - On sub-skill failure: roll back the partial dep, log the failure to `docs/decisions.yaml`, surface in `PR_BODY.md`.
4. **Update `models/<name>/pbg_<slug>/core.py`** to import each wrapper and call its `register_with(core)` helper (or `core.register_link(...)` directly).
5. **Run `pytest tests/test_core_integration.py`** — must pass for `build_core()` and process registry.
6. **Update `workspace.yaml`** — `models.<name>.pbg_processes` += newly added wrappers; `stages.pull_processes.status = complete`.
7. **`PR_BODY.md`** with the wrappers added, any deferred via failed dispatches, and links to spawned `/pbg-expert` PRs.
8. **Report refresh** — call `/pbg-report` (deferred until Task 21 lands).
9. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Sub-skill rollback (per spec §12 rule 12)

If `/pbg-expert <tool>` fails partway through, the parent skill MUST:
- Undo any partial install (`uv pip uninstall pbg-<tool>` if installed).
- Append a decision entry to `docs/decisions.yaml` with `{skill: pbg-pull-processes, target: <model>, summary: "/pbg-expert <tool> failed; deferred", source: <error excerpt>}`.
- Continue with the remaining wrappers.
- Final summary in PR_BODY documents successes and deferrals.

## Idempotency

Re-running on a complete `stages.pull_processes` is rejected with a clear message. Re-running on `in_progress` is treated as a resume — picks up where it left off (state inferred from `models.<name>.pbg_processes` plus the stage branch's commits).
