---
name: viva-harden-investigation
description: Use when an existing viva Investigation or Study needs to be made more rigorous, trustworthy, or defensible — an overclaiming verdict, a failing/partial report-card gate, a deferred/scaffolded study, an unresolved decisions_needed, a single-seed/uncalibrated claim, findings lacking biological interpretation, or a reviewer asking "is this real?"/"what does this mean biologically?". Also triggers on "harden", "de-risk", "stress-test", "make rigorous", or biology-forward authoring.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: "[investigation-slug] | biology-forward <study-slug>"
---

# viva-harden-investigation

Take an investigation that *looks* done and make its conclusions survive scrutiny. Hardening is
not "sprinkle more seeds everywhere" — it is: **verify the source is canonical, find the one gap
that most weakens the headline claim, and close that gap the right way for its kind.**

**Two failures this skill exists to prevent** (both observed in baseline agents):
1. Diagnosing from a summary / memory / a tree you never confirmed is current. Investigation
   content drifts across branches and worktrees — a study called a "deferred scaffold" on one
   branch may have *run and passed* on `origin/main`. Trusting the wrong tree gives a wrong premise.
2. Producing an undifferentiated rigor checklist (n≥4 seeds, add stats, add provenance…) without
   first locating the *load-bearing* weakness or root-causing a real divergence. Generic rigor
   poured onto an un-diagnosed failing gate hides the signal instead of explaining it.

## Workflow

**0. Verify canonical source — before reading anything for content.**
`git fetch origin main` and confirm the tree you are about to diagnose IS current `origin/main`
(or the branch you intend). Re-derive each study's state from its actual canonical axes in
`study.yaml` — `simulation_status`, `gate_status`, `evaluation_status`, and the investigation's
`executive.verdict_status` / `decisions_needed` — **not** from a memory, a prior survey, or prose.
Then verify the claim is *real, not just declared*: (a) the artifacts/numbers a `ran`/`passed`
study cites must actually exist on disk and its pipeline must run in the **canonical** env — a
`ran` status with uncommitted artifacts or an un-runnable pipeline is a **reproducibility gap**,
not a result; (b) when the claim is a *passed gate*, re-run it under a **seed/parameter sweep** — a
pass that holds only at one seed or one calibration is **knife-edge**, not a certificate.

**1. Survey & triage — locate the load-bearing gap.**
Run `/viva-report --audit` if available (Pass A surfaces verdict↔chart drift, stale framings,
uncommitted state, suggested follow-ups); else audit the gate axes by hand. Rank
the gaps by *leverage on the headline claim* and pick the ONE that matters most. Do not enumerate;
prioritize.

**2. Classify the hardening mode — each needs different work:**

| Gap | Do this |
|-----|---------|
| Unbacked claim / deferred scaffold (`evidence_for` items are *targets*) | RUN it, measure, replace targets with real numbers |
| Passed-but-thin (single seed, one generation, uncalibrated, directional-only gate) | Re-run at scale; add seeds, statistics, tolerance bands, fitted metrics (the generic-rigor part) |
| Un-graded or un-cited **hard** gating axis (bare `passed: bool`, magic threshold, no evidence) | Grade it via [`/viva-tests`](../viva-tests/SKILL.md) `enrich` — a **cited** acceptance band + a signed `margin` + a `knob` — so the gate carries evidence and an agent-actionable gradient, not just pass/fail. An un-graded hard axis is itself a hardening gap. |
| Failing / partial report-card gate with a real divergence | **ROOT-CAUSE it first — REQUIRED: superpowers:systematic-debugging.** No fix, no added rigor, until you can state the cause. A verdict of *real & understood* (no bug) is a COMPLETE hardening: document the mechanism, resolve the decide, recommend an optional fix — do **not** force a code patch |
| Overclaimed verdict (`verdict: pass, confidence: high` on thin evidence) | Reconcile `verdict_status`/confidence to the evidence via `/viva-study set-verdicts` / `set-conclusion` |
| Open `decisions_needed` / empty followups | Resolve, or fill with concrete follow-up proposals (`/viva-study propose-followup`, `seed-from-followup`) |

