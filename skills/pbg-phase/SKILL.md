---
name: pbg-phase
description: "Drive one phase of model development. Reads the phase's frontmatter from phases/phase-N.md, walks the Implementation Tasks list, dispatches /pbg-expert when a missing wrapper is needed, writes code + tests, runs the Phase Gate. The dashboard's basic phase forms (add, start, evaluate gate) handle simple state changes; this skill handles the substantive code work that benefits from Claude Code's assistance."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep Agent
argument-hint: <n>
---

# pbg-phase

The iterative model-building skill. Run from a workspace root after the
phase entry exists in `workspace.yaml.phases` and the corresponding
`phases/phase-<n>.md` file is on disk.

## Prerequisites

- For phase 1: workspace bootstrap complete; observables and visualizations registered (Setup section of the dashboard)
- For phase n>1: `phases/phase-(n-1).md` has `gate_passed: true`
- Working tree clean

## Lifecycle

1. **Pre-flight** — verify prerequisites; refuse if working tree dirty.
2. **Branch** — `phase/<n>` (or `phase/<n>-revision-<k>` if reopening complete phase).
3. **Read context** — parse `phases/phase-<n>.md` frontmatter and body. Read `workspace.yaml` for the related observables, visualizations, and registered processes.
4. **Mark in_progress** — update phase frontmatter status; commit.
5. **Walk Implementation Tasks** one at a time:
   - Each task = code edits in `pbg_<workspace_slug>/` + at least one test in `tests/` + commit.
   - If a missing pbg-* wrapper is discovered: dispatch `/pbg-expert <tool>` (Agent tool, general-purpose). On success, install editably + register in `pbg_<workspace_slug>/core.py`.
   - If a new mechanism needs custom types: edit `pbg_<workspace_slug>/types.py`.
   - If wiring changes: edit `pbg_<workspace_slug>/wiring.py`.
6. **Auto-generate test cases** for each `acceptance_tests[*]` entry in the phase frontmatter:
   ```python
   from pbg_superpowers.phase_md import parse_phase_md
   from pbg_superpowers.phase_gate import generate_test_module
   from pathlib import Path
   fm, _ = parse_phase_md(open("phases/phase-<n>.md").read())
   generate_test_module(fm, Path("tests/test_phases.py"))
   ```
   The user (with Claude's help) implements each placeholder.
7. **Run pytest** — record per-acceptance-test pass/fail; update each test's `status` field in the phase frontmatter.
8. **Persist deliverables** — code-diff summary, parameter table, plots (if visualizations are configured), test report — under `phases/deliverables/phase-<n>-*`.
9. **Run gate evaluation** — if all acceptance_tests passing AND custom gate items checked off, set `status: complete, gate_passed: true`. Otherwise `gate_pending`.
10. **Update workspace.yaml** to mirror the phase frontmatter status. Commit.
11. **Refresh the dashboard** by calling `python3 scripts/render-dashboard.py` (no arg — single dashboard in v0.3.0).
12. **PR_BODY.md** at workspace root: code changes summary, parameters added, deliverables, gate-evaluation result, open questions. If gate didn't pass, list failing acceptance entries.
13. **gh handoff** — print `gh pr create --base main --head phase/<n>`; offer to run with explicit consent. NEVER force-push, push to main, or skip PR review.

## Revision protocol

Re-running on a complete phase opens `phase/<n>-revision-<k>`; gate must pass before promoting back to `complete`.

## Sub-skill dispatch

When a phase's Implementation Tasks need a new pbg-* wrapper that doesn't exist locally, dispatch `/pbg-expert <tool>` (Agent subagent, general-purpose). On success, install with `uv pip install -e ../pbg-<tool>` and register in `core.py`. On failure, log a decision entry and continue with non-blocking implementation tasks; mark gate_pending if the missing wrapper is critical.

## Safety rules (mirrored from spec §12)

- Only modify files inside the workspace.
- Never run `rm -rf`, `git push --force`, `git reset --hard`, `git submodule deinit -f`.
- Never push without explicit user approval (each `gh pr create` invocation is its own consent).
- Never push to main; never force-push.
- Use the workspace's `.venv/`. Never `sudo`, never global pip.
- Tests must pass before final commit. Failure → status stays `in_progress` (not `complete`).
- `workspace.yaml` integrity: validate via `scripts/lint-workspace.py` before any commit that touches it.
