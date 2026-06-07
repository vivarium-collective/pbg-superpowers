# Investigation-scoped Inputs + Global Tagged/Multi-emitter SimulationsDB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Inputs owned by each investigation (per-investigation `inputs:` + sidebar section + migration), and rebuild SimulationsDB as one global table tagged by investigation/study with SQLite/Parquet/XArray emitter pills, defaulting to the loaded investigation.

**Architecture:** Pure helpers in pbg-superpowers (`inputs_dir`, `investigation_inputs`, `emitter_type_of`, `list_all_runs`), vendored into the dashboard (drift-guarded like `workspace_paths`/`viz_freshness`). The dashboard's inputs endpoint becomes investigation-scoped; SimulationsDB reads the run-registry sweep (built on the merged `emitter_path`/`backfill_study_runs`). Two independent phases: Inputs, then SimulationsDB.

**Tech Stack:** Python 3.12 stdlib (sqlite3, json, pathlib), pytest; vanilla-JS SPA + Jinja template. Existing `pbg_superpowers` + `vivarium_dashboard` packages.

**Spec:** `docs/superpowers/specs/2026-06-07-investigation-scoped-inputs-and-simdb-design.md`.
**Branches:** `pbg-superpowers feat/inputs-simdb-redesign` + `vivarium-dashboard feat/inputs-simdb-redesign`.

---

## File Structure

**pbg-superpowers**
- Modify `pbg_superpowers/workspace_paths.py` — add `inputs_dir(slug)`.
- Create `pbg_superpowers/investigation_inputs.py` — `investigation_inputs(ws_root, slug)` (pure: resolve datasets/refs/expert_docs from `investigations/<slug>/inputs/` + `investigation.yaml.inputs`, with repo-level read-through).
- Create `pbg_superpowers/runs_index.py` — `emitter_type_of(path)`, `_all_runs(runs_db)`, `list_all_runs(ws_root)`.
- Create `pbg_superpowers/migrate_inputs.py` — `pbg-migrate-inputs`.
- Modify `skills/pbg-investigation/SKILL.md`, `docs/concepts/vivarium-dashboard-model.md`.

**vivarium-dashboard**
- Modify `vivarium_dashboard/lib/workspace_paths.py` (vendored `inputs_dir`), create `lib/runs_index.py` (vendored), drift-guard tests.
- Modify `vivarium_dashboard/server.py` — `GET /api/iset/<slug>/inputs`, `GET /api/simulations`; remove global inputs route.
- Modify `vivarium_dashboard/static/walkthrough.js` + `templates/index.html.j2` — Inputs into the per-investigation rail; SimulationsDB tagged table.

---

# Phase 1 — Investigation-scoped Inputs

## Task 1: `inputs_dir(slug)` + vendored mirror (TDD)

**Files:** Modify `pbg_superpowers/workspace_paths.py`; Test `tests/test_workspace_paths_nested.py` (append). Then mirror into `vivarium_dashboard/lib/workspace_paths.py` + its drift-guard test.

- [ ] **Step 1: Failing test** (append to `tests/test_workspace_paths_nested.py`):

```python
def test_inputs_dir_nested(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert wp.inputs_dir("inv-a") == tmp_path / "investigations" / "inv-a" / "inputs"
```

- [ ] **Step 2: Run — FAIL** (`AttributeError: inputs_dir`). `pytest tests/test_workspace_paths_nested.py -k inputs_dir -q`

- [ ] **Step 3: Implement** — add to the `WorkspacePaths` class, mirroring `study_dir`/`report_dir`:

```python
    def inputs_dir(self, inv_slug: str) -> Path:
        """investigations/<inv_slug>/inputs (per-investigation owned inputs)."""
        return self.dir("investigations") / inv_slug / "inputs"
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Mirror** the method verbatim into `vivarium_dashboard/lib/workspace_paths.py` and confirm that repo's `workspace_paths` drift-guard test still passes (`vivarium-dashboard$ .venv/bin/python -m pytest tests/test_workspace_paths.py -q`).
- [ ] **Step 6: Commit** (each repo) `feat(paths): inputs_dir(slug) for per-investigation inputs`

---

## Task 2: `investigation_inputs()` resolver (TDD, pbg-superpowers)

**Files:** Create `pbg_superpowers/investigation_inputs.py`; Test `tests/test_investigation_inputs.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_investigation_inputs.py
from pathlib import Path
import yaml
from pbg_superpowers.investigation_inputs import investigation_inputs

def _ws(tmp):
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp / "investigations" / "inv-a"; (inv / "inputs" / "datasets").mkdir(parents=True)
    return tmp, inv

