# Study-Detail Spine Reorg — Design

**Status:** approved design (interactive mockups accepted 2026-08-16). Cross-repo:
`vivarium-workbench` (renders + persists) and `viva-superpowers` (skills that fill it).

**Goal:** make the study-detail page intuitive by one organizing rule —
**Design = everything you specify · Evidence = everything that came out** — and fill
the panels that are currently empty or buried (Readouts, Results, Analyses), plus complete
the Assurance trio (Tests · Audit · Build).

**Mockups:** `study_design_reorg.html` (whole spine, 🧬), `studies_tab_reorg.html`
(Assurance trio, 🧪) — this session's scratchpad.

---

## 1. The target spine

Current arrangement (`vivarium_workbench/templates/study-detail.html:174-219`, act-clusters):

| Act (`data-act`) | Tabs today (`data-kind`) |
|---|---|
| study | Overview (`overview`) |
| design | Model (`compose`), Readouts (`readouts`) |
| evidence | Simulations (`simulate`), Visualizations (`visualize`) |
| assurance | Tests (`tests`) |
| decision | Decide (`conclusions`) |

Target arrangement:

| Act | Target tabs | Change |
|---|---|---|
| study | Overview | — |
| **design** | Model, Readouts, **Simulations** | Simulations MOVES here from evidence; Readouts rebuilt |
| **evidence** | **Results**, **Analyses**, Visualizations | Results NEW; Analyses promoted out of the Simulations panel |
| **assurance** | Tests, **Audit**, **Build** | Audit + Build NEW; rigor/repro move from Tests → Audit |
| decision | Decide | — |

**Rationale:** Design holds what you author before a run (the model, the emit plan, the
runs themselves). Evidence holds what came back (raw results, analyses, pictures). Assurance
grades it (pass · trust · provenance). Decision closes it.

**Internal `data-kind` names** (keep the existing convention; new panels get new kinds):
`overview, compose, readouts, simulate` (moves), `results` (new), `analyses` (new),
`visualize, tests, audit` (new), `build` (new), `conclusions`.

---

## 2. Architecture (verified, origin/main)

Server-rendered **Jinja + vanilla-JS + `lib/*_views.py` workers + thin FastAPI routes**.
No SPA/bundler.

- **Template:** `vivarium_workbench/templates/study-detail.html` — tab strip `:174-219`,
  panel `<section class="study-tab-panel" data-kind=… id="panel-…">` blocks
  (`overview:439, compose:656, simulate:1010, readouts:1057, visualize:1089, tests:1161,
  conclusions:1424`).
- **Client:** `vivarium_workbench/static/study-detail.js` — `_setStudyTab(kind)` toggles
  panels + lazy-loads (`if (kind==='readouts') _loadReadouts()` etc.); `_gotoStudyTab` jumps.
- **Workers:** `vivarium_workbench/lib/*_views.py`, each `build_*(ws_root, slug) ->
  tuple[dict|bytes, int]`; HTML-string card renderers `render_*_html(...) -> str`.
- **Routes:** thin `@app.get("/api/study-*")` in `vivarium_workbench/api/app.py` delegating
  to a lib worker.
- **Guards to keep green:** `tests/test_no_ai_deps.py` (AI-free — importing
  `viva_superpowers` *deterministic* modules IS allowed; no LLM SDKs),
  `tests/test_study_detail_render.py` (tab/panel markup), `test_fastapi_route_gaps.py`.

**Data already on disk (no new capture needed):**

| Panel | Source (verified) |
|---|---|
| Readouts | emit-plan leaf paths → `lib/observables_views.build_observables`; emitter identity/config → `lib/emitters.py` (`default_emitter`, `label_for_run`, `output_kind`); shapes via the same observables introspection |
| Simulations | `lib/simulations_index` rows (`store_path`/`db_path`/`emitter`/`n_steps`) from `runs.db` `runs_meta` |
| Results | run store → `/api/simulation-run-download` (per-run zip) + `lib/composite_run_views.build_composite_run` (trajectory) |
| Analyses | `lib/analysis_outputs.py` (`list_analysis_outputs`/`resolve_analysis_output`/`build_analysis_outputs_zip`) + routes `/api/study-analysis-outputs`, `/api/study-analysis-file`, `/api/study-analysis-zip` |
| Tests | `behavior_test_card.render_behavior_tests_html`; `/api/study-tests-run` → `tests.last_results` |
| Audit | `/api/study-rigor` (rigor scorecard), `/api/study-audit` (L0–L5); **sufficiency** → `viva_superpowers.test_audit.build_audit_report`/`audit_gate` (deterministic, importable) |
| Build | `viva_superpowers.loop_state` reads `.pbg/loop/<study>.json` (locked hash, reopen trail, iteration history, outcome) |

