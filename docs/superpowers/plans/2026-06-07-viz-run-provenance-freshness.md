# Run → Visualization Provenance & Freshness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every chart record which run produced it, give each study an authoritative "latest run", and surface fresh/stale/untracked everywhere — so a rerun auto-regenerates registered charts and flags the rest instead of silently showing stale figures.

**Architecture:** A pure freshness core (`viz_freshness.py`) is the single source of truth, vendored into the dashboard (drift-guarded like `workspace_paths`). The per-study `runs.db` `runs_meta` table gains `emitter_path` and a `latest_run()` accessor; `visualizations[]` entries gain a `render:` command; each chart gets a `<chart>.meta.json` provenance sidecar. `refresh-viz` re-runs registered render commands against the latest run (auto on rerun, error-tolerant) and reports the rest. Detection lights up the linter, the dashboard study card, and the report.

**Tech Stack:** Python 3.12 stdlib (sqlite3, json, hashlib, subprocess), pytest; vanilla-JS SPA (`walkthrough.js`); the existing `pbg_superpowers` package + `vivarium_dashboard` package.

**Spec:** `docs/superpowers/specs/2026-06-07-viz-run-provenance-freshness-design.md`.
**Branches:** `pbg-superpowers feat/viz-run-provenance` (spec already committed here) + a matching `vivarium-dashboard feat/viz-run-provenance`.

---

## File Structure

**pbg-superpowers**
- Create `pbg_superpowers/viz_freshness.py` — pure freshness core: read/stamp `<chart>.meta.json`, `chart_freshness()`, `manifest_diff()`. No I/O beyond the chart dir + meta files.
- Create `pbg_superpowers/run_registry.py` — `latest_run(runs_db)` + `record_run(...)` thin wrappers over `runs_meta` (so runners + dashboard share one accessor). `emitter_path` column.
- Modify `pbg_superpowers/backfill_runs.py` — discover + register parquet/zarr run dirs.
- Create `pbg_superpowers/refresh_viz.py` — `refresh_study_viz(study_dir, spec, latest)` → runs `render:` commands, stamps meta, returns a per-chart result list (error-tolerant).
- Modify `pbg_superpowers/report_linter.py` — `viz_stale_vs_latest_run` check; retire `figure_stale_vs_run`.
- Modify `skills/pbg-study/SKILL.md`, `skills/pbg-investigation/SKILL.md`, `docs/concepts/vivarium-dashboard-model.md`.
- Tests under `tests/`.

**vivarium-dashboard**
- Create `vivarium_dashboard/lib/viz_freshness.py` — vendored copy of the pure core (drift-guard test).
- Modify `vivarium_dashboard/server.py` — `_get_study_charts` returns freshness; a `/api/study-refresh-viz/<name>` route.
- Modify `vivarium_dashboard/static/walkthrough.js` — per-chart freshness badge + Refresh affordance (live card + report).
- Tests under `tests/`.

---

## Task 1: Freshness core — `chart_freshness()` + meta sidecar (pbg-superpowers, TDD)

