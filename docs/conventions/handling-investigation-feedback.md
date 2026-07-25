# Handling Investigation Feedback

How to take a reviewer's feedback on an investigation report and turn it into
correct, verified, shipped changes — without the failure modes that have bitten
past rounds. This is a **checklist + workflow**, not background reading; follow
it in order.

Feedback arrives two ways, and you must read BOTH:

1. **Inline annotations** — a `feedback-<inv>-<date>.yaml` exported from the
   report's inline-feedback widget (`annotations:` keyed by section id, e.g.
   `study-dnaa-0-parameter-foundation-embeds`). Import with
   `pbg-feedback-import`.
2. **Prose** — the message the reviewer writes alongside (or instead of) the
   widget. It often carries the *most important* asks (e.g. "make it clear
   which studies ran / passed") that have no widget anchor. Treat prose with
   equal weight.

## The workflow

```
parse (annotations + prose)
  → map each point to a concrete action
  → classify: one-study content fix  vs  systemic/infrastructural
  → run heavy work in the background, verify against REAL data
  → VERIFY THE RENDERED ARTIFACT (not just the yaml)
  → commit + push per repo
  → regenerate the report + eyeball it before saying "ready to send"
```

### 1. Parse — enumerate every point

Build an explicit table: each feedback item → which study/section → what it
asks. Include the prose asks, not just the widget annotations. A point you
don't write down is a point you'll drop.

### 2. Map each point to an action

For each item, decide the concrete change. Distinguish:

- a **value/parameter** ask ("decrease the synthesis probability a little") →
  may require a **re-run**; size the compute and run it in the background.
- a **status/clarity** ask ("I can't tell if it ran / passed") → almost always
  **infrastructural** (see below), not a per-study edit.
- a **scientific** ask ("seed 4 looks unstable") → verify against the data
  yourself before echoing it; the reviewer may be approximately right but
  imprecise (e.g. it was *seed 2*, not seed 4).

### 3. Classify: content fix vs. infrastructural

| If the issue… | …fix it |
|---|---|
| is specific to one study's numbers/prose | in that `study.yaml` |
| would recur across investigations (status legibility, missing run records, ambiguous markers) | in the **renderer / linter / status backbone**, then apply to this study |

Status legibility is the canonical example: the report derives a study's
run/test/verdict markers from `runs[].outcomes` and the 6-axis status fields,
**not** from a hand-set `status: passed`. Fixing one study's yaml without
fixing the derivation just moves the problem to the next investigation. See
[reviewer-facing status clarity](../concepts/vivarium-workbench-model.md#reviewer-facing-status-clarity).

### 4. Run heavy work in the background, verify against real data

Long sims (a multi-generation lineage is ~40 min) go in the background; poll or
wait on a completion condition. **Never** record a test result or a numeric
claim you haven't recomputed from the actual run output (parquet) — write a
small `scripts/verify_*.py` and cite it in the study's `verified_by:`. Past
rounds shipped fabricated "pass" numbers with no run behind them.

### 5. VERIFY THE RENDERED ARTIFACT — the lesson that keeps biting

The single most common failure: declaring something fixed because the *data* or
*yaml* looks right, when the thing the reviewer literally sees still reads
wrong.

- The per-investigation report a reviewer downloads is built **client-side** in
  `walkthrough.js` (`_buildInvestigationReportHtml`). Its per-test pills come
  from the **latest run's `outcomes[test_name].result`** — a test with
  `status: passed` but no recorded outcome still renders **⏳ pending**.
- So after editing, **trace the render path and confirm the rendered output**,
  not just the spec. Run `pbg-report` (Pass B lint surfaces the gaps), and
  open the dashboard to see the actual study cards.

### 6. Account for the install / deployment gap

A workspace's `.venv` usually runs **non-editable, git-pinned** installs of
`pbg-superpowers` and `vivarium-workbench`. Editing the source repos does
**not** change what the workspace's dashboard serves until you make the source
live:

```bash
uv pip install -e <path-to-vivarium-workbench> --no-deps
uv pip install -e <path-to-pbg-superpowers> --no-deps
python -m viva_superpowers.dashboard restart
```

If a correct change "doesn't show up," check the install mode before debugging
the code: `python -c "import vivarium_workbench, os; print(os.path.dirname(vivarium_workbench.__file__))"`
(run from *outside* the source repo so cwd doesn't mask the real import).

### 7. Commit, push, regenerate, eyeball

- One cohesive commit per repo; investigation content (study yamls) and tooling
  (renderer/linter) are **separate repos and separate PRs**.
- Run `/pbg-report` (Pass A audit + Pass B lint) and **open the report** before
  telling anyone it's ready to send. "The data is right" ≠ "the report is
  ready."
- Surface reviewer-specific decisions explicitly: a blocked study should carry
  its open question in `executive.decisions_needed` naming the person whose
  call it is (e.g. a parameter inconsistency for the domain expert).

## Anti-patterns this convention exists to prevent

- **Claiming "passed" off the headline status while the test pills still read
  pending** — verify the rendered pills (step 5).
- **Recording a verdict number with no run behind it** — recompute from parquet
  (step 4).
- **Fixing one study's yaml for a problem that recurs everywhere** — fix the
  infrastructure (step 3).
- **Debugging "my change doesn't work" when it was never installed** — check the
  install mode (step 6).
- **Echoing a reviewer's imprecise detail verbatim** — verify against the data
  (step 2).
- **Imposing the strictest reading of an acceptance criterion and recording a
  FAIL** — when a metric is evaluated over a multi-generation lineage, default to
  the *aggregate* (generation-average / steady-generation) reading, not strict
  per-generation. See "Acceptance criteria" below. (Cost of getting this wrong:
  a wrongly-recorded QUALIFIED/FAIL, plus chasing a "drift" the reviewer never
  considered a failure — a whole confirmatory sweep that wasn't needed.)
- **Accumulating per-run plots in a study's charts** — when a new canonical/latest
  run supersedes earlier ones, REMOVE the superseded runs' figures. A charts section
  showing several runs reads as "which one is real?" to a reviewer. Keep only the
  latest/canonical run's plots.
- **Trimming `visualizations:` and thinking the chart is gone** — the report
  discovers every `*.png`/`*.svg` FILE in `charts/` (via `/api/study-charts`), NOT
  the `visualizations:` list. Editing the list changes nothing a reviewer sees; you
  must `git rm` the file (and fix any prose/`provenance` that references it). Verify
  with `curl /api/study-charts/<study>` — it must return only the charts you intend.
  (Real case: a reviewer asked three times to "keep only the latest one"; the
  `visualizations:` list already had one entry, but five chart files were still on
  disk and still rendering — this is exactly the "verify the rendered artifact",
  step 5, trap.)

## Acceptance criteria: default to the aggregate for steady-state / lineage metrics

A metric measured across a multi-generation lineage is almost never "in band on
every tick of every generation." Two reasons, both expected, neither a failure:

1. **Stabilization transient** — the first generation(s) after a burned-in resume
   (or after a mechanism change) are still settling; early gens may sit outside
   the band while the system relaxes to steady state.
2. **Within-cycle oscillation** — pools that accumulate-then-halve at division
   (DnaA, mass, most counts) exceed/undershoot the band within a cycle by design;
   they are "in band" on the *cycle/generation average*, not every instant.

So when a study yaml encodes a band test, **default `pass_if.op` to the aggregate**
(`generation_average_in_range`, or a steady-generation mean that drops the startup
gens) rather than `in_range_every_generation`. Reserve the strict per-generation
form for criteria a reviewer has explicitly stated must hold every generation.

Signals that the aggregate is the intended criterion (treat as the default unless
told otherwise):
- the reviewer's language is "**within the band**" / "in range", not "every
  generation";
- the study's own `scientific_argument`/evidence already notes the metric
  oscillates or that "in band = cycle-mean, not every tick";
- the metric is a pool that doubles per cycle.

If genuinely ambiguous, encode the criterion explicitly in the test and surface
the choice to the reviewer **before** recording a fail — do not pick the strict
reading, record FAIL, and start diagnosing a non-problem.

## Related

- [Reviewer-facing status clarity](../concepts/vivarium-workbench-model.md#reviewer-facing-status-clarity) — the `study_clarity_summary` backbone + the report-linter clarity checks.
- `/pbg-report` skill — the pre-send audit + lint + render.
- `viva_superpowers.study_status` — derive-on-read status (the single source of truth for run/test/verdict markers).
