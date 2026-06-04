---
name: pbg-report
description: Regenerate the workspace dashboard + per-investigation reports. Runs a reviewer-readiness audit FIRST (Pass A — verdict ↔ chart drift, stale framings, demoted-chart citations, uncommitted state, suggested follow-ups), THEN the structural lint (Pass B — schema correctness, status contradictions, placeholders), then renders. Use BEFORE sending the report to an external reviewer. Idempotent.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [model-name | --all | --audit | --lint | --force | --skip-audit]
---

# pbg-report

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
eval "$(python -m pbg_superpowers.paths --env --workspace "$WORKSPACE_ROOT")"
```

This exports `$INVESTIGATIONS_DIR`, `$STUDIES_DIR`, `$REPORTS_DIR`, etc. (each = absolute path). Use these variables for the studies/investigations/references/reports paths below — do NOT hardcode `investigations/`, `studies/`, `reports/`. (The hidden `.pbg/` machine-state dir stays at the workspace root by default — use it literally.)

## Pass A — Reviewer-readiness audit (NEW)

Runs **before** the structural lint. Read-only. For each `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` (resolved from `workspace.yaml` `layout:`; `investigations/<slug>/` by default), perform these checks in order. Print findings as you go; group by severity (blocking / warning / info) at the end.

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

### A3b. Superseded-run chart hygiene

For each study, inspect `visualizations:` (and the `charts/` dir). If figures from **multiple different runs/seeds** are present (e.g. a `seed0` reproduction alongside a `seed1` canonical run), that reads to a reviewer as "which run is real?".

- **warning** — a study's charts mix more than one run/seed. Recommend: keep only the **canonical / latest run's** figures; remove or demote the superseded run's plots. (Reviewers routinely ask for exactly this — "remove plots from previous runs, keep only the latest.") When a new canonical run lands, prune the old run's figures in the same edit rather than accumulating them.

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
5. **Run outcomes** — scan `$STUDIES_DIR/*/study.yaml` `runs:` for any outcome other than `completed`. Flag.

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

Render anyway? (Pass B and render are next.)
```

If `blocking > 0` and `--force` is NOT set, exit before Pass B with a non-zero status. Resolve, add `--force`, or address findings via a follow-up commit.

## Pass B — Structural lint (UNCHANGED)

The existing pre-publication linter from `pbg_superpowers.report_linter.lint_workspace_report()`. Checks every study under the workspace's studies and investigations dirs (`$STUDIES_DIR` / `$INVESTIGATIONS_DIR`, layout-resolved; the linter resolves these itself from `--ws`):

- **incomplete_summaries** (error) — `evaluation_status: evaluated` but `conclusion_logic` is empty.
- **status_contradictions** (error) — gate/evaluation/sim/impl/review combinations that cannot logically co-exist.
- **missing_provenance** (error) — a finding marked run-derived but with empty `provenance.run_ids`.
- **unresolved_placeholders** (error) — string fields containing `TBD`/`TODO`/`XXX`/`[fill in]`/`<insert>`.
- **duplicate_modal_phrases** (warning) — pairs of behavior_test descriptions ≥90% character-identical.
- **truncated_takeaways** (error) — `conclusion_logic.if_pass`/`if_fail` ending mid-sentence or <20 chars.
- **status_claims_done_no_runs_recorded** (warning) — a study declares completion (`status: completed` / `gate_status: passed` / `evaluation_status: evaluated`) but records no run provenance at all (no `runs:`/`simulation_set:`/`planned_runs:`), so it renders as not-run/pending despite the headline.
- **reviewer_clarity_ambiguity** (warning) — anything that would read ambiguously on the per-study run/test/verdict strip: ran-but-every-test-pending (no `runs[].outcomes` recorded), or `gate_status: passed` while a test is recorded FAILED. Single-sourced from `study_status.study_clarity_summary`.

Only **error**-level findings block publication.

Internally:

```bash
# Pass B only:
python -m pbg_superpowers.report_linter --ws .
```

## Render

After both passes succeed (or `--force`):

```bash
# Prefer the vivarium-dashboard full SPA renderer when installed
# (produces the 110+ KB interactive SPA shell at $REPORTS_DIR/index.html;
#  pass the workspace ROOT — the renderer resolves the layout-aware reports dir itself):
python -c "from pathlib import Path; \
           from vivarium_dashboard.lib.report import render_workspace_report; \
           render_workspace_report(Path('.'))"

# Fall back to pbg-superpowers' slim renderer if the above is not installed:
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'))"
```

Forced render with auto-logged overrides:

```bash
python -c "from pathlib import Path; \
           from pbg_superpowers.report import render_workspace_report; \
           render_workspace_report(Path('.'), force=True)"
```

The skill reads `workspace.yaml` for the workspace slug, then builds `pbg_doc` from `pbg_<slug>.document.build_document()` if available; falls back to an empty dict.

## Before sending to a reviewer — verify the rendered artifact

A clean lint + a successful render does **not** mean the report reads correctly.
The per-investigation report a reviewer downloads is built **client-side**
(`walkthrough.js`), and its per-study run/test/verdict markers derive from
`runs[].outcomes` + the 6-axis status — not from a study's hand-set
`status: passed`. So:

1. **Open the dashboard and look at the actual study cards** (`/pbg-dashboard
   open --investigation <slug>`), or download the report. Confirm the
   "Ran · Tests · Verdict" strip and the test pills say what you expect — a
   test with no recorded `runs[].outcomes` shows **⏳ pending** even if its
   `status` is `passed`.
2. **If a correct change isn't showing**, check the install mode before
   debugging the code: a workspace `.venv` often runs **non-editable, git-pinned**
   `vivarium-dashboard` / `pbg-superpowers`. Make the source live and restart:
   ```bash
   uv pip install -e <path-to-vivarium-dashboard> --no-deps
   uv pip install -e <path-to-pbg-superpowers> --no-deps
   python -m pbg_superpowers.dashboard restart
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
      "reason": "force-published via /pbg-report --force",
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

`/pbg-report` produces deterministic output given the same inputs. The `--today` argument can be passed through for byte-stable CI runs:

```bash
python -c "..." # render_*_report(..., today='2026-05-09')
```

## Safety

- Never modifies `workspace.yaml`, `decisions.yaml`, or any other persistent state — read-only consumer.
- Pass A is read-only: it can SUGGEST follow-ups but never executes them.
- Refuses to run if `workspace.yaml` is malformed.
- Per-model rendering catches `build_core()` failures, logs them, and emits a stub deep-dive panel rather than crashing the entire report.

## When other skills invoke this

Other skills should invoke `/pbg-report --skip-audit` as part of step 8 of the spec §7 lifecycle. Routine refreshes don't need Pass A.

For reviewer-ready snapshots (sending to an expert, attaching to a PR description, downloading from the dashboard's investigation page), invoke `/pbg-report` with NO flags — both passes run, you get the audit + suggested follow-ups + the render.

## Example end-to-end (from a recent session)

A typical Pass A finding cascade:

```
$ /pbg-report

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
