# Biology-forward results (spine stage #5) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Bring the quantitative biology forward into the structured finding slots the report renderer ALREADY draws — `evidence.observed`, `expected.range`/`cites`, `provenance.run_ids`, divergence — by filling them deterministically from the data that now exists (computed_outcomes + band provenance + readouts + canonical run), so the science renders as structured data instead of trapped prose. The mechanism narrative stays authored, guided by a skill. Two parts: a deterministic writer (pbg-superpowers, wired into sync, dashboard renders) + a biology-forward authoring skill (the only AI part).

**Architecture:** (a) `viva_superpowers/finding_observations.py`: `populate_finding_observations(study_dir) -> {filled, skipped}` — for each finding with a resolvable test link (`evidence.from_test`, or finding id/ref matching a test name), fill ONLY ABSENT code-owned sub-fields from that test's computed_outcome + band + readout units + canonical run; never touch authored prose; never fabricate (no test link → skip). Mirror `band_provenance`/`simulation_set` (ruamel comment-preserving, idempotent). (b) wire into `study_outcomes.sync` (4th best-effort, AFTER compute_outcomes so measured_value exists). (c) a `/pbg-biology-forward` skill that, after the numbers are filled, guides the agent to author the mechanism prose using the auto-filled observed-vs-band as scaffold.

**Tech:** Python 3.11+, ruamel.yaml, pytest. `.venv/bin/python`.

**Code-owned (auto, fill-absent-only):** `evidence.observed` (← `computed_outcomes[T].measured_value`), `evidence.units` (← matched readout units), `expected.range`/`expected.threshold` (← `band_provenance._band_from_pass_if(test.pass_if)`), `expected.cites` (← `test.cites`), `provenance.run_ids` (← `canonical_run(spec).name`), `evidence.divergence_factor` (arithmetic: measured vs band/literature_target), and the measured side of `calibration_anchor` (`observed_value`, `divergence_factor`).
**Authored (NEVER touch):** `statement`, `summary`, `explanation`, `status`, `kind`, `expected.summary`, `expert_reference`, `calibration_anchor.literature_target`, `next_action`.

---

## File map
- Create: `viva_superpowers/finding_observations.py`, `skills/pbg-biology-forward/SKILL.md`.
- Modify: `viva_superpowers/study_outcomes.py` (`sync` 4th step) + `pyproject.toml` (CLI) + skill catalog (`docs/skills.md`, manifest).
- Test: `tests/test_finding_observations.py`.

---

## Task 1: `populate_finding_observations` (deterministic, conservative)
- [ ] **Step 1: Failing tests** (study.yaml from RAW TEXT w/ comments) — a study with: a `tests[]` entry `T` (band `pass_if{low,high}`, `cites:[k]`); a canonical run whose `computed_outcomes.T.measured_value = 0.28`; a `readouts[]` with units for T's path; and a finding `F` with `evidence.from_test: T` but EMPTY `evidence.observed`/`expected`. After `populate_finding_observations(study_dir)`: F gains `evidence.observed: 0.28` (+ units), `expected.range: [low,high]` + `expected.cites:[k]`, `provenance.run_ids:[<canonical>]`, and a `divergence_factor`; F's authored `statement`/`summary`/`status` + ALL other findings + comments are byte-unchanged. A finding with NO `from_test` (run-anchored only) → SKIPPED (never fabricated). Idempotent (False/no-write on second call). Returns `{filled, skipped}`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — ruamel round-trip (mirror `band_provenance.set_band_provenance`); build a test index (name→test) with band via `_band_from_pass_if` + `cites`; read the canonical run's `computed_outcomes` (`study_outcomes.canonical_run`); for each finding resolve its test via `evidence.from_test` (skip if unresolvable); fill ONLY absent code-owned sub-fields; compute `divergence_factor` (measured vs band: if measured < low → `(low-measured)/low` style, or measured/literature_target when calibration_anchor present — pick one clear arithmetic + document it; guard div-by-zero); write only if changed. NEVER touch authored sub-fields.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(finding_observations): populate observed/expected/divergence from computed_outcomes`

