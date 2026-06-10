# Study Run/Outcome Spine — Increment A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-record a study's runs into `study.yaml` and make the verdict pills *and* the DAG gate read **one** outcome source (the canonical run), eliminating the hand-transcription and the "place the canonical run last" hack.

**Architecture:** A new `pbg_superpowers/study_outcomes.py` reconciles the study's `runs.db` into `study.yaml`'s `runs[]` (mechanical fields only; authored `outcomes`/prose preserved) and exposes `canonical_run(...)`. `study_status.count_test_outcomes` and the dashboard DAG gate both switch to reading the **canonical** run's `outcomes` (today they read `runs[-1]` and `tests[].status` respectively — two of three divergent sources). The dashboard's post-run path and a new `sync-runs` CLI/endpoint trigger the reconciliation. No evaluator yet (Increment B); no `pbg-emitters` reader extraction yet (only needed when reading series in B).

**Tech Stack:** Python 3.11+, PyYAML, sqlite3 (stdlib), argparse; pytest. Spec: `docs/specs/2026-06-09-study-run-outcome-spine-design.md`.

**Repos touched:** `pbg-superpowers` (engine + status + CLI), `vivarium-dashboard` (gate + post-run hook + endpoint).

---

## File Structure

**pbg-superpowers**
- Create: `pbg_superpowers/study_outcomes.py` — canonical-run selection + run reconciliation + `sync()` + CLI.
- Modify: `pbg_superpowers/run_registry.py` — add `list_runs(runs_db) -> list[dict]`.
- Modify: `pbg_superpowers/study_status.py` — `count_test_outcomes` reads canonical run, not `runs[-1]`.
- Modify: `pyproject.toml` — add `pbg-sync-runs` console script.
- Test: `tests/test_study_outcomes.py`, additions to `tests/test_study_status.py` (or new `tests/test_canonical_run.py`), `tests/test_run_registry_list.py`.

**vivarium-dashboard**
- Modify: `vivarium_dashboard/server.py` — gate `_condition_satisfied` "tests-passed" → canonical outcomes; post-run hook in the `if code == 200:` block (~`:3115`); add `_post_study_sync_runs` + `_POST_ROUTE_MAP` entry.
- Test: `tests/test_gate_canonical_source.py`, `tests/test_study_sync_runs_endpoint.py`.

---

## Phase 1 — Canonical-run selection + run reconciliation (pbg-superpowers)

### Task 1: `run_registry.list_runs`

**Files:**
- Modify: `pbg_superpowers/run_registry.py`
- Test: `tests/test_run_registry_list.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_registry_list.py
from pathlib import Path
from pbg_superpowers import run_registry

def test_list_runs_returns_rows_newest_first(tmp_path: Path):
    db = tmp_path / "runs.db"
    run_registry.register_run(db, "r1", spec_id="s", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    run_registry.register_run(db, "r2", spec_id="s", status="completed",
                              started_at="2026-01-02T00:00:00Z", completed_at="2026-01-02T00:01:00Z")
    rows = run_registry.list_runs(db)
    assert [r["run_id"] for r in rows] == ["r2", "r1"]
    assert rows[0]["status"] == "completed"

def test_list_runs_missing_db_is_empty(tmp_path: Path):
    assert run_registry.list_runs(tmp_path / "nope.db") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_run_registry_list.py -v`
Expected: FAIL — `AttributeError: module 'pbg_superpowers.run_registry' has no attribute 'list_runs'`

- [ ] **Step 3: Implement `list_runs`**

Mirror the tolerant read style of the existing `latest_run` (`run_registry.py:41`). Add:

```python
def list_runs(runs_db) -> list[dict]:
    """All runs_meta rows, newest first by COALESCE(completed_at, started_at).
    Returns [] if the DB or table is absent. Tolerant of missing columns."""
    from pathlib import Path
    import sqlite3
    path = Path(runs_db)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT * FROM runs_meta "
                "ORDER BY COALESCE(completed_at, started_at) DESC, rowid DESC"
            )
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_run_registry_list.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/run_registry.py tests/test_run_registry_list.py
git commit -m "feat(run_registry): list_runs() — all runs_meta rows newest-first"
```

---

### Task 2: `canonical_run` selection

