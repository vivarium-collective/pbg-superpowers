# Agentic model-building loop — systematic design

**Status:** design — approved in brainstorming 2026-08-16, pending spec review.

**Goal.** Turn an open-ended study *question* into a validated model by an
autonomous loop: agents author acceptance-criteria Tests, an audit gates the
Tests' *sufficiency*, the Tests are pre-registered (locked), then the loop builds
the model, runs simulations, evaluates against the graded Tests, and iterates the
**model** (never the locked Tests) until the severity gate passes — or gives up
honestly. Must be **systematic** (an explicit, versionable protocol) and
**iterable** (we improve the protocol over time).

**Builds on (already shipped):** `study_evaluator` (measure/pass_if → graded
outcomes), `report_card_verdict/v2` (`check`/`Expected`, signed margin + severity),
`severity_gate` + `report.json`/`test_diff.json`, `study_verdict.roll_up_verdict`,
`viva-navigate` (`needs_attention` worklist: `uncovered_ac`/`hard_gate`/
`test_regression`), `viva-test` CLI, `rigor.py` (13-dim rigor scorecard +
`threshold_sensitivity`), `band_provenance`, the `/viva-study` lifecycle. See
`docs/superpowers/specs/2026-08-15-tests-as-agent-feedback-design.md` and
`2026-08-16-unified-grading-vocabulary-slice2-design.md`.

**Architecture rule (binding):** the plugin owns **judgment/evaluation** (AI in
`/viva-*` skills + deterministic `viva_superpowers` helpers); the workbench
**renders + persists** (AI-free). One-way dependency (workbench → plugin). Both
new components are `/viva-*` skills backed by `viva_superpowers` helpers; nothing
AI lands in the workbench.

## 1. Motivation

Every phase of "question → validated model" already has a skill EXCEPT two gaps:
1. **No driver** loops build→run→evaluate→edit until the gate passes (only the
   one-pass `viva-investigation run`; the discipline is prose `<HARD-GATE>`s).
2. **No test-sufficiency audit** — `rigor.py` grades the *study's defense*
   (provenance, pre-registration, falsifiability, calibration ladder, threshold
   brittleness) but nothing asks *"do these Tests actually discriminate a correct
   model from a plausible wrong one, and do they cover the question?"*

The hard part is **integrity**: an agent that authors its own Tests *and* iterates
the model until they pass can cheat three ways — author weak Tests, weaken Tests
when they fail, or tweak the model to pass without real validity. The design's
spine is the mechanism that forecloses all three.

## 2. Goals / non-goals

**Goals.**
- An explicit, versionable **loop protocol** (state machine + gates + invariants +
  termination) — the systematic artifact.
- A **persisted loop-state** artifact so the protocol is resumable, auditable, and
  dispatchable (the seam that lets a supervised in-session run today become an
  autonomous dispatched run later).
- **Component A — `/viva-audit-tests`**: a sufficiency audit that adds
  discrimination, objective-coverage, redundancy, and discriminating-control
  checks; outputs a graded `report_card_verdict/v2` report.
- **Component B — `/viva-model-build`**: the driver skill that executes the
  protocol against the loop-state, calling the existing skills at each state.
- **Integrity by construction:** audit-gate + pre-registration lock; the loop can
  edit only the model; honest give-up.
- A **validation harness**: a known-good fixture study the loop must pass and a
  known-impossible one it must give up on.

**Non-goals.**
- No new grading vocabulary (Slice 2 done) and no change to `study.yaml` grammar.
- No autonomous multi-machine execution / new run backend (uses the existing
  workbench run model + Ray).
- The workbench gets no AI. The audit's *reasoning* is in the skill; only
  deterministic helpers (redundancy-by-path, coverage-by-mechanism-tag,
  band-width math) live in `viva_superpowers`.
- Not building a general planner — the protocol is fixed and small; the agent's
  freedom is *within* a state (how to author a test, how to edit the model), not
  in reordering the protocol.