> **Bounded-metric CIs.** A normal-approximation CI on a bounded metric (a
> fraction in [0,1], a count, a non-negative rate) can spill outside the
> metric's support — e.g. a lower bound below 0 on a [0,1] fraction. Use a
> Wilson score interval, or at minimum clamp the normal-approx CI to the
> metric's support; never report a CI bound outside the metric's range.

**2b. Reviewer lens — hunt the review's durable failure modes.**
After classifying the load-bearing gap, sweep the investigation once against
this checklist. Each row is a failure mode external peer review keeps finding in
*finished* investigations — and each now has a rigor-scorecard dimension or
report-linter check behind it (see
[`docs/conventions/rigor-checklist.md`](../../docs/conventions/rigor-checklist.md)),
so point authors at the enforcing check rather than re-litigating the principle:

| Failure mode to hunt | Signature | Enforced by |
|---|---|---|
| Post-hoc gate presented as acceptance | behavior_test with no `gate_class`, or a threshold that first appears in the same commit as the run it grades | `gate_class` lint; rigor threshold-provenance + pre-registration dims; `study_verdict.preregistration_status()` |
| Tuned surrogate labeled substitutability | swap/equivalence claim with no HELD-OUT condition (tuned and graded on the same data); degrees-of-freedom vs constraints unreported | rigor held-out-generalization dim; `/viva-tests audit` discrimination |
| Under-powered stochastic causal claim | n < 20 replicates per arm, gated on a single seed, no rank test, no drift-null control | rigor Replication dim (causal-claim tier) |
| Authored criterion dressed as emergence | interpretation-tier finding missing `mechanism_origin`, or `engineered` behavior narrated as emergent | rigor engineered-vs-emergent dim |
| Missing conservation ledger | a representation conversion (lattice→particles, field→agents, …) with no tally of the conserved quantity on both sides | conservation-ledger check |
| Unseeded stochastic / dropped config keys | a stochastic process with no explicit seed; a composite config key that never reaches its process | `stochastic_unseeded` / `config_consumption` lints |
| Decorative physical unit labels | µm / mM / minutes on axes or claims with no `units_and_time:` declaration or calibration behind them | `units_declared` / unearned-unit-labels lint |
| Best-seed headline | verdict or claim quotes the flagship seed instead of the ensemble band | band-not-best-seed lint; lead with the band |

Any hit is a hardening gap in its own right — fold it into the step-2 table
(most land in "passed-but-thin" or "overclaimed verdict") and fix it per kind.
Remediation is usually a reclassification, not a rewrite: a post-hoc gate
becomes an honest `gate_class: regression_pin`; a best-seed headline becomes a
band; a tuned surrogate claim narrows to "fits condition A" until a held-out
condition exists.

**3. Look for cross-investigation leverage.** The same signature (e.g. an O₂ exchange deficit)
often weakens two investigations at once. Root-cause once; update *every* study/investigation that
cites it, including the `decisions_needed` your finding resolves.

**4. Execute in isolation, integrate carefully.** Work in a dedicated worktree off *current*
`origin/main` (REQUIRED: superpowers:using-git-worktrees); never commit in the shared checkout.
Commit deliverables early and often. Keep **run-only scaffolding out of what you land** — SUMMARY
files, env-shadow helpers, local `.gitignore`/`.deps` entries are for the run, not the canonical
branch. If the worktree needs a dependency newer than a shared venv, shadow it locally
(git-ignored) — never mutate a venv other running work depends on.

**Integrating a headless / parallel agent's branch:** its base is almost always stale (origin
moved on while it ran). A whole-branch merge — or reading `git diff origin/main..branch` — shows
**phantom reversions**: files `main` added *after* the agent branched appear deleted. Do NOT merge
wholesale. **Cherry-pick per commit** onto current `origin/main`, then verify
`git diff --stat origin/main HEAD` contains ONLY your deliverables — any unrelated deletion (CI
config, lockfile, audit allowlists) is a base-gap artifact to drop.

