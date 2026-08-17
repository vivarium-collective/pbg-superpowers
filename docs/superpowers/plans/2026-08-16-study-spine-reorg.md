# Study-Detail Spine Reorg — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.
> Steps use checkbox (`- [ ]`) tracking. Each task = one slice = one cohesive PR-sized diff.

**Goal:** Reorganize the workbench study-detail spine to Design(Model·Readouts·Simulations) →
Evidence(Results·Analyses·Visualizations) → Assurance(Tests·Audit·Build), fill the empty/buried
panels, and propagate the structure to the viva-superpowers skills/docs.

**Architecture:** Server-rendered Jinja (`study-detail.html`) + vanilla JS (`study-detail.js`) +
`lib/*_views.py` workers + thin FastAPI routes (`api/app.py`). New panels reuse on-disk data;
no new capture. AI-free workbench (may import `viva_superpowers` deterministic modules only).

**Tech Stack:** Python 3, FastAPI, Jinja2, vanilla JS, pytest.

**Spec:** `docs/superpowers/specs/2026-08-16-study-spine-reorg-design.md` (READ IT — full
per-panel data sources, verified paths, and rationale live there; this plan is task boundaries).

**Repos / worktrees:**
- workbench: `~/code/vivarium-workbench--study-spine-reorg` (branch `study-spine-reorg`)
- superpowers: `~/code/viva-superpowers--study-spine-reorg` (branch `study-spine-reorg`)

## Global Constraints
- Workbench stays AI-free: `tests/test_no_ai_deps.py` must pass. New `lib/*_views.py` may import
  `viva_superpowers.test_audit` / `.loop_state` / `.rigor` (deterministic) — never an LLM SDK.
- One concern per lib module; routes thin. Worker signature: `build_*(ws_root, slug) -> tuple[dict|bytes, int]`.
- Every new panel renders a graceful empty state (unbuilt composite / no runs / no analyses /
  no loop file) — never a 500.
- Vocabulary: Study (not Investigation); `/api/study-*`; body/query key `study:`.
- `pytest -q` green before each commit. Don't commit `.pbg/` state; don't touch `notes/`,
  `references/notes/`. No new skills (keep skill-count guards untouched).
- Current tab strip: `vivarium_workbench/templates/study-detail.html:174-219`; panels at
  `:439/656/1010/1057/1089/1161/1424`; `_setStudyTab(kind)` in
  `vivarium_workbench/static/study-detail.js`.

---

### Task 1: Tab reorg + Results/Analyses relocation (Slice 1, workbench)

**Files:**
- Modify: `vivarium_workbench/templates/study-detail.html` (tab strip `:174-219`; simulate panel `:1010`)
- Modify: `vivarium_workbench/static/study-detail.js` (`_setStudyTab`, analysis/raw-data loaders)
- Modify: `vivarium_workbench/lib/study_page.py` (`act_gate_states` / any tab-kind lists if present)
- Test: `tests/test_study_detail_render.py`

**Interfaces produced:** panels `id="panel-results" data-kind="results"` and
`id="panel-analyses" data-kind="analyses"` exist under the `evidence` act-cluster; `simulate`
pillar sits under the `design` cluster; JS `_loadResults()` and `_loadAnalyses()` exist and are
dispatched from `_setStudyTab`.

- [ ] **Step 1:** In the tab strip, move the `simulate` pillar button from the `evidence`
  cluster into the `design` cluster (after `readouts`). Add `results` and `analyses` pillar
  buttons to the `evidence` cluster (order: Results, Analyses, Visualizations).
- [ ] **Step 2:** Add `<section class="study-tab-panel" data-kind="results" id="panel-results" hidden>`
  and `<section ... data-kind="analyses" id="panel-analyses" hidden>`. Relocate the "Analysis
  result files" markup out of the `simulate` panel into `panel-analyses`; relocate the "Raw
  simulation data" downloads out of `simulate` into `panel-results` (downloads only this slice —
  per-store preview is Task 4).
- [ ] **Step 3:** In `study-detail.js`, rename/relocate `_loadAnalysisOutputs` → `_loadAnalyses`
  (targets `#panel-analyses`), add a minimal `_loadResults()` (raw-data download list targeting
  `#panel-results`), and dispatch both from `_setStudyTab` (`if (kind==='analyses')…`, `if
  (kind==='results')…`). Keep the per-run "⬇ Data" link in the simulate table.