---

## 3. Per-panel design

### 3.1 Readouts (Design) — REBUILD
The Design-time emit **contract**, three blocks:
1. **Emitter & config** — emitter class + module (`emitters.default_emitter`/`label_for_run`),
   emit interval, buffer, output dir, emit scope (`declared`). From `lib/emitters.py` +
   `workspace.yaml`/study `runtime.default_emitter`.
2. **Emitted paths** — the declared store leaf paths from `observables_views.build_observables`
   (`leaves`), each with its authored `readouts[]` name/description/units when present.
3. **Outputs & shapes** — table: store path · dtype · shape `(n_steps,)` · units · bytes.

Extend `lib/readouts_views.build_study_readouts` payload with an `emitter` block + per-path
`dtype/shape/units/bytes` (shape derived from `n_steps` + leaf catalog; bytes best-effort or
omitted when unbuilt). No observed values here — those are Results. Keep the existing
soft-degrade path (unbuilt composite → authored-only rows) but always render the emitter block.
Route stays `/api/study-readouts`. Rebuild `_renderReadoutsTable` in the JS.

### 3.2 Simulations (Design) — MOVE + SLIM
Move the `simulate` pillar into the `design` cluster (after Readouts). The panel keeps the
runs table (baseline/variants/steps/dt/seed/status) and its per-run "⬇ Data" convenience link,
but the **"Study artifacts" strip splits out**: raw-data downloads → Results; analysis files →
Analyses. Panel `data-kind` stays `simulate`.

### 3.3 Results (Evidence) — NEW
Per-store preview of the latest run's emitted trajectory + downloads.
- New `lib/results_views.py::build_study_results(ws_root, slug) -> (dict, int)`: resolves the
  latest run (`simulations_index`/`run_index`), reads its store via existing
  `composite_run_views`/emitter reader, returns per-store `{path, dtype, first, last, min, max,
  sparkline:[…downsampled…]}` + the run's download refs.
- Route `GET /api/study-results?study=`. Downloads reuse `/api/simulation-run-download`
  (+ format variants). Panel `id="panel-results" data-kind="results"`; JS `_loadResults()`.
- Preview only (sparkline + first/last/min/max); full arrays via download. No new capture.

### 3.4 Analyses (Evidence) — PROMOTE
Lift the analysis-outputs UI out of the Simulations panel into its own Evidence panel: one card
per analysis (grouped by `AnalysisStep`/output group) listing its artifacts (png/json/csv/md)
with per-file download + an all-artifacts zip. Reuse `lib/analysis_outputs.py` +
`/api/study-analysis-outputs`/`-file`/`-zip` unchanged. Panel `id="panel-analyses"
data-kind="analyses"`; JS `_loadAnalyses()` (relocate `_loadAnalysisOutputs`).

### 3.5 Visualizations (Evidence) — UNCHANGED
Same `visualize` panel; only its cluster membership is unchanged (stays under Evidence).

### 3.6 Tests (Assurance) — SPLIT
Keep the graded **behavior report card** (`behavior_test_card`) as the Tests panel. **Move** the
rigor scorecard + L0–L5 reproducibility rendering OUT of this panel into Audit.

### 3.7 Audit (Assurance) — NEW
"Is the bar high enough to trust?" Three groups:
1. **Sufficiency** — `viva_superpowers.test_audit.build_audit_report(spec)` →
   `report_card_verdict/v2` axes (discrimination, objective_coverage, redundancy,
   discriminating_control, band_provenance) + `audit_gate` (pass/warn/fail).
2. **Rigor scorecard** — `/api/study-rigor` (moved from Tests).
3. **Reproducibility** — `/api/study-audit` L0–L5 (moved from Tests).

New `lib/audit_panel_views.py::build_study_test_audit(ws_root, slug)` importing
`viva_superpowers.test_audit` (deterministic — passes `test_no_ai_deps`). Route
`GET /api/study-test-audit?study=`. Panel `id="panel-audit" data-kind="audit"`; JS `_loadAudit()`.

### 3.8 Build (Assurance) — NEW
"Was the pass earned honestly?" Loop provenance from `.pbg/loop/<study>.json`:
locked-tests hash, reopen trail (`reopen_count` + `prior_hashes`), iteration history, outcome
(DONE / honest give-up). New `lib/loop_provenance_views.py::build_study_loop_state(ws_root,
slug)` importing `viva_superpowers.loop_state`. Route `GET /api/study-loop-state?study=`.
Panel `id="panel-build" data-kind="build"`; JS `_loadBuild()`. **Graceful empty state** when no
loop file exists (studies not built by `/viva-model-build`): a one-line "not built via the loop"
note, not an error.

