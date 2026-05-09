---
name: pbg-phase-plan
description: "Lay out the multi-phase plan for a model using the Phase Template format. Walks the user through enumerating phases (number, name, objective, prereqs, gate criteria); writes phases/plan.md and phases/phase-N.md (status: planned). No implementation in this stage."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <model-name>
---

# pbg-phase-plan

Stage 8 of the canonical PR flow. Operates in the model repo (the submodule).

## Prerequisites

- `stages.baseline.status` is `complete`.
- Working tree clean in the model submodule.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if baseline not complete.
2. **Branch** — `stage/8-phase-plan` in the model repo.
3. **Walkthrough** — terminal-first; mirror to dashboard if `/pbg-server` is running:
   - Ask: how many phases? (positive integer)
   - For each phase, capture: number, name, one-line objective, prereq_phases (default `[n-1]`), at least one acceptance-test stub, at least one Phase Gate criterion.
4. **Write files via the helper:**
   ```python
   from pbg_superpowers.phase_files import create_initial_plan
   create_initial_plan(Path("phases"), "<model-name>", [
       {"n": 1, "name": "...", "objective": "...", "acceptance_tests": [{"id": "phase-1.t1", "desc": "...", "status": "pending"}]},
       {"n": 2, "name": "...", "objective": "...", "prereq_phases": [1], "acceptance_tests": [...]},
   ])
   ```
   This produces `phases/plan.md` (umbrella table) and one `phases/phase-N.md` per phase (status: planned, gate_passed: false).
5. **Update workspace.yaml** — `models.<name>.phases` becomes a list of `{n, name, status: planned}` entries; mark `models.<name>.stages.phase_plan.status = complete`.
6. **PR_BODY.md** — list all phases with their objectives and dependency edges; flag any open questions captured during the walkthrough.
7. **Report refresh** — `/pbg-report <model>` renders the phase tracker (showing all pills as `planned`).
8. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Notes

- This stage produces NO implementation code. Phase implementation happens in `/pbg-phase <n>` (Task 25).
- Each phase must specify at least an objective and a Phase Gate. Empty-section headings are allowed in the body — the user (or `/pbg-phase`) fills them in later.
- Acceptance test IDs follow the schema-enforced regex `phase-<int>.t<int>` — the schema rejects anything else at validate time.

## Idempotency

Re-running on a complete `stages.phase_plan` is treated as a re-plan. The skill MUST present existing phases first; new entries can append, existing entries can be amended (with an explicit confirmation per file). NEVER silently delete a phase file.
