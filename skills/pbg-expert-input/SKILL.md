---
name: pbg-expert-input
description: Capture domain-expert expectations for a model and convert them to "if X, then Y" acceptance tests. Logs open expert questions. Writes models/<name>/expert/{expectations.md, questions.md, acceptance.yaml}.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <model-name>
---

# pbg-expert-input

Stage 6 of the canonical PR flow. Operates in the model repo (the submodule).

## Prerequisites

- Model exists in workspace.yaml.
- `stages.add_model.status` is `complete`.
- Working tree clean in the model submodule.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if prerequisites unmet.
2. **Branch** — `stage/6-expert-input` in the model repo.
3. **Walkthrough** — interactively capture, terminal-first; mirror to dashboard if `/pbg-server` is running:
   - **Expectations** — capture expert-stated expected behaviors as plain-language entries in `expert/expectations.md`. Free-form prose; one entry per behavior.
   - **Acceptance tests** — for each expectation, draft an "if X, then Y" test in `expert/acceptance.yaml`:
     ```yaml
     tests:
       - id: baseline.t1
         statement: "If FBA growth rate < 0, simulation refuses to step."
         perturbation: "Set objective to infeasible."
         observable: "Composite raises a clear error or sets a fail flag."
       - id: phase-1.t1
         statement: "If DnaA synthesis is stopped, DnaA concentration decreases over time."
         perturbation: "Knock out dnaA gene transcription."
         observable: "DnaA(t) shows monotonic decrease over 30 minutes."
     ```
   - **Open questions** — log unresolved questions in `expert/questions.md` (e.g., "Should DnaA-ATP/ADP states be modelled?"). These feed `phases/plan.md` later.
4. **Update workspace.yaml** — mark `models.<name>.stages.expert_input.status = complete`.
5. **PR_BODY.md** — list expectations captured, acceptance tests drafted, and unresolved questions.
6. **Report refresh** — `/pbg-report` (deferred until Task 21 lands).
7. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Notes

- `expert/acceptance.yaml` is the **executable contract** for the model. Stage 7 (`/pbg-baseline`) runs the baseline-relevant subset before declaring the baseline complete. Stages 9..N (`/pbg-phase <n>`) auto-generate `tests/test_phases.py` cases from per-phase frontmatter that traces back to these acceptance entries.
- Acceptance test IDs use the form `<scope>.t<n>`: `baseline.t1`, `phase-1.t1`, etc. The schema enforces this for phase frontmatter; this skill follows the same convention.
- Open questions log doubles as a feedback loop with experts: each entry can be resolved later by promoting it into an acceptance test or annotating with the answer.

## Safety

- Never overwrite existing `expert/*` files without showing a diff and getting explicit consent.
- Never invent expectations or acceptance criteria — every entry must have come from the user (or an expert they're channeling). When in doubt, log it as an open question instead.

## Idempotency

Re-running on a complete `stages.expert_input` is treated as an amendment — append-only updates to expectations, acceptance tests, and open questions. The skill MUST present what's already there before asking for additions.
