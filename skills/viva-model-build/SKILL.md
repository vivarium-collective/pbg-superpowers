---
name: viva-model-build
description: Use when an open-ended study question should be turned into a validated model by an autonomous loop — authors acceptance-criteria Tests, audits their sufficiency, locks them, then builds/runs/evaluates and iterates the MODEL (never the locked Tests) until the severity gate passes or gives up honestly. Drives the agentic model-building protocol.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <study-slug> [--question "<text>"] [--max-iterations N] [--autonomous]
---

# /viva-model-build

Drive the **agentic model-building loop**: an open-ended `question` → validated
model, by iterating the model against pre-registered, audited Tests. This skill is
the *driver* — orchestration + invariant enforcement only. It never grades, never
authors Tests, never edits a locked Test. Grading is `study_evaluator`; Test
authoring is `/viva-study`; sufficiency is `/viva-audit-tests`.

Spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`.
Preconditions (per `/viva-orient`): a workspace + the workbench running.

## The protocol (state machine)

The loop's state lives in `.pbg/loop/<study>.json` (`model_build_loop/v1`), managed
by `viva_superpowers.loop_state`. Advance ONE state per step; after each, persist +
`validate`. Never skip a gate.

```
AUTHOR → AUDIT ─fail→ AUTHOR
   AUDIT ─pass/warn→ LOCK → BUILD ─verify-gate→ RUN → EVALUATE → DECIDE
   DECIDE ─pass→ DONE
   DECIDE ─fail→ NAVIGATE → (edit MODEL) → BUILD …            [budget remaining]
   NAVIGATE ─budget spent→ GIVE_UP
```

| State | Do | Gate to leave |
|---|---|---|
| **AUTHOR** | From `question:`, author `behavior_tests[]` (measure/pass_if/cites/classification) via `/viva-study` Design subcommands. Draft the model plan. | Tests exist + `/viva-study verify` L0/L1 clean. |
| **AUDIT** | `/viva-audit-tests <study>`. Read its gate + insufficient dimensions. | `pass` or `warn` → LOCK. `fail` → back to AUTHOR (strengthen the flagged Tests). |
| **LOCK** | Pre-register: freeze the Tests. `loop_state.lock_tests`. | always. |
| **BUILD** | Build/edit the model (`/viva-expert`, or `variant-set-params` for parameter edits). | `/viva-study verify` + `check-observables` (HARD pre-run gate). |
| **RUN** | `/viva-study run-baseline`/`run-variant`/`run-script`. Workbench `auto_evaluate` fills `runs[].outcomes`. | run completes. |
| **EVALUATE** | Read `study_verdict.roll_up_verdict` + the severity gate (`report.json`) + `test_diff.json` (what the last edit moved). | always. |
| **DECIDE** | `roll_up == passed` (gate `pass`)? | pass → DONE. else → NAVIGATE. |
| **NAVIGATE** | `/viva-navigate decisions`: take the top `hard_gate`/`test_regression`/`uncovered_ac` item; edit the **MODEL/params only**. Budget check. | budget remaining → BUILD. spent → GIVE_UP. |

## Invariants (enforce every iteration — the loop's integrity)

- **I1 / I2 — locked Tests immutable; model-only edits.** After LOCK you may edit
  the composite / `conditions.model_settings` / params — **never** `behavior_tests[]`.
  If a Test itself is genuinely wrong (not merely failing), you must **re-open**:
  go back to AUTHOR with a justification, re-run AUDIT, and `lock_tests` again
  (which records the reopen in `prereg_record.prior_hashes` + `reopen_count`).
  Weakening a Test to make it pass is a protocol violation — the trail makes it visible.
- **I3 — provided-mechanisms-only.** A model change must cite its mechanism source
  (a paper, an expert input). Do not invent a mechanism to force a pass.
- **I4 — honest termination.** Never report `passed` the gate doesn't support.
  Budget exhaustion → **GIVE_UP** with the failing hard axes and why iteration
  stalled — an honest OPEN result.
- **I5 — record every iteration.** `loop_state.record_iteration(state, edit=..., target="model",
  margin_deltas=..., gate=...)` (all keyword-only after `state`) after each model edit,
  so the trajectory is auditable.

After every state transition, run
`loop_state.validate(state, current_behavior_tests)` and STOP with an error if it
returns any violation.

## Loop-state operations (inline python)

```bash
STUDY="${1:?usage: /viva-model-build <study-slug> [--question ...] [--max-iterations N] [--autonomous]}"
QUESTION="${QUESTION:-}"          # from --question, if given
MAX_ITERS="${MAX_ITERS:-12}"      # from --max-iterations, if given
# Create (or load) the loop state from the study's question. Every dynamic value
# is passed as an argv token — NOT interpolated into the quoted heredoc body.
python - "$STUDY" "$QUESTION" "$MAX_ITERS" <<'PY'
import sys, yaml
from viva_superpowers import loop_state as ls, paths
ws = paths.workspace_root()
study, question, max_iters = sys.argv[1], sys.argv[2], int(sys.argv[3])
st = ls.load(ws, study)
if st is None:
    sf = paths.workspace_dir("studies", root=ws) / study / "study.yaml"
    spec = yaml.safe_load(sf.read_text()) if sf.is_file() else {}
    q = question or spec.get("question") or (spec.get("purpose") or {}).get("question") or ""
    st = ls.create(ws, study, q, max_iterations=max_iters)
    ls.save(ws, study, st)