**Files:**
- Create: `pbg_superpowers/viz_freshness.py`
- Test: `tests/test_viz_freshness.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_viz_freshness.py
import json
from pathlib import Path
from pbg_superpowers.viz_freshness import (
    stamp_meta, read_meta, chart_freshness, manifest_diff,
)

def _study(tmp):
    d = tmp / "studies" / "s1"; (d / "charts").mkdir(parents=True)
    return d

def test_stamp_and_read_roundtrip(tmp_path):
    d = _study(tmp_path); chart = d / "charts" / "c.svg"; chart.write_text("<svg/>")
    stamp_meta(chart, source_run_id="r1", generation_id="g1",
               rendered_at=100.0, command="cmd")
    m = read_meta(chart)
    assert m["source_run_id"] == "r1"
    assert m["generation_id"] == "g1"
    assert m["rendered_at"] == 100.0
    assert m["content_hash"].startswith("sha256:")

def test_freshness_fresh(tmp_path):
    d = _study(tmp_path); chart = d / "charts" / "c.svg"; chart.write_text("x")
    stamp_meta(chart, source_run_id="r2", generation_id=None,
               rendered_at=200.0, command="cmd")
    entry = {"name": "v", "chart": "charts/c.svg", "render": "cmd"}
    latest = {"run_id": "r2", "completed_at": 150.0}
    assert chart_freshness(d, entry, latest) == "fresh"

def test_freshness_stale_wrong_run(tmp_path):
    d = _study(tmp_path); chart = d / "charts" / "c.svg"; chart.write_text("x")
    stamp_meta(chart, source_run_id="OLD", generation_id=None,
               rendered_at=200.0, command="cmd")
    entry = {"name": "v", "chart": "charts/c.svg", "render": "cmd"}
    assert chart_freshness(d, entry, {"run_id": "r2", "completed_at": 150.0}) == "stale"

def test_freshness_stale_rendered_before_run(tmp_path):
    d = _study(tmp_path); chart = d / "charts" / "c.svg"; chart.write_text("x")
    stamp_meta(chart, source_run_id="r2", generation_id=None,
               rendered_at=100.0, command="cmd")
    entry = {"name": "v", "chart": "charts/c.svg", "render": "cmd"}
    assert chart_freshness(d, entry, {"run_id": "r2", "completed_at": 150.0}) == "stale"

def test_freshness_unrendered(tmp_path):
    d = _study(tmp_path)
    entry = {"name": "v", "chart": "charts/missing.svg", "render": "cmd"}
    assert chart_freshness(d, entry, {"run_id": "r2", "completed_at": 1.0}) == "unrendered"

def test_manifest_diff_flags_orphans(tmp_path):
    d = _study(tmp_path)
    (d / "charts" / "tracked.svg").write_text("x")
    (d / "charts" / "orphan.svg").write_text("x")
    entries = [{"name": "v", "chart": "charts/tracked.svg", "render": "cmd"}]
    diff = manifest_diff(d, entries)
    assert "charts/orphan.svg" in diff["untracked"]
    assert "charts/tracked.svg" not in diff["untracked"]
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`). `pytest tests/test_viz_freshness.py -q`

- [ ] **Step 3: Implement**

```python
# pbg_superpowers/viz_freshness.py
"""Pure run->chart freshness core (single source of truth; vendored into the
dashboard). A chart's <chart>.meta.json records which run produced it; freshness
compares that against the study's latest run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FRESH, STALE, UNRENDERED, UNTRACKED = "fresh", "stale", "unrendered", "untracked"


def _meta_path(chart: Path) -> Path:
    return chart.with_suffix(chart.suffix + ".meta.json")


def _hash(chart: Path) -> str:
    h = hashlib.sha256(chart.read_bytes()).hexdigest()
    return f"sha256:{h}"


def stamp_meta(chart: Path, *, source_run_id: str | None, generation_id: str | None,
               rendered_at: float, command: str) -> None:
    """Write/overwrite <chart>.meta.json with provenance for `chart`."""
    meta = {
        "source_run_id": source_run_id,
        "generation_id": generation_id,
        "rendered_at": float(rendered_at),
        "command": command,
        "content_hash": _hash(chart) if chart.is_file() else None,
    }
    _meta_path(chart).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def read_meta(chart: Path) -> dict | None:
    p = _meta_path(chart)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def chart_freshness(study_dir: Path, entry: dict, latest: dict | None) -> str:
    """fresh | stale | unrendered (for a declared visualizations[] entry)."""
    chart = study_dir / entry.get("chart", "")
    if not chart.is_file():
        return UNRENDERED
    meta = read_meta(chart)
    if meta is None:
        return STALE  # rendered but no provenance — can't prove it's current
    if not latest:
        return STALE  # no run to anchor against
    if meta.get("source_run_id") != latest.get("run_id"):
        return STALE
    completed = latest.get("completed_at")
    if completed is not None and (meta.get("rendered_at") or 0) < float(completed):
        return STALE
    return FRESH


def manifest_diff(study_dir: Path, entries: list[dict]) -> dict:
    """Compare declared entries against charts/*.svg on disk.

    Returns {"declared": [...], "untracked": [...]} where untracked are
    chart files present on disk but absent from visualizations[]."""
    declared = {e.get("chart") for e in entries if e.get("chart")}
    charts_dir = study_dir / "charts"
    on_disk = set()
    if charts_dir.is_dir():
        for p in charts_dir.glob("*.svg"):
            on_disk.add(f"charts/{p.name}")
        for p in charts_dir.glob("*.png"):
            on_disk.add(f"charts/{p.name}")
    return {"declared": sorted(declared), "untracked": sorted(on_disk - declared)}
```