## 3. The loop protocol (state machine)

States, the gate that leaves each, and the transition:

| State | Does | Gate to leave | On gate fail |
|---|---|---|---|
| **AUTHOR** | From the open `question:`, author `behavior_tests[]` (acceptance criteria: measure/pass_if/cites/classification) + a model plan. | Tests exist + structurally valid (`verify` L0/L1). | stay AUTHOR |
| **AUDIT** | Run `/viva-audit-tests`; the sufficiency report. | audit **overall != fail** (no hard-insufficient dimension). | → AUTHOR (refine Tests) |
| **LOCK** | Pre-register: freeze `behavior_tests[]`, record `locked_tests_hash` + `prereg_record` (criteria predate any run — feeds `rigor` dim 9). | always. | — |
| **BUILD** | Build/edit the model/composite (`/viva-expert` or params). | `verify` + `check-observables` (pre-run HARD gate). | stay BUILD |
| **RUN** | Run the canonical simulation(s) (`viva-study run-*`). | run completes; `auto_evaluate` fills `runs[].outcomes`. | → BUILD (fix run) |
| **EVALUATE** | `roll_up_verdict` + `severity_gate(report.json)` + `test_diff.json` (what the last edit moved). | — (always advances). | — |
| **DECIDE** | `verdict == passed` (gate `pass`, `fail==0 & pass>0`)? | pass → **DONE** (findings + report). | → NAVIGATE |
| **NAVIGATE** | `viva-navigate decisions`: rank `hard_gate`/`test_regression`/`uncovered_ac`; pick the top actionable item; edit the **model/params only**. Budget check. | budget remaining → → BUILD. | budget spent → **GIVE-UP** |

**DONE** writes findings + the three-track verdicts + a report. **GIVE-UP** writes
an honest OPEN result (the failing hard axes + why iteration stalled) — never a
fabricated pass.

**Re-open (the only way a locked Test changes):** an explicit
`AUTHOR`-with-`reopen` transition, allowed only when the loop can justify that the
Test itself was wrong (not merely that the model fails it). It bumps a
`reopen_count`, re-enters AUDIT, and re-LOCKs. The prereg record retains the prior
locked hash — so every Test change is visible and audited, and "weakening to pass"
shows up as a reopen right after a fail.

**Invariants (loop-level, enforced by the driver + checkable post-hoc):**
- **I1 — locked Tests are immutable** between LOCK and DONE/GIVE-UP except via
  re-open→AUDIT. A diff of `behavior_tests[]` against `locked_tests_hash` at any
  iteration that is not a reopen is a protocol violation.
- **I2 — model-only edits** in NAVIGATE→BUILD (the edit target is the composite /
  `conditions.model_settings` / params, never `behavior_tests[]`).
- **I3 — provided-mechanisms-only** (House Rules): the loop may not invent a
  mechanism to pass; a model change must cite its mechanism source.
- **I4 — honest termination**: budget exhaustion → GIVE-UP with the failing axes;
  no state may emit a `passed` verdict the gate doesn't support.
- **I5 — every iteration is recorded** in loop-state history (edit + margin_deltas
  + gate), so the trajectory is auditable.

## 4. The persisted loop-state (dispatch seam + audit trail)

`.pbg/loop/<study>.json` (resolved via `WorkspacePaths`; AI-free — the workbench
may read/render it, the skill writes it through a `viva_superpowers` helper):

```json
{
  "schema": "model_build_loop/v1",
  "study": "<slug>",
  "question": "<the open-ended question, verbatim>",
  "state": "NAVIGATE",
  "iteration": 3,
  "budget": {"max_iterations": 12, "spent": 3},
  "audit": {"overall": "within_tol", "ref": "viz/report_card/test-audit.verdict.json"},
  "locked_tests_hash": "sha256:...",
  "prereg_record": {"locked_at_iteration": 0, "prior_hashes": []},
  "reopen_count": 0,
  "last_verdict": {"roll_up": "failed", "gate": "fail",
                   "gated_by": [{"card": "behavior-tests", "id": "atp_fraction_in_band"}]},
  "history": [
    {"iteration": 2, "edit": "raised dnaA synthesis rate 1.3x (cite: Hansen 1991)",
     "target": "model", "margin_deltas": {"atp_fraction_in_band": +0.03}, "gate": "fail"}
  ]
}
```

