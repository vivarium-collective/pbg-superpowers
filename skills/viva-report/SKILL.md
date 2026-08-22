---
name: viva-report
description: Use when the dashboard or a per-investigation report needs to be regenerated after new results, or before sending a report to an external reviewer — runs a reviewer-readiness audit and a structural lint first, then renders.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [model-name | --all | --audit | --lint | --force | --skip-audit]
---

# /viva-report

Regenerates the workspace dashboard + per-investigation reports. Runs a
reviewer-readiness audit FIRST (Pass A — verdict ↔ chart drift, stale
framings, demoted-chart citations, uncommitted state, suggested follow-ups,
AND required proposals for new visualizations a reviewer should consider),
THEN the structural lint (Pass B — schema correctness, status
contradictions, placeholders), then renders. Idempotent.

Transversal skill (no stage). Run **before sending the report to an external reviewer** (e.g. Chris on a PR) OR at end-of-stage to refresh the dashboards.

## Why two passes

Earlier versions of this skill ran only the structural lint (Pass B). Real reports kept shipping with **internal inconsistencies that lint can't catch**:

- The executive verdict cites a chart that was demoted to companion-status by a later commit ("Beulig 50-80 g/L target" while the load-bearing chart says "9.6 g/L peak").
- Numerical claims in the verdict drift from the chart-meta values that back them.
- New parquet runs land in `studies/.../parquet-runs/` but the executive panel still references the old reference sim.
- Uncommitted regenerated SVGs in the working tree would land in the next render but aren't on the branch yet.
- Obvious next experiments (e.g. "we ran single_daughters; both_daughters would tell a different story") are NOT surfaced as `decisions_needed`.

These are reviewer-readiness issues: lint says "the YAML is well-formed"; the audit asks "would the reviewer find this self-consistent?" Both matter; both run before render.

## Operation

| Flag | Behavior |
|---|---|
| (no args) | Pass A audit → Pass B lint → render. Refuse on blocking findings from either. |
| `--audit` | Pass A only; print findings + suggested follow-ups; do NOT render. |
| `--lint` | Pass B only; print findings; do NOT render. (Legacy path.) |
| `--skip-audit` | Skip Pass A; run Pass B + render. Use for routine end-of-stage refreshes invoked by other skills. |
| `--force` | Bypass blocking findings from either pass; log to `.pbg/report-lint-overrides.json` and render. |

## Resolve workspace directories first

Set `WORKSPACE_ROOT` to the workspace root (the directory holding `workspace.yaml`; `.` for the common case where the skill runs from the workspace root). Then resolve the workspace dirs (honors `workspace.yaml` `layout:` — works for flat or nested workspaces):

```bash
eval "$(python -m viva_superpowers.paths --env --workspace "$WORKSPACE_ROOT")"
```

This exports `$INVESTIGATIONS_DIR`, `$STUDIES_DIR`, `$REPORTS_DIR`, etc. (each = absolute path). Use these variables for the studies/investigations/references/reports paths below — do NOT hardcode `investigations/`, `studies/`, `reports/`. (The hidden `.pbg/` machine-state dir stays at the workspace root by default — use it literally.)

## Resolve the workbench server URL

Pass B (lint), Pass B½ (readout migration), and Render are thin clients of the
`vivarium-workbench` dashboard API — resolve its URL with `/viva-catalog`'s
exact preamble:

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

## Pass A — Reviewer-readiness audit (NEW)

Runs **before** the structural lint. Read-only. For each `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` (resolved from `workspace.yaml` `layout:`; `investigations/<slug>/` by default), perform these checks in order. Print findings as you go; group by severity (blocking / warning / info) at the end.