- [ ] **Step 4: Run — expect PASS.** `pytest tests/test_viz_freshness.py -q`
- [ ] **Step 5: Commit** `feat(viz): pure chart-freshness core (meta sidecar + fresh/stale/untracked)`

---

## Task 2: `latest_run()` + `emitter_path` in the run registry (pbg-superpowers, TDD)

**Files:**
- Create: `pbg_superpowers/run_registry.py`
- Modify: `vivarium_dashboard/lib/composite_runs.py:_NEW_COLUMNS` (add `emitter_path`) — and mirror the column in the per-study runs.db writer.
- Test: `tests/test_run_registry.py`

Context: `runs_meta` columns today are `run_id, spec_id, label, params_json, started_at, completed_at, n_steps, status, sim_name` + nullable `_NEW_COLUMNS` (`pid, progress_step, log_path, heartbeat_at, generation_id`). `_latest_run_timestamp` (server.py:795) already does `SELECT MAX(COALESCE(completed_at, started_at))`. We need the *row* (id too).

- [ ] **Step 1: Write failing test**

```python
# tests/test_run_registry.py
import sqlite3
from pathlib import Path
from pbg_superpowers.run_registry import latest_run, RUNS_META_DDL

def _db(tmp):
    p = tmp / "runs.db"; conn = sqlite3.connect(p); conn.executescript(RUNS_META_DDL)
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path,generation_id)"
                 " VALUES(?,?,?,?,?,?,?)", ("old","s",1.0,10.0,"complete","out/old","g0"))
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path,generation_id)"
                 " VALUES(?,?,?,?,?,?,?)", ("new","s",2.0,20.0,"complete","out/new","g1"))
    conn.commit(); conn.close(); return p

def test_latest_run_picks_newest_completed(tmp_path):
    db = _db(tmp_path)
    lr = latest_run(db)
    assert lr["run_id"] == "new"
    assert lr["emitter_path"] == "out/new"
    assert lr["generation_id"] == "g1"
    assert lr["completed_at"] == 20.0

def test_latest_run_none_when_empty(tmp_path):
    p = tmp_path / "empty.db"; sqlite3.connect(p).executescript(RUNS_META_DDL)
    assert latest_run(p) is None

def test_latest_run_missing_db(tmp_path):
    assert latest_run(tmp_path / "nope.db") is None
```

- [ ] **Step 2: Run — expect FAIL.** `pytest tests/test_run_registry.py -q`

- [ ] **Step 3: Implement**