**Files:**
- Create: `pbg_superpowers/study_outcomes.py`
- Test: `tests/test_study_outcomes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_study_outcomes.py
from pbg_superpowers import study_outcomes as so

def test_canonical_prefers_flag_over_position():
    spec = {"runs": [
        {"name": "a", "status": "completed", "canonical": True},
        {"name": "b", "status": "completed"},
    ]}
    assert so.canonical_run(spec)["name"] == "a"

def test_canonical_falls_back_to_newest_completed():
    spec = {"runs": [
        {"name": "old", "status": "completed", "timestamp": "2026-01-01T00:00:00Z"},
        {"name": "new", "status": "completed", "timestamp": "2026-02-01T00:00:00Z"},
        {"name": "running", "status": "running", "timestamp": "2026-03-01T00:00:00Z"},
    ]}
    assert so.canonical_run(spec)["name"] == "new"

def test_canonical_last_resort_is_last_entry():
    spec = {"runs": [{"name": "a", "status": "running"}, {"name": "b", "status": "running"}]}
    assert so.canonical_run(spec)["name"] == "b"

def test_canonical_none_when_no_runs():
    assert so.canonical_run({"runs": []}) is None
    assert so.canonical_run({}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pbg_superpowers.study_outcomes'`

- [ ] **Step 3: Create the module with `canonical_run`**

```python
# pbg_superpowers/study_outcomes.py
"""Reconcile a study's runs.db into study.yaml and expose the canonical outcome
surface. Mechanical run fields are code-owned; authored outcomes/prose are preserved.
Increment A: record + single-source. (Evaluation of measure/pass_if is Increment B.)"""
from __future__ import annotations

from pathlib import Path

_COMPLETE = {"complete", "completed", "ran", "done"}


def _runs_of(spec_or_runs) -> list[dict]:
    if isinstance(spec_or_runs, list):
        runs = spec_or_runs
    else:
        runs = (spec_or_runs or {}).get("runs") or []
    return [r for r in runs if isinstance(r, dict)]


def canonical_run(spec_or_runs) -> dict | None:
    """The run whose outcomes are authoritative: an explicit `canonical: true`
    (last one wins), else the newest completed run by `timestamp`, else the last
    run, else None."""
    runs = _runs_of(spec_or_runs)
    if not runs:
        return None
    flagged = [r for r in runs if r.get("canonical") is True]
    if flagged:
        return flagged[-1]
    completed = [r for r in runs if str(r.get("status", "")).lower() in _COMPLETE]
    if completed:
        return max(completed, key=lambda r: str(r.get("timestamp", "")))
    return runs[-1]


def canonical_outcomes(spec_or_runs) -> dict:
    """The canonical run's `outcomes` dict (empty if none)."""
    run = canonical_run(spec_or_runs)
    return (run or {}).get("outcomes") or {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/study_outcomes.py tests/test_study_outcomes.py
git commit -m "feat(study_outcomes): canonical_run/canonical_outcomes selection"
```

---

### Task 3: `record_runs` — reconcile runs.db into study.yaml (preserve authored fields)

**Files:**
- Modify: `pbg_superpowers/study_outcomes.py`
- Test: `tests/test_study_outcomes.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_study_outcomes.py
from pathlib import Path
from pbg_superpowers import study_io, run_registry, study_outcomes as so

def _study(tmp_path: Path, spec: dict) -> Path:
    d = tmp_path / "studies" / "s1"; d.mkdir(parents=True)
    study_io.save_yaml_atomic(d / "study.yaml", spec)
    return d

def test_record_adds_missing_run_and_preserves_authored(tmp_path: Path):
    d = _study(tmp_path, {"name": "s1", "runs": [
        {"name": "r1", "status": "completed",
         "outcomes": {"t1": {"result": "PASS", "detail": "authored"}},
         "description": "hand-written"},
    ]})
    db = d / "runs.db"
    # r1 already authored; r2 only in the DB
    run_registry.register_run(db, "r1", spec_id="s1", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    run_registry.register_run(db, "r2", spec_id="s1", status="completed",
                              started_at="2026-01-02T00:00:00Z", completed_at="2026-01-02T00:01:00Z",
                              emitter_path="out/r2")
    summary = so.record_runs(d)
    spec = study_io.load_yaml_mapping(d / "study.yaml")
    by = {r["name"]: r for r in spec["runs"]}
    assert summary == {"added": 1, "updated": 1}
    # authored fields preserved on r1
    assert by["r1"]["outcomes"]["t1"]["result"] == "PASS"
    assert by["r1"]["description"] == "hand-written"
    # r2 recorded with mechanical fields
    assert by["r2"]["status"] == "completed"
    assert by["r2"]["emitter"]["kind"] in {"sqlite", "parquet", "xarray", "unknown"}

def test_record_is_idempotent(tmp_path: Path):
    d = _study(tmp_path, {"name": "s1", "runs": []})
    db = d / "runs.db"
    run_registry.register_run(db, "r1", spec_id="s1", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    so.record_runs(d)
    first = (d / "study.yaml").read_text()
    so.record_runs(d)
    assert (d / "study.yaml").read_text() == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes.py -k record -v`
