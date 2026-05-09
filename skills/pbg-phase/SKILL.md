---
name: pbg-phase
description: "Implement one phase of a model's plan. Reads phases/phase-N.md, walks Implementation Tasks, runs sims, generates readouts, runs acceptance tests, evaluates Phase Gate. Updates frontmatter status and workspace.yaml."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep Agent
argument-hint: <n> [<model-name>]
---

# pbg-phase

Stages 9..N. Operates in the model repo (the submodule).

## Prerequisites

- For phase 1: `stages.phase_plan.status` is `complete`.
- For phase n>1: phase (n-1) has `gate_passed: true`.
- Working tree clean in the model submodule.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if prerequisites unmet. If invoked on a `complete` phase, ask: amend / extend / abort.
2. **Branch** — `phase/<n>` (or `phase/<n>-revision-<k>` if reopening a complete phase).
3. **Read `phases/phase-<n>.md`** — parse frontmatter for objective, biology, tasks, expected behavior. Mark `status: in_progress`; commit a "phase open" marker.
4. **Walkthrough** — walk Implementation Tasks one at a time:
   - Each task = code edits + at least one new test + commit. Use the body's `### Implementation Tasks` section as the source of TODOs.
   - If a missing wrapper is discovered: dispatch `/pbg-expert <tool>` (Agent tool, general-purpose). On success, install editably + register in `pbg_<slug>/core.py`.
5. **Auto-generate `tests/test_phases.py`** from acceptance entries:
   ```python
   from pathlib import Path
   from pbg_superpowers.phase_md import parse_phase_md
   from pbg_superpowers.phase_gate import generate_test_module
   fm, _ = parse_phase_md(open("phases/phase-<n>.md").read())
   generate_test_module(fm, Path("tests/test_phases.py"))
   ```
   The generated file has one `pytest.fail("not yet implemented")` per acceptance entry. The user implements each test body during the walkthrough.
6. **Run `pytest tests/test_phases.py`** — record pass/fail per acceptance entry. Update each entry's `status` field in the phase frontmatter (`pending` → `passing` / `failing`).
7. **Persist deliverables** — write code-diff summary, parameter table, plots, and test report under `phases/deliverables/phase-<n>-*`.
8. **Run gate evaluation:**
   ```python
   from pbg_superpowers.phase_md import parse_phase_md
   from pbg_superpowers.phase_gate import evaluate_gate
   fm, _ = parse_phase_md(open("phases/phase-<n>.md").read())
   result = evaluate_gate(fm)
   # On result.passed: status=complete, gate_passed=true
   # On not passed: status=gate_pending, gate_passed=false
   ```
9. **Update workspace.yaml.models.<name>.phases[n-1]** to mirror frontmatter status/gate. Commit.
10. **Run `/pbg-report <model>`** — refreshes the phase tracker pill and adds a deep-dive section if gate passed.
11. **PR_BODY.md** — list code changes, parameters added, deliverables, gate-evaluation result, open questions. If gate didn't pass, list the failing acceptance entries.
12. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Revision protocol

If invoked on a `complete` phase: ask amend / extend / abort. `amend` opens `phase/<n>-revision-<k>` and re-runs steps 4-11. The revised gate must pass before the phase status returns to `complete` (otherwise it stays `gate_pending`).

If a later phase reveals a flaw in an earlier one's assumption: file an entry in that earlier phase's `open_questions`, flip its `gate_passed: false` with a justification commit. The dashboard surfaces this as a regression. The next `/pbg-phase n+1` invocation refuses until the flagged phase is resolved.

## Sub-skill rollback (per spec §12 rule 12)

If a dispatched `/pbg-expert` invocation fails partway:
- Roll back any partial code changes that depend on that wrapper (`git restore <files>`).
- Append a decision entry to `docs/decisions.yaml`.
- Surface the failure in `PR_BODY.md`.
- Continue with non-blocking implementation tasks if any remain; otherwise mark `status: gate_pending` and stop.

## External models (external: true)

For in-place imports (`workspace.yaml.models.<name>.external == true`):
- Phase plan and per-phase markdown live at `models-overlay/<name>/phases/` rather
  than `models/<name>/phases/`. The workspace owns coordination state; the upstream
  repo stays clean.
- `tests/test_phases.py` and the phase-gate runner still target the upstream's
  test directory (so acceptance tests live where the model code does).
- Deliverables (`models-overlay/<name>/phases/deliverables/phase-N-*`) are
  workspace-owned.
- The PR_BODY targets the upstream remote; `gh pr create` resolves the model's
  upstream and opens the PR there.