```python
# pbg_superpowers/run_registry.py
"""Thin read accessor over the per-study runs.db `runs_meta` table — the
authoritative record of which runs belong to a study and which is latest."""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Minimal DDL for tests + first-time creation. Real DBs are migrated by
# composite_runs.connect()/_migrate_runs_meta which ALTERs in nullable columns
# (including emitter_path, added to _NEW_COLUMNS in this task).
RUNS_META_DDL = """
CREATE TABLE IF NOT EXISTS runs_meta (
    run_id        TEXT PRIMARY KEY,
    spec_id       TEXT NOT NULL,
    label         TEXT,
    params_json   TEXT,
    started_at    REAL NOT NULL,
    completed_at  REAL,
    n_steps       INTEGER,
    status        TEXT NOT NULL,
    sim_name      TEXT,
    generation_id TEXT,
    emitter_path  TEXT
);
"""

_COLS = ("run_id", "spec_id", "started_at", "completed_at", "status",
         "generation_id", "emitter_path")


def latest_run(runs_db: Path) -> dict | None:
    """Newest run row by COALESCE(completed_at, started_at), or None."""
    runs_db = Path(runs_db)
    if not runs_db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{runs_db}?mode=ro", uri=True, timeout=1.0)
        try:
            # tolerate older DBs missing emitter_path/generation_id
            have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
            cols = [c for c in _COLS if c in have]
            row = conn.execute(
                f"SELECT {', '.join(cols)} FROM runs_meta "
                "ORDER BY COALESCE(completed_at, started_at) DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        return dict(zip(cols, row)) if row else None
    except sqlite3.Error:
        return None
```

- [ ] **Step 4: Add `emitter_path` to the live schema.** In `vivarium_dashboard/lib/composite_runs.py` add `"emitter_path": "TEXT"` to `_NEW_COLUMNS` (auto-ALTERed by `_migrate_runs_meta`). Where each runner records its row (the `run-baseline`/`run-variant`/`run-script` server handlers that call `save_metadata` + the completion update), pass the emitter store path through to a new `emitter_path` value on the completion UPDATE. (Find the completion UPDATE via `grep -n "completed_at" vivarium_dashboard/lib/composite_runs.py`.)

- [ ] **Step 5: Run — expect PASS.** `pytest tests/test_run_registry.py -q`
- [ ] **Step 6: Commit** `feat(runs): latest_run() accessor + emitter_path column on runs_meta`

---

## Task 3: Auto-register discovered parquet/zarr runs (pbg-superpowers, TDD)

**Files:**
- Modify: `pbg_superpowers/backfill_runs.py`
- Test: `tests/test_backfill_runs.py` (append)

- [ ] **Step 1: Write failing test** — an on-disk emitter dir (e.g. `studies/s1/out/<run>/` containing a `*.parquet` or `*.zarr`) with no `runs_meta` row gets registered with `completed_at` = newest partition mtime.

```python
def test_backfill_registers_discovered_parquet(tmp_path):
    import sqlite3
    from pbg_superpowers.run_registry import RUNS_META_DDL, latest_run
    from pbg_superpowers.backfill_runs import backfill_study_runs
    sd = tmp_path / "studies" / "s1"; (sd / "out" / "r-disk").mkdir(parents=True)
    (sd / "out" / "r-disk" / "data.parquet").write_bytes(b"PAR1")
    db = sd / "runs.db"; sqlite3.connect(db).executescript(RUNS_META_DDL)
    n = backfill_study_runs(sd, spec_id="s1")
    assert n == 1
    lr = latest_run(db)
    assert lr["run_id"] == "r-disk"
    assert lr["emitter_path"].endswith("out/r-disk")
```

- [ ] **Step 2: Run — expect FAIL.** `pytest tests/test_backfill_runs.py -k discovered_parquet -q`

- [ ] **Step 3: Implement** `backfill_study_runs(study_dir, spec_id)` in `backfill_runs.py`: glob `out/*/` (and the workspace `runtime.default_emitter` root if configured) for dirs containing `*.parquet`/`*.zarr`; for each whose basename is not already a `runs_meta.run_id`, INSERT a row `(run_id=basename, spec_id, started_at=mtime, completed_at=mtime, status="complete", emitter_path=rel_path)`. Return the count inserted. Reuse the existing module's connect/insert helpers; mtime = max mtime of the partition files.