**5. Close the loop.** Record findings (`/viva-study findings`, `set-verdicts`), resolve/fill
`decisions_needed`, seed follow-ups, then re-run `/viva-report --audit` until the drift it flagged
is gone. A hardening is done when the report card and the verdict tell the same story as the data.

**Landing & publishing.** These repos use strict protection (`enforce_admins`, required review,
up-to-date-required). A PR you authored can't be self-approved, and with `enforce_admins` ON,
`gh pr merge --admin` is *refused* — don't thrash it. Landing needs a reviewer, or (only on the
owner's explicit say-so) a **minimal** `enforce_admins` toggle OFF → merge → **restore ON**,
verified, touching nothing else in the protection config. Strict mode serializes a batch: each
merge puts the siblings BEHIND, so `update-branch` + re-run CI between merges. After merge, the
read-only dashboard auto-publishes from `main` on `workspace/**` changes — confirm the Publish
workflow goes **green** (a triggered run ≠ a successful one).

### Aspect: biology-forward

Invoked as `/viva-harden-investigation biology-forward <study-slug>`. Brings the
quantitative biology forward into the structured finding slots the report
renderer already draws, then guides the agent to author the mechanism prose
using the auto-filled numbers as a scaffold. Fills the quantitative slots
(`evidence.observed`, `expected.range`, `divergence_factor`) via the workbench
API, then guides the agent to write the biological interpretation
(statement/summary/explanation/status) over that scaffold. This is the tool
step 5 ("Close the loop") reaches for when findings carry numbers but no
mechanism prose.

**Architecture:**
- **Deterministic part** (code-owned, never hand-edit): the workbench's
  `POST /api/study-findings-populate-observations` fills `evidence.observed`,
  `evidence.units`, `expected.range`/`cites`, `provenance.run_ids`,
  `evidence.divergence_factor`, and the measured side of `calibration_anchor` —
  all from `computed_outcomes` + band + readouts.
- **Authored part** (AI only): the agent writes `statement`, `summary`,
  `explanation`, `status`, and `expected.summary` (+ selects
  `expert_reference.quote` from `GET /api/expert-search` candidates).

**Dashboard-AI-free rule:** the AI reasoning stays entirely in this skill
(viva-superpowers). The workbench only serves deterministic reads/writes — no
judgment happens server-side. All number-writes go through
`POST /api/study-findings-populate-observations` (never hand-edited YAML).

**Thin client (Phase 2.1f):** this aspect does no compute of its own — every
deterministic step is a `curl` call against the running dashboard server. If a
step below looks like it needs local Python beyond parsing JSON, that's a sign
the workbench API under-covers the op — STOP and report it (the fix is a
workbench-side endpoint enhancement, not a bash reimplementation here).

#### Preconditions

1. A pbg workspace with the named study exists (`studies/<study-slug>/study.yaml`).
2. The study has `findings[]` with at least one entry carrying `evidence.from_test`.
3. The canonical run has been evaluated: `computed_outcomes[T].measured_value` must
   exist for the linked test. Run `/viva-study run-baseline` + sync if not present.
4. The dashboard server is running (`.pbg/server/server-info` exists) — the
   preamble below errors out with a fix-it hint if not.

#### Common preamble

```bash
# Walk up to workspace root.
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace"; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "ERROR: dashboard server not running. Run /viva-workbench start"; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
python3 -m viva_superpowers.server_preflight --url "$URL" || true  # version-skew preflight (warns; never fails)
```

#### Step 0 — Prerequisite: sync the canonical run

If the canonical run's `computed_outcomes` may be stale (a fresh run just
completed), reconcile `runs.db` → `study.yaml` first so `measured_value` is
present for the linked tests:

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-sync-runs" | python3 -m json.tool
```

#### Step 1 — Fill the quantitative slots (deterministic)

Call `POST /api/study-findings-populate-observations` to fill all absent
code-owned slots:

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```

