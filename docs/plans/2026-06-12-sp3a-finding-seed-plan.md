# SP3a — finding → next-study seeding (unify the seed paths) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 1 / SP3 (reflexive loops), piece a. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** Make a finding's `next_action` actionable end-to-end — a finding can seed (originate) a child study from the dashboard — by unifying the fragmented seed paths behind the single `seed_from_followup` mechanism, with the dashboard delegating to it (not reimplementing). Honors AI-free (deterministic seed math in pbg-superpowers; prose-refinement in the skill) + centralize-over-duplication.

**The disconnect (grounding):** FOUR followup field families (`finding.next_action`, `followup_proposals[]`, legacy `follow_up_studies[]`, `discovery_implications.followup_study_proposals[]`) and TWO disjoint seed paths — the CLI `seed_from_followup.py` (reads `followup_proposals`+`findings`, prints but doesn't write — the SKILL prose flow writes) and the dashboard `lib/study_seed.py` + `/api/study-seed-followup` (reads `follow_up_studies`/`discovery_implications.followup_study_proposals`, writes directly). `finding.next_action` is dashboard-unreachable, and even the CLI can't seed a finding STANDALONE (it requires a resolvable `followup_proposals[]` entry).

**Tech:** Python + JS; pytest. Repos: pbg-superpowers (the shared mechanism) + vivarium-workbench (the API + button). `.venv/bin/python`.

**Anchors:** `seed_from_followup.py` `build_child_seed_from_finding`(:312), `apply_from_finding`(:423), `find_proposal`(:173), the `ChildSeed`/`seeded_from` machinery (:83-123); dashboard `lib/study_seed.py` `seed_followup_study`(:64) + `_post_study_seed_followup` (server.py:12555) + button `_seedFollowupStudy` (study-detail.js:150) + the "Next" row (study-detail.js:1191-1207).

---

## Task 1: Standalone finding-seed in `seed_from_followup` (pbg-superpowers)

**Files:** Modify `viva_superpowers/seed_from_followup.py`; Test `tests/test_seed_from_followup.py`.

- [ ] **Step 1: Failing test.** A finding with a `next_action` can seed a child study WITHOUT a pre-existing `followup_proposals[]` entry:
```python
def test_seed_standalone_from_finding(tmp_study_with_finding_next_action):
    # study has findings[0] = {id: F-01, statement, next_action: "test X under Y", evidence:{...}}, NO followup_proposals
    from viva_superpowers.seed_from_followup import resolve_seed_source, build_child_seed_from_finding
    src = resolve_seed_source(study_spec, finding_id="F-01")   # synthesizes an inline proposal stub
    seed = build_child_seed_from_finding(study_spec, "F-01", src.proposal)
    assert seed.seeded_from.get("finding") == "F-01"
    assert seed.purpose.get("question")    # derived from the finding's next_action/statement
def test_resolve_seed_source_covers_all_families(...):
    # finding_id / proposal_id / followup_idx each resolve to a SeedSource
    assert resolve_seed_source(spec, proposal_id="p1").proposal
    assert resolve_seed_source(spec, followup_idx=0)   # legacy family
```
- [ ] **Step 2: fail. Step 3: implement** `resolve_seed_source(study_spec, *, finding_id=None, proposal_id=None, followup_idx=None) -> SeedSource` that normalizes ALL four families into one `SeedSource{proposal, finding_id?}`; when `finding_id` is given and no `proposal_id`, SYNTHESIZE an inline proposal stub (id derived from the finding) so the finding seeds standalone (stamping `seeded_from.finding` without a pre-existing `followup_proposals[]` row). `build_child_seed_from_finding` already maps a finding → ChildSeed — make `apply_from_finding`/the resolver accept the synthesized stub. Derive `purpose.question`/`expected_outcome` from the finding's `next_action`+`statement` via the existing conservative heuristics (meant to be skill-refined).
- [ ] **Step 4: pass. Step 5: commit** — `feat(seed-from-followup): resolve_seed_source unifies the 4 families + standalone finding seeding`

## Task 2: `write_child_study` — a callable atomic writer (pbg-superpowers)

**Files:** `viva_superpowers/seed_from_followup.py`; Test `tests/test_seed_from_followup.py`.

- [ ] **Step 1: Failing test** — `write_child_study` creates the child study.yaml + the parent stamp atomically (lifting the SKILL prose-flow writes into Python):
```python
def test_write_child_study_creates_child_and_stamps_parent(tmp_workspace):
    from viva_superpowers.seed_from_followup import resolve_seed_source, write_child_study
    src = resolve_seed_source(parent_spec, finding_id="F-01")
    res = write_child_study(ws, parent_slug, src, new_slug="child-01")
    assert (ws_studies / "child-01" / "study.yaml").is_file()       # child created
    parent = _read(parent_study_yaml); 
    # the finding/proposal is stamped seeded (seeded_study / status) — not duplicated
    assert res["new_slug"] == "child-01"
```
- [ ] **Step 2: fail. Step 3: implement** `write_child_study(ws_root, parent_slug, seed_source, *, new_slug=None) -> dict`: build the child seed (reuse `build_child_seed_from_finding`/the proposal path), write `studies/<new_slug>/study.yaml` via the atomic `study_io` writer, stamp the parent (the finding's `seeded_study`/the proposal's `status: seeded`) via ruamel round-trip — the writes the SKILL prose flow currently does, now callable. Reuse the dashboard's investigation back-link convention if present (or leave to the API). Idempotent on the parent stamp (fill-absent).
- [ ] **Step 4: pass. Step 5: commit** — `feat(seed-from-followup): write_child_study — callable atomic child-write + parent stamp`

## Task 3: Dashboard delegates + the finding-seed button (vivarium-workbench)

**Files:** (vivarium-workbench, branch `feat/sp3a-finding-seed-dashboard` off origin/main) `vivarium_workbench/lib/study_seed.py`, `server.py` (`_post_study_seed_followup` ~12555), `static/study-detail.js` (the Next row ~1191 + the button). Use vivarium-workbench's `.venv`.

- [ ] **Step 1: Failing test** — `/api/study-seed-followup` accepts `{parent, finding_id}` and seeds via the shared pbg helper.
```python
def test_seed_followup_accepts_finding_id(tmp_v2ecoli_study_with_finding):
    body, code = server.Handler._post_study_seed_followup_test({"parent": parent, "finding_id": "F-01"})
    assert code == 200 and (studies_dir / body["new_slug"] / "study.yaml").is_file()
```
- [ ] **Step 2: fail. Step 3: implement.** Extend `_post_study_seed_followup` to accept `{parent, finding_id}` (in addition to the existing `followup_idx`/`proposal_id`) and route through the new pbg `resolve_seed_source` + `write_child_study` (lazy import, tolerant). Make `lib/study_seed.py` DELEGATE to the pbg mechanism (don't reimplement — per centralize-over-duplication); keep its investigation back-link. Add a "Seed study from this finding" button on the study-detail "Next" row (study-detail.js:1204-1207) for any finding with a `next_action`, POSTing `{parent, finding_id}`.
- [ ] **Step 4: pass. Step 5: commit** — `feat(server): /api/study-seed-followup accepts finding_id (delegates to pbg seed mechanism) + Seed-from-finding button`

## Task 4: Golden + lineage render + manual

**Files:** Test (pbg-superpowers + dashboard).

- [ ] **Step 1 (golden, skipif v2e-invest absent, READ-ONLY → tmp copy):** a real study with a finding `next_action` → `resolve_seed_source(..., finding_id=...)` + `write_child_study` to a TMP copy produces a child + stamps the parent; the real v2e-invest untouched.
- [ ] **Step 2 (lineage render, cheap):** in the report (walkthrough.js) render the finding→seeded-study lineage from the existing `seeded_from.finding`/`seeded_study` stamps (a small "→ seeded study X" link on a finding) so the loop is visible. Structural test.
- [ ] **Step 3:** the new tests green; the suites no new failures (pre-existing verified via base). **MANUAL VERIFY (pending — no JS harness):** serve v2e-invest; a finding with a next_action shows a "Seed study from this finding" button; clicking creates a child + stamps the parent; the lineage shows in the report.
- [ ] **Step 4: commit** — `test(seed): finding-seed golden + lineage render`

---

## Self-Review
- Coverage: standalone finding seed + the unifying resolver (T1), callable writer (T2), dashboard delegation + button (T3), golden+lineage (T4). Matches SP3a.
- AI-free: the seed/merge math + write are deterministic in pbg-superpowers; the dashboard delegates + renders; the skill refines the derived question prose. No second seed implementation.
- The apply target (`findings[].next_action` → a seeded study) is exactly SP3b's `kind: next_action` write path — the loops join here.
- Rendering structural-tested + manual (no JS harness).

## Notes for the executor
- `.venv/bin/python -m pytest`. REUSE `build_child_seed_from_finding`/the `ChildSeed`/`seeded_from` machinery + `study_io` atomic writes — do NOT add a 3rd seed implementation; the dashboard DELEGATES to pbg.
- The derived `purpose.question`/`expected_outcome` heuristics are conservative + skill-refined — keep them conservative.
- Don't modify the real v2e-invest; goldens use a tmp copy.