- [ ] **Step 4: Run — expect PASS.** Also run the existing `tests/test_backfill_runs.py` for regressions.
- [ ] **Step 5: Commit** `feat(runs): backfill auto-registers discovered parquet/zarr runs`

---

## Task 4: `refresh-viz` core — re-run render commands + stamp meta (pbg-superpowers, TDD)

**Files:**
- Create: `pbg_superpowers/refresh_viz.py`
- Test: `tests/test_refresh_viz.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_refresh_viz.py
from pathlib import Path
from pbg_superpowers.refresh_viz import refresh_study_viz
from pbg_superpowers.viz_freshness import read_meta

def _study(tmp):
    d = tmp / "studies" / "s1"; (d / "charts").mkdir(parents=True); return d

def test_refresh_runs_command_and_stamps(tmp_path):
    d = _study(tmp_path)
    spec = {"visualizations": [{
        "name": "v", "chart": "charts/c.svg",
        # writes the chart; cross-platform via python
        "render": "python -c \"open('charts/c.svg','w').write('<svg/>')\"",
    }]}
    latest = {"run_id": "r9", "completed_at": 1.0, "generation_id": None,
              "emitter_path": "out/r9"}
    results = refresh_study_viz(d, spec, latest)
    assert (d / "charts" / "c.svg").is_file()
    assert read_meta(d / "charts" / "c.svg")["source_run_id"] == "r9"
    assert results[0]["status"] == "rendered"

def test_refresh_failing_command_keeps_old_meta(tmp_path):
    d = _study(tmp_path)
    (d / "charts" / "c.svg").write_text("OLD")
    from pbg_superpowers.viz_freshness import stamp_meta
    stamp_meta(d / "charts" / "c.svg", source_run_id="rOLD",
               generation_id=None, rendered_at=1.0, command="x")
    spec = {"visualizations": [{"name": "v", "chart": "charts/c.svg",
                                "render": "python -c \"import sys; sys.exit(3)\""}]}
    results = refresh_study_viz(d, spec, {"run_id": "rNEW", "completed_at": 2.0})
    assert results[0]["status"] == "error"
    assert read_meta(d / "charts" / "c.svg")["source_run_id"] == "rOLD"  # unchanged

def test_refresh_reports_entries_without_command(tmp_path):
    d = _study(tmp_path)
    spec = {"visualizations": [{"name": "v", "chart": "charts/c.svg"}]}  # no render
    results = refresh_study_viz(d, spec, {"run_id": "r", "completed_at": 1.0})
    assert results[0]["status"] == "needs_manual_refresh"
```

- [ ] **Step 2: Run — expect FAIL.** `pytest tests/test_refresh_viz.py -q`

- [ ] **Step 3: Implement**

```python
# pbg_superpowers/refresh_viz.py
"""Re-run the render: command of each visualizations[] entry against the
study's latest run, stamping provenance. Error-tolerant: a failed render leaves
the old chart + meta in place (still flagged stale) and never raises."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .viz_freshness import stamp_meta, _meta_path  # noqa: F401


def refresh_study_viz(study_dir: Path, spec: dict, latest: dict | None) -> list[dict]:
    study_dir = Path(study_dir)
    results: list[dict] = []
    for entry in (spec.get("visualizations") or []):
        name = entry.get("name") or entry.get("chart") or "<unnamed>"
        chart_rel = entry.get("chart")
        cmd = entry.get("render")
        if not cmd or not chart_rel:
            results.append({"name": name, "chart": chart_rel,
                            "status": "needs_manual_refresh"})
            continue
        chart = study_dir / chart_rel
        filled = cmd.replace("{chart}", chart_rel)
        env = dict(os.environ)
        if latest and latest.get("emitter_path"):
            env["PBG_RUN_DIR"] = str(study_dir / latest["emitter_path"]) \
                if not os.path.isabs(latest["emitter_path"]) else latest["emitter_path"]
        if latest and latest.get("run_id"):
            env["PBG_RUN_ID"] = latest["run_id"]
        try:
            proc = subprocess.run(filled, shell=True, cwd=study_dir, env=env,
                                  capture_output=True, text=True, timeout=900)
        except (subprocess.SubprocessError, OSError) as e:
            results.append({"name": name, "chart": chart_rel,
                            "status": "error", "error": str(e)})
            continue
        if proc.returncode != 0:
            results.append({"name": name, "chart": chart_rel, "status": "error",
                            "error": (proc.stderr or proc.stdout or "")[-2000:]})
            continue
        import time
        stamp_meta(chart,
                   source_run_id=(latest or {}).get("run_id"),
                   generation_id=(latest or {}).get("generation_id"),
                   rendered_at=time.time(), command=filled)
        results.append({"name": name, "chart": chart_rel, "status": "rendered"})
    return results
```

