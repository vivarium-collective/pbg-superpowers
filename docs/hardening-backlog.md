# pbg-ecosystem hardening backlog (P1/P2)

**Status:** parked / not started. **Last updated:** 2026-06-10.

This is the remaining production-hardening work from the Fable-5 cross-repo review (2026-06-09). The **P0 correctness/security fixes shipped** (10 PRs merged: `allocate_core` isolation, engine global state, `report.py` nested layout, dashboard CSRF, + the safe-cleanup pass). The **investigation/study-spine program is complete and separate** (run/outcome spine + readout coordination + stages #2–#5). Everything below is the leftover P1/P2 — independent items of varying value, risk, and churn.

Repos in scope: `bigraph-schema` → `process-bigraph` → (`pbg-superpowers` · `vivarium-dashboard` · `pbg-template` · `pbg-emitters`). ~66K LOC first-party Python.

---

## A — CI lint/type gates (ruff)
**The systemic gap: there is no lint or type CI gate anywhere.**

- Add a curated, low-noise ruff ruleset (pyflakes `F` / unused-imports / import-sort `I` / `E9`), run `ruff check --fix`, baseline the remainder with per-file-ignores, and add a CI lint job per repo.
- **Do not** enable `ruff format` (full reformatting = massive churn) — lint only.
- Optionally a lenient `mypy` gate later, scoped to typed modules.

*Value: high (foundational). Risk: low. Churn: low if lint-only. Effort: medium (per-repo lint-debt triage). Parallelizable (1 agent/repo). ~5 PRs.*

## B — Cross-repo data-contract versioning
**The biggest fragility per the review.** The emitter schemas (SQLite/Parquet/zarr) and the study/investigation YAML schemas are **hand-mirrored across repos and unversioned** — a schema change in one repo can silently break another.

- Add a `schema_version` field to the contracts, and a single source-of-truth schema package (or a cross-repo contract-test) that fails when one repo's view of a contract drifts from another's.

*Value: highest. Risk: medium (touches the data layer). Effort: large — needs its own brainstorm/spec before implementation.*

## C — Targeted perf fixes
Concrete, bounded, low-risk:
1. `vivarium-dashboard` `/api/simulations` — add a cache.
2. `pbg-superpowers` `discover_all` — move off the request path.
3. engine per-tick walk + `JSONEmitter` O(n²) — fix the quadratic path.

*Value: medium. Risk: low. Effort: small each. ~3 small PRs.*

## D — Mechanical hygiene
- Pin dependencies + add lockfiles (reproducibility).
- Replace `print()` with `logging` across the repos.

*Value: medium. Risk: low. Mechanical/broad. Good parallel-agent work.*

## E — God-file splits (LAST — riskiest)
- `vivarium-dashboard/server.py` ~13K LOC.
- `process-bigraph/composite.py` ~3.4K LOC.

*Value: medium (maintainability). Risk: high (broad ripple). Do last, carefully.*

---

## Minor leftovers
- `report.py` `render_workspace_report` "models" refactor + `study_link` path (deferred from P0 #112).
- `refresh_viz.py` `shell=True` (dashboard) — a separate small security item.
- `pbg-superpowers tests/test_simulation_set.py::test_golden_dnaa2` asserts `v2e-invest` is fully clean and trips on a pre-existing untracked feedback YAML there — a too-strict local-only golden (CI skips it). Relax it to check only that *its* target wasn't dirtied.

## Recommended order
**A** (CI ruff gate — foundational, parallel) → **C** (perf — concrete) → **B** (data contracts — own design pass) → **D** (hygiene) → **E** (god-files, last). Items are largely independent; reprioritize freely.