print("state:", st["state"], "iteration:", st["iteration"],
      "spent:", st["budget"]["spent"], "/", st["budget"]["max_iterations"])
PY
```

The study must already exist (create it first with `/viva-study new` / `fill-overview`);
`/viva-model-build` bootstraps the *loop*, not the study.

Advance a state and persist (example — LOCK after a passing audit):
```bash
python - "$STUDY" <<'PY'
import sys, yaml
from viva_superpowers import loop_state as ls, paths
ws, study = paths.workspace_root(), sys.argv[1]
st = ls.load(ws, study)
spec = yaml.safe_load((paths.workspace_dir("studies", root=ws) / study / "study.yaml").read_text())
st = ls.lock_tests(st, spec.get("behavior_tests") or [])
viol = ls.validate(st, spec.get("behavior_tests") or [])
assert not viol, viol
ls.save(ws, study, st)
PY
```

Use the same pattern for `advance(st, "BUILD"|"RUN"|...)`, `record_iteration(...)`,
and `advance(st, "DONE"|"GIVE_UP", last_verdict=...)`.

## Supervised vs autonomous (the hybrid seam)

- **Default (supervised):** checkpoint — pause and surface a summary — after **LOCK**
  and every **4 iterations** (and always at DONE / GIVE_UP). The human can inspect
  the loop-state trajectory + margins and intervene.
- **`--autonomous`:** no checkpoints; run to DONE/GIVE_UP. The protocol and the
  loop-state file are identical either way — that is the dispatch seam a future
  autonomous runner reads. Use only after the loop is trusted on the study class.

## Termination report

- **DONE:** record `findings` + the three-track verdicts (`/viva-study set-verdicts`,
  `findings --auto`) + render (`/viva-report`). Note reopen_count (how many audited
  Test revisions it took).
- **GIVE_UP:** write an honest OPEN conclusion — the failing `gate.gated_by` axes,
  the best margins reached, and the mechanism gap — never a fabricated pass.

## Red flags — STOP

- Editing `behavior_tests[]` after LOCK without a recorded re-open → I1 violation.
- Reporting a pass the severity gate marks `fail` → I4 violation.
- A model edit with no cited mechanism → I3 violation.
- The audit still `fail` but you locked anyway → you skipped the AUDIT gate.