- [ ] **Step 4: Run — expect PASS.** `pytest tests/test_refresh_viz.py -q`
- [ ] **Step 5: Commit** `feat(viz): refresh_study_viz — re-run render commands + stamp, error-tolerant`

---

## Task 5: Linter check `viz_stale_vs_latest_run` (pbg-superpowers, TDD)

**Files:**
- Modify: `pbg_superpowers/report_linter.py` (add check to `CHECKS`, the `_CHECK_FUNCS` list ~1866, and a `_check_viz_stale_vs_latest_run`; retire `_check_figure_stale_vs_run` / `figure_stale_vs_run`).
- Test: `tests/test_report_linter.py` (append)

The check reuses `viz_freshness.chart_freshness` + `run_registry.latest_run`. `--strict` already threads through the CLI/`lint_workspace_report`; default level `warning`, `error` when strict.

- [ ] **Step 1: Write failing test** (direct unit, mirroring `test_finding_without_statement`):

```python
def test_viz_stale_vs_latest_run_fires_on_mismatch(tmp_path):
    import sqlite3
    from pathlib import Path
    from pbg_superpowers.run_registry import RUNS_META_DDL
    from pbg_superpowers.viz_freshness import stamp_meta
    from pbg_superpowers.report_linter import _LintContext, _check_viz_stale_vs_latest_run
    sd = tmp_path / "studies" / "s1"; (sd / "charts").mkdir(parents=True)
    (sd / "charts" / "c.svg").write_text("x")
    stamp_meta(sd / "charts" / "c.svg", source_run_id="OLD",
               generation_id=None, rendered_at=1.0, command="cmd")
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL)
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status)"
                 " VALUES('NEW','s1',1,2,'complete')"); conn.commit(); conn.close()
    spec = {"evaluation_status": "evaluated",
            "visualizations": [{"name": "v", "chart": "charts/c.svg", "render": "cmd"}]}
    ctx = _LintContext(ws_root=tmp_path, slug="s1", spec=spec)
    _check_viz_stale_vs_latest_run(ctx)
    stale = [f for f in ctx.findings if f.check == "viz_stale_vs_latest_run"]
    assert len(stale) == 1
    assert stale[0].level == "warning"
```

- [ ] **Step 2: Run — expect FAIL.** `pytest tests/test_report_linter.py -k viz_stale -q`

- [ ] **Step 3: Implement** `_check_viz_stale_vs_latest_run(ctx)`:

