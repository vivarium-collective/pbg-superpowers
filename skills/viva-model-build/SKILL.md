---
name: viva-model-build
description: Use when an open-ended study question should be turned into a validated model by an autonomous loop — authors acceptance-criteria Tests, audits their sufficiency, SELECTs where the model comes from (reuse / compose / build-new, under a sourcing audit), locks them, then builds/runs/evaluates and iterates the MODEL (never the locked Tests) until the severity gate passes or gives up honestly. Drives the agentic model-building protocol.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <study-slug> [--question "<text>"] [--max-iterations N] [--autonomous]
---

# /viva-model-build

Drive the **agentic model-building loop**: an open-ended `question` → validated
model, by iterating the model against pre-registered, audited Tests. This skill is
the *driver* — orchestration + invariant enforcement only. It never grades, never
authors Tests, never edits a locked Test. Grading is `study_evaluator`; Test
authoring is `/viva-study`; sufficiency is `/viva-tests audit`.

Spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`.
Preconditions (per `/viva-orient`): a workspace + the workbench running.

## The protocol (state machine)

The loop's state lives in `.pbg/loop/<study>.json` (`model_build_loop/v1`), managed
by `viva_superpowers.loop_state`. Advance ONE state per step; after each, persist +
`validate`. Never skip a gate.

This state — locked-tests hash, reopen trail, iteration history, DONE/give-up
outcome — surfaces in the study's Assurance › Build tab (a graceful "not built
via the loop" note when no loop file exists yet).

```
AUTHOR → AUDIT ─fail→ AUTHOR
   AUDIT ─pass/warn→ SELECT → SPIKE → LOCK → BUILD ─verify-gate→ RUN → EVALUATE → DECIDE
   SELECT ─sourcing fail→ SELECT (revise the decision — don't lock a misfit)
   SPIKE ─not expressible→ AUTHOR/SELECT (the engine can't express it — don't lock)
   DECIDE ─pass→ DONE
   DECIDE ─fail→ NAVIGATE ─{TUNE|SELECT|MODIFY|MEASURE}→ BUILD …   [budget remaining]
   NAVIGATE ─budget spent→ GIVE_UP
```

| State | Do | Gate to leave |
|---|---|---|
| **AUTHOR** | From `question:`, author `behavior_tests[]` (measure/pass_if/cites/classification) via `/viva-study` Design subcommands. Draft the model plan. | Tests exist + `/viva-study verify` L0/L1 clean. |
| **AUDIT** | `/viva-tests audit <study>`. Read its gate + insufficient dimensions. | `pass` or `warn` → SELECT. `fail` → back to AUTHOR (strengthen the flagged Tests). |
| **SELECT** | Decide **where the model comes from**. Survey the catalog (`/viva-catalog list` + each candidate module's `describe()`) and assemble `{module: [capability tokens]}`. Choose **reuse** one module / **compose** several / **build-new**. Record `study.yaml.requires: [tokens]` + `sourcing: {decision, modules, rationale}` (mirror to `state["sourcing"]`). Grade it: `module_sourcing.build_sourcing_report(spec, catalog)` → `sourcing_gate`. Reuse an existing module contributes it to the workspace core (`<pkg>.core.build_core` inheriting the reused module), not a parallel core. | `pass`/`warn` → LOCK. `fail` → stay in SELECT and revise: **source_fit** mismatch = a chosen module doesn't cover `requires`; **reinvention** = built new where a catalogued module already fits. Never LOCK a `fail`. |
| **SPIKE** | **Feasibility probe before locking numbers.** After the qualitative claim is fixed and a source is chosen but BEFORE thresholds freeze, run a cheap probe (~100 steps) through the ACTUAL simulator showing the chosen mechanism vocabulary can produce the phenomenon directionally. Record it: `loop_state.record_spike(state, expressible=<bool>, artifact={...}, note=...)`. | `expressible: true` → LOCK. `false` → back to AUTHOR/SELECT — the engine can't express the phenomenon; **never LOCK** (a lock over a non-expressible spike is an I0 violation). |
| **LOCK** | Pre-register: freeze the Tests. `loop_state.lock_tests`. | always (after a passing SPIKE). |
| **BUILD** | Build/edit the model (`/viva-expert`, or `variant-set-params` for parameter edits). | `/viva-study verify` + `check-observables` (HARD pre-run gate). |
| **RUN** | `/viva-study run-baseline`/`run-variant`/`run-script`. Workbench `auto_evaluate` fills `runs[].outcomes`. | run completes. |
| **EVALUATE** | Read `study_verdict.roll_up_verdict` + the severity gate (`report.json`) + `test_diff.json` (what the last edit moved). | always. |
| **DECIDE** | `roll_up == passed` (gate `pass`)? | pass → DONE. else → NAVIGATE. |
| **NAVIGATE** | `/viva-navigate decisions`: take the top `hard_gate`/`test_regression`/`uncovered_ac` item and choose a **typed action** — `TUNE` (params), `SELECT` (swap a model variant), `MODIFY` (structural edit), `MEASURE` (run an experiment to reduce uncertainty), or `GIVE_UP`. A failing margin should first trigger **diagnosis**, not a reflexive edit: a `MODIFY` must carry `diagnosis={"hypotheses":[≥2], "discriminating_measure": ...}` (I6). Edit the **MODEL/params only**. Record via `record_iteration(..., action=..., diagnosis=...)`. Budget check. | budget remaining → BUILD. spent → GIVE_UP. |

## Invariants (enforce every iteration — the loop's integrity)

- **I1 / I2 — locked Tests immutable; model-only edits.** After LOCK you may edit
  the composite / `conditions.model_settings` / params — **never** `behavior_tests[]`.
  If a Test itself is genuinely wrong (not merely failing), you must **re-open**:
  go back to AUTHOR with a justification, re-run AUDIT, and `lock_tests` again
  (which records the reopen in `prereg_record.prior_hashes` + `reopen_count`).
  Weakening a Test to make it pass is a protocol violation — the trail makes it visible.
- **I0 — feasibility before lock.** Never LOCK a contract against a phenomenon the
  simulator cannot express. The SPIKE stage records `spike.expressible`; a lock over
  a non-expressible spike is an I0 violation (`loop_state.validate`). Absence of a
  spike is not a violation (back-compat), but a supervised run should always take it.
- **I3 — provided-mechanisms-only.** A model change must cite its mechanism source
  (a paper, an expert input). Do not invent a mechanism to force a pass.
- **I7 — model discrepancy (anti-overfitting).** `TUNE` (parameter calibration) must
  not compensate indefinitely for structural error. A run of ≥3 consecutive TUNE
  iterations that never clears the gate is a persistent residual — `loop_state.validate`
  flags it; escalate to `SELECT`/`MODIFY`/`GIVE_UP` (a diagnosed structural change or an
  honest give-up), don't keep nudging parameters.
- **I6 — diagnosis before structural change.** A `MODIFY` (structural model edit)
  must be justified by a `diagnosis` with ≥2 competing hypotheses AND the MEASURE
  that discriminates them — a failed margin triggers diagnosis, not a reflexive edit.
  `loop_state.validate` flags a MODIFY without one. TUNE/SELECT/MEASURE and legacy
  iterations are exempt.
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

SELECT — record + grade the sourcing decision before locking (gate `fail` blocks LOCK):
```bash
python - "$STUDY" <<'PY'
import sys, yaml
from viva_superpowers import loop_state as ls, module_sourcing as ms, paths
ws, study = paths.workspace_root(), sys.argv[1]
st = ls.load(ws, study)
spec = yaml.safe_load((paths.workspace_dir("studies", root=ws) / study / "study.yaml").read_text())
catalog = spec.get("catalog") or {}          # {module: [capability tokens]} from the catalog survey
report = ms.build_sourcing_report(spec, catalog)   # grades spec.requires + spec.sourcing
gate = ms.sourcing_gate(report)                    # pass | warn | fail
st = ls.advance(st, "SELECT", sourcing={**(spec.get("sourcing") or {}), "gate": gate})
ls.save(ws, study, st)
print("sourcing gate:", gate)
assert gate != "fail", f"SELECT gate FAIL — revise the sourcing decision, do NOT lock. {report}"
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

## Orchestration — fan out independent work, wait event-driven

The loop's slow parts are mostly **independent** and should run **concurrently**, not
serially:

- **Fan out** independent simulator work — multiple seeds, multiple conditions, the
  points of a calibration grid, and independent member studies of an investigation.
  A calibration is a program, not a conversation: use
  `pbg_cpm_studies.model_building.calibrate` (a sensitivity screen picks the knobs to
  sweep; `refine(..., max_workers=N)` evaluates the grid concurrently) instead of an
  LLM narrating a hand grid — the hand sweep was the single biggest token cost observed.
- **Wait event-driven, never poll.** Dispatch background work and act on its completion
  signal; do not sit in fixed-interval sleeps checking one job at a time (that serial
  polling dominated wall-clock). Synchronize only at real barriers (an audit gate, a
  DECIDE).
- **One state, one truth.** The ledger and the render are views of the loop state, not
  separate files: fold commits/rulings/deferred findings in with
  `loop_state.record_note(state, kind=..., text=...)`, and produce the trajectory with
  `loop_state.to_trajectory(state)` rather than capturing a second copy.

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
- Locking a model whose `sourcing_gate` is `fail` (source_fit mismatch / reinvention) → you skipped the SELECT gate.
- Building a new module when a catalogued one already covers `requires` → `reinvention` mismatch; reuse it instead.
