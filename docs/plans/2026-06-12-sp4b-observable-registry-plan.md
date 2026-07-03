# SP4b — Observable-edge enrichment + cross-study observable registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 2 (Navigate) / SP4, piece b — the bolt-on completing the linkage index. Builds on SP4a (merged). Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** Add the `composite --emits--> observable` (and `--contains--> process`) edges to SP4a's linkage index via composite introspection, enabling the two observable-registry queries: **`studies_for_observable`** (cross-study: which studies/composites measure observable X) and **`composite_emits`** (what a composite emits + which studies use it). Keyed on SP2b's canonical observable vocabulary.

**The isolation invariant (from the grounding):** the composite build is the ONLY expensive edge. It is injected behind an `observables_for_ref` function so SP4a's pure YAML core never depends on (or pays for) a build. The dashboard supplies the build via the existing cached `_observables_for_ref` (SP2b-i, merged → `available_observables`); pbg-superpowers' enrichment takes the injected fn.

**Tech:** Python + JS; pytest. Repos: pbg-superpowers (enrichment + queries + skill) + vivarium-workbench (the endpoint wiring + render). `.venv/bin/python`. AI-free; the index stays EPHEMERAL.

**Reuse (confirmed):** SP4a `linkage_index.build_index` (the YAML core; has study→observables via `_observables_of_study` + `findings_for_observable`); SP2b-i `_observables_for_ref(ws, ref) -> {leaves, catalogs}` (dashboard, cached in `_COMPOSITE_STATE_CACHE`); SP2b `readout_resolver` for the canonical observable token. Study→composite edges already in the index (`baseline[].composite`).

---

## Task 1: `enrich_observable_edges` + the observable-registry queries (pbg-superpowers)

**Files:** Modify `pbg_superpowers/linkage_index.py`; Test `tests/test_linkage_index.py`.