## Task 2: Wire into sync + CLI + golden
- [ ] **Step 1: Failing test** — `study_outcomes.sync` calls `populate_finding_observations` best-effort (4th step, AFTER compute_outcomes; same try/except; `summary["findings"] = {filled, skipped}`). 
- [ ] **Step 2-4:** implement + a `pbg-populate-findings` CLI (mirror the others). 
- [ ] **Golden (skipif absent):** TMP COPY of a real dnaa study that has both `tests[]` with computed_outcomes-able bands AND findings — if a finding has `from_test`, assert its observed/expected get filled from the real computed outcome; assert authored finding prose + comments byte-preserved; v2e-invest untouched (`git -C ... status --porcelain` clean). If no real finding has a `from_test` link, document it and prove on the synthetic fixture. **Commit** — `feat(finding_observations): sync + CLI + golden`

## Task 3: `/pbg-biology-forward` skill (the AI authoring part)
- [ ] **Step 1:** `skills/pbg-biology-forward/SKILL.md` — front-matter (`name: pbg-biology-forward`, `user-invocable: true`, `allowed-tools: Bash(*) Read Edit`, `argument-hint: "<study-slug>"`). Body workflow:
  1. Run `populate_finding_observations` (fills the numbers) — show the resulting observed-vs-band scaffold per finding.
  2. For each finding with filled numbers, the AGENT authors only the irreducible prose: the `statement` headline (the biological claim), `summary`/`explanation` (the mechanism — "what this means"), the scientific `status` call (confirms/partial/contradicts/novel given observed vs expected), and the `expected.summary` literature claim; select an `expert_reference.quote` from `expert_search.search_expert_docs` candidates.
  3. Guardrail: the numbers are code-owned (never hand-edit observed/expected — re-run populate); the interpretation is authored; never overstate beyond what the divergence supports; uncertain mechanism → mark `status: novel`/note, don't fabricate a literature match.
  - Reference the real helpers by name (`populate_finding_observations`, `search_expert_docs`); register in `docs/skills.md` + the skill-manifest test.
- [ ] **Step 2:** light test that the skill file exists w/ valid front-matter + referenced symbols import; full suite green. **Commit** — `feat(skill): pbg-biology-forward — author mechanism prose over auto-filled observations`

---

## Self-Review
- Goal: fill the structured finding slots from deterministic data (T1) → renderer lights up; wired into sync (T2); the mechanism prose authored via a skill (T3). The numbers are code-owned/never-fabricated; the science interpretation is the skill's.
- Constraint: deterministic writer = pbg-superpowers Python; dashboard/report renderer already draws the slots (no dashboard change needed); the AI is ONLY the skill.
- Never-clobber + never-fabricate: fill-absent-only; no `from_test` link → skip (don't guess which test a run-anchored finding measures); ruamel comment-preserving; idempotent.
- Types: `populate_finding_observations(study_dir)->{filled,skipped}`.

## Notes for executor
- `.venv/bin/python -m pytest`. Mirror `band_provenance.set_band_provenance` (ruamel, idempotent, never-fabricate) + the `study_outcomes.sync` best-effort wiring (as compute_outcomes/populate_simulation_set/write_gate_evaluator do).
- Inputs: `study_outcomes.canonical_run`/`canonical_outcomes`, `band_provenance._band_from_pass_if`, the per-run `computed_outcomes[test].measured_value` (study_evaluator), `readouts[].units`. Finding→test link = `evidence.from_test` (see `study_findings.existing_finding_tests`).
- The report renderer slots are `walkthrough.js _renderFinding` `evMain` (evidence.observed) / `expMain` (expected.range+cites) — already present; NO dashboard change required for the render.
- Don't modify real v2e-invest (tmp/inline). Pick ONE clear divergence_factor arithmetic and document it in the docstring.