- [ ] **Step 4:** Update `tests/test_study_detail_render.py`: assert `simulate` is under
  `data-act="design"`; assert `panel-results` + `panel-analyses` exist under `evidence`; assert
  Visualizations still present. Run `pytest tests/test_study_detail_render.py -q` → PASS.
- [ ] **Step 5:** `pytest -q` (esp. `test_no_ai_deps.py`, `test_fastapi_route_gaps.py`) → PASS. Commit.

---

### Task 2: Readouts rebuild (Slice 2, workbench)

**Files:**
- Modify: `vivarium_workbench/lib/readouts_views.py` (`build_study_readouts`)
- Modify: `vivarium_workbench/templates/study-detail.html` (readouts panel `:1057`)
- Modify: `vivarium_workbench/static/study-detail.js` (`_loadReadouts`, `_renderReadoutsTable`)
- Test: `tests/test_readouts_views.py` (new)

**Interfaces consumed:** `lib/observables_views.build_observables` (leaf paths), `lib/emitters.py`
(`default_emitter`, `label_for_run`, `output_kind`).
**Interfaces produced:** `/api/study-readouts` payload gains `emitter: {name, module, interval,
buffer, output_dir, scope}` and per-path `dtype/shape/units/bytes`.

- [ ] **Step 1:** Write failing `tests/test_readouts_views.py`: `build_study_readouts` returns a
  payload with an `emitter` block (name/module) and rows carrying `shape` + `dtype`, against a
  fixture study. Run → FAIL.
- [ ] **Step 2:** Extend `build_study_readouts`: add the `emitter` block from `lib/emitters.py`
  (+ workspace/study `runtime.default_emitter`), and per-path `dtype`/`shape` (`(n_steps,)` from
  run/spec) / `units` (authored) / `bytes` (best-effort, omit if unknown). Preserve the existing
  soft-degrade (unbuilt → authored-only rows) but always emit the `emitter` block.
- [ ] **Step 3:** Rebuild the Readouts panel + `_renderReadoutsTable` into three blocks — Emitter
  & config, Emitted paths, Outputs & shapes (per the mockup / spec §3.1).
- [ ] **Step 4:** `pytest tests/test_readouts_views.py -q` → PASS; extend
  `test_study_detail_render.py` for the three readouts blocks.
- [ ] **Step 5:** `pytest -q` → PASS. Commit.

---

### Task 3: Assurance trio — Audit + Build panels (Slice 4, workbench)

**Files:**
- Create: `vivarium_workbench/lib/audit_panel_views.py`, `vivarium_workbench/lib/loop_provenance_views.py`
- Modify: `vivarium_workbench/api/app.py` (2 thin routes)
- Modify: `vivarium_workbench/templates/study-detail.html` (assurance cluster; tests panel `:1161`)
- Modify: `vivarium_workbench/static/study-detail.js` (`_loadAudit`, `_loadBuild`)
- Test: `tests/test_audit_panel_views.py`, `tests/test_loop_provenance_views.py` (new)

**Interfaces consumed:** `lib/report_card_section.render_report_cards_section` (renders ALL
cards under `<study>/viz/report_card/`); `viva_superpowers.test_audit.build_audit_report`/
`audit_gate`; `viva_superpowers.loop_state` (load `.pbg/loop/<study>.json`); existing
`/api/study-rigor`, `/api/study-audit`.
**Interfaces produced:** `GET /api/study-test-audit?study=` → `build_study_test_audit`;
`GET /api/study-loop-state?study=` → `build_study_loop_state`; panels `panel-audit`, `panel-build`.

**REQUIREMENT (user, this turn): the Tests panel must show the COMPLETE set of the study's
report cards** — every v2ecoli / `TEST_REGISTRY` card present under `viz/report_card/`, each with
its `verdict.json` (overall + per-axis). Splitting rigor/repro out to Audit must NOT drop any
report card from Tests. A report card GRADES (carries a verdict) → Tests; an analysis DERIVES
(artifact, no verdict) → Evidence › Analyses. That verdict-vs-artifact line is the Tests/Analyses boundary.

