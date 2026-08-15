# Tests as Agent Feedback — Design

**Status:** Design (approved in brainstorming 2026-08-15)
**Owner:** viva-superpowers (with v2ecoli + vivarium-workbench adopters)
**Related:** `2026-08-08-unified-behavior-tests-report-card.md`;
`project_report_cards_and_analysis_flush`; the post-sim Step family
(`viva_superpowers.post_sim`, shipped in viva-superpowers #254).

## 1. Motivation

A study's **report card is the compiled test result** — grading a finished run
against expectations. We want the study to be a **hardened unit of agent-driven
model building**: an agent edits the model, rebuilds, runs the study, and reads
the test results as a **feedback signal — a gradient, not a boolean** — to drive
the next edit.

Crucially, a rich grading system **already exists** and the workbench frontend +
publish + audit already depend on its on-disk/JSON shapes. This design does **not**
introduce a parallel contract. It **strengthens and streamlines the existing
infrastructure** in the planned direction:

- **Rename** the abstraction to what it is — `Test` — where it is still called
  `ReportCard` in Python (the UI already calls it "Tests").
- **Strengthen** the existing graded axis with agent-gradient fields (a signed
  `margin`/distance-to-pass, `severity`, `knob`, `citation`).
- **Streamline** the two near-verbatim duplicated card/flush stacks (v2ecoli's and
  viva_superpowers') onto one shared home, and centralize the verdict vocabulary
  that is currently defined in ~4 places.
- **Add** the genuinely new pieces: a cross-iteration **diff** and a **`/viva-tests`
  skill** to author/enrich/run tests.

## 2. What already exists (grounding — do not reinvent)

From the infrastructure map (2026-08-15):

- **The graded contract already IS a typed test result.**
  `v2ecoli/library/report_card.py::grade_card` + `verdict_json` produce the
  `report_card_verdict/v1` schema:
  `{schema, model_ref, reference_model, generated, overall,
  groups:{gslug:{verdict, axes:[{id, label, verdict, value, meter, detail}]}}}`.
  Each **axis is a check** already carrying a stable `id`, a per-axis `verdict`, a
  measured `value`, a normalized `meter` (0..1 display distance), and `detail`,
  graded against a reference with tolerance.
- **`overall` is sacrosanct**, vocabulary `{within_tol, drift, mismatch, ungraded}`
  (`report_card.py:21`). Everything keys on it: `study_spec` loader,
  `saved_visualizations`, `composite_flush.rollup_run_verdict`,
  `study_audit._check_report_card_verdict`, publish.
- **Four coexisting verdict schemas**, each keyed on `overall`:
  `report_card_verdict/v1` (graded), `behavior_test_card/v1`, `conclusion_card/v1`,
  `run_verdict/v1` (per-run rollup of cards).
- **The bases are duplicated.** `viva_superpowers/post_sim.py` is a near-verbatim
  lift of `v2ecoli/workflow/post_sim.py` + `report_cards/__init__.py`
  (`ReportCardStep`, `StudyContext`, `write_card`, `prune`, `applicable`). Drift
  risk; the streamline target is one home (viva_superpowers), v2ecoli re-imports.
- **"Modular tests" is already the merged UI concept.** `study.yaml` `tests:` spans
  `kind: behavioral | report_card`; Task 10 merged the "Report Cards" pillar into a
  single **"Tests"** panel. The `test_modular_tests_*` suite pins:
  `report_card_urls[card] = {url, verdict, groups, html_stub}` and
  `tests[].kind ∈ {behavioral, report_card}` with `card` as the FK.
- **Two flush orchestrators, same output.** v2ecoli `workflow/flush.py::run_flush`
  (re-run over a dir; honors `spec["report_cards"]` allowlist) and workbench
  `lib/composite_flush.py::run_flush` (post-run; env-worker analyses →
  `rollup_run_verdict`). Both write `viz/report_card/<card>.{html,verdict.json}`.
- **Gating is layered.** `study_audit.py` only checks *presence* of a truthy
  `overall` (soft L4, workbench-free). Value-level gating is
  `viva_superpowers.study_verdict.roll_up_verdict` / `computed_gate_verdict`.
- **HTML is part of the contract.** Cards carry
  `REPORT_CARD_MARKER = '<meta name="viv-artifact" content="report-card">'` and an
  `obadge` glyph span (`✓ ≈ ✗ –`) the loader parses as a verdict fallback.

## 3. Goals / Non-goals

**Goals**
- One shared home for the Test base + grading + vocabulary (viva_superpowers);
  v2ecoli's duplicated copies become thin re-exports (delete the drift).
- `ReportCardStep → TestStep` (+ `write_card → write_test`, `REPORT_CARD_REGISTRY →
  TEST_REGISTRY`) with **working deprecation-aliases** so no repo breaks on the
  same commit.
- **Extend the `report_card_verdict/v1` axis** (bump to `/v2`, back-compat readable)
  with `margin` (signed distance-to-pass), `severity` (`hard|soft|directional`),
  `knob` (list of influencing model params), `citation` (band/reference source).
- A `check(...)` helper that computes an axis's `verdict` + `margin` from
  `observed` + an `Expected` (value/band/predicate), so a graded axis is one call.
- **Centralize the verdict vocabulary** + the PASS/FAIL→canonical and canonical→
  four-value display mappings in one viva_superpowers module.
- **Cross-iteration `diff_reports(prev, curr)`** → `diff.json` (the iteration signal).
- The workflow-engine **Evaluate tail** as the canonical flush:
  `ResultsStep → {AnalysisStep, VisualizationStep, TestStep…} → TestReportStep`,
  where `TestReportStep` writes the run rollup + diff. Legacy flushes reuse the
  same helpers (one implementation of write/rollup/diff).
- `/viva-tests` skill: `author` / `enrich` / `run`.

**Non-goals (deferred, YAGNI)**
- A **knob recommender** (ranked next-action). The `knob` field is defined now;
  no recommender is built.
- Collapsing the two flush *triggers* into one entrypoint. We unify the *logic*
  (shared helpers) but leave v2ecoli's `run_flush` and workbench's
  `composite_flush.run_flush` as-is beyond re-pointing them at the shared home.
- Per-scale record slicing in `ResultsHandle`.
- Migrating the `overall` vocabulary itself (it stays `{within_tol, drift,
  mismatch, ungraded}` forever; the agent reads *through* it).

## 4. Global Constraints

- **`overall` and its vocabulary are immutable.** Every `.verdict.json` keeps a
  top-level `overall ∈ {within_tol, drift, mismatch, ungraded}` and its `schema`
  string. New fields are additive; `/v2` must be readable by every existing loader
  (which only reads `overall` + `groups`).
- **The typed contract lives in `viva_superpowers`/stdlib, never
  `vivarium_workbench`.** `study_audit.py` imports it and must stay workbench-free
  (it ships in the package v2ecoli CI imports).
- **Preserve the HTML contract:** `REPORT_CARD_MARKER` in `<head>` and the `obadge`
  glyph span in every rendered card (the loader's verdict fallback parses them).
- **Preserve the API contract:** `report_card_urls[card] = {url, verdict, groups,
  html_stub}` and `tests[].kind` — asserted by `test_modular_tests_payload/e2e`.
- **Preserve the two default synthesized cards' behavior:** `behavior-tests` and
  `conclusion` stay never-raise + idempotent; `conclusion` stays excluded from
  finding-derivation (feedback-loop guard).
- **JSON safety:** `_sanitize` (non-finite → `null`) + `allow_nan=False`.
- **Determinism:** aggregation/diff run as a Step in the DAG; timestamps/ids are
  passed in, never generated inside a Step (workflow engine `Date.now()`-free rule).
- **Preserve v2ecoli's `Analysis` live-`conn` surface** when unifying (a prior
  collapse broke ~30 subclasses — see the `post_sim.py` docstring warning).

## 5. The strengthened axis contract (`report_card_verdict/v2`)

Extend the existing axis in `grade_card`/`verdict_json`. `/v2` is `/v1` **plus**
optional fields; loaders reading `/v1` see `/v2` unchanged (they only read
`overall` + `groups.*.verdict` + `axes.*.{id,label,verdict,value,meter,detail}`).

```
axis (v2) = {
  # --- v1, unchanged ---
  id: str            # STABLE — agents diff by (test, group, id); never positional
  label: str
  verdict: str       # within_tol | drift | mismatch | ungraded  (per-axis)
  value: float|str|None   # measured/observed
  meter: float|None  # 0..1 display normalization (unchanged)
  detail: str|None
  # --- v2, additive ---
  expected: {kind:"value"|"band"|"predicate", value?, low?, high?, op?, tol?, statement?}
  margin: float|None      # signed distance-to-pass in the axis's own units: >=0 pass, <0 fail
  severity: str           # "hard" | "soft" | "directional"  (default "hard")
  units: str|None
  knob: [str]|None        # model params / wiring most influencing this axis (hint; no recommender)
  citation: str|None      # reference / acceptance-band source grounding `expected`
}
```

`verdict ↔ agent semantics`: `within_tol = pass`, `mismatch = fail`,
`drift = warn/directional`, `ungraded = no-data`. So the agent reads `verdict`
(discrete) **and** `margin` (gradient) together — no new top-level `status` field
that would fight `overall`.

### 5.1 The `check(...)` helper (`viva_superpowers/test_contract.py`)

Pure data + stdlib, importable anywhere (audit, skill, agent):

```python
def value(target, op="~=", tol=0.05) -> Expected
def band(low, high) -> Expected
def predicate(statement) -> Expected

def check(id, label, observed, expected, *, severity="hard",
          units=None, knob=None, cite=None, detail=None) -> dict   # a v2 axis
```

`check` computes `margin` and `verdict`:
- **band**: `margin = min(observed-low, high-observed)`; `within_tol` iff `>=0` else `mismatch`.
- **value `~=` (rel tol t)**: `margin = t*|target| - |observed-target|`; `within_tol` iff `>=0`.
- **value comparison op** (`<=,>=,<,>,==`): `margin` = signed slack to the boundary.
- **predicate / non-numeric observed**: `margin=None`; caller supplies `verdict=`.
- **directional**: never yields a gating `mismatch` (see §7); records `margin` for the diff.

A `TestBuilder` convenience groups axes into `groups` and calls the existing
`verdict_json(...)` so authors write `check(...)` calls and get a valid `/v2` doc.

## 6. Unify the bases (streamline)

- **`viva_superpowers` becomes the single home.** Move `grade_card`, `verdict_json`,
  the renderers (`render_html`, `render_markdown`, `render_verdict_html`), and the
  vocabulary out of `v2ecoli/library/report_card.py` into
  `viva_superpowers/report_card.py` (or `test_grading.py`). `v2ecoli/library/report_card.py`
  becomes a thin re-export (back-compat).
- **Rename in `viva_superpowers/post_sim.py`:** `ReportCardStep → TestStep`,
  `REPORT_CARD_REGISTRY → TEST_REGISTRY` (same dict), `write_card → write_test`,
  `register_post_sim` kind `"report_card" → "test"`. Every old name kept as a
  working alias; alias use emits `DeprecationWarning`. `iter_post_sim("report_card")`
  maps to `"test"`.
- **`TestStep` keeps the exact runtime contract** (`inputs {study}`,
  `outputs {view:string, data:tree}`, `applies` + `build(study) -> (verdict,html)`,
  guarded `invoke`). `build` MAY return a `/v2` doc (preferred) or the legacy
  `(dict, html)` tuple; `update()` normalizes both.
- **v2ecoli's duplicated `workflow/post_sim.py` + `report_cards/__init__.py`** become
  thin re-exports of the viva bases, **preserving `Analysis`'s live-`conn` surface**.
  The three v2ecoli cards (`tests`, `vs_literature`, `vs_vecoli`) keep subclassing
  (via alias) and now grade through the shared `grade_card`.
- **On-disk filenames unchanged** (`viz/report_card/<card>.{html,verdict.json}`);
  HTML still carries the marker + `obadge`.

## 7. Gating semantics (respect severity)

- `overall` (per verdict.json) stays **worst-verdict-for-display**, unchanged.
- The **gate** (`viva_superpowers.study_verdict.roll_up_verdict` /
  `computed_gate_verdict`) is extended to respect `severity`: only **hard** axes
  with `mismatch` fail the gate; `soft` axes are recorded, never gate;
  `directional` axes never gate (they feed the diff). Where an axis lacks
  `severity` (v1 docs), default `hard` — preserves current gate behavior.
- `study_audit` is unchanged (still soft-checks *presence* of a truthy `overall`).

## 8. Aggregation + cross-iteration diff

- **Aggregate** reuses/extends `run_verdict/v1` → `run_verdict/v2`:
  `{schema, overall, cards:[{name, overall}], counts:{cards, axes, within_tol,
  drift, mismatch, ungraded, hard_mismatch}}`. Written where `composite_flush`
  writes `run_dir/verdict.json` today; a study-level copy lands in
  `<study>/viz/tests/report.json`.
- **Diff (new)** `viva_superpowers/test_diff.py::diff_reports(prev, curr) ->
  {schema:"test_diff/v1", per:[{card, group, id, change, margin_delta}],
  rollup:{fixed, broke, improved, regressed, new, gone}}`, keyed by
  `(card, group, id)`. `change ∈ {unchanged, improved, regressed, fixed, broke,
  new, gone}` (`fixed`=mismatch→within_tol, `broke`=within_tol→mismatch,
  `improved/regressed`=same verdict, margin moved good/bad). Written to
  `<study>/viz/tests/diff.json`. **This is the artifact the agent reads to judge
  its last edit.**
- **`prev`** = the previous run's `report.json`, kept in a bounded
  `<study>/viz/tests/history/` ring the report step rotates.

## 9. Flush wiring (canonical = the workflow-engine Evaluate tail)

```
[emitter output] → ResultsStep → { AnalysisStep, VisualizationStep, TestStep… } → TestReportStep
```

- **`TestReportStep`** (new, in `post_sim.py`): collects the run's `TestStep` `data`
  outputs (wired in) + `StudyContext`, builds the `run_verdict/v2` aggregate, writes
  `report.json` (+ HTML index) via a shared `write_report(ctx, report)`, loads the
  previous `report.json` from `history/`, computes `diff_reports`, writes
  `diff.json`, rotates history, and emits `{report, diff, gate}` so the workflow
  bridge surfaces `report`/`diff` alongside the existing `verdict`.
- **Legacy flushes reuse the shared helpers.** v2ecoli `run_flush` and workbench
  `composite_flush.run_flush` keep their triggers but call the *same* `write_test`,
  `verdict_json`, `rollup`, and (new) `diff_reports` — so there is one
  implementation, two triggers.
- **v2ecoli `build.py`:** `SimGateCard(ReportCardStep) → SimGateTest(TestStep)`;
  `build` returns a `/v2` doc with a graded axis:
  `check("emitted_records", "Emitted records", observed=n_rows,
  expected=value(1, op=">="), severity="hard")`. Add the `TestReportStep` node.

## 10. Workbench consumption (render the new signal)

- `study_spec.load_study_detail_spec`: surface the `/v2` axis extras
  (`margin`, `severity`, `knob`, `citation`) in `report_card_urls[card].groups`
  (already passed through — just ensure they survive) and add
  `spec["test_diff"] = <diff.json>` when present.
- `study-detail.js` `_fillReportCardModules`: render per-axis `margin` (a signed
  bar / distance-to-pass) and, when a `diff` is present, badge each axis with its
  change (`fixed/broke/improved/regressed`) — the "since last run" signal in the
  unified **Tests** panel. `citation`/`knob` shown on hover/detail.
- `report_card_urls`, `tests[].kind`, the `data-test-kind`/`data-card`/
  `report-card-verdict` markup, and publish's iframe/base-path staging are
  **unchanged** (the `test_modular_tests_*` suite must stay green).

## 11. Centralize the vocabulary (`viva_superpowers/test_vocab.py`)

One module owns: the canonical verdicts (`within_tol/drift/mismatch/ungraded`) +
`_COLOR/_GLYPH/_RANK`; the `PASS/FAIL/PARTIAL/SKIP/PENDING/GAP → canonical`
aliases (today in `study_spec._VERDICT_ALIASES` + `behavior_test_card` +
`conclusion_card._RESULT_TO_CANON`); and the `canonical → four-value display`
(`met/conditional-pass/not met/not assessable`, today `study_page._OUTCOME_TOKEN_MAP`).
The three repos import from here; the scattered copies become re-exports. This is
the "streamline" that keeps the display join consistent.

## 12. `/viva-tests` skill (viva-superpowers plugin)

Thin client over the shared helpers + workbench API (AI-free/provenance
conventions of the other `/viva-*` skills):

- **`author <study> <name>`** — scaffold a `TestStep` subclass whose `build` opens
  the run via `ResultsHandle` (`.records()`/`.conn()`) and returns a `/v2` doc from
  `check(...)` calls; wire it into the study's Evaluate stage + `tests:` list
  (`kind: report_card`, `card: <name>`).
- **`enrich <study> <test>`** — read the test's `build()` + the study's
  observables/analyses and upgrade bare axes into graded ones: add
  `expected`/`margin`/`severity`, and `knob`/`citation` where the study's evidence
  (`viva-cite-bands`, acceptance bands) supports them. *This is the "add more
  signal so the model-building agent can improve its design" lever.* Proposes bands
  over magic numbers; asks for confirmation.
- **`run <study>`** — run the study's tests, return the `run_verdict/v2` report +
  `test_diff/v1` as the agent-consumable signal; point at `report.json`/`diff.json`.

### 12.1 Updates to the other `/viva-*` skills

The skills that already touch report cards / verdicts adopt the Test vocabulary and
consume the strengthened signal (a small, consistent pass, not a rewrite):

- **`/viva-study`** — its Evaluate stage now speaks "tests," calls the shared
  `check(...)`/grading, and at Decide surfaces the `run_verdict/v2` report + the
  `test_diff` (what moved since the last run) as the loop's feedback. This is where
  the hardened build-loop lives for a human-driven study.
- **`/viva-cite-bands`** — becomes the natural authoring path for a Test axis's
  `expected` **band** + `citation`: linking a reference to an acceptance band now
  writes directly into the axis (`band(low, high)` + `cite=…`), so `/viva-tests
  enrich` and `/viva-cite-bands` share one target.
- **`/viva-report`** — renders the strengthened axes (margin, change-since-last-run)
  and reads the centralized vocabulary instead of its own copy.
- **`/viva-navigate`** ("decisions needed") — its needs-attention ranking consumes
  `severity` + `margin` (hard mismatches and directional regressions rank first),
  and reads `test_diff` to flag "regressed since last run."
- **`/viva-harden-investigation`** — treats "every gating axis is graded with a
  cited band + a `knob`" as a hardening criterion it can check and drive.
- **`/viva-orient`** (skill map) + `docs/skills.md` — updated so "report card" reads
  "test," and `/viva-tests` appears in the Studies-&-runs group.

All of these import the vocabulary + contract from `viva_superpowers` (§11) — no
skill carries its own verdict vocabulary after this.

## 13. The hardened loop (documentation)

`docs/concepts` note + the skill:

```
edit model → rebuild → run study
     ↑                      │
     │       read viz/tests/report.json + diff.json
     │                      │
  next edit ← failing/low-margin HARD axes (+ their knobs),
              and DIRECTIONAL axes whose margin trends the wrong way
```

Convergence = gate `pass` with hard margins ≥ 0 and directional margins trending
up. The study dir (spec + tests + `report.json` + `diff.json` + `history/`) is the
inspectable, hardened unit.

## 14. Testing

- **Contract** (`viva_superpowers`): `check()` margin/verdict per `Expected` kind
  (band inside/edge/outside, value `~=`/comparison, predicate no-margin);
  severity-aware gate rollup (hard-mismatch gates, soft/directional never gate);
  `/v2` round-trips and is read unchanged by a `/v1` reader; `_sanitize` on
  non-finite margins.
- **Diff**: prev/curr exercising every `change` transition + `margin_delta` signs.
- **Rename/back-compat**: subclassing `ReportCardStep` lands in `TEST_REGISTRY`;
  `REPORT_CARD_REGISTRY is TEST_REGISTRY`; `write_card` warns + writes the same
  files; a legacy `(dict, html)` build still yields `{view, data}`; v2ecoli's three
  cards still grade via the moved `grade_card`.
- **Vocabulary**: the centralized aliases/severity maps reproduce today's
  `study_spec`/`study_page`/`conclusion_card` outputs (golden tests).
- **Workbench contract**: the full `test_modular_tests_{payload,render,js,e2e}`
  suite stays green; add cases asserting `margin`/`change` render in the Tests
  panel and `test_diff` surfaces on the study payload.
- **Integration**: `TestReportStep` over two toy tests writes `report.json` +
  `diff.json`, rotates `history/`, emits gate; `v2ecoli-workflow-run` end-to-end
  surfaces `verdict` + `report` + `diff`, with the gate axis graded (margin present).

## 15. Slices / scope

1. **viva_superpowers** (foundation): `test_vocab.py`, `test_contract.py`
   (`Expected`/`check`/`TestBuilder`), move grading+renderers+`report_card_verdict/v2`
   in, `post_sim.py` rename + aliases, `test_diff.py`, `TestReportStep`,
   severity-aware `study_verdict` rollup. All back-compat.
2. **v2ecoli** (adopt + de-dup): `report_card.py`/`workflow/post_sim.py`/
   `report_cards/__init__.py` → thin re-exports (preserve `Analysis`);
   `SimGateCard → SimGateTest` graded; wire `TestReportStep`; `run_flush` uses shared
   helpers.
3. **vivarium-workbench** (render the signal): surface `margin`/`severity`/`knob`/
   `citation` + `test_diff` in the Tests panel; `composite_flush` uses shared
   rollup/diff; keep the `test_modular_tests_*` contract green; centralize vocab
   imports.
4. **Skills**: new `/viva-tests` (`author`/`enrich`/`run`); the §12.1 pass over
   `/viva-study`, `/viva-cite-bands`, `/viva-report`, `/viva-navigate`,
   `/viva-harden-investigation`, `/viva-orient` + `docs/skills.md` (adopt shared
   vocab/contract, consume `margin`/`severity`/`diff`). Depends on slices 1–3.

Deferred: knob recommender; unifying the two flush triggers; per-scale slicing;
migrating the `overall` vocabulary.