- [ ] **Step 1: Failing tests** (inject a STUB `observables_for_ref` — no real build needed for the unit test):
```python
from pbg_superpowers.linkage_index import build_index, enrich_observable_edges, studies_for_observable, composite_emits

def _stub_obs(ref):  # the injected build
    return {"leaves": ["agents.0.listeners.mass.cell_mass", "agents.0.bulk[ATP[c]]"], "catalogs": {}} if "baseline" in ref else {"leaves": [], "catalogs": {}}

def test_enrich_adds_composite_emits_edges(tmp_ws_two_studies_one_composite):
    idx = build_index(ws)                      # YAML core — no composite edges yet
    enrich_observable_edges(idx, _stub_obs)    # injects the build
    emits = [e for e in idx["edges"] if e["type"] == "emits"]
    assert any(e["from"].startswith("composite:") and e["to"].startswith("observable:") for e in emits)

def test_studies_for_observable_cross_study(tmp_ws_two_studies_measure_cell_mass):
    # both studies use a composite that emits cell_mass → both are returned for the observable
    res = studies_for_observable(ws, "listeners.mass.cell_mass", observables_for_ref=_stub_obs)
    assert set(res["studies"]) >= {"s1", "s2"}
    assert res["composites"]                    # the emitting composites

def test_composite_emits(tmp_ws):
    res = composite_emits(ws, "v2ecoli.composites.baseline.baseline", observables_for_ref=_stub_obs)
    assert "cell_mass" in " ".join(res["emits"]) and res["used_by_studies"]

def test_enrich_is_pure_given_injected_fn(tmp_ws):
    before = _snapshot(tmp_ws); idx = build_index(ws); enrich_observable_edges(idx, _stub_obs)
    assert _snapshot(tmp_ws) == before          # still no YAML writes
```
- [ ] **Step 2: fail. Step 3: implement.** `enrich_observable_edges(index, observables_for_ref) -> index`: for each `composite:` node in the index, call `observables_for_ref(spec_id)` → `{leaves, catalogs}`; add `composite --emits--> observable:<token>` edges (normalize the leaf to the canonical observable token via `readout_resolver` where applicable; strip the lineage `agents.<n>.` prefix consistent with SP2b-i so it matches studies' bare tokens). Optionally `composite --contains--> process` if the build exposes processes. Tolerate `observables_for_ref` raising (skip that composite). Then `studies_for_observable(ws, token, *, observables_for_ref) -> {studies, composites}` (build the index, enrich, then: composites that `emits` the token, and studies that `uses_composite` those) and `composite_emits(ws, composite_id, *, observables_for_ref) -> {emits:[tokens], used_by_studies:[...]}`. The enrichment touches NO YAML (pure given the injected fn).
- [ ] **Step 4: pass. Step 5: commit** — `feat(linkage-index): composite->observable edge enrichment (injected build) + studies_for_observable/composite_emits queries`

## Task 2: Wire the dashboard endpoint to the enrichment (vivarium-workbench)

**Files:** (vivarium-workbench, branch `feat/sp4b-observable-dashboard` off origin/main) `server.py` (`_linkage_index` ~the SP4a worker); Test `tests/test_linkage_index_endpoint.py`. Use its `.venv`.

- [ ] **Step 1: Failing test** — `GET /api/linkage-index?observable=<token>` returns the cross-study registry (using the real `_observables_for_ref` build).
```python
def test_linkage_observable_query(tmp_v2ecoli_ws):
    body, code = server.Handler._linkage_index_test(ws, observable="listeners.mass.cell_mass")
    d = json.loads(body); assert code == 200
    assert "studies" in d and "composites" in d   # the registry
```
- [ ] **Step 2: fail. Step 3: implement.** In `_linkage_index`, wire `?observable=<token>` → `linkage_index.studies_for_observable(ws, token, observables_for_ref=lambda ref: _observables_for_ref(ws, ref))` and `?composite=<id>` → `composite_emits(...)`, passing the dashboard's cached `_observables_for_ref` as the injected build (so the enrichment reuses `_COMPOSITE_STATE_CACHE`, ~3s once per composite). Tolerate failure (empty, never 500). The full-graph path stays YAML-only (no enrichment unless an observable/composite query is asked).
- [ ] **Step 4: pass. Step 5: commit** — `feat(server): /api/linkage-index observable/composite queries (enrichment via cached _observables_for_ref)`

## Task 3: `/pbg-navigate` observable + composite subcommands (pbg-superpowers)

**Files:** Modify `skills/pbg-navigate/SKILL.md`; Test `tests/test_navigate_skill.py`.

- [ ] **Step 1:** Add `observable <token>` (which studies/composites measure it — the cross-study registry) and `composite <id>` (what it emits + which studies use it) subcommands to `skills/pbg-navigate/SKILL.md`, each calling `/api/linkage-index?observable=`/`?composite=`. Pure query, AI-free. Note they trigger a composite build (cached).
- [ ] **Step 2:** Extend `tests/test_navigate_skill.py` to assert the new subcommands + `studies_for_observable`/`composite_emits` are named.
- [ ] **Step 3: pass. Commit** — `feat(pbg-navigate): observable + composite registry subcommands`

## Task 4: Golden + manual

- [ ] **Step 1 (golden, skipif v2e-invest absent + composite-buildable, READ-ONLY):** `studies_for_observable("/Users/eranagmon/code/v2e-invest", "<real observable>", observables_for_ref=<real build>)` returns the studies that measure it across the dnaa investigation (cross-study); `composite_emits` on a real composite returns its emitted observables + the studies using it; PURE (no writes). If the composite can't build in the test env, skip gracefully. v2e-invest untouched.
- [ ] **Step 2:** new tests green; suites no new failures (pre-existing via base). **MANUAL VERIFY (pending):** serve v2e-invest; `/api/linkage-index?observable=<token>` returns the studies measuring it; `/pbg-navigate observable <token>` lists them.
- [ ] **Step 3: commit** — `test(linkage-index): observable-registry golden + suite`

---

## Self-Review
- Coverage: the enrichment + the 2 observable queries (T1), the endpoint wiring (T2), the skill subcommands (T3), golden+manual (T4). Completes SP4 (a + b).
- Isolation invariant held: the build is injected; SP4a's YAML core + the full-graph path stay build-free; only the observable/composite queries pay for a build (cached).
- AI-free; the index stays EPHEMERAL; reuses `_observables_for_ref`/`available_observables` (SP2b-i) — no reimplementation.
- Keyed on SP2b's canonical observable vocabulary (strip the lineage prefix to match studies' bare tokens — the SP2b-i lesson).
- Rendering: none required (the registry surfaces via the endpoint + skill); a dashboard cross-study view is optional/deferred.

## Notes for the executor
- `.venv/bin/python -m pytest`. Inject a STUB `observables_for_ref` in the unit tests (no real build); the golden uses the real build (skip if unbuildable). REUSE SP4a's `build_index` + SP2b-i's `_observables_for_ref` — do NOT reimplement composite building or observable introspection.
- Match SP2b-i's lineage-prefix normalization (`agents.<n>.`) so composite-emitted leaves match studies' bare observable tokens — else the registry is empty (the SP2b-i false-positive lesson, inverted).
- The index is EPHEMERAL — enrichment mutates the in-memory index only, never YAML.
- Don't modify the real v2e-invest; golden read-only.
