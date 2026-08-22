# Rigor checklist — the required information every study/investigation should carry

A skeptical reviewer of a simulation-based investigation asks the same questions
every time. The dashboard now answers them deterministically with the **evidence
& rigor scorecard** (`viva_superpowers.rigor`): it reads declared fields and
reports, per study, `ok` / `warn` / `gap` on each dimension below, plus an
investigation roll-up. **A missing field is a `gap`** — that is the feedback.

Author studies so the scorecard goes green. This is the canonical list of
required information; `/pbg-study` and `/pbg-investigation` reference it, and the
report surfaces each dimension. None of it is a hard gate — it is standing
feedback — but a finished study should address every dimension or say why not.

## Every study runs at least one composite (the model)

- **`baseline:`** `- {name, composite: <pkg.composites.id>, params: {...}}` — the
  composite(s) the study runs and their parameter settings. The report's **Model**
  banner and "What we ran" section read this; each composite links to the
  bigraph-loom static view. A study with no composite is flagged red.

## Per-study rigor dimensions (8)

| Dimension | Field(s) to declare | How to satisfy |
|---|---|---|
| **Replication** | `robustness: {n_replicates, seeds, parameter_sweep}` (or `simulation_set[].seeds`) | Stochastic model → ≥3 seeds; deterministic → a parameter sweep (`parameter_sweep: true`). One run is a `gap`. For a bounded metric (fraction, count, non-negative rate) report a Wilson score interval or a normal-approx CI clamped to the metric's support — never a bound outside its range. |
| **Controls & calibration** | `controls: [{name, kind: negative\|positive\|borderline\|adversarial, hypothesis, expected, observed, result: PASS\|FAIL}]` | A system that SHOULD fail (negative) **and** a clearly-passing/borderline case (positive) to calibrate the metric across its range. Build the negative control with the **Intervention process** (`viva_superpowers.intervention` — clamp/knockout/scale a store, e.g. an externally-supplied component). |
| **Alternative hypotheses** | `alternative_hypotheses: [{claim, discriminated_by, status: excluded\|not-excluded\|untested}]` (or `discovery_implications.alternate_hypotheses`) | List the competing explanation(s) for each interpretation and how the evidence (often a control) discriminates them. `status: excluded` is the goal. |
| **Claim discipline** | finding `tier: observation \| mechanism \| interpretation` (+ `evidence.from_test`) | Separate what was measured (observation) from the mechanistic reading and the theoretical interpretation; interpretation claims must carry evidence. |
| **Falsifiability** | `falsifiability:` (str) or per behavior_test `could_fail_if` | State plainly how the claim could fail — what result would overturn it (often: "if the negative control behaved like the positive"). |
| **Engineered vs emergent** | interpretation finding `mechanism_origin: engineered \| emergent` | For any interpretation claim, say whether the mechanism is coded (engineered) or arises (emergent). Don't dress up an engineered rule as emergence. |
| **Limitations** | `limitations:` / `does_not_show:` (or `discovery_implications.remaining_uncertainties`) | What this result does NOT show — model scope/fidelity, what's out of frame. |
| **Next steps** | `discovery_implications` (with `followup_study_proposals`) or `follow_up_studies` | The Decide-phase synthesis: resolved/remaining uncertainties, alternate hypotheses, and concrete follow-up study proposals (each `{id, title, motivation}` — give real motivation, not just a title). |

## Conditional rigor dimensions (appended only when the claim class applies)

These dimensions come from external peer review (G2/G3/G6) and are appended to
the scorecard **only for the claim class they police** — a deterministic,
non-causal, non-converting study never sees them. When they do apply, a missing
field is a `gap` — that is the feedback.

| Dimension | Applies when | Field(s) to declare | How to satisfy |
|---|---|---|---|
| **Statistical power (causal stochastic claims)** (G2) | A finding is causal/directional (`claim_type: causal\|directional`, or `tier: interpretation` with a declared `arms:`/`contrast:`) AND the study is stochastic (seeds/`stochastic: true`) | `statistics: {test, p_value, effect_size, n_per_arm, gate_on: ensemble}` + a drift-null control (`controls[].kind: null` or `statistics.null_arm`) | The ≥3-seed replication floor is NOT statistical power. A causal contrast between stochastic arms needs **n≥20 replicates per arm**, a declared rank/nonparametric test with a p-value (and effect size), a **drift-null / no-effect control arm**, and the pass/fail gate on the **ensemble statistic** — never a single flagship seed (`gate_on: flagship_seed` is a `gap`). |
| **Held-out generalization** (G3) | The study makes a substitutability / equivalence / "same interface, different mechanism" / surrogate claim (`claim_type: substitutability\|equivalence\|surrogate`, or clear finding text) | `held_out: {train: [...], test: [...]}` (aliases `generalization` / `train_test`) + `degrees_of_freedom: {free_parameters, matched_observables}` | Evaluate the surrogate on a **held-out condition it was NOT tuned on** (test ≠ train). Agreement only on the tuned condition is *surrogate calibration, not yet mechanism-independence* (`warn`). Also state degrees of freedom vs constraints — how many free parameters were fit vs how many observables were matched. |
| **Conservation ledger** (G6) | The study converts a conserved quantity between representations (e.g. lattice pixels → particles, field mass → flux) — declared via `representation_conversion` or clearly described in a finding | `representation_conversion: {from, to, quantity, ledger: {test, result: PASS}}` (list form `representation_conversions:` for several; study-level `conservation_ledger:` also read) | Declare each conversion and back it with a **ledger check** — a test asserting the quantity is conserved (not manufactured or lost) across the conversion, with a recorded passing result. A named-but-unrun ledger is a `warn`; no ledger is a `gap`. |

## Investigation-level dimensions (5)

| Dimension | What to do |
|---|---|
| **Adversarial testing** | Add at least one study with `kind: adversarial` — systems that should NOT qualify (mimic / parasitic-or-dependent / externally-maintained / random-cyclic). The metric passes by REJECTING them. |
| **Falsification exposure** | Don't let every study pass with nothing ever failing. A discriminating negative control, an adversarial study, or a non-passing result all count. |
| **Comparative framing** | `investigation.yaml: competing_frameworks: [{name, relation}]` — compare your interpretive lens to alternatives (active inference, organizational/constraint closure, viability theory, …) so the findings are shown to uniquely support it. |
| **Traceable methodology** | Already provided by the framework: study DAG (`pipeline_gate.prerequisites`) + explicit `acceptance_criteria` + pass/fail gates + traceable findings. Foreground it — it is often the strongest contribution. |
| **Per-study rigor** | Sum of the per-study gaps above — drive each member study toward 8/8. |

## Worked example

`pbg-autopoiesis` is the reference: every study scores 8/8 and the investigation
5/5. Its study-1 shows the controls pattern (an externally-maintained-membrane
**negative control built with the Intervention process** that persists when
starved → precariousness tracks self-production, not external upkeep, plus a
positive self-producing control to calibrate), and study-5 is the adversarial
capstone (the metric rejects an externally-maintained mimic and a network missing
self-production). Mirror that shape.
