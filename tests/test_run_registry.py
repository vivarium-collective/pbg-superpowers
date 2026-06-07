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

def test_latest_run_tolerates_db_without_emitter_path(tmp_path):
    # An older runs.db missing emitter_path/generation_id must still work.
    p = tmp_path / "legacy.db"; conn = sqlite3.connect(p)
    conn.executescript("CREATE TABLE runs_meta(run_id TEXT PRIMARY KEY, spec_id TEXT NOT NULL,"
                       " started_at REAL NOT NULL, completed_at REAL, status TEXT NOT NULL);")
    conn.execute("INSERT INTO runs_meta VALUES('r','s',1.0,5.0,'complete')")
    conn.commit(); conn.close()
    lr = latest_run(p)
    assert lr["run_id"] == "r"
    assert "emitter_path" not in lr  # column absent → key omitted