The response reports `{study, filled, skipped}`.
- `filled` — findings that received at least one new code-owned field.
- `skipped` — findings with no `evidence.from_test` link or no `measured_value`.

If `filled == 0` and you expected fills, check:
- Does the finding have `evidence.from_test: <test-name>`?
- Does the canonical run's `computed_outcomes` have a `measured_value` for that test?
  Re-run Step 0 (`POST /api/study-sync-runs`) or `/viva-sync-runs` to refresh.

#### Step 2 — Show the observed-vs-band scaffold

After populate, `Read` the study's `study.yaml` (the `Read` tool) and look at
each `findings[]` entry that now carries `evidence.observed`. For each, note:

- `evidence.observed` (+ `evidence.units`)
- `expected.range` (or `expected.threshold`)
- `evidence.divergence_factor`
- `provenance.run_ids`

These filled numbers are the scaffold you author the prose over in Step 4.
(Reading the YAML is a native file read — no local compute.)

#### Step 3 — Surface expert-doc candidates (optional but recommended)

For each finding that needs an `expert_reference.quote`, call
`GET /api/expert-search` to find relevant passages in the workspace's expert
PDFs. `q` is a comma-separated list of search terms:

```bash
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=<test-name>,<numeric-bound>,<domain-term>" \
  --data-urlencode "max_hits=5" | python3 -m json.tool
```

`q` should include: the test name or readout name, the numeric bounds
(e.g. `0.2`, `0.5`), and any domain keywords (e.g. `DnaA-ATP`, `fraction`).

Response shape:
```json
{
  "terms": ["<test-name>", "0.2", "0.5", "<domain-term>"],
  "hits": [
    { "doc": "<filename>.pdf", "page": 3, "snippet": "…±100 chars around match…", "term": "<matched-term>" }
  ]
}
```

Present the snippets and let the agent select a verbatim quote for
`expert_reference.quote`. If needed, open the cited PDF page with the `Read`
tool for fuller context.

#### Step 4 — Author the mechanism prose (the only AI step)

For each finding whose numbers are filled, the agent writes ONLY the irreducible
authored slots. Use the scaffold from Step 2 as a guide:

| Slot | What to write |
|---|---|
| `statement` | One-sentence biological claim ("The DnaA-ATP fraction lands in the [0.2,0.5] band…") |
| `summary` | Mechanism explanation — what the number means and why the model produces it |
| `explanation` | Optional deeper mechanistic rationale |
| `status` | `confirms` / `partial` / `contradicts` / `novel` — based on divergence_factor |
| `expected.summary` | The literature claim the test is checking against (one sentence) |
| `expert_reference.quote` | Verbatim sentence from the expert PDF (selected in Step 3) |

Write the prose to `study.yaml` using the `Edit` tool. The numbers (`observed`,
`range`, `divergence_factor`, `run_ids`) are code-owned — never hand-edit them.
If the numbers change (e.g. after a new run), re-run Step 1
(`POST /api/study-findings-populate-observations`) to refresh them.

#### Step 5 — Validate (idempotency check)

Re-call `POST /api/study-findings-populate-observations` to confirm it's
idempotent (returns `filled=0`):

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```

Expected output: `{"study": ..., "filled": 0, "skipped": N}` — nothing changed
because all code-owned slots are already present.

#### Guardrails

| Rule | Enforcement |
|---|---|
| Numbers are code-owned | `POST /api/study-findings-populate-observations` fills only absent slots; never hand-edit `evidence.observed`, `expected.range`, `divergence_factor`, `provenance.run_ids` |
| Never overstate beyond divergence | If `divergence_factor > 0`, the finding `status` must be `partial` or `contradicts`, never `confirms` |
| Uncertain mechanism → mark novel | If you cannot find a literature match, set `status: novel` and do not fabricate `expert_reference` |
| No from_test → skip | A finding with only `from_run` is never auto-filled (never-fabricate rule); document it as an authored finding |
| Idempotent | Re-running populate on an already-filled study is always safe |
| Non-circular observable | The readout's domain/denominator must be fixed independently of the mechanism under test — a metric computed only over the sub-population the mechanism gates/selects (e.g. recruitment measured only over the cells the mechanism activated) is circular by construction |

#### Quick-reference: divergence_factor arithmetic

```
With expected.range [low, high]:
  inside [low, high]  → divergence_factor = 0.0  (status: confirms)
  below low           → (low - measured) / low   (positive; status: partial/contradicts)
  above high          → (measured - high) / high (positive; status: partial/contradicts)