- [ ] **Step 1:** Write failing `tests/test_audit_panel_views.py`
  (`build_study_test_audit(ws,slug)` returns sufficiency axes + gate from `test_audit`) and
  `tests/test_loop_provenance_views.py` (`build_study_loop_state` returns locked hash + reopen
  trail when a loop file exists; graceful `{present: false}` when absent). Run → FAIL.
- [ ] **Step 2:** Implement `lib/audit_panel_views.py` (imports `viva_superpowers.test_audit`) and
  `lib/loop_provenance_views.py` (imports `viva_superpowers.loop_state`), each `build_*(ws_root,
  slug) -> (dict, int)` with graceful empty states.
- [ ] **Step 3:** Add thin routes `/api/study-test-audit`, `/api/study-loop-state` in `api/app.py`.
- [ ] **Step 4:** Add `audit` + `build` pillars to the `assurance` cluster and `panel-audit` /
  `panel-build` sections. Move rigor-scorecard + L0–L5 rendering OUT of the tests panel into
  `panel-audit`; the sufficiency axes render above them. **Keep the FULL report-card rendering in
  the Tests panel** (`render_report_cards_section` / `report_card_urls` — every card, not a
  subset). Add `_loadAudit`/`_loadBuild` + dispatch from `_setStudyTab`. Build panel graceful
  empty state when no loop file.
- [ ] **Step 5:** Extend `tests/test_study_detail_render.py`: assert the Tests panel renders every
  report card from a multi-card fixture (none dropped) and that rigor/repro moved to `panel-audit`.
  `pytest -q` (incl. new tests + `test_no_ai_deps.py`) → PASS. Commit.

---

### Task 4: Results preview enrichment (Slice 3, workbench)

**Files:**
- Create: `vivarium_workbench/lib/results_views.py`
- Modify: `vivarium_workbench/api/app.py` (1 thin route)
- Modify: `vivarium_workbench/templates/study-detail.html` (results panel), `static/study-detail.js` (`_loadResults`)
- Test: `tests/test_results_views.py` (new)

**Interfaces consumed:** `lib/composite_run_views.build_composite_run` (trajectory),
`lib/simulations_index`/`run_index` (latest run + `store_path`), existing
`/api/simulation-run-download`.
**Interfaces produced:** `GET /api/study-results?study=` → `build_study_results(ws_root, slug)`
returning per-store `{path, dtype, first, last, min, max, sparkline:[…]}` + download refs.

- [ ] **Step 1:** Write failing `tests/test_results_views.py`: `build_study_results` returns
  per-store preview stats + a downsampled `sparkline` for a fixture study with a run; graceful
  empty when no run. Run → FAIL.
- [ ] **Step 2:** Implement `lib/results_views.py::build_study_results` (resolve latest run →
  read store → per-store first/last/min/max + downsampled sparkline). Preview only; full arrays
  stay in downloads.
- [ ] **Step 3:** Add `/api/study-results` route; upgrade the Results panel + `_loadResults` from
  downloads-only (Task 1) to preview table + per-store download + download-all.
- [ ] **Step 4:** `pytest tests/test_results_views.py -q` → PASS; extend render test.
- [ ] **Step 5:** `pytest -q` → PASS. Commit.

---

### Task 5: Skill + docs propagation (Slice 5, superpowers)

**Files (in `~/code/viva-superpowers--study-spine-reorg`):**
- Modify: `docs/concepts/vivarium-workbench-model.md` (skill↔concept map + tab/sticky-nav ordering `:265-269`)
- Modify: `skills/viva-study/SKILL.md`, `skills/viva-viz/SKILL.md`, `skills/viva-report/SKILL.md`,
  `skills/viva-navigate/SKILL.md`, `skills/viva-audit-tests/SKILL.md`, `skills/viva-model-build/SKILL.md`
  (prose only, where they name tabs)
- Test: `tests/` (`pytest -q`, `test_skill_conventions.py`, `test_skill_manifests.py`)

**Interfaces produced:** docs describe the target spine; SKILL.md prose references correct tabs
+ notes each skill's panel surface (Readouts/Analyses/Audit/Build). No new skills.