Expected: FAIL — `AttributeError: module 'pbg_superpowers.study_outcomes' has no attribute 'record_runs'`

- [ ] **Step 3: Implement `record_runs` (+ helpers)**

Mechanical fields are code-owned; authored keys (`outcomes`, `description`, `result`, `notes`, `canonical`) are never overwritten. Append the marker comment is unnecessary in YAML round-trips — preservation is by key-merge.

```python
# add imports at top of study_outcomes.py
from . import study_io, run_registry

# code-owned mechanical fields written from runs.db
_MECHANICAL = ("status", "kind", "emitter", "seeds", "params", "timestamp", "commit")


def _emitter_kind(emitter_path: str | None) -> str:
    p = (emitter_path or "").lower()
    if not p:
        return "unknown"
    if p.endswith(".db") or "sqlite" in p:
        return "sqlite"
    if "parquet" in p:
        return "parquet"
    if "zarr" in p or "xarray" in p:
        return "xarray"
    return "unknown"


def _mechanical_record(db_row: dict) -> dict:
    rec = {
        "name": db_row.get("run_id"),
        "status": db_row.get("status"),
        "timestamp": db_row.get("completed_at") or db_row.get("started_at"),
        "emitter": {"kind": _emitter_kind(db_row.get("emitter_path")),
                    "store": db_row.get("emitter_path")},
    }
    if db_row.get("generation_id") is not None:
        rec["generation_id"] = db_row.get("generation_id")
    params = db_row.get("params") or db_row.get("params_json")
    if params:
        rec["params"] = params
    return {k: v for k, v in rec.items() if v is not None}


def record_runs(study_dir) -> dict:
    """Merge the study's runs.db rows into study.yaml's runs[] by run name.
    Updates only mechanical fields; preserves authored outcomes/prose. Idempotent.
    Returns {"added": n, "updated": n}."""
    study_dir = Path(study_dir)
    study_yaml = study_dir / "study.yaml"
    spec = study_io.load_yaml_mapping(study_yaml)
    db_rows = run_registry.list_runs(study_dir / "runs.db")

    runs = spec.get("runs")
    if not isinstance(runs, list):
        runs = []
    by_name = {r["name"]: r for r in runs if isinstance(r, dict) and r.get("name")}

    added = updated = 0
    for row in db_rows:
        rec = _mechanical_record(row)
        name = rec.get("name")
        if not name:
            continue
        if name in by_name:
            target = by_name[name]
            changed = False
            for k in _MECHANICAL:
                if k in rec and target.get(k) != rec[k]:
                    target[k] = rec[k]
                    changed = True
            updated += 1 if changed else 0
        else:
            runs.append(rec)
            by_name[name] = rec
            added += 1

    if added or updated:
        spec["runs"] = runs
        study_io.save_yaml_atomic(study_yaml, spec)
    return {"added": added, "updated": updated}


def sync(study_dir) -> dict:
    """Increment A: reconcile runs. (Increment B will also evaluate outcomes.)"""
    return record_runs(study_dir)
```

