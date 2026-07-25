# SP2c — Expert-inputs → study citations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 1 / SP2c (the small reflexive-input loop). Spec/program: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** Close the "investigation references → member-study band citations" break. Today a study's acceptance bands often lack `cites` while the investigation collects references in `inputs.references` — but nothing connects them; the agent hand-matches. SP2c surfaces the gap deterministically (pbg-superpowers, dashboard-renderable) and the `/pbg-cite-bands` skill proposes+applies the pairings (the judgment stays in the skill — dashboard AI-free).

**Verified:** investigation `inputs.references` ARE workspace bib_keys (e.g. `dnaa-abundance-jb-1991`) that resolve in `references/papers.bib` (`bibtex.bib_keys`), so `set_band_provenance(study, test, cites=[bib_key])` works with them as-is — no cite-resolution work needed. Reuse `band_provenance.bands_missing_provenance` (uncited bands), `investigation_inputs.investigation_inputs` (the references), `band_provenance.set_band_provenance` (apply). `WorkspacePaths` for the nested layout.

**Tech:** Python, pytest. Repo: pbg-superpowers (the function + the skill); no dashboard code change in this MVP. `.venv/bin/python`.

---

## Task 1: `investigation_citation_gaps` (pure surface)

**Files:** Create `viva_superpowers/citation_gaps.py`; Test `tests/test_citation_gaps.py`.

- [ ] **Step 1: Failing tests.**
```python
from viva_superpowers.citation_gaps import investigation_citation_gaps

def test_gaps_surfaces_uncited_bands_x_investigation_refs(tmp_inv_with_uncited_band):
    # investigation has inputs.references: [ref-a, ref-b]; member study has a band with no cites
    gaps = investigation_citation_gaps(tmp_inv_with_uncited_band.ws, "the-inv")
    assert "the-study" in gaps
    g = gaps["the-study"]
    assert any(b["test"] == "the-uncited-band" for b in g["uncited_bands"])
    assert set(g["available_references"]) == {"ref-a", "ref-b"}

def test_no_gaps_when_all_bands_cited(tmp_inv_all_cited):
    gaps = investigation_citation_gaps(tmp_inv_all_cited.ws, "the-inv")
    assert all(not g["uncited_bands"] for g in gaps.values())

def test_empty_when_no_member_studies(tmp_empty_inv):
    assert investigation_citation_gaps(tmp_empty_inv.ws, "the-inv") == {}
```
- [ ] **Step 2: fail. Step 3: implement** `investigation_citation_gaps(ws_root, inv_slug) -> dict[study_slug, {"uncited_bands": [{test, observable?}], "available_references": [bib_key]}]`: resolve the investigation's member studies (via `WorkspacePaths`/the investigation.yaml `studies:`); `available_references` = `investigation_inputs(ws_root, inv_slug)["references"]` bib_keys (+ workspace-level refs if `repo_fallback`); per study, `uncited_bands` = `bands_missing_provenance(study_spec)`. Pure read — no writes. Best-effort per study (a bad study.yaml → skip, don't raise).
- [ ] **Step 4: pass. Step 5: commit** — `feat(citation-gaps): investigation_citation_gaps surfaces uncited bands x available investigation references`

## Task 2: CLI entry for the gaps (so the skill + future dashboard can call it)

**Files:** `viva_superpowers/citation_gaps.py` (a `main`), `pyproject.toml` (console script); Test `tests/test_citation_gaps.py`.

- [ ] **Step 1: Failing test** — `main(["--workspace", ws, "--investigation", "the-inv"])` prints JSON of the gaps (capture stdout, parse, assert the structure).
- [ ] **Step 2: fail. Step 3: implement** a `main(argv=None)` that prints `json.dumps(investigation_citation_gaps(...))`; add `pbg-citation-gaps = "viva_superpowers.citation_gaps:main"` to `pyproject.toml`.
- [ ] **Step 4: pass. Step 5: commit** — `feat(citation-gaps): pbg-citation-gaps CLI`

## Task 3: Extend `/pbg-cite-bands` skill to pull investigation references

**Files:** Modify `skills/pbg-cite-bands/SKILL.md` (instructions only — the AI judgment); Test: a structural assertion that the skill references the new function.

- [ ] **Step 1:** Add a section to `skills/pbg-cite-bands/SKILL.md`: when citing a study that belongs to an investigation, first run `investigation_citation_gaps` (or `pbg-citation-gaps`) to see the investigation's available references; for each uncited band, the agent PROPOSES the most topically-relevant investigation reference(s) as `cites` (the judgment — match the reference's subject to the band's observable), confirms with the user, and applies via `set_band_provenance(study_dir, test_name, cites=[bib_key])`. Keep the existing workspace-bib citing path; this ADDS the investigation-inputs pool as a first-class candidate source. Make clear: the agent never fabricates a citation — it only links references the investigation already declared.
- [ ] **Step 2:** Add `tests/test_cite_bands_skill_references_gaps.py` asserting `skills/pbg-cite-bands/SKILL.md` mentions `investigation_citation_gaps`/`pbg-citation-gaps` + `set_band_provenance` (so the wiring can't silently regress).
- [ ] **Step 3: Run → pass. Step 4: commit** — `feat(pbg-cite-bands): pull investigation references as band-citation candidates via investigation_citation_gaps`

## Task 4: Golden + suite

**Files:** Test `tests/test_citation_gaps.py` (skipif v2e-invest absent).

- [ ] **Step 1 (skipif `/Users/eranagmon/code/v2e-invest` absent, READ-ONLY):** `investigation_citation_gaps("/Users/eranagmon/code/v2e-invest", "dnaa-replication")` returns a dict keyed by its real member studies; `available_references` includes its real bib_keys (`dnaa-abundance-jb-1991` etc.); structure valid. No writes to v2e-invest.
- [ ] **Step 2:** `tests/test_citation_gaps.py tests/test_cite_bands_skill_references_gaps.py` green; full pbg-superpowers suite no new failures (pre-existing: expert_search cache, study_evaluator_golden). **Commit** — `test(citation-gaps): v2e-invest golden + suite`

---

## Self-Review
- Coverage: gap-surface (T1), CLI (T2), skill wiring (T3), golden (T4). Matches the focused references→band-citations scope.
- AI-free split honored: the deterministic surface + apply are pbg-superpowers; the reference↔band judgment is in the skill only.
- No placeholders: reuses `bands_missing_provenance`/`investigation_inputs`/`set_band_provenance`/`bib_keys`; investigation refs already resolve as bib_keys (verified).
- Deferred (noted, not built): a dashboard render of the citation gaps (a follow-up surfacing); conditions/model_change reference propagation (the broader scope not chosen).

## Notes for the executor
- `.venv/bin/python -m pytest`. REUSE the four existing functions; do not reimplement band/inputs/bib logic. Pure read in T1 (no writes). Best-effort per study.
- The skill change is INSTRUCTIONS (markdown) — the agent does the judgment; the only code is the surface + apply, both already deterministic.
- Don't modify the real v2e-invest; the golden is read-only.