- [ ] **Step 1:** Update `docs/concepts/vivarium-workbench-model.md`: the skill↔concept map + the
  sticky-nav/tab ordering to Design(Model·Readouts·Simulations) → Evidence(Results·Analyses·
  Visualizations) → Assurance(Tests·Audit·Build); document Readouts = emitter+config+paths+shapes.
- [ ] **Step 2:** Prose fixes in the six SKILL.md files where they name tabs; add a one-line
  "surfaces in …" note (viva-study→Readouts/Results; viva-viz→Analyses; viva-audit-tests→Audit;
  viva-model-build→Build). Do NOT change any `description:` front-matter (keeps `test_skill_conventions`).
- [ ] **Step 3:** `pytest -q` → PASS (skill guards unchanged-green). Verify no count-string edits
  were needed (no skills added/renamed). Commit.

---

### Task 6: Model panel — full composite cards with semantic detail (workbench)

**Requirement (user, this turn):** the Model tab must show the study's ACTUAL composite(s) as the
same rich cards the Modules/Composites view uses, with **full Semantic detail ON** (inputs/outputs
ports + types + contract + full config schema — the "Full"/loom zoom level).

**Files:**
- Modify: `vivarium_workbench/templates/study-detail.html` (compose panel `:656`)
- Modify: `vivarium_workbench/static/study-detail.js` (Model loader)
- Likely add: a shared JS module (e.g. `vivarium_workbench/static/composite-card.js`) extracting
  `_renderCompositeCardFull`/`_renderCompositeCardGrid` + helpers from `static/walkthrough.js`
  so BOTH the Modules page and the study Model panel render identical cards (DRY — don't fork the
  renderer). If study-detail already loads walkthrough.js, reuse directly instead.
- Test: `tests/test_study_detail_render.py` (+ `tests/js/` if present)

**Interfaces consumed:** `/api/composite-resolve` (ports/inputs/outputs/schema/interface per
composite — `lib/composite_resolve.py`), `/api/composites` (`lib/composites_query.py`);
existing `_renderCompositeCardFull(c)` + `window._registryZoom='full'` semantic-detail state in
`static/walkthrough.js`.
**Interfaces produced:** the Model (compose) panel renders one Full composite card per study
composite (baseline + variants), semantic detail on by default, keeping the existing "🧬 explore &
run ↗" loom action.

- [ ] **Step 1:** Extract the composite-card renderer(s) (`_renderCompositeCardFull`,
  `_renderCompositeCardGrid`, `_regPortColumn`, and their direct helpers) from `walkthrough.js`
  into a shared `static/composite-card.js`; include it on both the Modules page and study-detail.
  Verify the Modules view still renders identically (no regression).
- [ ] **Step 2:** In the compose panel, replace the bare composite name + explore button with a
  `#model-composite-cards` mount; add `_loadModelCards()` to study-detail.js that fetches
  `/api/composite-resolve` for each study composite and renders a Full card (semantic detail on).
  Dispatch from `_setStudyTab('compose')`. Keep the notebook + explore/run actions.
- [ ] **Step 3:** Graceful states: unbuilt/unresolvable composite → the card's existing
  degraded render (not a 500); a study with no composite → a clear empty note.
- [ ] **Step 4:** Extend `test_study_detail_render.py` (Model panel mounts composite cards);
  run any `tests/js/` card tests. `pytest -q` → PASS. Commit.

---

## Self-Review
- **Spec coverage:** Task 1 = spine reorg §3.2/3.3/3.4; Task 2 = Readouts §3.1; Task 3 = Assurance
  §3.6/3.7/3.8; Task 4 = Results §3.3; Task 5 = propagation §4. All spec sections mapped.
- **Placeholders:** none — each task names exact files, interfaces, and test targets; full
  per-panel detail is in the referenced spec.
- **Type consistency:** every new worker is `build_*(ws_root, slug) -> (dict, int)`; panels use
  `data-kind` = `results/analyses/audit/build`; routes `/api/study-{results,test-audit,loop-state}`.
- **Sequencing:** Tasks 1–4 share `study-detail.html`/`.js` → strictly sequential. Task 5 is the
  other repo (independent) but kept last for a coherent final review.
