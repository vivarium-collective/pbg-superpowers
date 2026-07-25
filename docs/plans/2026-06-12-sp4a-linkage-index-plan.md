# SP4a — Linkage index (YAML-only) + cheap reverse queries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 2 (Navigate) / SP4, piece a. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** A derived, cached **linkage index** over the workspace YAML — the explicit knowledge graph (studies ↔ composites ↔ observables ↔ sources ↔ findings ↔ acceptance ↔ study-DAG) — exposing the cheap reverse queries that today require grep: **AC→study gating matrix + GAPS**, **source↔study**, **finding-by-observable**, and the **study-DAG**. Pure derive (no composite builds, no SP2b dependency); the index is EPHEMERAL (never written back to YAML). SP4b (observable-edge enrichment needing composite builds) is deferred.

**Surfaced live gap (motivation):** `chromosome-cycle-calibration` has 5 `acceptance_criteria` with NO `study:` link — the AC→study matrix flags exactly these.

**Tech:** Python + JS; pytest. Repos: pbg-superpowers (the index + queries + skill) + vivarium-workbench (the endpoint + the AC-matrix panel). `.venv/bin/python`.

**AI-free:** the index + queries are deterministic pbg-superpowers derives; the dashboard renders; the `/pbg-navigate` skill queries. No AI.

**Reuse (confirmed):** `WorkspacePaths`, `study_io.load_yaml_mapping`, `band_provenance.bands_missing_provenance`(:58), `investigation_inputs`(:12), `investigation_status.roll_up_acceptance`(:70)/`canonical_outcomes`. Edge anchors: study→composite (`study.yaml baseline[].composite`/`variants[].base_composite`), study→observables (`_collect_study_observables` shape), study→sources (study `cites[]` + band cites), investigation→source (`inputs.*` OR top-level `references`/`expert_docs` — NORMALIZE the split-shape), AC (`investigation.yaml acceptance_criteria[].{study,behavior}`), finding→test/run (`findings[].evidence.{from_test,from_run}`+`provenance.run_ids`), study-DAG (`pipeline_gate.{prerequisites,enables}[].study`).

---

## Task 1: `linkage_index.build_index` + reverse-query helpers (pbg-superpowers, pure)

**Files:** Create `viva_superpowers/linkage_index.py`; Test `tests/test_linkage_index.py`.

- [ ] **Step 1: Failing tests.**
```python
from viva_superpowers.linkage_index import (
    build_index, ac_gating_matrix, studies_for_source, findings_for_observable, study_dag)

def test_ac_gating_matrix_flags_unkeyed_criteria(tmp_inv_mixed_ac):
    # one AC has study: + result, one AC has NO study: (the gap)
    m = ac_gating_matrix(ws, "the-inv")
    assert any(r["covered_by"] for r in m["criteria"])          # keyed AC → a study + result
    assert any(r["gap"] is True and not r["covered_by"] for r in m["criteria"])  # unkeyed AC flagged

def test_studies_for_source_inverts_cites(tmp_ws_two_studies_cite_X):
    assert set(studies_for_source(ws, "bib-key-X")) == {"s1", "s2"}

def test_findings_for_observable(tmp_ws_finding_measures_obs):
    assert "F-01" in [f["finding"] for f in findings_for_observable(ws, "listeners.mass.cell_mass")]

def test_study_dag_edges(tmp_ws_dag):
    dag = study_dag(ws, "the-inv")   # nodes + prerequisite edges from pipeline_gate
    assert any(e["from"] and e["to"] for e in dag["edges"])

def test_build_index_pure_read(tmp_ws):
    before = _snapshot(tmp_ws); build_index(tmp_ws); assert _snapshot(tmp_ws) == before  # no writes
```
- [ ] **Step 2: fail. Step 3: implement** `build_index(ws_root) -> {nodes, edges}` (the typed node/edge dict from the grounding) as a PURE derive over the workspace YAML (`WorkspacePaths` + `study_io`); reuse `roll_up_acceptance`/`canonical_outcomes` for the AC results, `bands_missing_provenance`/the study `cites[]` for sources, `investigation_inputs` for the input pool. NORMALIZE the investigation→source split-shape (read both `inputs.references/datasets/expert_docs` AND top-level `references`/`expert_docs`). Then the reverse-query helpers as `edges`-by-target lookups: `ac_gating_matrix(ws, inv)` (per-criterion study→result, `gap: true` when no `study:` link), `studies_for_source(ws, key)`, `findings_for_observable(ws, token)` (via `evidence.from_test`→`measure.field`), `study_dag(ws, inv)` (nodes + prerequisite edges). Best-effort per study (bad yaml skipped). PURE — no writes.
- [ ] **Step 4: pass. Step 5: commit** — `feat(linkage-index): YAML-only knowledge-graph index + AC-matrix/source/finding/DAG reverse queries (pure)`

## Task 2: `GET /api/linkage-index` (vivarium-workbench)