**Multi-investigation option — dispatch per investigation, in parallel.** Running A1–A8 inline against every investigation means the coordinating agent reads every `investigation.yaml`, every chart `meta.json`, and the full git log itself — on a multi-investigation workspace that burns the coordinator's context for no benefit, since only the findings matter downstream (obra's `requesting-code-review` lesson: "reviewing the diff inline burns the context window — dispatch a reviewer subagent; only the findings come back"). For a workspace with **2+ investigations**, the coordinator MAY instead dispatch one fresh-eyes reviewer subagent per investigation, in parallel, via `superpowers:dispatching-parallel-agents`, each filled from `skills/viva-report/audit-reviewer-prompt.md`. Each reviewer runs the same A1–A8 checklist scoped to its one investigation and returns findings only (A7 format) — the investigation YAML, charts, and git state it inspected stay in its own context. The coordinator concatenates the returned findings blocks before proceeding to Pass B. For a **single-investigation** workspace, running inline as below is simpler and just as cheap — treat dispatch as an optional, not forced, path.

### A1. Branch state

```bash
git status --porcelain
git log --oneline origin/main..HEAD | head -5
```

- **blocking** if uncommitted changes touch `$STUDIES_DIR/*/study.yaml`, `$STUDIES_DIR/*/charts/`, or `$INVESTIGATIONS_DIR/*/investigation.yaml`. Either commit or stash. Print which files.
- **info** if branch is N commits ahead of `origin/main` and N > 0. Show head 5 commits so the user remembers what's pending.

### A2. Executive-verdict freshness

For each investigation:

```bash
# Find newest chart svg mtime under any member study
find "$STUDIES_DIR"/*/charts/ -name '*.svg' -print0 | xargs -0 stat -f "%m %N" 2>/dev/null | sort -rn | head -1
stat -f "%m %N" "$INVESTIGATIONS_DIR/<slug>/investigation.yaml"
```

- **warning** if any chart SVG was modified AFTER `investigation.yaml`. Suggest: "The verdict block predates the latest chart edits — confirm `executive.new_empirical_evidence` references the newest charts."

### A3. Chart-reference integrity

Extract every `chart:` and `companion_charts:` path mentioned anywhere in `$INVESTIGATIONS_DIR/<slug>/investigation.yaml`. For each path:

- **blocking** if the file doesn't exist. The render would 404.
- **warning** if the cited chart appears in any study yaml's `companion_charts:` list (= was demoted) but the investigation verdict cites it as the primary `chart:`. The verdict is one revision behind. Print the (verdict line, demoting study) pair.

### A3b. Superseded-run chart hygiene — count the FILES, not the `visualizations:` list

**The report's charts section renders every `*.png`/`*.svg` FILE in a study's `charts/` directory** (via `/api/study-charts` → `discover_static_study_charts`), **NOT** the `visualizations:` list in `study.yaml`. So trimming `visualizations:` does NOT remove a chart from what a reviewer sees — the file is still discovered. To actually drop a chart you must **delete the file** (`git rm charts/<name>.png charts/<name>.svg`).

Check: `ls "$STUDIES_DIR"/<study>/charts/*.png` and count distinct chart basenames. Compare against the canonical/latest run.

- **warning** — a study's `charts/` dir holds figures from **more than one run/seed** (e.g. a `seed0` reproduction + `step2/step3` sixpanels alongside the `seed1` canonical). Reviewers read this as "which run is real?" and routinely ask to "keep only the latest." Recommend deleting the superseded **files** (not just the `visualizations:` entries), and rewriting any prose/`provenance` references that point at the deleted files so the report has no dead paths. When a new canonical run lands, prune the old run's files in the same edit.

Prefer the programmatic check when charts carry run tags (written by `figure_refresh`/`refresh_viz`): `viva_superpowers.chart_store.classify_charts(study_dir)` buckets charts into `canonical` / `referenced` / `superseded` / `untagged`, and `prune(study_dir, dry_run=True)` lists exactly the superseded files (a chart tagged to a non-canonical, non-pinned run). Report those as the warning here; only delete on an explicit refresh/regen with `prune(study_dir, dry_run=False)` (it spares `untagged` files and is a no-op when no canonical run resolves).