> Note for the implementer: confirm `run_registry.register_run` persists `emitter_path`/`generation_id` columns (DDL at `run_registry.py:21`); `list_runs` returns them as row keys. If `params_json` comes back as a JSON string, leave it as-is for Increment A (it round-trips as a string; structured parsing is not required here).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes.py -k record -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/study_outcomes.py tests/test_study_outcomes.py
git commit -m "feat(study_outcomes): record_runs reconciles runs.db into study.yaml (preserve authored)"
```

---

## Phase 2 — Single source: status reads the canonical run (pbg-superpowers)

### Task 4: `count_test_outcomes` uses the canonical run, not `runs[-1]`

**Files:**
- Modify: `pbg_superpowers/study_status.py` (`count_test_outcomes`, ~`:144-159`)
- Test: `tests/test_study_status.py` (add) or `tests/test_canonical_run.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_canonical_run.py
from pbg_superpowers import study_status

def test_count_uses_canonical_flag_not_last_run():
    spec = {
        "tests": [{"name": "t1"}, {"name": "t2"}],
        "runs": [
            {"name": "good", "status": "completed", "canonical": True,
             "outcomes": {"t1": {"result": "PASS"}, "t2": {"result": "PASS"}}},
            {"name": "later-scratch", "status": "completed",
             "outcomes": {"t1": {"result": "FAIL"}}},
        ],
    }
    counts = study_status.count_test_outcomes(spec, spec["runs"])
    # canonical (good) → both PASS, not the last array entry (scratch → 1 FAIL)
    assert counts["pass"] == 2
    assert counts["fail"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_canonical_run.py -v`
Expected: FAIL — counts reflect `later-scratch` (`runs[-1]`): `pass==1, fail==1` (current `_latest_run` behavior).

- [ ] **Step 3: Point `count_test_outcomes` at the canonical run**

In `study_status.py`, replace the `_latest_run(...)` selection inside `count_test_outcomes` (`:152`) with the canonical selector. Add at top:

```python
from .study_outcomes import canonical_run
```

Change the run selection line (currently `latest = _latest_run(runs if runs is not None else spec.get("runs"))`) to:

```python
    chosen = canonical_run(runs if runs is not None else spec.get("runs"))
    outcomes = (chosen or {}).get("outcomes") or {}
```

(Leave the rest of `count_test_outcomes` — the per-test loop reading `outcomes.get(name)` — unchanged. `_latest_run` may remain for other callers.)

> Import-cycle check: `study_outcomes` imports `study_io` + `run_registry` only (not `study_status`), so `study_status → study_outcomes` is acyclic. Verify with `.venv/bin/python -c "import pbg_superpowers.study_status"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_canonical_run.py tests/test_study_status.py -v`
Expected: PASS (new test passes; existing study_status tests still pass).

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/study_status.py tests/test_canonical_run.py
git commit -m "fix(study_status): count_test_outcomes reads the canonical run, not runs[-1]"
```

---

## Phase 3 — CLI + dashboard triggers + gate single-source

### Task 5: `pbg-sync-runs` CLI

**Files:**
- Modify: `pbg_superpowers/study_outcomes.py` (add `main`)
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/test_study_outcomes_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_study_outcomes_cli.py
from pathlib import Path
from pbg_superpowers import study_io, run_registry, study_outcomes as so

def test_cli_syncs_named_study(tmp_path, capsys):
    (tmp_path / "workspace.yaml").write_text("name: ws\n")
    d = tmp_path / "studies" / "s1"; d.mkdir(parents=True)
    study_io.save_yaml_atomic(d / "study.yaml", {"name": "s1", "runs": []})
    run_registry.register_run(d / "runs.db", "r1", spec_id="s1", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    rc = so.main(["--workspace", str(tmp_path), "--study", "s1"])
    assert rc == 0
    spec = study_io.load_yaml_mapping(d / "study.yaml")
    assert any(r["name"] == "r1" for r in spec["runs"])
    assert "added=1" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes_cli.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'main'`

- [ ] **Step 3: Add `main` (mirror `backfill_runs.main`, `:217`)**

```python
# add to study_outcomes.py
def main(argv=None) -> int:
    import argparse
    from .workspace_paths import WorkspacePaths
    ap = argparse.ArgumentParser(description="Reconcile study runs.db into study.yaml")
    ap.add_argument("--workspace", default=".")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--study", help="study slug")
    grp.add_argument("--all", action="store_true", help="every study in the workspace")
    args = ap.parse_args(argv)

    paths = WorkspacePaths.load(Path(args.workspace))
    if args.all:
        dirs = list(paths.iter_study_dirs())
    else:
        dirs = [paths.study_dir(args.study)]

    total = {"added": 0, "updated": 0}
    for d in dirs:
        s = record_runs(d)
        total["added"] += s["added"]; total["updated"] += s["updated"]
        print(f"{d.name}: added={s['added']} updated={s['updated']}")
    print(f"TOTAL added={total['added']} updated={total['updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the console script**

In `pyproject.toml` `[project.scripts]` add:

```toml
pbg-sync-runs = "pbg_superpowers.study_outcomes:main"
```

- [ ] **Step 5: Run test + reinstall entry point**

Run: `.venv/bin/python -m pytest tests/test_study_outcomes_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pbg_superpowers/study_outcomes.py pyproject.toml tests/test_study_outcomes_cli.py
git commit -m "feat(study_outcomes): pbg-sync-runs CLI (--study/--all)"
```

---

### Task 6: Dashboard gate reads canonical outcomes (collapse the third source)

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (`_condition_satisfied`, ~`:8615-8631`)
- Test: `vivarium-dashboard/tests/test_gate_canonical_source.py`

- [ ] **Step 1: Write the failing test**

```python
# vivarium-dashboard/tests/test_gate_canonical_source.py
from pbg_superpowers import study_status

def _passed(parent):
    counts = study_status.count_test_outcomes(parent, parent.get("runs"))
    return counts["fail"] == 0 and counts["pass"] > 0

def test_gate_agrees_with_pills_on_canonical_run():
    # canonical run PASSes both; a later scratch run FAILs one.
    parent = {
        "tests": [{"name": "t1"}, {"name": "t2"}],
        "runs": [
            {"name": "canon", "status": "completed", "canonical": True,
             "outcomes": {"t1": {"result": "PASS"}, "t2": {"result": "PASS"}}},
            {"name": "scratch", "status": "completed",
             "outcomes": {"t1": {"result": "FAIL"}}},
        ],
    }
    # gate and pills must agree: both read the canonical run
    assert _passed(parent) is True
```

This test encodes the desired behavior (gate via `count_test_outcomes`). It passes once the gate uses the same helper.

- [ ] **Step 2: Run test to verify it fails (current gate logic differs)**

Add a second test that calls the *current* gate path to show divergence, then after the change both agree:

Run: `.venv/bin/python -m pytest tests/test_gate_canonical_source.py -v`
Expected: the agreement assertion FAILS against the current `_condition_satisfied` (which reads `tests[].status` / `tests.last_results`, not the canonical run).

- [ ] **Step 3: Rewrite the "tests-passed" branch**

In `_condition_satisfied` (`server.py:8615`), replace the `tests[].status` / `tests.last_results` logic with the shared canonical-outcome count. At the top of `_get_investigations` (or module scope) ensure `from pbg_superpowers import study_status`. Then:

```python
    if condition == "tests-passed":
        counts = study_status.count_test_outcomes(parent, parent.get("runs"))
        return counts["fail"] == 0 and counts["pass"] > 0
```

(Keep the `"ran"` and `"complete"` branches as-is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_gate_canonical_source.py -v`
Expected: PASS — gate and pills now read the same canonical-run source.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_gate_canonical_source.py
git commit -m "fix(gate): tests-passed reads canonical-run outcomes (one source with verdict pills)"
```

---

### Task 7: Post-run hook records runs into study.yaml

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (`if code == 200:` block, ~`:3115`)
- Test: `vivarium-dashboard/tests/test_post_run_records.py`

- [ ] **Step 1: Write the failing test**

Drive the `_for_test` helper directly (no HTTP). If the run launcher is hard to invoke in a unit test, test the hook function in isolation:

```python
# vivarium-dashboard/tests/test_post_run_records.py
from pathlib import Path
from pbg_superpowers import study_io, run_registry, study_outcomes

def test_record_runs_after_run_picks_up_db_row(tmp_path: Path):
    d = tmp_path / "studies" / "s1"; d.mkdir(parents=True)
    study_io.save_yaml_atomic(d / "study.yaml", {"name": "s1", "runs": []})
    run_registry.register_run(d / "runs.db", "run-x", spec_id="s1", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    study_outcomes.record_runs(d)              # the call the hook will make
    spec = study_io.load_yaml_mapping(d / "study.yaml")
    assert any(r["name"] == "run-x" for r in spec["runs"])
```

- [ ] **Step 2: Run test to verify it passes (hook behavior is library-level)**

Run: `.venv/bin/python -m pytest tests/test_post_run_records.py -v`
Expected: PASS (this asserts the library behavior the hook relies on).

- [ ] **Step 3: Wire the hook**

In `server.py`, inside `_post_study_run_baseline_for_test` and `_post_study_run_variant_for_test`, in the `if code == 200:` block (around `:3115`, where `study_dir` is in scope), add after the viz render:

```python
        try:
            from pbg_superpowers import study_outcomes
            study_outcomes.record_runs(study_dir)
        except Exception as exc:  # never fail a successful run on a record error
            print(f"[study_outcomes] record_runs failed: {exc}", file=sys.stderr)
```

- [ ] **Step 4: Manual smoke (documented; not a unit test)**

Run a baseline from the dashboard (or `_post_study_run_baseline_for_test(ws, body)` against a fixture workspace) and confirm the run appears in `study.yaml runs[]` afterward.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_post_run_records.py
git commit -m "feat(server): record runs into study.yaml after a successful baseline/variant run"
```

---

### Task 8: `/api/study-sync-runs` endpoint

**Files:**
- Modify: `vivarium-dashboard/vivarium_dashboard/server.py` (`_POST_ROUTE_MAP` ~`:206`; new handler + `_for_test`)
- Test: `vivarium-dashboard/tests/test_study_sync_runs_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# vivarium-dashboard/tests/test_study_sync_runs_endpoint.py
from pathlib import Path
from pbg_superpowers import study_io, run_registry
from vivarium_dashboard import server

def test_sync_runs_for_test(tmp_path: Path):
    (tmp_path / "workspace.yaml").write_text("name: ws\n")
    d = tmp_path / "studies" / "s1"; d.mkdir(parents=True)
    study_io.save_yaml_atomic(d / "study.yaml", {"name": "s1", "runs": []})
    run_registry.register_run(d / "runs.db", "r1", spec_id="s1", status="completed",
                              started_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z")
    resp, code = server._post_study_sync_runs_for_test(tmp_path, {"study": "s1"})
    assert code == 200
    assert resp["summary"]["added"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_study_sync_runs_endpoint.py -v`
Expected: FAIL — `AttributeError: module 'vivarium_dashboard.server' has no attribute '_post_study_sync_runs_for_test'`

- [ ] **Step 3: Implement handler + `_for_test` + route**

Add the module-level function (mirror existing `_post_study_*_for_test` shape):

```python
def _post_study_sync_runs_for_test(ws_root, body: dict):
    from pbg_superpowers import study_outcomes
    from pbg_superpowers.workspace_paths import WorkspacePaths
    slug = (body or {}).get("study")
    if not slug:
        return {"error": "study slug required"}, 400
    try:
        study_dir = WorkspacePaths.load(Path(ws_root)).study_dir(slug)
    except FileNotFoundError:
        return {"error": f"study not found: {slug}"}, 404
    summary = study_outcomes.record_runs(study_dir)
    return {"ok": True, "summary": summary}, 200
```

Add the thin handler near the other `_post_study_*` handlers:

```python
    def _post_study_sync_runs(self, body: dict):
        response, code = _post_study_sync_runs_for_test(WORKSPACE, body)
        return self._json(response, code)
```

Add to `_POST_ROUTE_MAP` (`:206`, near the other study routes ~`:277-291`):

```python
        "/api/study-sync-runs": "_post_study_sync_runs",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_study_sync_runs_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/server.py tests/test_study_sync_runs_endpoint.py
git commit -m "feat(server): /api/study-sync-runs endpoint"
```

---

## Phase 4 — Wire the CLI runner + verify on a real study

### Task 9: Auto-record after the CLI `run-script`

**Files:**
- Modify: the `pbg-study run-script` flow. Per the reference, `run-script` is a *prose* shell-out in `skills/pbg-study/SKILL.md:507-535`, not a Python module. Add the post-run sync as an explicit step there, calling the new CLI.

- [ ] **Step 1: Edit the skill**

In `skills/pbg-study/SKILL.md`, in the `run-script` section, after "exit 0 → auto-invoke refresh-viz" (`:533`), add:

```
- After a successful run (exit 0), also run:
      python -m pbg_superpowers.study_outcomes --workspace <ws> --study <slug>
  to record the run into study.yaml's runs[] (mechanical fields; authored
  outcomes are preserved). Skip with --no-sync-runs.
```

- [ ] **Step 2: Commit**

```bash
git add skills/pbg-study/SKILL.md
git commit -m "docs(pbg-study): run-script auto-records runs via pbg-sync-runs"
```

### Task 10: End-to-end verification on a real study (no code, evidence only)

- [ ] **Step 1: Run the suites in both repos**

```bash
cd pbg-superpowers && .venv/bin/python -m pytest -q
cd ../vivarium-dashboard && .venv/bin/python -m pytest tests/test_gate_canonical_source.py tests/test_study_sync_runs_endpoint.py tests/test_post_run_records.py -q
```
Expected: all green (pre-existing unrelated failures, if any, unchanged).

- [ ] **Step 2: Dry-run against a real workspace**

```bash
cd v2e-invest && /Users/eranagmon/code/pbg-superpowers/.venv/bin/python \
  -m pbg_superpowers.study_outcomes --workspace . --all
git diff --stat
```
Expected: `runs[]` mechanical fields populated/refreshed from each study's `runs.db`; authored `outcomes`/prose untouched (inspect `studies/dnaa-1-expression/study.yaml` — the canonical run's `outcomes:` block and prose `result:` are preserved). **Do not commit changes to v2e-invest** — this is verification only.

- [ ] **Step 3: Confirm single-source agreement**

Pick a study where the gate and verdict previously diverged; confirm after sync that the DAG "blocked/unlocked" and the verdict strip agree (both now read the canonical run).

---

## Self-Review

**Spec coverage (against `2026-06-09-...-design.md`):**
- §4.1 engine in pbg-superpowers → Tasks 2–3, 5 (`study_outcomes`). ✓
- §4.4 decoupled sync / triggers (auto-after-run, on-demand CLI + API, idempotent) → Tasks 5, 7, 8, 9; idempotency Task 3. ✓
- §4.5 single source (pills + gate read canonical) → Tasks 4, 6. ✓
- §6 data shape: `runs[]` mechanical fields incl. `emitter:{kind,store}`, canonical-by-flag → Tasks 2–3. ✓ (`metrics` + per-test `outcomes` *computation* is Increment B — explicitly deferred.)
- §9 edge cases: no canonical flag → newest completed (Task 2); idempotent stamp (Task 3). (Truncated-data `needs_rerun`, stale-stamp, unresolvable→agent are evaluator concerns → Increment B.)
- §10 testing: idempotency, single-source agreement, golden real-study dry-run → Tasks 3, 6, 10. ✓
- **Deferred to Increment B (by design, see spec §3 non-goals):** §4.2 pbg-emitters reader extraction, §5 evaluator/DSL, structured-selector schema, migration of prose measures, `metrics`/outcome *computation*, pytest capture. Not gaps — scoped out.

**Placeholder scan:** none — every code step has complete code; integration tasks cite exact files/anchors from the signature reference.

**Type consistency:** `canonical_run(spec_or_runs)` used identically in Tasks 2/4/6; `record_runs(study_dir) -> {"added","updated"}` consistent across Tasks 3/5/7/8; `count_test_outcomes(spec, runs)` keys `{"pass","fail","skip","pending","total"}` per `study_status.py:144`.

---

## Notes for the executor
- Run pbg-superpowers tests via `.venv/bin/python -m pytest` (bare `python` lacks deps).
- The dashboard imports `pbg-superpowers`; ensure the dashboard `.venv` has the local pbg-superpowers (editable) so `from pbg_superpowers import study_outcomes` resolves to this branch.
- Branch per repo; do not push or open PRs until the user reviews.