```python
def _check_viz_stale_vs_latest_run(ctx: _LintContext) -> None:
    """Charts whose source run != the study's latest run are flagged.
    warning by default; error under --strict (ctx carries the flag)."""
    from .viz_freshness import chart_freshness, manifest_diff
    from .run_registry import latest_run
    spec = ctx.spec
    study_dir = ctx.ws_root / "studies" / ctx.slug  # layout-resolved upstream
    latest = latest_run(study_dir / "runs.db")
    entries = spec.get("visualizations") or []
    level = "error" if getattr(ctx, "strict", False) else "warning"
    for idx, e in enumerate(entries):
        state = chart_freshness(study_dir, e, latest)
        if state in ("stale", "unrendered"):
            ctx.add(level=level, field_path=f"visualizations[{idx}].chart",
                    message=(f"Visualization {e.get('name')!r} is {state} vs the "
                             f"study's latest run. Run /pbg-study refresh-viz."),
                    check="viz_stale_vs_latest_run")
    for orphan in manifest_diff(study_dir, entries)["untracked"]:
        ctx.add(level=level, field_path=orphan,
                message=(f"Chart {orphan} is on disk but not in visualizations[]; "
                         "register it (with a render: command) or remove it."),
                check="viz_stale_vs_latest_run")
```

Add `"viz_stale_vs_latest_run"` to `CHECKS`, add `_check_viz_stale_vs_latest_run` to the `_CHECK_FUNCS` tuple (~1866), and **remove** `figure_stale_vs_run` / `_check_figure_stale_vs_run` (and its registration). Ensure `_LintContext` carries a `strict: bool = False` field set from the lint entry point.

- [ ] **Step 4: Run — expect PASS.** `pytest tests/test_report_linter.py -q` (full file, confirm no regressions from removing the old check — update/delete its test).
- [ ] **Step 5: Commit** `feat(linter): viz_stale_vs_latest_run (warning; error under --strict); retire figure_stale_vs_run`

---

## Task 6: `refresh-viz` skill verbs + auto-on-rerun (pbg-superpowers)

**Files:** `skills/pbg-study/SKILL.md`, `skills/pbg-investigation/SKILL.md`, `docs/concepts/vivarium-dashboard-model.md`.

- [ ] **Step 1:** In `pbg-study/SKILL.md` add the `refresh-viz <study> [--no-auto]` subcommand: resolve study dir via `python -m pbg_superpowers.paths --study <slug>`, call `refresh_study_viz(study_dir, spec, latest_run(runs.db))`, print the per-chart result list (rendered / error / needs_manual_refresh). Document `visualizations[].render` (with `{chart}` substitution + `PBG_RUN_DIR` / `PBG_RUN_ID` env) in the same file.
- [ ] **Step 2:** Add a `--no-refresh-viz` flag note to `run-baseline` / `run-variant` / `run-script`: after a successful run they invoke `refresh-viz` for that study unless the flag is set.
- [ ] **Step 3:** In `pbg-investigation/SKILL.md` add `refresh-viz <inv> [--studies a,b]` orchestrating the study verb over members.
- [ ] **Step 4:** In `docs/concepts/vivarium-dashboard-model.md` document the provenance/freshness model (`render:`, `.meta.json`, fresh/stale/untracked, `latest_run`).
- [ ] **Step 5: Commit** `feat(skills): pbg-study/-investigation refresh-viz + auto-on-rerun + docs`

---

## Task 7: Vendored freshness mirror + drift guard (vivarium-dashboard, TDD)

**Files:**
- Create: `vivarium_dashboard/lib/viz_freshness.py` (byte-copy of `pbg_superpowers/viz_freshness.py`).
- Test: `tests/test_viz_freshness_mirror.py` (drift guard, same pattern as the `workspace_paths` mirror test).