def test_reads_declared_inputs(tmp_path):
    ws, inv = _ws(tmp_path)
    (inv / "investigation.yaml").write_text(yaml.safe_dump({
        "name": "inv-a",
        "inputs": {"datasets": [{"name": "d1", "path": "inputs/datasets/d1.csv"}],
                   "references": ["Boesen2024"], "expert_docs": ["inputs/notes/x.md"]},
    }), encoding="utf-8")
    out = investigation_inputs(ws, "inv-a")
    assert out["datasets"][0]["name"] == "d1"
    assert out["references"] == ["Boesen2024"]
    assert out["expert_docs"] == ["inputs/notes/x.md"]

def test_empty_when_no_inputs_block(tmp_path):
    ws, inv = _ws(tmp_path)
    (inv / "investigation.yaml").write_text("name: inv-a\n", encoding="utf-8")
    out = investigation_inputs(ws, "inv-a")
    assert out == {"datasets": [], "references": [], "expert_docs": [], "_repo_fallback": False}

def test_repo_fallback_when_unmigrated(tmp_path):
    # No inputs: block AND repo-level datasets/ present -> read-through, flagged.
    ws, inv = _ws(tmp_path)
    (inv / "investigation.yaml").write_text("name: inv-a\n", encoding="utf-8")
    (ws / "datasets").mkdir(); (ws / "datasets" / "shared.csv").write_text("x")
    out = investigation_inputs(ws, "inv-a", repo_fallback=True)
    assert out["_repo_fallback"] is True
    assert any("shared.csv" in d.get("path", "") for d in out["datasets"])
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

```python
# pbg_superpowers/investigation_inputs.py
"""Resolve an investigation's owned inputs (datasets / references / expert docs)
from investigations/<slug>/inputs/ + investigation.yaml's `inputs:` block, with an
optional transitional read-through to repo-level datasets/ during migration."""
from __future__ import annotations

from pathlib import Path
import yaml

from .workspace_paths import WorkspacePaths


def investigation_inputs(ws_root: Path, slug: str, *, repo_fallback: bool = False) -> dict:
    wp = WorkspacePaths.load(Path(ws_root))
    inv_yaml = wp.dir("investigations") / slug / "investigation.yaml"
    spec = {}
    if inv_yaml.is_file():
        try:
            spec = yaml.safe_load(inv_yaml.read_text(encoding="utf-8")) or {}
        except Exception:
            spec = {}
    block = spec.get("inputs") or {}
    out = {
        "datasets": list(block.get("datasets") or []),
        "references": list(block.get("references") or []),
        "expert_docs": list(block.get("expert_docs") or []),
        "_repo_fallback": False,
    }
    if not (out["datasets"] or out["references"] or out["expert_docs"]) and repo_fallback:
        repo_ds = Path(ws_root) / "datasets"
        if repo_ds.is_dir():
            out["datasets"] = [{"name": p.name, "path": f"datasets/{p.name}"}
                               for p in sorted(repo_ds.iterdir()) if p.is_file()]
            out["_repo_fallback"] = True
    return out
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(inputs): investigation_inputs() resolver + repo read-through`

---

## Task 3: Scoped inputs endpoint (vivarium-dashboard, TDD)

**Files:** Modify `vivarium_dashboard/server.py`; create vendored `vivarium_dashboard/lib/investigation_inputs.py` (mirror, drift-guarded); Test `tests/test_iset_inputs.py`.

- [ ] **Step 1:** Vendor `investigation_inputs.py` into `vivarium_dashboard/lib/` (byte-faithful function body) + a drift-guard test like the `viz_freshness` mirror.
- [ ] **Step 2: Failing test** — a nested investigation with an `inputs:` block; assert `GET /api/iset/<slug>/inputs` (via the pure seam `_iset_inputs_payload(ws_root, slug)`) returns the declared datasets/references/expert_docs.
- [ ] **Step 3: Run — FAIL.**
- [ ] **Step 4: Implement** — add `_iset_inputs_payload(ws_root, slug)` delegating to the vendored `investigation_inputs(ws_root, slug, repo_fallback=True)`; add route `GET /api/iset/<slug>/inputs` (mirror the existing `/api/iset/<slug>/report` route added in the restructure). Remove the global `page-workspace-inputs` data route (or have it 410 with a pointer to per-investigation inputs).
- [ ] **Step 5: Run — PASS.** Run existing iset tests for regressions.
- [ ] **Step 6: Commit** `feat(dashboard): per-investigation inputs endpoint (/api/iset/<slug>/inputs)`

---

## Task 4: Inputs in the per-investigation sidebar (vivarium-dashboard)

**Files:** `templates/index.html.j2` (remove global Inputs rail item ~317-326; the inputs page section ~521), `static/walkthrough.js` (rail render + an inputs panel in the investigation detail).

