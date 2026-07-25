"""Tests for viva_superpowers.backfill_runs — register on-disk emitter runs.

Covers the dashboard-blindspot case: a bespoke sweep persists a zarr/parquet
store under .pbg/runs/<id>/ but never writes a `simulations` row, so the Sim DB
shows nothing. backfill() walks the stores, inserts the missing rows (resolving
study/investigation from the run_id), and completes stale `running` rows.
"""
import sqlite3
from pathlib import Path

from viva_superpowers.backfill_runs import backfill


def _make_ws(tmp_path: Path) -> Path:
    ws = tmp_path
    runs = ws / ".pbg" / "runs"
    runs.mkdir(parents=True)
    # a zarr run on disk that is NOT recorded in the DB
    (runs / "pdmp-03-abc-2d" / "store.zarr").mkdir(parents=True)
    # study -> investigation map
    inv = ws / "investigations" / "pdmp"
    inv.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(
        "name: pdmp\nstudies:\n  - pdmp-03-inference\n", encoding="utf-8")
    # run DB with a simulations table + one stale 'running' row (completed_at NULL)
    db = ws / ".pbg" / "composite-runs.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE simulations (simulation_id TEXT PRIMARY KEY, name TEXT, "
        "started_at TEXT, completed_at TEXT, study_slug TEXT, "
        "investigation_slug TEXT, metadata TEXT)")
    conn.execute(
        "INSERT INTO simulations (simulation_id, name, started_at, completed_at) "
        "VALUES ('stale-run', 'stale-run', '2026-01-01T00:00:00Z', NULL)")
    conn.commit()
    conn.close()
    return ws


def test_backfill_inserts_and_resolves(tmp_path):
    res = backfill(_make_ws(tmp_path))
    ins = {r["run_id"]: r for r in res["inserted"]}
    assert "pdmp-03-abc-2d" in ins
    assert ins["pdmp-03-abc-2d"]["emitter"] == "xarray"
    assert ins["pdmp-03-abc-2d"]["study"] == "pdmp-03-inference"   # >=2 shared segments
    assert ins["pdmp-03-abc-2d"]["investigation"] == "pdmp"
    assert "stale-run" in res["completed_stale"]


def test_backfill_idempotent(tmp_path):
    ws = _make_ws(tmp_path)
    backfill(ws)
    res2 = backfill(ws)
    assert "pdmp-03-abc-2d" in res2["skipped"]
    assert res2["inserted"] == []


def test_backfill_dry_run_writes_nothing(tmp_path):
    ws = _make_ws(tmp_path)
    res = backfill(ws, dry_run=True)
    assert any(r["run_id"] == "pdmp-03-abc-2d" for r in res["inserted"])
    conn = sqlite3.connect(str(ws / ".pbg" / "composite-runs.db"))
    n = conn.execute(
        "SELECT COUNT(*) FROM simulations WHERE simulation_id='pdmp-03-abc-2d'"
    ).fetchone()[0]
    conn.close()
    assert n == 0


def test_backfill_missing_db_is_graceful(tmp_path):
    res = backfill(tmp_path)
    assert "error" in res
