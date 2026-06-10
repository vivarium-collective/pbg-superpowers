# Readout Coordination & Self-Describing Stores — Design

**Date:** 2026-06-09
**Status:** Draft (awaiting review)
**Supersedes/absorbs:** the original "Increment B3" (aggregate/bulk resolution) — now one facet of this larger coordination.

---

## 1. Problem (grounded)

Readouts are the natural coordination point for observables but are the most-drifted part of the schema. Grounding found:

- **Three incompatible readout dialects** in real studies: `identifier: listeners.monomer_counts[3861]` + bracket-index (dnaa-1, dnaa-0); `store_path:` with *prose* placeholders (`bulk.<resolved-at-runtime...>`, `derived`) (dnaa-00/01/02); and the schema's `index_by{type,value}` — which **no code reads**. Plus `notes:` vs `description:`, and `status` values that don't match the schema enum.
- **Readouts barely drive anything.** `collect_emit_paths_from_spec` (vivarium-dashboard `lib/composite_runs.py:480`) reads only `readouts[].store_path` — so the real dnaa studies (which use `identifier:`) contribute **zero** emit paths. The CLI/canonical path instead emits whole stores (`bulk`, `listeners`) regardless.
- **Vector/bulk resolution is hand-baked or model-coupled.** `monomer_counts[3861]` is a magic index; "sum across DnaA forms" lives in a `notes:` string; and the form→index map for `monomer_counts` is **only recoverable from `sim_data`** (v2ecoli doesn't persist listener name catalogs). `bulk` is self-describing via the `bulk__id` column; listener vectors are not.
- **No structure linkage.** Nothing validates a readout against what the composite actually exposes; `index_by` (the designed carrier) is dead.

Net: the same observable is named ad-hoc in study tests, readouts, viz, and the emit config, with no single source and no structural validation — and the data often can't be re-interrogated from the stored run alone.

## 2. Goal

Make **Readouts the one structured observable vocabulary**, derived-from/validated-against the bigraph structure, that **drives the emitter config** (emitter-aware, incl. xarray packing) and **feeds the evaluator** (resolving bulk/vector/aggregate observables from the stored run alone). End-to-end: **structure → readout → emit → store → reader → measure**, one declaration.

## 3. Design decisions (agreed)

1. **Unified structured Readout spine.** One canonical readout schema: `name`, `description`, a structured selector `index_by: {type, value}` (`type ∈ bulk_id | monomer_id | rna_id | tf_id | listener_path | literal_index`; `value` = the key), an optional `aggregate` (e.g. `{op: sum, over: [id,...]}` for "DnaA forms"), `units`, `status`. The store_path/array-index is *resolved*, never hand-written. Migrate the three dialects to this. Readouts are authored by humans but **validated + autocompleted against structure**.

2. **Self-describing stores.** Persist the id/name catalog **with** the data so a run resolves run-only, no `sim_data`:
   - **xarray/zarr:** an `id` coordinate dim on each array observable — this IS the efficient packing decision (one variable + id coord, chunked) *and* the name catalog. (Your XArrayEmitter point.)
   - **parquet:** keep `bulk__id`; **add `output_metadata__<vector>`** for listener vectors (e.g. `monomer_counts`) so `field_metadata` resolves names. (Adopts vEcoli's persistence, which v2ecoli currently omits.)
   - **sqlite:** store the catalog alongside.

3. **A single resolver** maps a structured Readout ⇄ structure (validate/enumerate) ⇄ emit config (emitter-aware) ⇄ evaluator series. The evaluator's `measure` references readouts (or the same `index_by`), so B2's evaluator gains bulk/vector/aggregate via this resolver — finally computing the authored dnaa vector tests.

## 4. The chain (target)

```
bigraph composite structure                 (collect_input_ports + bulk__id / monomer catalogs)
        │  enumerate available observables + id catalogs
        ▼
study Readouts (index_by + aggregate)        ← validated/autocompleted against structure
        │  resolve (one resolver)
        ├──▶ emit config  (emitter-aware: parquet columns / sqlite subtree / xarray id-coord packing)
        │          ▼
        │      RUN → self-describing store  (data + id/name catalog)
        │          ▼
        └──▶ evaluator measure  ──▶ RunReader resolves id→series/aggregate (run-only)
```

## 5. Decomposition (sequenced sub-projects — each ships working software)

1. **Self-describing emitters** (pbg-emitters, +v2ecoli usage): persist id/name catalogs — xarray `id` coord on array observables; parquet `output_metadata__<vector>` for listener vectors; sqlite catalog. *Foundation for run-only resolution.*
2. **RunReader catalog + id resolution** (pbg-emitters): `RunReader.catalog(observable)` and `series(id_by=…, aggregate=…)` — resolve a structured selector (and aggregate over a list of ids) to a numeric series from the self-describing store. Builds on #1; falls back to the existing `bulk__id` for bulk now.
3. **Unified Readout schema + resolver** (pbg-template schema + pbg-superpowers): the canonical readout schema (`index_by`+`aggregate`); a resolver `readout → {emit_selector, evaluator_selector}`; migrate the 3 dialects.
4. **Structure introspection/validation** (pbg-superpowers + a dashboard endpoint): enumerate available observables + id catalogs from the built composite (`collect_input_ports` + catalogs); validate readouts at author time; flag `aspirational`.
5. **Emit-config generation from readouts** (vivarium-dashboard): `collect_emit_paths`/emitter injection honors `index_by`/`aggregate`, emitter-aware (incl. xarray packing). Replaces the store_path-only collector.
6. **Evaluator via readout resolution** (pbg-superpowers): B2 evaluator resolves `measure` through the readout resolver + RunReader catalog → computes the authored dnaa **vector** tests (the original B3 payoff). Adds the `per_minute` rate window.
7. **Migration + goldens**: convert studies to the unified readouts; golden tests proving the dnaa vector verdicts now compute run-only.

## 6. Non-goals
- Changing the simulation science or composite structure.
- A new viz system (viz keeps referencing readouts).
- Forcing every emitter to re-pack legacy stores (resolution falls back to `sim_data`/`bulk__id` during transition — see risks).

## 7. Risks & open questions
- **v2ecoli emitter change (#1, parquet `output_metadata`)** touches v2ecoli's ParquetEmitter usage; coordinate, and keep a `sim_data` fallback for runs predating the change (Hybrid resolution during transition).
- **xarray packing specifics** (chunking, whether to pack whole arrays + id-coord vs selected indices) — settle at plan time for sub-project #1; default: whole array + `id` coord (flexible + self-describing), chunked.
- **Migration of `monomer_counts[3861]` magic indices** → `index_by{type: monomer_id, value: …}` + `aggregate` needs the monomer catalog; do it after #1/#2 so the migration can validate.
- **Backward read compatibility:** RunReader must still read old stores (no id catalog) via the current path + `sim_data` fallback.
- **Scope:** this is ~7 sub-projects across pbg-emitters / pbg-superpowers / pbg-template / vivarium-dashboard / v2ecoli — sequence strictly; #1→#2 first (run-only resolution), then #3/#6 deliver the visible payoff.

## 8. Recommended entry point
Start with **#1 (self-describing emitters)** then **#2 (RunReader catalog/resolution)** — they make runs self-contained and unblock everything else. Best built once the foundation PRs (pbg-emitters #6 RunReader; pbg-superpowers #115 evaluator) merge, so #1/#2 extend RunReader on `main`.