With calibration_anchor.literature_target L:
  divergence_factor = (measured - L) / L   (signed; positive = above target)

With threshold T only:
  divergence_factor = (measured - T) / T   (signed)
```

**Guard:** `literature_target` must be in the observable's own units. A
parameter-calibration citation (e.g. a Kd) belongs in the study's
`model_settings[].cites`, never here — writing a parameter value as
`literature_target` on a differently-united observable makes
`divergence_factor` meaningless. See `/viva-tests cite-bands` Step 3.

#### Full workflow example

```bash
# (preamble above sets $URL)

# 0. Prerequisite: reconcile the canonical run's outcomes
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' "$URL/api/study-sync-runs" | python3 -m json.tool

# 1. Fill the numbers
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool

# 2. Read studies/dnaa-2/study.yaml (Read tool); note observed / range /
#    divergence_factor for each finding with evidence.observed.

# 3. Search expert PDFs for a quote
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=DnaA-ATP,0.2,0.5,fraction" \
  --data-urlencode "max_hits=5" | python3 -m json.tool

# 4. Agent authors the prose with Edit tool (statement/summary/status/expert_reference)

# 5. Validate idempotency (expect filled=0)
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```

---

## Red flags — STOP

- "The survey/memory says study X is a scaffold" → confirm on current `origin/main` first (step 0).
- "Let me add seeds and statistics to this failing gate" → root-cause it first (step 2).
- "Here are 11 things to improve" with no ranking → you skipped triage (step 1).
- A gate whose threshold matches the run it grades, presented as acceptance → it's a `regression_pin` until a pre-stated prior exists (step 2b).
- A headline number from the best seed of a stochastic ensemble → lead with the band; gate on the ensemble statistic (step 2b).
- An observable computed only over the sub-population the mechanism gates/selects (e.g. measuring recruitment over just the cells the mechanism activated) → circular by construction; require the observable's domain/denominator be fixed independently of the mechanism under test.
- Hardening the investigation you were handed without checking a sibling has the same defect (step 3).
- Committing in the shared `~/code/<repo>` checkout instead of a worktree (step 4).
- Merging an agent's whole branch, or trusting `diff origin/main..branch` — cherry-pick per commit and check the landed diff is deliverables-only (step 4).
- Landing an agent's `SUMMARY.md` / env-shadow helpers into the canonical branch (step 4).
- Forcing a code patch when the root cause is real, understood biology → document + resolve the decide instead (step 2).
- Re-trying `gh pr merge --admin` against `enforce_admins` — it won't bypass; get a review or an owner-authorized minimal toggle (step 5).
- Any branch-protection change beyond a minimal, restored-immediately `enforce_admins` toggle, or without explicit owner authorization (step 5).

## Real-world impact

Across 7 v2ecoli investigations hardened this way: a stale-branch survey mislabeled *passed*
studies as "scaffolds" (Step 0 caught it); the real #143 gap was **real FBA behavior + an
averaging-window fragility, not a bug** → closed by documenting + resolving the decide, no forced
patch; a study marked `ran` proved **unreproducible** (uncommitted artifacts + an un-runnable
pipeline) and an SBC "PASS" proved **knife-edge** under a seed sweep — both caught only by
re-deriving, not trusting the status. Landing exposed the base-gap trap (a branch diff falsely
showing `ci.yml` deleted) — per-commit cherry-pick + a deliverables-only check kept main's newer
work intact.
