---
name: viva-tests
description: Use when authoring, enriching, running, auditing, or citing evidence for a study's Tests — the graded report cards that compile a run into a pass/fail verdict AND a signed margin an agent reads to drive iterative model building. Covers scaffolding a TestStep, grading checks into cited bands, running for the report + diff, auditing Tests-sufficiency before a pre-registration lock, and citing acceptance-band provenance from expert PDFs.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: "<author|enrich|run|audit|cite-bands> <study> [name] — see SKILL.md"
---

# /viva-tests

A study's **Test** is the compiled result of grading a finished run against
expectations — the gating verdict AND the **agent-feedback signal** for iterative
model building. This skill authors, enriches, and runs Tests so a model-building
agent (or you) can close the loop: *edit the model → run the study → read the
graded margins and the diff of what the edit moved → pick the next edit.*

A Test is a `viva_superpowers.TestStep` (the renamed `ReportCardStep`; the old name
still imports). Its `build()` emits a `report_card_verdict/v2` document whose axes
are **graded checks**, built with `viva_superpowers.check()`:

```python
from viva_superpowers import TestStep, TestBuilder, check, band, value

class AcetateOverflowTest(TestStep):
    name = "acetate_overflow"
    def build(self, study):
        obs = ...  # measured from the run (see § run: open via ResultsHandle)
        v = (TestBuilder(model_ref=study.study_name)
             .add("Physiology",
                  check("acetate_flux", "Acetate flux", obs,
                        band(2.5, 4.0), units="mM/h", severity="hard",
                        knob=["PtsG.kcat"], cite="Nanchen2006"))
             .build())
        return v, "<html>...</html>"
```