A pure `viva_superpowers/loop_state.py` owns read/advance/validate (I1-I5 are
assertions here). The driver skill never edits the JSON by hand — it calls the
helper, which is unit-testable without an agent. This module IS the dispatch seam:
a future autonomous dispatcher reads the same file and advances the same states.

## 5. Component A — `/viva-audit-tests` (sufficiency audit)

**Input:** a study slug (its `question`, `behavior_tests[]`, `conditions`,
`readouts`, `controls`, and — if a run exists — its outcomes). **Output:** a
graded `report_card_verdict/v2` audit report written to
`viz/report_card/test-audit.{html,verdict.json}` (so it renders like any card and
the loop's AUDIT gate reads its `overall`). Dimensions, each an axis via `check()`:

Reuse (already deterministic — call, don't reimplement):
- **provenance** — `rigor._test_threshold_sourced` / `band_provenance.bands_missing_provenance`: every numeric band carries `cites` or `pass_if.provenance`.
- **pre-registration** — `rigor` dim 9 / `study_verdict.preregistration_status`.
- **falsifiability + calibration ladder** — `rigor` dims 5, 11.
- **brittleness** — `rigor.threshold_sensitivity` (knife-edge pass at ±10/20%), when a run exists.

New (the audit's real value-add):
- **discrimination / gameability** (the headline). For each primary Test:
  (a) *band-width sanity* — deterministic: flag a band whose half-width exceeds a
  fraction (default 50%) of `|target|` or spans the full plausible readout range
  (from `readouts` units / a declared plausible range) as "trivially wide"; (b)
  *null-model probe* (AI + optional compute): would a scrambled/knockout/null
  model (mechanism removed) *also* satisfy this band? Reasoned by the skill, and —
  where a null variant is cheap — optionally run and graded. A Test a null model
  passes is `mismatch` (insufficient).
- **objective coverage** — every mechanism named in `question` / `purpose.mechanism`
  / `study_card` has ≥1 primary Test. Deterministic scaffold: mechanism tags vs
  Test `cites`/`measure.path`; AI closes the semantic gap. Uncovered mechanism →
  `mismatch`.
- **redundancy / independence** — Tests keyed on distinct `measure.path`/`field`/
  `formula`; a suite collapsing onto one observable is `drift` (looks broad, tests
  one thing). Deterministic (`viva_superpowers/test_audit.py::redundancy`).
- **discriminating control** — a Test exists that the *correct* model should FAIL
  if the mechanism were absent (promote `controls[]` negative-control logic into a
  gating Test). Absent → `drift`.

`overall = worst axis`; `fail` iff any hard-severity dimension is `mismatch`
(discrimination / objective-coverage are `hard`; redundancy / control are `soft`).
Split: `viva_superpowers/test_audit.py` holds the deterministic checks (unit-
tested, AI-free); the skill supplies the reasoning (null-model plausibility,
mechanism-semantics) and assembles the report via `TestBuilder`.

## 6. Component B — `/viva-model-build` (the driver)

A `/viva-*` skill whose body IS the protocol (§3): it reads/creates the loop-state,
and at each state calls the existing skills — AUTHOR/`/viva-study` design,
AUDIT/`/viva-audit-tests`, LOCK/`loop_state.lock`, BUILD/`/viva-expert` +
`viva-study verify`+`check-observables`, RUN/`viva-study run-*`, EVALUATE/
`roll_up_verdict`+`severity_gate`, NAVIGATE/`viva-navigate decisions` — advancing
the loop-state through the helper (which enforces I1-I5) after each. It stops at
DONE or GIVE-UP, or at a **checkpoint** (default: after LOCK, and every N
iterations) where a supervised run surfaces to the human. `--autonomous` removes
the checkpoints (the dispatchable mode); the protocol and loop-state are identical
either way — that is the hybrid seam.

The driver never grades or edits Tests itself: grading is `study_evaluator`, Test
authoring is `/viva-study`, sufficiency is `/viva-audit-tests`. It is
orchestration + invariant-enforcement only.

## 7. Integrity / anti-gaming (how the three cheats are foreclosed)

- **Weak Tests** → the AUDIT gate (discrimination + objective-coverage as hard
  dimensions) blocks LOCK until the Tests actually discriminate and cover the
  question.
- **Weakening Tests on failure** → I1 freezes them after LOCK; the only change path
  is re-open→AUDIT, which is recorded (`reopen_count`, `prior_hashes`) and re-gated.
  A reopen immediately after a fail is a visible, reviewable event, not a silent
  weakening.
- **Tweaking the model to pass invalidly** → I3 (provided-mechanisms-only, cited
  edits) + the discriminating-control Test (a correct model must fail it absent the
  mechanism) + `rigor.threshold_sensitivity` catching knife-edge passes. A pass
  that survives the discriminating control and isn't knife-edge is a real pass.
- **Faking termination** → I4; GIVE-UP is the honest exit, and `study_audit --gate`
  (offline CI) independently refuses to bless a `passed` verdict the gate doesn't
  support.

## 8. Validation (how we test THIS system)

- **Unit** (`tests/test_test_audit.py`, `tests/test_loop_state.py`): the
  deterministic audit checks (band-width, redundancy-by-path, coverage-by-tag) on
  crafted specs; `loop_state` read/advance/validate incl. each invariant assertion
  (an I1 violation raises; an I4 fake-pass raises).
- **Fixture studies** (`tests/_fixtures/loop/`): a **known-good** study whose
  question has a real, reachable model — the loop must reach DONE within budget; a
  **known-impossible** study (a question no model in the toolkit can satisfy) — the
  loop must GIVE-UP honestly with the failing axes, never DONE. These are the
  regression harness for the protocol.
- **Live** (out of the automated suite): the first real open-ended study, run
  supervised, to exercise the whole thing end-to-end and surface protocol gaps —
  the "test this out" step. Findings feed the next protocol version.

## 9. Decomposition for writing-plans

Order (each an independently landable slice; the lock depends on the audit):
1. **`loop_state.py`** + `model_build_loop/v1` schema + invariant assertions (pure,
   unit-tested). The systematic backbone.
2. **`test_audit.py`** deterministic checks + **`/viva-audit-tests`** skill +
   graded report. Component A. The AUDIT gate.
3. **`/viva-model-build`** driver skill (protocol over §3, checkpoints,
   `--autonomous` seam). Component B.
4. **Fixture harness** (known-good + known-impossible) + docs.
Catalog guards: a new user-invocable skill updates the pinned set + the
"N user-facing skills" count in `test_skill_manifests` / `docs/skills.md` / README
/ AGENTS.md / CLAUDE.md (two new skills → +2).

## 10. Open decisions (resolve in the plan)

- **Loop-state home:** `.pbg/loop/<study>.json` (chosen — keeps `study.yaml`
  clean; workbench reads it) vs a `study.yaml` block. Confirm the workbench render
  path if we want the loop trajectory visible in the dashboard.
- **Null-model probe depth:** reasoning-only vs actually running a knockout variant
  in the audit. Default: reasoning-only in v1; a cheap knockout run is an opt-in
  the audit *recommends*, not a hard requirement (keeps the audit pre-run and fast).
- **Budget default** (`max_iterations`) and the checkpoint cadence N.
- **Skill names:** `/viva-audit-tests` + `/viva-model-build` vs folding the driver
  into `/viva-study loop`. Recommend standalone skills (clean surfaces).
