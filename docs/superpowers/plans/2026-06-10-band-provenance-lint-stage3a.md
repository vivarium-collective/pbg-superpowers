# Band provenance + lint (spine stage #3a) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Close the gap where expert-sourced acceptance BANDS (e.g. `Boesen 2024 [0.2, 0.5]`, `[300, 800]`) travel as PROSE in `readouts[].notes` / test `notes` with no machine link to a source. Make band provenance **structured** (cites on the band-bearing fields, which the schema mostly already supports) and **enforced** (a band→cites linter mirroring the existing finding→bib lint). All deterministic — pbg-superpowers lint + pbg-template schema; the dashboard already renders `cites` (its References section). NO AI here (3b is the agent skill).

**Architecture:** (a) pbg-template schema: add `cites` (bib-key array) to `readouts[]` and `tests[]` items (`behavior_tests[]` already has `cites` + `calibration_anchor.cites`). (b) pbg-superpowers `report_linter.py`: new checks mirroring `_check_finding_cites_unknown_bib_key` (report_linter.py:772) — a WARN when a numeric-band test has no `cites`, and an ERROR when any `cites` on tests/behavior_tests/readouts references a bib_key absent from `references/papers.bib`. (c) a small helper `bands_missing_provenance(spec)` so 3b's skill + the report can target uncited bands.

**Tech:** Python 3.11+, pytest. `.venv/bin/python`. Known sets via `pbg_superpowers.bibtex.bib_keys(ws_root)`.

---

## File map
- Modify: `pbg-template/template/.pbg/schemas/study.schema.json` (add `cites` to `readouts[]` items ~672, `tests[]` items ~192 — additive).
- Modify: `pbg_superpowers/report_linter.py` (new `_check_*` functions; they auto-run via the existing check-collection mechanism — confirm how `_check_finding_cites_unknown_bib_key` gets invoked and follow it).
- Create: `pbg_superpowers/band_provenance.py` (the `bands_missing_provenance` helper) — or put it in report_linter if simpler.
- Test: `tests/test_band_provenance.py` (+ extend any report_linter test).

---

## Task 1: Schema — `cites` on readouts + tests (pbg-template, additive)
- [ ] **Step 1:** In `pbg-template/template/.pbg/schemas/study.schema.json`, add to `readouts[]` items and `tests[]` items: `"cites": {"type": "array", "items": {"type": "string"}, "description": "bib_keys (in references/papers.bib) sourcing this band/observable."}`. Keep `additionalProperties: true`. (behavior_tests already has `cites` at ~813 — leave it.)
- [ ] **Step 2:** A schema test (mirror pbg-template's existing readout/schema tests) asserting a readout/test WITH `cites` validates AND an existing real dnaa readout/test (no cites) still validates (back-compat). `python -m pytest -q` green. **Step 3: Commit** (pbg-template branch `feat/band-cites-schema`) — `feat(schema): cites on readouts + tests (band provenance)`.

## Task 2: Lint — band without cites (WARN)
- [ ] **Step 1: Failing test** (`tests/test_band_provenance.py`): build a `_LintContext`-style spec (read how report_linter tests construct ctx + ws_root with a `references/papers.bib`) with a `behavior_tests[]` AND a v4 `tests[]` entry each having a numeric band (`pass_if` with `low`/`high`, or `measure.kind` a band kind, or `calibration_anchor.literature_target`) but NO `cites` → the new check emits a `warning` ("band has no source citation; add cites: [bib_key] sourcing it"). A band test WITH a resolvable `cites` → no warning. Assert the `check=` name + level=warning + field_path.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `_check_band_test_missing_cites(ctx)` mirroring `_check_finding_cites_unknown_bib_key` (772): iterate `ctx.spec.get("behavior_tests")` + `ctx.spec.get("tests")`; a test "has a band" if `pass_if` has numeric `low`/`high`/`threshold` OR `calibration_anchor.literature_target` is set; if it has a band and (no `cites` or empty) → `ctx.add(level="warning", field_path=..., message=..., check="band_test_missing_cites")`. Ensure it's collected/run like the other `_check_*` (follow the existing registration).
- [ ] **Step 4: Run → pass.** **Step 5: Commit** (pbg-superpowers branch `feat/band-provenance-lint`) — `feat(report_linter): warn on numeric-band tests without cites`.

## Task 3: Lint — cites must resolve in papers.bib (ERROR) for tests/behavior_tests/readouts
- [ ] **Step 1: Failing test** — a `behavior_tests[]`/`tests[]`/`readouts[]` entry whose `cites: [unknownkey]` is not in `papers.bib` → an `error` ("cites unknown bib_key … Add it to references/papers.bib first."), mirroring the finding check; a resolvable cite → no error; no papers.bib → silent (like the finding check).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `_check_band_cites_unknown_bib_key(ctx)` — generalize `_check_finding_cites_unknown_bib_key` over `behavior_tests[].cites`, `tests[].cites`, `readouts[].cites` (and `calibration_anchor.cites`), each against `_bib_keys_for_workspace(ctx.ws_root)`; same silent-when-no-bib behavior.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(report_linter): error on tests/readouts cites with unknown bib_key`.

## Task 4: Helper + golden
- [ ] **Step 1: Failing test** — `bands_missing_provenance(spec) -> list[dict]` returns `{name, kind ("behavior_test"|"test"|"readout"), band, field_path}` for every band-bearing entry lacking a resolvable `cites`. Test on an inline spec mirroring real dnaa-2 (`tests[]` with `pass_if {low:0.2,high:0.5}` no cites; `readouts[]` with the prose "Boesen 2024" band in notes, no cites) → both returned.
- [ ] **Step 2-4:** implement (pure function; reuse the band-detection from Task 2) + pass + commit `feat(band_provenance): bands_missing_provenance helper`.
- [ ] **Golden (skipif absent):** point the linter/helper at a TMP COPY of real dnaa-2 study.yaml + its workspace papers.bib (read-only) and assert it flags the `[0.2,0.5]`/`[300,800]` bands as missing provenance (today they ARE uncited). NEVER modify v2e-invest.
- [ ] **Final:** full suite `.venv/bin/python -m pytest -q` green.

---

## Self-Review
- Goal: structured cites on bands (T1 schema) + enforced via lint (T2 warn-no-cites, T3 error-unknown-key) + targetable for 3b (T4 helper). Mirrors the proven finding→bib lint.
- Constraint honored: pure code (pbg-superpowers lint + pbg-template schema); dashboard already renders cites (no change, no AI).
- Back-compat: schema additive (existing uncited studies still validate; the lint emits WARNINGS for missing cites, ERRORS only for unknown keys — doesn't break existing reports). Silent when no papers.bib.
- Types: `bands_missing_provenance(spec)->list[dict]`; checks add via `ctx.add(level, field_path, message, check=)`.

## Notes for executor
- `.venv/bin/python -m pytest`. Read `report_linter.py:772-834` (the two finding checks) + how checks are collected/run (find where `_check_finding_cites_unknown_bib_key` is invoked — likely a registry of `_check_*` functions) and follow it exactly so the new checks run.
- `pbg_superpowers.bibtex.bib_keys(ws_root)` / `_bib_keys_for_workspace` is the known-key source.
- pbg-template schema = SEPARATE branch/commit (`feat/band-cites-schema`); run pbg-template `pytest`.
- Real dnaa studies READ-ONLY; golden uses tmp copies.
