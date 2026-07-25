# Band-citation extraction skill (spine stage #3b) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Facilitate the AI agent extracting study-design provenance from the expert documents — specifically, guide it to source the uncited acceptance BANDS (found by 3a's `bands_missing_provenance`) by surfacing candidate evidence (`expert_search`) and writing the structured provenance (`cites` + `calibration_anchor`) deterministically. This is the ONLY AI part of stage #3, and it lives entirely as a pbg-superpowers SKILL (per the dashboard-AI-free principle). The agent does the reading/judgment; code surfaces candidates + writes the closed schema + validates.

**Architecture:** (a) a deterministic write helper `band_provenance.set_band_provenance(study_dir, test_name, cites, calibration_anchor=None)` — ruamel comment-preserving write of `cites`/`calibration_anchor` onto a named `behavior_tests[]`/`tests[]` entry, never clobbering other fields (mirror `simulation_set._write_simset_preserving_comments`). (b) a user-invocable skill `skills/pbg-cite-bands/SKILL.md` orchestrating the loop: `bands_missing_provenance` → `search_expert_docs` → agent picks source+quote → `set_band_provenance` (or park unverified in `proposed_inputs`) → band→cites lint validates.

**Tech:** Python 3.11+, ruamel.yaml (helper); the skill is markdown. `.venv/bin/python`.

---

## File map
- Modify: `viva_superpowers/band_provenance.py` (add `set_band_provenance` + a `_write_*_preserving_comments` clone).
- Create: `skills/pbg-cite-bands/SKILL.md`.
- Test: `tests/test_set_band_provenance.py`.

---

## Task 1: `set_band_provenance` write helper (deterministic, comment-preserving)
- [ ] **Step 1: Failing tests** (load study.yaml from RAW TEXT with comments): given a study with a `tests[]`/`behavior_tests[]` entry named `T` (a band, no cites) + surrounding comments, `set_band_provenance(study_dir, "T", cites=["boesen2024"], calibration_anchor={"literature_target": 0.35, "cites": ["boesen2024"]})`:
  - sets `cites: [boesen2024]` and `calibration_anchor` on entry `T`;
  - leaves `T`'s `measure`/`pass_if`/`name` and ALL other entries untouched;
  - preserves comments byte-for-byte (only the targeted entry gains keys);
  - returns `True`; a second identical call returns `False` (idempotent, no write);
  - a non-existent test name → returns `False` (no write), never fabricates an entry;
  - merges into an existing `cites` list (dedup) rather than clobbering if one is present.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `set_band_provenance(study_dir, test_name, cites, calibration_anchor=None) -> bool` — ruamel round-trip (`YAML(); preserve_quotes=True; width=4096`), find the entry by `name` across `behavior_tests` then `tests`, set/merge `cites` (dedup, preserve order) + optionally `calibration_anchor`, write via `study_io.atomic_write` only if changed. Never touch other entries/keys.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(band_provenance): set_band_provenance comment-preserving write`

## Task 2: The `/pbg-cite-bands` skill (markdown)
- [ ] **Step 1:** Create `skills/pbg-cite-bands/SKILL.md` with front-matter (`name: pbg-cite-bands`, a clear `description`, `user-invocable: true`, `allowed-tools: Bash(*) Read Edit`, `argument-hint: "<study-slug>"`). Follow the existing skill style (see `skills/pbg-status/SKILL.md`, `skills/pbg-report/SKILL.md`).
- [ ] **Step 2:** The skill body documents the workflow precisely:
  1. **Preconditions:** a pbg workspace + the named study; `references/papers.bib` exists (the bib source).
  2. **Find uncited bands:** `.venv/bin/python -c "import json; from viva_superpowers.band_provenance import bands_missing_provenance; from viva_superpowers.study_io import load_yaml_mapping; print(json.dumps(bands_missing_provenance(load_yaml_mapping('<study_dir>/study.yaml'))))"` → the list of `{name, kind, band, field_path}`.
  3. **Surface candidate evidence per band:** `viva_superpowers.expert_search.search_expert_docs(ws_root, terms=[...band/readout name + numeric bounds + domain terms...])` → `[{doc, page, snippet, term}]`. Show the candidates to the user.
  4. **Agent judgment (the AI step):** read the candidate snippets (and, if needed, the cited PDF page) and choose the source — the bib_key in `references/papers.bib` and a verbatim quote — that establishes the band. If the source is NOT already in `papers.bib`, instruct the user to add the BibTeX entry first (the band→cites lint requires it); if the agent is UNCERTAIN or the expert didn't provide the source, record it in `investigation.yaml proposed_inputs` (pending expert accept) instead of asserting it on the band. NEVER fabricate a citation.
  5. **Write provenance:** `viva_superpowers.band_provenance.set_band_provenance(study_dir, test_name, cites=[bib_key], calibration_anchor={"literature_target": <midpoint>, "cites": [bib_key]})`.
  6. **Validate:** run the report linter (or note that `band_test_missing_cites` should now be clear and `band_cites_unknown_bib_key` must not fire) to confirm the provenance resolves.
  - Emphasize: surface-and-let-the-human/agent-decide; never auto-assert an unverified citation; all writes go through `set_band_provenance` (comment-preserving), never hand-edited YAML.
- [ ] **Step 3:** If pbg-superpowers registers skills in a catalog/manifest (check `docs/skills.md`, `.claude-plugin/`), add `pbg-cite-bands` there. **Commit** — `feat(skill): pbg-cite-bands — guided band-provenance extraction`

## Task 3: Smoke + docs
- [ ] **Step 1:** A light test that the skill file exists with valid front-matter (mirror any existing skill-frontmatter test) and that the helper + `bands_missing_provenance` + `search_expert_docs` it references are importable. Add `pbg-cite-bands` to `docs/skills.md` if that catalog exists.
- [ ] **Step 2:** Full suite `.venv/bin/python -m pytest -q` green. **Step 3: Commit** — `docs+test: register pbg-cite-bands skill`

---

## Self-Review
- Goal: facilitate the agent sourcing bands from docs — candidate surfacing (`search_expert_docs`) + closed-schema write (`set_band_provenance`) + validation (3a lint). The AI judgment is the skill's; everything around it is deterministic.
- Constraint: the AI lives ONLY in the skill (pbg-superpowers); the write helper is plain Python; NO dashboard touch, NO dashboard AI.
- Never-fabricate: uncertain/expert-not-provided → `proposed_inputs` (pending), never a fabricated cite; `set_band_provenance` never creates a non-existent test.
- Types: `set_band_provenance(study_dir, test_name, cites, calibration_anchor=None) -> bool`.

## Notes for executor
- `.venv/bin/python -m pytest`. Mirror `simulation_set._write_simset_preserving_comments` / `study_outcomes._write_runs_preserving_comments` for the ruamel write.
- Reuse merged 3a (`band_provenance.bands_missing_provenance`) + `expert_search.search_expert_docs(ws_root, terms, max_hits)`.
- Skill conventions: kebab-case `skills/<name>/SKILL.md`, YAML front-matter, `user-invocable: true`. The skill is MARKDOWN guidance for the agent, not code.
- Don't modify real v2e-invest; helper tests use tmp copies / inline text.