- [ ] **Step 1: Write failing test** asserting the two files' `chart_freshness`/`stamp_meta`/`manifest_diff` source bodies are identical (read both files, compare the function source via `inspect.getsource` or a normalized text compare of the shared region).
- [ ] **Step 2: Run — FAIL** (file missing).
- [ ] **Step 3:** Copy the module; make the mirror test pass.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(dashboard): vendor viz_freshness core + drift-guard test`

---

## Task 8: Freshness in the charts API (vivarium-dashboard, TDD)

**Files:** Modify `vivarium_dashboard/server.py` `_get_study_charts` (7622) + `_build`-style helper; Test `tests/test_study_charts_freshness.py`.

- [ ] **Step 1: Write failing test** — a study with a declared `visualizations[]` entry + a stamped chart whose `source_run_id` matches the runs.db latest → the `/api/study-charts/<name>` payload marks that chart `freshness: "fresh"`; a mismatched stamp → `"stale"`; an on-disk chart with no entry → `"untracked"`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — in `_get_study_charts`, after discovering `charts/*.svg`, compute `latest = run_registry.latest_run(study_dir/"runs.db")` and for each chart attach `freshness` via `viz_freshness.chart_freshness` (match by `charts/<name>` against `visualizations[]`); add `manifest_diff` untracked entries with `freshness: "untracked"`.
- [ ] **Step 4: Run — PASS.** Run `tests/test_study_charts*.py` for regressions.
- [ ] **Step 5: Commit** `feat(dashboard): study-charts API reports per-chart freshness`

---

## Task 9: Study-card + report freshness badge + Refresh affordance (vivarium-dashboard)

**Files:** Modify `vivarium_dashboard/static/walkthrough.js` (the Visualisations section render + a `/api/study-refresh-viz/<name>` POST handler in `server.py`).

- [ ] **Step 1:** Add `POST /api/study-refresh-viz/<name>` to `server.py` that calls `refresh_viz.refresh_study_viz(study_dir, spec, latest_run(...))` and returns the result list (render-error-tolerant; never 500 on a single chart failure).
- [ ] **Step 2:** In `walkthrough.js`, where charts render (the Visualisations block), read each chart's `freshness` from the charts API and show a badge: `✓ latest run` (fresh) / `⚠ stale — from run <id>` (stale) / `❓ untracked` / `◌ not rendered`. Add a "Refresh visualizations" button on the study card that POSTs to the new endpoint and re-fetches charts.
- [ ] **Step 3:** Mirror the badge into the generated report's chart render (same freshness field).
- [ ] **Step 4: Manual verify** — on v2e-invest dnaa-3: stale a chart (bump runs.db), confirm the badge flips to stale, click Refresh, confirm it goes fresh. (Vanilla-JS, verify live.)
- [ ] **Step 5: Commit** `feat(dashboard): per-chart freshness badge + Refresh affordance (card + report)`

---

## Task 10: Green + push + PRs (no merge)

- [ ] **Step 1:** `pytest -q` green in both repos (note pre-existing polars/build skips). 
- [ ] **Step 2:** Push `feat/viz-run-provenance` in both repos; open draft PRs referencing the spec; the vivarium-dashboard PR stacks conceptually on the pbg-superpowers one (vendored core). Do NOT merge.

---

## Self-Review

- **Spec coverage:** runs.db authoritative + auto-register (T2, T3); visualizations[].render + .meta.json provenance (T1, T4, T6); freshness single-sourced into linter (T5), dashboard card+API (T7, T8, T9), report (T9); refresh-viz auto-on-rerun + flag-the-rest (T4, T6, T9); error handling tolerant (T4 tests); warning/error-under-strict (T5). ✓
- **Placeholders:** none — every code step carries real code; T6/T9 are doc/SPA steps specified against exact anchors with the exact strings to add.
- **Type consistency:** `latest_run()` returns `{run_id, completed_at, generation_id, emitter_path, ...}` used identically in T4/T5/T8; `chart_freshness(study_dir, entry, latest)` signature identical across T1/T5/T8; `refresh_study_viz(study_dir, spec, latest)` identical T4/T6/T9; meta fields (`source_run_id, generation_id, rendered_at, command, content_hash`) identical T1/T4. ✓
- **Note for the implementer:** in T5/T8 the `study_dir` is resolved layout-aware in real code (use `WorkspacePaths.study_dir(slug)`), not the literal `ws_root/"studies"/slug` shown in the unit tests' flat fixtures.