Each axis carries: `verdict` (`within_tol`/`drift`/`mismatch`/`ungraded`), a signed
**`margin`** (≥0 pass; the gradient), `severity` (`hard` gates / `soft` records /
`directional` should-improve), and optional `knob` (which model param moves it) +
`citation` (the band's evidence). `check()` computes `verdict`+`margin` from
`observed` vs an `Expected` — `band(low, high)`, `value(target, op, tol)`, or
`predicate(...)`. **Prefer cited bands over magic numbers.**

## Common prelude
1. `/viva-tests` assumes a workspace + a running workbench. If `.pbg/server/server-info`
   is absent, fail with: "Run `/viva-workbench start` first."
2. Resolve the study dir (nested- and flat-aware): `investigations/<inv>/studies/<slug>/`
   then legacy `studies/<slug>/`. The workbench endpoints resolve the slug server-side.

---

## author `<study> <name>`
Scaffold a new `TestStep` and wire it into the study.

1. Create the subclass in the workspace package's tests module
   (`pbg_<pkg>/tests_cards/<name>.py` or the workspace's existing report-card
   module — follow the workspace convention; grep for existing `TestStep`/
   `ReportCardStep` subclasses). Give it `name = "<name>"`, `applies(study) -> bool`
   (default `True`), and `build(study) -> (verdict_v2_doc, html)`.
2. In `build`, open the run's results via the handle `ResultsStep` produced —
   `study` (a `StudyContext`) for run-free cards, OR read the run's emitted records
   for data-driven ones (`.records()` / `.conn()` DuckDB view named `results`).
   Return a `/v2` doc assembled from `check()` calls via `TestBuilder`.
3. Register the class with the workspace core (the workspace's `build_core()` /
   `core_extensions` already discovers `TestStep` subclasses via `__init_subclass__`;
   just importing the module registers it).
4. Declare it in `study.yaml` under `tests:` as `{name: <name>, kind: report_card,
   card: <name>}` (the workbench merges report_cards + behavioral tests into one
   "Tests" panel). Save via the study's normal edit path (`/viva-study`), never by
   hand-editing if a subcommand exists.

Scaffold each axis as a **graded** `check()` from the start — even a placeholder
`band()` beats a bare `passed: bool`.

## enrich `<study> <test>`
Upgrade an existing Test's axes into stronger agent signal. This is the primary
lever for "add more detail so the model-building agent can improve its design."

1. Read the test's `build()` and the study's observables/analyses (what the run
   actually measures). For each axis that is a bare pass/fail (no `expected`/`margin`),
   propose a graded replacement:
   - an `expected` **band** or `value` grounded in a cited reference — use
     `/viva-tests cite-bands` (below) to link the reference and
     write the acceptance band; the same `band(low, high)` + `cite=` lands on the axis.
   - a `severity` (`hard` if it must pass to accept the model; `directional` for a
     quantity that should trend the right way but not gate).
   - a `knob`: the model parameter(s)/wiring most influencing this axis, so the agent
     knows what to turn.
2. Never invent thresholds — derive them from the analyses + cited bands and confirm
   with the human before writing. Bands over magic numbers.
3. Re-run (`run` below) and check the axis now reports a numeric `margin`.

## Gate discipline: gate_class + held-out grading

**Every gate carries a `gate_class`.** When authoring or enriching, classify
each gating check / behavior_test as
`gate_class: regression_pin | acceptance_criterion`. The rule is *when the
threshold was stated*, not how strict it is: a threshold chosen **after** seeing
the run is a **`regression_pin`** — it locks observed behavior against silent
drift (worth having!) but is not evidence the behavior is right; a directional
prior declared **before** the run — in the study's `preregistered:` block — is
an **`acceptance_criterion`**, the only kind that can confirm or refute. The
report's verdict counts split the two, and a pin counted as acceptance is the
classic post-hoc-gate failure the `audit` subcommand and
`/viva-harden-investigation`'s reviewer lens both hunt. (See
[pbg-study → Born-rigorous defaults](../viva-study/SKILL.md) for the scaffold
shapes; the rigor scorecard's threshold-provenance dim reads the result.)

**Substitutability / equivalence needs a held-out grading axis.** A claim that
module X can stand in for Y ("swap", surrogate, equivalence) is only graded by
a **held-out condition**: the tuning (train) condition and the grading (test)
condition must differ, the test axis must be marked as held-out so the report
can show train vs test, and the surrogate's **degrees of freedom vs the
constraints it was fit to** must be recorded. A surrogate tuned and graded on
the same condition demonstrates curve-fitting, not substitutability — the
audit's discrimination reasoning treats it as insufficient, and the rigor
held-out-generalization dim reads `gap` without it.

## run `<study>`
Run the study's tests and return the structured feedback signal.

1. Trigger the run through the workbench (the study's Simulate→Evaluate path; the
   run flush writes the cards + the diff). Do NOT re-implement running — use the
   study run endpoint.
2. Read back and report:
   - `<study>/viz/tests/report.json` (or the run's `run_verdict`): overall gate +
     per-card verdicts + counts (`hard_mismatch` is the gate-relevant one).
   - the run's `test_diff.json` (surfaced as `spec["test_diff"]`): per-axis
     `change ∈ {fixed, broke, improved, regressed, new, gone, unchanged}` +
     `margin_delta` — **what the last edit moved**.
3. Present, most-actionable first: **hard `mismatch` axes** (+ their `knob`s), then
   **`directional` axes trending the wrong way** (negative `margin_delta`), then
   fixed/improved wins. This ordered list is the next-edit worklist.

---

### Subcommand: audit

Judge whether a study's `behavior_tests[]` are rigorous enough to VALIDATE a
model — not too weak, not gameable — BEFORE they are pre-registered/locked and
the model-iteration loop begins. This is the AUDIT gate of the agentic
model-building loop (spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`).

The sufficiency report + gate this subcommand produces surfaces in the study's
Assurance › Audit tab (alongside the rigor scorecard and L0–L5 reproducibility).

#### What it checks

Deterministic (from `viva_superpowers.test_audit.build_audit_report`):
- **discrimination** (hard) — no trivially-wide band a wrong model would also pass.
- **objective coverage** (hard) — every mechanism the `question`/`purpose.mechanism` names has a primary Test.
- **redundancy** (soft) — Tests key on distinct observables.
- **discriminating control** (soft) — a Test the correct model should FAIL absent the mechanism.
- **band provenance** (soft) — numeric bands carry `cites`/`provenance`.

Deterministic sourcing audit (only when the study carries a `sourcing:` decision,
i.e. it went through the loop's SELECT phase — from
`viva_superpowers.module_sourcing.build_sourcing_report` + `sourcing_gate`):
- **source_fit** (hard) — the chosen module(s)' declared capabilities cover the task's `requires` tokens.
- **reinvention** (hard) — didn't build-new where a catalogued module already fits.
- **novelty_justified** (soft) — build-new only when nothing catalogued fits.
- **survey_recorded** (soft) — a rationale / candidates were recorded (the catalog was surveyed).

AI reasoning you add on top (the deterministic scaffold can't):
- **null-model plausibility** — for each primary Test, reason whether a scrambled/knockout/null model (mechanism removed) would ALSO satisfy the band. If yes, the Test is insufficient even if its band is narrow — say so and downgrade `discrimination`.
- **semantic coverage** — the mechanism-token scaffold flags literal misses; confirm real coverage (a Test may cover a mechanism the tokenizer didn't match, or vice-versa).
- **sourcing near-miss (semantic capability fit)** — `source_fit` matches capability TOKENS exactly, so it can be wrong two ways the tokens can't see. For each `missing_capabilities` token a `source_fit` mismatch reports, reason whether the chosen module *semantically* provides it under a differently-named token (task needs `diffusion`; the module declares `pde_transport`). A true near-miss means the manifest **tags** are incomplete, not the sourcing wrong — recommend adding the token to the module's declared capabilities and treat the hard mismatch as a `warn`, not a `fail`. Conversely, flag an exact-token match that is semantically hollow (the module lists `spatial` but only 1-D; the task needs 3-D) — **downgrade source_fit to a mismatch even though the deterministic pass matched.**

#### Run

```bash
STUDY="${1:?usage: /viva-tests audit <study-slug>}"
python - "$STUDY" <<'PY'
import sys, json, yaml
from pathlib import Path
from viva_superpowers import paths, test_audit
ws = paths.workspace_root()
sf = paths.workspace_dir("studies", root=ws) / sys.argv[1] / "study.yaml"
spec = yaml.safe_load(sf.read_text()) if sf.is_file() else {}
rep = test_audit.build_audit_report(spec)
gate = test_audit.audit_gate(rep)
print("audit gate:", gate)
for g in rep["groups"].values():
    for ax in g["axes"]:
        if ax["verdict"] != "within_tol":
            print(f"  {ax['verdict']:9} {ax['id']}  {json.dumps(ax.get('detail') or {})}")
print(json.dumps(rep))  # for the caller / to write test-audit.verdict.json
PY
```

When the study carries a `sourcing:` decision, also run the deterministic sourcing
audit (skips cleanly when absent — most studies have no `sourcing:` block):

```bash
python - "$STUDY" <<'PY'
import sys, json, yaml
from viva_superpowers import paths, module_sourcing as ms
ws = paths.workspace_root()
spec = yaml.safe_load((paths.workspace_dir("studies", root=ws) / sys.argv[1] / "study.yaml").read_text())
if not spec.get("sourcing"):
    print("no sourcing decision — sourcing audit skipped"); raise SystemExit
catalog = spec.get("catalog") or {}          # {module: [capability tokens]} from the SELECT survey
rep = ms.build_sourcing_report(spec, catalog)
gate = ms.sourcing_gate(rep)
print("sourcing gate:", gate)
for g in rep["groups"].values():
    for ax in g["axes"]:
        if ax["verdict"] != "within_tol":
            print(f"  {ax['verdict']:9} {ax['id']}  {json.dumps(ax.get('detail') or {})}")
print(json.dumps(rep))   # near-miss judgment reasons over detail.missing_capabilities
PY
```

Then apply the AI-reasoning dimensions (null-model, semantic coverage, **sourcing
near-miss**): if any finds an insufficiency the deterministic pass missed, treat the
audit as **fail** and report which Tests to strengthen — EXCEPT a sourcing hard
mismatch your near-miss judgment attributes to incomplete manifest tags (a real
semantic fit under a different token), which is a `warn` + a recommendation to fix
the module's declared capabilities, not a `fail`. On `fail`, the loop returns to
AUTHOR (Tests) or SELECT (sourcing); only a `pass`/`warn` audit may proceed to the
pre-registration lock.

#### Gate contract

- `fail` → a hard dimension (discrimination / objective_coverage; or sourcing source_fit / reinvention) is a mismatch, OR your null-model / semantic / sourcing-near-miss reasoning found one. Do NOT lock; strengthen the Tests (return to AUTHOR) or revise the sourcing decision (return to SELECT).
- `warn` → only soft dimensions flagged (redundancy / control / provenance; or sourcing novelty_justified / survey_recorded), OR a sourcing source_fit mismatch your near-miss judgment attributes to a manifest tagging gap (fix the module's declared capabilities). Lockable, but note the gaps.
- `pass` → sufficient. Proceed to lock.

The overall gate is the worse of the test-sufficiency gate and (when present) the
sourcing gate, after your near-miss reasoning has adjusted either.

---

### Subcommand: cite-bands

Guided band-provenance extraction: guides the agent through sourcing the
acceptance bands in a study's `behavior_tests[]` / `tests[]` that lack a
`cites` bib_key.  The AI does the reading and judgment; the vivarium-workbench
API surfaces candidates, writes the provenance, and validates.

A cited band is also the acceptance band on a **graded Test axis** —
`viva_superpowers.check(observed, band(low, high), cite=…)` inside a `TestStep`
(see `author`/`enrich` above). Recording provenance here and
grading a Test axis via `/viva-tests enrich` share one target: the band + its
`cites` bib_key land on the axis so its verdict carries a signed margin *and* the
evidence a reviewer would ask for.

**Dashboard-AI-free rule:** the AI reasoning stays entirely in this skill
(viva-superpowers).  The workbench only serves deterministic reads/writes —
no judgment happens server-side.  All writes go through `POST
/api/band-provenance` (never hand-edited YAML, never a client-side
reimplementation of the write).

**Thin client (Phase 2.1e):** this subcommand does no compute of its own — every
step is a `curl` call against the running dashboard server.  If a step below
looks like it needs local Python beyond parsing JSON, that's a sign the
workbench API under-covers the op — STOP and report it (the fix is a
workbench-side endpoint enhancement, not a bash reimplementation here).

#### Preconditions

1. A pbg workspace with the named study exists (study directory at
   `studies/<study-slug>/study.yaml`).
2. `references/papers.bib` exists at the workspace root (the bib source the
   linter checks against).  If a citation source is not yet in `papers.bib`,
   add the BibTeX entry there **first** before recording it on the band.
3. The dashboard server is running (`.pbg/server/server-info` exists) — the
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

#### Step 1 — Find uncited bands

Call `GET /api/band-provenance?study=<study-slug>` to get the list of
band-bearing entries that lack a `cites` field:

```bash
curl -sf "$URL/api/band-provenance?study=<study-slug>" | python3 -m json.tool
```

Response shape:
```json
{
  "study": "<study-slug>",
  "missing": [
    {
      "name": "<test-name>",
      "kind": "behavior_test" | "test" | "readout",
      "band": { "low": 0.2, "high": 0.5 },
      "field_path": "behavior_tests[0]"
    }
  ]
}
```

If `missing` is `[]`, all bands are already cited — nothing to do.

#### Step 1b — Pull the investigation's references as candidates

When the study belongs to an **investigation**, the investigation usually
already declares a curated pool of supporting references in its
`investigation.yaml` `inputs.references` block (workspace bib_keys that resolve
in `references/papers.bib`). These are first-class candidates for the uncited
bands — surface them via `GET /api/citation-gaps?investigation=<inv-slug>`:

```bash
curl -sf "$URL/api/citation-gaps?investigation=<investigation-slug>" | python3 -m json.tool
```

Response shape, keyed by member study slug:
```json
{
  "investigation": "<investigation-slug>",
  "gaps": {
    "<study-slug>": {
      "uncited_bands": [{ "test": "<test-name>", "observable": "<optional>" }],
      "available_references": ["dnaa-abundance-jb-1991", "dnaa-stability-jb-1999"]
    }
  }
}
```

For each uncited band in the study you are citing, the agent PROPOSES the most
**topically-relevant** reference(s) from `available_references` — matching the
reference's subject to the band's observable/test. **This match is the agent's
judgment.** Then:

1. Confirm the proposed pairing(s) with the user.
2. Apply via `POST /api/band-provenance` with `cites=[bib_key]`
   (Step 4 below) — the references already resolve as bib_keys, so no
   cite-resolution work is needed.

**Never fabricate.** Only link references the investigation has already declared
in `inputs.references` (or another key already in `references/papers.bib`). If
none of the investigation's references topically fits a band, fall through to
the expert-PDF search (Step 2) or park it in `proposed_inputs` (Step 3) — do not
invent a bib_key.

This investigation-inputs pool is an **additional** candidate source; the
expert-PDF path below still applies for bands it does not cover.

#### Step 2 — Surface candidate evidence per band

For each uncited band, call `GET /api/expert-search` to find relevant
passages in the workspace's expert PDFs. `q` is a comma-separated list of
search terms:

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

Show the snippets to the user so they can review the evidence.

#### Step 3 — Agent judgment (the only AI step)

**Parameter calibration vs acceptance band — classify before writing.** Does
the cited number share **units** with the observable the band tests (e.g.
both a 0-1 fraction, both a cell count)? Only then may it become
`calibration_anchor.literature_target`. If the cited number is a **parameter
value in the parameter's own units** (a Kd, an affinity, a rate constant —
never the observable's units), it calibrates the *model*, not the *band*:
route it to the study's `model_settings[].cites` instead, and **never** write
it as a behavior-test `literature_target`. A Kd recorded as the
`literature_target` on a dimensionless fraction silently corrupts
`divergence_factor` downstream (see the `biology-forward` aspect of
`/viva-harden-investigation`'s arithmetic block) — this is the trap to avoid.

A cited parameter itself always falls into one of three buckets — label it
explicitly, never leave it ambiguous:
1. **Cited** (`cites: [bib_key]`) — a real literature value the model is calibrated to.
2. **Recorded modeling choice** (`provenance: theory`, note "not fit") — a deliberate choice, not fit to data.
3. **Pending** (`proposed_inputs`, per Step 3 above) — not yet sourced.
Bucket 2 must be explicitly labelled as such — never silently treated as (1) cited or as data-anchored.

Read the candidate snippets.  If needed, open the cited PDF page with the
`Read` tool for fuller context.

**Choose the source** — pick:
- `bib_key`: the BibTeX key in `references/papers.bib` that establishes the band
- verbatim quote: the sentence or phrase that states the numeric range

**If the source is NOT in `papers.bib`:**
Add the BibTeX entry to `references/papers.bib` before proceeding.  The
`band_cites_unknown_bib_key` linter will error on any key not in that file.

**If you are UNCERTAIN, or the expert did not provide a source:**
Record the band as a pending item in `investigation.yaml` under
`proposed_inputs` (see below) rather than asserting an unverified citation.
NEVER fabricate a citation — a made-up bib_key will cause a linter error
and silently corrupt the provenance record.

```yaml
# investigation.yaml — add under proposed_inputs:
proposed_inputs:
  - kind: band_provenance_pending
    study: <study-slug>
    test_name: <test-name>
    note: "Band [0.2, 0.5] — source not confirmed; awaiting expert input"
```

#### Step 4 — Write provenance

Call `POST /api/band-provenance` to record the citation.  This is the ONLY
sanctioned write path — the workbench forwards it to a ruamel
comment-preserving round-trip so no comments or unrelated keys are disturbed:

```bash
BODY=$(python3 -c '
import json, sys
print(json.dumps({
    "study": sys.argv[1],
    "test_name": sys.argv[2],
    "cites": [sys.argv[3]],
    # include calibration_anchor only when the midpoint is in the OBSERVABLE's
    # own units (see the classification callout above) — a parameter value
    # (Kd/rate/affinity) belongs in model_settings[].cites, never here.
    "calibration_anchor": {
        "literature_target": float(sys.argv[4]),
        "cites": [sys.argv[3]],
    } if len(sys.argv) > 4 else None,
}))
' "<study-slug>" "<test-name>" "<bib_key>" "<midpoint-value>")

curl -sf -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/band-provenance" | python3 -m json.tool
```

Response shape: `{"study": ..., "test_name": ..., "written": bool}`
- `written: true` — file was updated (cite was missing or changed).
- `written: false` — entry not found (never fabricates) OR already identical (idempotent).

#### Step 5 — Validate

Re-call `GET /api/band-provenance?study=<study-slug>` to confirm the band is
no longer listed:

```bash
curl -sf "$URL/api/band-provenance?study=<study-slug>" | python3 -m json.tool
```

Then call the report linter to confirm the band checks are clean:
- `band_test_missing_cites` does NOT fire for the updated band.
- `band_cites_unknown_bib_key` does NOT fire (the bib_key is known).

```bash
curl -sf "$URL/api/report-lint" | python3 -c '
import json, sys
findings = json.load(sys.stdin).get("findings", [])
band_checks = [f for f in findings if "band" in f.get("check", "")]
print(json.dumps(band_checks, indent=2))
'
```

#### Guardrails summary

| Rule | Enforcement |
|---|---|
| Never fabricate a citation | `POST /api/band-provenance` returns `written:false` for non-existent names — no entry is created |
| Never hand-edit YAML | All writes via `POST /api/band-provenance` (comment-preserving) |
| Unknown bib_key → linter error | `band_cites_unknown_bib_key` check, surfaced via `GET /api/report-lint` |
| Uncertain source → `proposed_inputs` | Park pending in `investigation.yaml`, not on the band |
| Idempotent writes | Calling again with same args returns `written:false`, no write |
| No client-side compute | Every read/write is an API call; the skill never imports `viva_superpowers.*` directly |

#### Full workflow example

```bash
# 0. Preamble (walk to workspace root, resolve $URL) — see "Common preamble" above.

# 1. Find uncited bands
curl -sf "$URL/api/band-provenance?study=dnaa-2" | python3 -m json.tool

# 2. Surface candidates
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=DnaA-ATP,0.2,0.5,fraction" \
  --data-urlencode "max_hits=5" | python3 -m json.tool

# 3. Agent reads snippets, picks source (Boesen2024, page 4)

# 4. Write provenance
BODY='{"study":"dnaa-2","test_name":"frac-test","cites":["Boesen2024"],"calibration_anchor":{"literature_target":0.35,"cites":["Boesen2024"]}}'
curl -sf -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/band-provenance" | python3 -m json.tool

# 5. Validate
curl -sf "$URL/api/band-provenance?study=dnaa-2" | python3 -m json.tool
```

---

## The hardened loop (why this exists)
```
edit model → run study → read report.json + test_diff.json
     ↑                              │
     └── next edit ← failing/low-margin HARD axes (+ knobs) + directional regressions
```
Convergence = gate `pass` (no hard `mismatch`) with hard margins ≥ 0 and directional
margins trending up. The study dir — spec + tests + `report.json` + `test_diff.json`
— is the inspectable, hardened unit an agent iterates against.

## Red flags — STOP
- "I'll assert `passed: bool`" → grade it: `check(..., band(lo, hi))` gives the agent a margin.
- "I'll pick a threshold" → derive it from analyses + a cited band (`/viva-tests cite-bands`); confirm.
- "I'll hand-write the verdict.json" → emit it from `TestStep.build()` via `check()`/`TestBuilder`; the on-disk `overall` vocabulary is load-bearing.
- "Every axis should gate" → only `hard` axes gate; use `directional` for should-improve quantities so a not-yet-calibrated model isn't falsely failed.
- "This gate passed, so the model is validated" → check its `gate_class`: a post-run threshold is a `regression_pin`, never acceptance evidence (§ Gate discipline).
- "The surrogate matches, so they're substitutable" → only on a HELD-OUT condition it wasn't tuned on, with DoF vs constraints reported (§ Gate discipline).