**Files:** (vivarium-workbench, branch `feat/sp4a-linkage-dashboard` off origin/main) `server.py`; Test `tests/test_linkage_index_endpoint.py`. Use its `.venv`.

- [ ] **Step 1: Failing test** — `GET /api/linkage-index?investigation=<inv>` returns the index/queries; tolerant.
```python
def test_linkage_index_endpoint(tmp_ws):
    body, code = server.Handler._linkage_index_test(server.WORKSPACE, investigation="the-inv")
    d = json.loads(body); assert code == 200
    assert "ac_matrix" in d or "nodes" in d   # the matrix + the graph
```
- [ ] **Step 2: fail. Step 3: implement** `_linkage_index(ws_root, *, investigation=None, source=None, observable=None) -> (body, code)`: lazy-import `viva_superpowers.linkage_index` (tolerant → empty); param-dispatch to the right query (or the full graph); return JSON. Add the `do_GET` branch `/api/linkage-index` (pre-alias block, like `/api/report-lint`) + a TTL cache keyed `("linkage", ws_root)` (mirror `_REGISTRY_CACHE`). Never 500.
- [ ] **Step 4: pass. Step 5: commit** — `feat(server): GET /api/linkage-index (linkage queries, TTL-cached, tolerant)`

## Task 3: `/pbg-navigate` skill (pbg-superpowers)

**Files:** Create `skills/pbg-navigate/SKILL.md`; Test `tests/test_navigate_skill.py`. (Register in the skills index if there's one.)

- [ ] **Step 1:** Create a read-only `/pbg-navigate` skill: subcommands `ac-gaps <inv>` (the AC→study matrix + unkeyed-AC gaps), `source <bib_key>` (which studies use it), `finding-by-observable <token>`, `dag <inv>` — each calling `linkage_index` / `GET /api/linkage-index` and printing the result. Pure query, AI-free (no judgment — it surfaces the deterministic index). Document each subcommand.
- [ ] **Step 2:** Add `tests/test_navigate_skill.py` asserting `skills/pbg-navigate/SKILL.md` names the subcommands + `linkage_index`/`/api/linkage-index`.
- [ ] **Step 3: pass. Commit** — `feat(pbg-navigate): read-only linkage-query skill (ac-gaps/source/finding-by-observable/dag)`

## Task 4: Dashboard AC→study gating matrix panel (the gap surface)

**Files:** (vivarium-workbench, same branch) `static/walkthrough.js` (investigation render) or the executive fold; Test: structural.

- [ ] **Step 1: Implement.** In the investigation view, render an **AC→study gating matrix** panel from `/api/linkage-index?investigation=<inv>` (reuse the report-lint readiness-panel rendering / the thread-A acceptance-rollup styling): rows = acceptance criteria; columns = `study` (linked to its section) + computed result; **unkeyed-AC rows flagged** (red "no study linked — gap"). This makes the chromosome-cycle 5-unlinked-AC gap visible. Tolerate the endpoint failing.
- [ ] **Step 2: Structural test** — `walkthrough.js` fetches `/api/linkage-index` + renders the ac-matrix with the gap flag. `node -c` clean. **Step 3: Commit** — `feat(spine-present): AC->study gating-matrix panel (flags unlinked acceptance criteria)`

## Task 5: Golden + manual

- [ ] **Step 1 (golden, skipif v2e-invest absent, READ-ONLY):** `build_index`/`ac_gating_matrix` on real v2e-invest — `chromosome-cycle-calibration` shows its 5 unkeyed-AC gaps; `dnaa-replication`'s AC matrix resolves studies+results; `studies_for_source` inverts a real bib_key; PURE (no writes). v2e-invest untouched.
- [ ] **Step 2:** new tests green; suites no new failures (pre-existing via base). **MANUAL VERIFY (pending):** serve v2e-invest; the investigation AC-matrix panel shows the criteria + flags the unlinked ones.
- [ ] **Step 3: commit** — `test(linkage-index): v2e-invest golden + suite`

---

## Self-Review
- Coverage: the YAML index + 4 cheap queries (T1), the endpoint (T2), the skill (T3), the AC-matrix panel (T4), golden+manual (T5). Matches SP4a.
- AI-free: deterministic derive + queries in pbg-superpowers; dashboard renders; skill queries. The index is EPHEMERAL (never written to YAML).
- Reuse: roll_up_acceptance/canonical_outcomes/band_provenance/investigation_inputs/WorkspacePaths — no reimplementation. Normalizes the investigation→source split-shape (a real correctness fix).
- Deferred: SP4b (composite→observable edges + cross-study observable registry, needs composite builds).
- Rendering structural-tested + manual (no JS harness).

## Notes for the executor
- `.venv/bin/python -m pytest`. The index is PURE (no writes — assert it). Reuse the existing derive helpers; don't reimplement AC roll-up. Normalize the investigation→source split-shape (both `inputs.*` and top-level).
- The endpoint is read-only + tolerant (never 500, empty on absence) like `/api/report-lint`; TTL-cached.
- Don't modify the real v2e-invest; golden read-only.