- [ ] **Step 1:** Remove the global top-rail **Inputs** link (`index.html.j2:317-326`). 
- [ ] **Step 2:** In the per-investigation rail group (where the loaded investigation's Studies render — `_renderRailInvestigationGroups`), add an **Inputs** entry that, when clicked, fetches `/api/iset/<slug>/inputs` for the current slug and renders datasets/references/expert-docs (reuse the markup from the old inputs page section). Show a small "migrating: showing repo-level inputs" note when the payload's `_repo_fallback` is true.
- [ ] **Step 3:** `node --check vivarium_dashboard/static/walkthrough.js`. Manual verify: load an investigation → Inputs appears in its rail → shows its datasets/refs.
- [ ] **Step 4: Commit** `feat(dashboard): Inputs moves into the per-investigation sidebar`

---

## Task 5: `pbg-migrate-inputs` + skill docs (pbg-superpowers, TDD)

**Files:** Create `pbg_superpowers/migrate_inputs.py` + `[project.scripts] pbg-migrate-inputs`; Test `tests/test_migrate_inputs.py`; docs `skills/pbg-investigation/SKILL.md`, `docs/concepts/vivarium-dashboard-model.md`.

- [ ] **Step 1: Failing test** — a workspace with repo-level `datasets/d1.csv` used (referenced in study.yaml) by exactly one investigation's study → `plan_inputs_migration(ws_root)` assigns `d1.csv` to that investigation; a dataset referenced by two investigations → reported `ambiguous` (not assigned).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `plan_inputs_migration(ws_root) -> {assignments: {slug: [items]}, ambiguous: [items]}` (heuristic: map each repo-level dataset/ref to the investigations whose studies reference it; 1 → assign, >1 → ambiguous) and `migrate_inputs(ws_root, *, apply=False)` that `git mv`s assigned datasets into `investigations/<slug>/inputs/datasets/` + writes the `inputs:` block; ambiguous items are printed, not moved. Idempotent. CLI `main()`.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5:** Document the `inputs:` block + `pbg-migrate-inputs` in `skills/pbg-investigation/SKILL.md` and the concept doc. Add `pbg-migrate-inputs` to `[project.scripts]`.
- [ ] **Step 6: Commit** `feat(inputs): pbg-migrate-inputs (assign single-use, report ambiguous) + docs`

---

# Phase 2 — Global tagged/multi-emitter SimulationsDB

## Task 6: `emitter_type_of(path)` (TDD, pbg-superpowers)

**Files:** Create `pbg_superpowers/runs_index.py`; Test `tests/test_runs_index.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_runs_index.py
from pbg_superpowers.runs_index import emitter_type_of

def test_emitter_types():
    assert emitter_type_of("out/r/data.parquet") == "Parquet"
    assert emitter_type_of("out/r/store.zarr") == "XArray"
    assert emitter_type_of("studies/s/runs.db") == "SQLite"
    assert emitter_type_of("") == "SQLite"
    assert emitter_type_of("out/r") == "SQLite"   # bare dir, unknown -> SQLite default
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

```python
# pbg_superpowers/runs_index.py
"""Global run index across all studies, tagged by investigation/study/emitter."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def emitter_type_of(emitter_path: str | None) -> str:
    p = str(emitter_path or "").lower()
    if ".zarr" in p:
        return "XArray"
    if ".parquet" in p:
        return "Parquet"
    return "SQLite"
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(runs): emitter_type_of (SQLite/Parquet/XArray)`

---

## Task 7: `list_all_runs(ws_root)` (TDD, pbg-superpowers)

**Files:** Modify `pbg_superpowers/runs_index.py`; Test `tests/test_runs_index.py` (append).

- [ ] **Step 1: Failing test** — a nested workspace, one study with a `runs.db` `runs_meta` row (`emitter_path='out/r/data.parquet'`) → `list_all_runs(ws)` returns one dict with `investigation`, `study`, `run_id`, `emitter_type=='Parquet'`. (Use `pbg_superpowers.run_registry.RUNS_META_DDL` to build the db; create `investigation.yaml` with `studies: [s1]` so `study_owner` resolves.)

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** (append to `runs_index.py`):

```python
def _all_runs(runs_db: Path) -> list[dict]:
    runs_db = Path(runs_db)
    if not runs_db.is_file():
        return []
    cols = ("run_id", "started_at", "completed_at", "status", "emitter_path")
    try:
        conn = sqlite3.connect(f"file:{runs_db}?mode=ro", uri=True, timeout=1.0)
        try:
            have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
            use = [c for c in cols if c in have]
            rows = conn.execute(
                f"SELECT {', '.join(use)} FROM runs_meta "
                "ORDER BY COALESCE(completed_at, started_at) DESC"
            ).fetchall()
        finally:
            conn.close()
        return [dict(zip(use, r)) for r in rows]
    except sqlite3.Error:
        return []


def list_all_runs(ws_root: Path) -> list[dict]:
    """All runs across every study, tagged investigation/study/emitter, newest first."""
    from .workspace_paths import WorkspacePaths
    from .backfill_runs import backfill_study_runs
    wp = WorkspacePaths.load(Path(ws_root))
    out: list[dict] = []
    for sd in wp.iter_study_dirs():
        slug = sd.name
        owner = wp.study_owner(slug)
        try:
            backfill_study_runs(sd, spec_id=slug)
        except Exception:
            pass
        for r in _all_runs(sd / "runs.db"):
            out.append({
                "investigation": owner,
                "study": slug,
                "run_id": r.get("run_id"),
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "status": r.get("status"),
                "emitter_path": r.get("emitter_path"),
                "emitter_type": emitter_type_of(r.get("emitter_path")),
            })
    out.sort(key=lambda x: (x.get("completed_at") or x.get("started_at") or 0), reverse=True)
    return out
```

- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(runs): list_all_runs — global run index tagged by investigation/study/emitter`

---

## Task 8: `/api/simulations` endpoint (vivarium-dashboard, TDD)

**Files:** create vendored `vivarium_dashboard/lib/runs_index.py` (mirror + drift guard); modify `server.py`; Test `tests/test_simulations_endpoint.py`.

- [ ] **Step 1:** Vendor `runs_index.py` into `vivarium_dashboard/lib/` (byte-faithful) + drift-guard test.
- [ ] **Step 2: Failing test** — nested workspace with two studies' runs (one Parquet, one SQLite) → `_simulations_payload(ws_root)` (pure seam) returns both, tagged with investigation/study/emitter_type. Confirm FAIL→PASS.
- [ ] **Step 3: Implement** `_simulations_payload(ws_root)` delegating to vendored `list_all_runs`; route `GET /api/simulations` returning `{runs: [...], current: _current_branch_slug(ws_root)}` (so the SPA can default-filter).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(dashboard): /api/simulations — global tagged run list (vendored list_all_runs)`

---

## Task 9: SimulationsDB tagged table (vivarium-dashboard)

**Files:** `static/walkthrough.js` (+ `templates/index.html.j2` SimulationsDB section ~1294).

- [ ] **Step 1:** Rebuild the SimulationsDB page render to fetch `/api/simulations` and draw a table: columns **investigation · study · run · emitter · time · status**, with an emitter-type pill (CSS classes `emitter-sqlite`/`emitter-parquet`/`emitter-xarray`, distinct colors).
- [ ] **Step 2:** Default-filter rows to `payload.current` (the loaded investigation) with a visible "All investigations" toggle; add dropdown filters for study + emitter type.
- [ ] **Step 3:** For a Parquet/XArray row, link the run to its `emitter_path` and, when a zarr viz exists, an "open viz" affordance (reuse the existing zarr path; no inline preview).
- [ ] **Step 4:** `node --check`. Manual verify on v2e-invest: SimulationsDB shows runs tagged by investigation/study with emitter pills, defaulting to the current investigation.
- [ ] **Step 5: Commit** `feat(dashboard): SimulationsDB tagged table + emitter pills + current-investigation default`

---

## Task 10: Green + push + PRs (no merge)

- [ ] **Step 1:** `pytest -q` green in both repos (note pre-existing polars/version-sync skips). `node --check` clean.
- [ ] **Step 2:** Push `feat/inputs-simdb-redesign` in both repos; open draft PRs referencing the spec (dashboard PR notes it depends on the pbg-superpowers vendored helpers). Do NOT merge.

---

## Self-Review

- **Spec coverage:** inputs_dir (T1); `inputs:` resolver + read-through (T2); scoped endpoint (T3); sidebar move (T4); migration (T5); emitter_type (T6); list_all_runs tagged+backfill (T7); /api/simulations + current (T8); tagged table + current-default + pills (T9); drift guards (T1/T3/T8). ✓
- **Placeholders:** none — pure helpers carry full test+impl; SPA/endpoint/migration tasks specify exact anchors + seams (`_iset_inputs_payload`, `_simulations_payload`, `plan_inputs_migration`) with code where it's code.
- **Type consistency:** `investigation_inputs(ws_root, slug, *, repo_fallback)` returns `{datasets, references, expert_docs, _repo_fallback}` used identically T2/T3/T4; `list_all_runs` row shape (`investigation, study, run_id, started_at, completed_at, status, emitter_path, emitter_type`) identical T7/T8/T9; `emitter_type_of` values `Parquet|XArray|SQLite` identical T6/T7/T9.
- **Note:** T9's zarr "open viz" reuses `_zarr_store_for_sim` (server.py ~2875); the implementer should confirm its signature before wiring.