---

## 4. Skill + docs propagation (viva-superpowers)

The panels read data the skills already write; propagation is (a) docs describing the new spine
and (b) prose fixes where a SKILL.md references the old tab layout. **No new skills** → the
count-string pins (`docs/skills.md:3`, `CLAUDE.md:9`, `tests/test_skill_manifests.py:26-33`)
stay unchanged.

- **`docs/concepts/vivarium-workbench-model.md`** — update the skill↔concept map and the
  sticky-nav / tab ordering (`:265-269`) to the target spine; document Readouts =
  emitter+config+paths+shapes, the Evidence split (Results/Analyses/Visualizations), and the
  Assurance trio (Tests/Audit/Build).
- **`/viva-study`** — its `check-observables` + `run-*` subcommands already record emitter +
  `emit_paths` (`run_registry.build_run_manifest`) and readout declarations that Readouts/Results
  render; update SKILL.md prose that names the old tabs.
- **`/viva-viz`** — writes the charts/analysis artifacts the Analyses panel lists; note the
  Analyses panel as the surface.
- **`/viva-audit-tests`** + **`/viva-model-build`** — already write the sufficiency report +
  `loop_state` the Audit/Build panels read; add a one-line "surfaces in Assurance › Audit/Build".
- **`/viva-report`, `/viva-navigate`** — prose fixes only where they reference tab names.

Data-flow confirmation (no capture gap): emitter/emit_paths → `run_registry`; runs →
`runs.db`; analyses → `studies/<slug>/charts/*` + analysis result files; sufficiency →
`test_audit`; loop → `.pbg/loop/<study>.json`. Readouts shows the *plan* (design-time), Results
shows *values* read from the run store — so per-readout observed-value storage is NOT needed.

---

## 5. Slices (each independently shippable + reviewable)

1. **Tab-strip reorg + relocation** (workbench) — move Simulations→Design; add Results +
   Analyses panels to Evidence; promote analyses out of Simulations; split raw-data downloads
   into Results (downloads only, no preview yet). Extend `test_study_detail_render.py` for the
   new cluster membership + panels.
2. **Readouts rebuild** (workbench) — emitter block + emitted paths + outputs & shapes; new
   `test_readouts_views` for the payload.
3. **Results preview** (workbench) — per-store sparkline + first/last/min/max via
   `results_views`; `test_results_views`.
4. **Assurance trio** (workbench) — split Tests; add Audit (`audit_panel_views`) + Build
   (`loop_provenance_views`) panels; `test_audit_panel_views` + `test_loop_provenance_views`.
5. **Skill + docs propagation** (viva-superpowers) — docs/concepts update + SKILL.md prose;
   keep `pytest -q` + `test_skill_conventions`/`test_skill_manifests` green.

Recommended build order: 1 → 2 → 4 → 3 → 5 (structure first, then the headline Readouts fix,
then Assurance, then Results polish, then propagation). Each slice is one PR.

---

## 6. Constraints (Global)

- **AI-free workbench:** new `lib/*_views.py` may import `viva_superpowers` *deterministic*
  modules (`test_audit`, `loop_state`, `rigor`) — never an LLM SDK. `test_no_ai_deps.py` must stay green.
- **One concern per lib module; thin routes.** Match existing `build_*(ws_root, slug) ->
  (payload, status)` convention and the `render_*_html -> str` card convention.
- **Graceful degrade:** every new panel renders a clear empty state when its source is absent
  (unbuilt composite, no runs, no analyses, no loop file) — never a 500.
- **Vocabulary:** Study (not Investigation); prefer `/api/study-*`; body key `study:`.
- **One change per commit; tests in `tests/`; `pytest -q` before commit.** Don't touch
  `notes/`/`references/notes/`. No `.pbg/` state committed.
- **No new skills** — do not trip the skill-count/manifest guards.

---

## 7. Testing

- Workbench: extend `tests/test_study_detail_render.py` (tab clusters + panel presence/order);
  add `tests/test_results_views.py`, `tests/test_audit_panel_views.py`,
  `tests/test_loop_provenance_views.py`, `tests/test_readouts_views.py`. Keep
  `test_no_ai_deps.py`, `test_fastapi_route_gaps.py` green. JS: mirror existing `tests/js/`.
- Superpowers: `pytest -q`; `test_skill_conventions.py`, `test_skill_manifests.py` unchanged-green.