### A4. Numerical-claim consistency

For each chart referenced from the verdict, read its `<basename>.meta.json` sibling (same dir). Extract numeric values + units from the meta's `interpretation:` and `caption:` fields. Grep the verdict text for the same units (g/L, mM, orders, hours, mg/L, etc.). Flag when a verdict number doesn't match its chart-meta within 5% (or isn't an obvious round-number of it).

- **warning** with a specific replacement suggestion. Example: verdict says "Beulig target 50-80 g/L" but the chart's meta now reports "Beulig batch peak 9.6 g/L" — flag and propose the replacement.

### A5. Decisions_needed audit

For each `executive.decisions_needed:` entry:

- **info** — list them. Ask: "Should this be resolved before sending to a reviewer?"
- **warning** if a decision's text matches a recent commit subject via `git log --grep` (= movement on the blocker happened; the verdict may not reflect it).

### A6. Suggested follow-ups — the heart of the audit

This is the part Claude has to be clever about. For each investigation, surface **1–3 concrete follow-ups a reviewer would likely ask for** BEFORE seeing the report. Each follow-up needs: a one-line title, what evidence would change about the verdict, and an effort estimate (`single-file edit` / `~5 min sim` / `multi-hour sim` / `blocked-on-X`).

Mine these sources:

1. **`preliminary_findings:` blocks in study yamls** — almost always have an implicit "what's the next-tier experiment that would strengthen this?" Patterns to look for:
   - `outcome: partial-killed-at-memory-ceiling` / `terminated-early` → "re-run with bounded scope, or commit the partial finding"
   - "single_daughters" in interpretation → "both_daughters is the natural counterfactual"
   - "seed=0" / "single seed" → "multi-seed sweep closes the 'coincidence vs robust' question"
   - "interpolated CSV" / "sparse samples" → "the wide-format raw data may have denser coverage"
   - "extrapolation" / "would need" / "if scaled" → "the extrapolation can be tested with one more run"
2. **`open_questions:` with `status: open`** — if the verdict claims an architectural unblock, check whether any blocking open_question actually contradicts it.
3. **Mass-listener gaps** — if behavior_tests in a study assert on observables that no chart visualizes, propose a chart.
4. **Stale review-thread topics** — when on a PR-attached branch: `gh pr view <N> --json reviews,comments`. For each unresolved thread topic, see whether commits since address it; flag any that DON'T match a recent commit.
5. **Run outcomes / case history** — scan `$STUDIES_DIR/*/study.yaml` `runs:` for any outcome other than `completed`. Flag. Also flag any run whose `provenance_status` is `env_stale` (reproduced under a DIFFERENT environment than the original run — the replay isn't like-for-like; suppressed automatically when the study declares `pinned_env:`) or `nondeterministic` (a CONFIRMED result_fingerprint mismatch under an IDENTICAL environment + seed — a real reproducibility bug). Both are stamped by `vivarium_workbench.lib.rerun` (Task 3/5) and surfaced by the workbench's `GET /api/needs-attention` scan as `kind: "env_stale"` / `"nondeterministic"` items — cite those directly rather than re-deriving them.

### A8. Propose new visualizations — REQUIRED

Every reviewer-facing render must propose **at least 2 new visualizations per
investigation** that do not yet exist and would make a finding clearer, more
convincing, or more explorable. This is not optional: a report whose findings
are under-visualized is not reviewer-ready. Be inventive — the point is to give
the reviewer concrete, creative options to consider, not to restate the charts
already present.

For each proposal, surface:
- **Title + form** — what it shows and the chart type (favor interactive Plotly;
  reach for the richer forms in `/viva-viz`'s creativity table — phase portraits,
  heatmaps of report-card axes, Sankey mass-balance, sunburst inventories,
  variance-band population traces, animated multi-gen accumulation, etc.).
- **Which finding it sharpens** — the verdict line or study claim it supports,
  and what becomes undeniable that prose alone leaves fuzzy.
- **Data source** — the run/observable/CSV it would draw from (so the reviewer
  knows it's buildable, not hypothetical).
- **Effort** — `single-file edit` / `~5 min` / `multi-hour sim` / `blocked-on-X`.

Mine for proposals: findings asserted in prose with no chart; behavior-test
observables nothing visualizes (A6.3); report-card / multi-axis results shown
only as a table; multi-seed or population results shown only as a mean;
relationships between two observables only ever plotted separately; any "we
found X" that a reader has to take on faith.

**Take the initiative.** When a proposal is cheap (`single-file edit` / `~5 min`)
and the data is already on disk, **build it now** rather than only listing it —
invoke `/viva-viz` or add it to the investigation's figure generator, place the
output where the report discovers it, and move the item from "proposed" to
"added this pass" in the output. Only leave a proposal un-built when it needs a
new/long simulation or is blocked. Never silently skip the proposal step because
"the charts look fine" — propose anyway; there is always a sharper view.

### A7. Output format

```
== Pass A: reviewer-readiness audit ==
  blocking:  <N> findings
  warning:   <N> findings
  info:      <N> findings

Findings (severity, scope, message, suggested fix):
  [blocking] verdict→chart: $INVESTIGATIONS_DIR/<slug>/investigation.yaml cites
             $STUDIES_DIR/.../charts/00_X.svg as primary, but that chart is in
             $STUDIES_DIR/<study>/study.yaml.preliminary_findings.companion_charts
             (= demoted). Promote chart 02_Y.svg instead.
  [warning]  numerical drift: verdict says "50-80 g/L" but chart-02 meta says
             "9.6 g/L peak". Update verdict line 372 to "9.6 g/L".
  ...

Suggested follow-ups before sending to reviewer:
  1. <title> — <one-line evidence change> — <effort>
  2. ...

Proposed visualizations (≥2 per investigation; A8):
  1. <title + form> — sharpens <finding> — from <data source> — <effort>
  2. ...
  Built this pass: <list any cheap ones you drew on the spot, with paths>

Render anyway? (Pass B and render are next.)
```

If `blocking > 0` and `--force` is NOT set, exit before Pass B with a non-zero status. Resolve, add `--force`, or address findings via a follow-up commit.

## Pass B — Structural lint

The pre-publication linter, via `GET /api/report-lint`. Checks every study under the workspace's studies and investigations dirs (the endpoint resolves these itself from the workspace root):

- **incomplete_summaries** (error) — `evaluation_status: evaluated` but `conclusion_logic` is empty.
- **status_contradictions** (error) — gate/evaluation/sim/impl/review combinations that cannot logically co-exist.
- **missing_provenance** (error) — a finding marked run-derived but with empty `provenance.run_ids`.
- **unresolved_placeholders** (error) — string fields containing `TBD`/`TODO`/`XXX`/`[fill in]`/`<insert>`.
- **duplicate_modal_phrases** (warning) — pairs of behavior_test descriptions ≥90% character-identical.
- **truncated_takeaways** (error) — `conclusion_logic.if_pass`/`if_fail` ending mid-sentence or <20 chars.
- **status_claims_done_no_runs_recorded** (warning) — a study declares completion (`status: completed` / `gate_status: passed` / `evaluation_status: evaluated`) but records no run provenance at all (no `runs:`/`simulation_set:`/`planned_runs:`), so it renders as not-run/pending despite the headline.
- **reviewer_clarity_ambiguity** (warning) — anything that would read ambiguously on the per-study run/test/verdict strip: ran-but-every-test-pending (no `runs[].outcomes` recorded), or `gate_status: passed` while a test is recorded FAILED. Single-sourced from `study_status.study_clarity_summary`.
- **readout_migration_status** (info + warning) — surfaces each study's readout migration status: `migratable` readouts (info — safe to canonicalize, see the next step) and `needs_human` readouts (warning — un-parseable prose/derived selectors that must be re-authored against `/api/observables` via `/viva-study check-observables`).

Only **error**-level findings (`severity: "error"`) block publication.

Internally:

```bash
# Pass B only:
curl -sf "$URL/api/report-lint" | python3 -c '
import json, sys
d = json.load(sys.stdin)
findings = d.get("findings") or []
by_sev = {"error": 0, "warning": 0, "info": 0}
for f in findings:
    by_sev[f.get("severity", "info")] = by_sev.get(f.get("severity", "info"), 0) + 1
    print(f"[{f[\"severity\"]}] {f[\"study\"]}: {f[\"check\"]} — {f[\"message\"]} ({f[\"field_path\"]})")
print(f"\n{by_sev[\"error\"]} error / {by_sev[\"warning\"]} warning / {by_sev[\"info\"]} info")
'
```

`by_sev["error"] > 0` is what blocks publication (unless `--force`). `/api/report-lint` already applies `.pbg/report-lint-overrides.json` server-side (an overridden `error` finding arrives here downgraded to `warning`, message prefixed `[overridden]`) — the skill only displays `findings`, it never re-derives an override key or re-applies the override file itself.

## Pass B½ — Canonicalize readouts (auto-migrate, before render)

`/viva-report` is one of the two triggers (the other is the explicit `/viva-study migrate-readouts`) that auto-canonicalize the safe `migratable` readouts. Run this after Pass B passes and **before** rendering, so the rendered report shows every study's readouts in canonical form.

For each member study under `$STUDIES_DIR` / `$INVESTIGATIONS_DIR`, call `POST /api/study-readout-migrate` with `write: true` and tally the un-parseable ones:

```bash
python3 - "$URL" "$STUDIES_DIR" <<'PY'
import json, sys, urllib.request
from pathlib import Path

url, studies_dir = sys.argv[1], sys.argv[2]
needs_human_total = 0
for sy in sorted(Path(studies_dir).glob('*/study.yaml')):
    slug = sy.parent.name
    body = json.dumps({"study": slug, "write": True}).encode()
    req = urllib.request.Request(
        f"{url}/api/study-readout-migrate", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        d = json.load(resp)
    entries = d.get("entries") or []
    canonicalized = d.get("canonicalized") or []
    needs_human = [e for e in entries if e.get("status") == "needs_human"]
    if canonicalized:
        print(f"{slug}: canonicalized {len(canonicalized)} readout(s)")
    if needs_human:
        print(f"{slug}: {len(needs_human)} readout(s) still need_human "
              f"(re-author via /viva-study migrate-readouts)")
        needs_human_total += len(needs_human)
print(f"\nreadout migration: {needs_human_total} needs_human readout(s) remain across all studies")
PY
```

`write: true` (or its synonym `apply: true`) is meaning-preserving, comment-safe, idempotent, and leaves every `needs_human` readout untouched — the endpoint only rewrites the resolvable ones (it wraps `viva_superpowers.readout_migration.migrate_study_file` server-side). It is a **true no-op** on an already-canonical study (the file is left byte-identical — `changed=False`/`written=False`), so re-running `/viva-report` never reflows a clean readouts block. Note: inline comments on an *individual readout entry* are not preserved across canonicalization (the readout dict is rebuilt from its resolved selector); comments on non-readout content survive. Report the total `needs_human` count as a (non-blocking) finding: these can't be auto-fixed and must be re-authored against the composite's real observables via `/viva-study migrate-readouts <slug>` (which uses `/viva-study check-observables` + `/api/observables`). The skill never writes to `study.yaml` directly — the endpoint does, server-side.

## Render

After both passes succeed (or `--force`):

```bash
# Plain render — produces the interactive SPA shell at $REPORTS_DIR/index.html:
curl -s -X POST -H "Content-Type: application/json" -d '{}' "$URL/api/render" | python3 -m json.tool
```

Forced render with auto-logged overrides:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"force": true}' "$URL/api/render" | python3 -m json.tool
```

`{"force": true}` makes `POST /api/render` log every currently-blocking (error-level, not-yet-overridden) `report-lint` finding to `.pbg/report-lint-overrides.json` server-side, then render — the skill never writes the override file itself. `{"ok": true}` at HTTP 200 on success; `{"error": "<str>"}` at HTTP 500 on a render failure (per-model rendering catches `build_core()` failures internally rather than aborting the whole render).

## What the rendered report now splits — author toward it

The rendered tests/verdict section no longer shows one undifferentiated pass
count. It splits four populations, so author studies with the fields that feed
the split (see [pbg-study → Born-rigorous defaults](../viva-study/SKILL.md)):

- **Committed pytests** — the study's `tests/` suite results (executable
  invariants).
- **`gate_class: regression_pin`** — post-run pins that lock observed behavior
  against drift. Rendered separately and **never counted as acceptance
  evidence**.
- **`gate_class: acceptance_criterion`** — pre-stated priors from the study's
  `preregistered:` block; the only rows that count toward "the model behaves as
  predicted".
- **Expected-fail controls** — adversarial / drift-null entries that PASS by
  failing.

A behavior_test with no `gate_class` renders unclassified and is a lint
finding — classify it at the source rather than forcing past it. The report
also renders a **provenance / environment block** per study (environment
fingerprint, seeds, run ids, and the `units_and_time:` declaration); a study
missing those fields shows the hole to every reviewer. When drafting or
auditing verdict prose (Pass A), keep the populations honest: a verdict line
whose evidence is all pins should say "pinned, not validated", and a headline
number from a stochastic ensemble should quote the band across seeds, not the
best seed.

## Before sending to a reviewer — verify the rendered artifact

A clean lint + a successful render does **not** mean the report reads correctly.
The per-investigation report a reviewer downloads is built **client-side**
(`walkthrough.js`), and its per-study run/test/verdict markers derive from
`runs[].outcomes` + the 6-axis status — not from a study's hand-set
`status: passed`. So:

1. **Open the workbench and look at the actual study cards** (`/viva-workbench
   open --investigation <slug>`), or download the report. Confirm the
   "Ran · Tests · Verdict" strip and the test pills say what you expect — a
   test with no recorded `runs[].outcomes` shows **⏳ pending** even if its
   `status` is `passed`.
2. **If a correct change isn't showing**, check the install mode before
   debugging the code: a workspace `.venv` often runs **non-editable, git-pinned**
   `vivarium-workbench` / `pbg-superpowers`. Make the source live and restart:
   ```bash
   uv pip install -e <path-to-vivarium-workbench> --no-deps
   uv pip install -e <path-to-pbg-superpowers> --no-deps
   vwb server-restart
   ```

The full reviewer-feedback workflow (parse → map → classify → verify-rendered →
ship) is documented in
[handling investigation feedback](../../docs/conventions/handling-investigation-feedback.md).

## Override file format

`.pbg/report-lint-overrides.json`:

```json
{
  "schema_version": 2,
  "overrides": [
    {
      "key": "<pass>:<check>:<scope-slug>:<sha256[:12]>",
      "added_at": "2026-05-17T15:14:00",
      "reason": "force-published via /viva-report --force",
      "pass": "A",
      "check": "verdict_chart_demoted",
      "scope_slug": "multiscale-bioprocess",
      "field_path": "executive.new_empirical_evidence[2].chart",
      "message": "...verbatim message at time of override..."
    }
  ]
}
```

`--force` is idempotent: re-running it on the same finding does not double-append. Pass A and Pass B overrides share the same file but disambiguate via the `pass:` field.

Schema version 2 (this revision) added the `pass:` field; pre-existing schema 1 entries (no `pass:` field) are treated as `pass: "B"` for backwards compatibility.

## Idempotency

`/viva-report` produces deterministic output given the same inputs. The `today` body field can be passed through `POST /api/render` for byte-stable CI runs:

```bash
curl -s -X POST -H "Content-Type: application/json" -d '{"today": "2026-05-09"}' "$URL/api/render" | python3 -m json.tool
```

## Safety

- Never modifies `workspace.yaml`, `decisions.yaml`, or any other persistent state — read-only consumer.
- Pass A is read-only with ONE deliberate exception: the A8 initiative to
  *build* a cheap, already-buildable visualization (a new figure file + its
  generator entry). It SUGGESTS follow-ups/experiments but never runs sims or
  edits study verdicts. Any figure it draws is additive (a new chart file),
  surfaced in the output as "Built this pass", and committed like any other
  chart — it never rewrites or deletes existing figures.
- Refuses to run if `workspace.yaml` is malformed.
- Per-model rendering catches `build_core()` failures, logs them, and emits a stub deep-dive panel rather than crashing the entire report.

## When other skills invoke this

Other skills should invoke `/viva-report --skip-audit` as part of step 8 of the spec §7 lifecycle. Routine refreshes don't need Pass A.

For reviewer-ready snapshots (sending to an expert, attaching to a PR description, downloading from the dashboard's investigation page), invoke `/viva-report` with NO flags — both passes run, you get the audit + suggested follow-ups + the render.

## Example end-to-end (from a recent session)

A typical Pass A finding cascade:

```
$ /viva-report

== Pass A: reviewer-readiness audit ==
  blocking:  0
  warning:   2
  info:      1

[warning] verdict→chart mismatch:
  investigations/multiscale-bioprocess/investigation.yaml:354
  cites .../charts/00_preliminary_v2ecoli_vs_beulig_gap.svg as primary,
  but that chart is listed in
  studies/mbp-05-palsson-benchmark/study.yaml.preliminary_findings.companion_charts.
  Recommend: promote .../charts/02_v2ecoli_vs_beulig_batch_actual.svg (the
  load-bearing chart per the same study yaml) and demote 00 to a
  companion_chart link in the verdict.

[warning] numerical drift:
  Verdict says "Beulig 50-80 gDW/L batch-phase endpoint".
  Chart 02's meta.json interpretation says "Beulig batch peak ≈ 9.6 g/L".
  Recommend: update the verdict line to "9.6 g/L peak (batch); the
  50-80 g/L is the fed-batch endpoint."

[info] 7 commits ahead of origin/main; last:
  decefdc feat(mbp-05): plateau-diagnostic chart 02 from 175-min salvaged trajectory
  395fc94 doc(mbp-05): correct preliminary finding to Beulig batch peak 9.6 g/L
  ...

Suggested follow-ups before sending to reviewer:
  1. Run cpa=1e9 with --no-single-daughters for one generation
     — would let chart 02 show "both daughters accumulates while single
     plateaus" empirically (currently chart only shows the single side).
     Effort: ~10 min sim + 5 min chart re-render.
  2. Resolve "mbp-03 entry into Build still gated by upstream PR" in
     decisions_needed — git log --grep "pbg-bioreactor-transport-fork"
     shows no movement; either remove the decision or update it to "still
     gated as of <date>".
     Effort: single-line edit.
  3. mbp-04..06 still phase=Design; chart panels render empty. Consider
     either rolling them into a "Planned next" section of the verdict OR
     adding a sentence per study about its status.
     Effort: single-file edit.

Render anyway? (Pass B and render are next.)
```

Each finding gives the reviewer-facing surface, the exact YAML location, and the proposed fix. The suggested follow-ups distinguish "you can do this in five minutes" from "blocked on someone else."
