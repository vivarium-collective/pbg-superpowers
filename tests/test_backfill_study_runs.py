import sqlite3
from pbg_superpowers.run_registry import RUNS_META_DDL, latest_run
from pbg_superpowers.backfill_runs import backfill_study_runs

def test_backfill_registers_discovered_parquet(tmp_path):
    sd = tmp_path / "studies" / "s1"; (sd / "out" / "r-disk").mkdir(parents=True)
    (sd / "out" / "r-disk" / "data.parquet").write_bytes(b"PAR1")
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL); conn.close()
    n = backfill_study_runs(sd, spec_id="s1")
    assert n == 1
    lr = latest_run(db)
    assert lr["run_id"] == "r-disk"
    assert lr["emitter_path"].endswith("out/r-disk")

def test_backfill_skips_already_registered(tmp_path):
    sd = tmp_path / "studies" / "s1"; (sd / "out" / "r-disk").mkdir(parents=True)
    (sd / "out" / "r-disk" / "data.parquet").write_bytes(b"PAR1")
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL)
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,status) VALUES('r-disk','s1',1.0,'complete')")
    conn.commit(); conn.close()
    assert backfill_study_runs(sd, spec_id="s1") == 0

def test_backfill_ignores_dirs_without_partitions(tmp_path):
    sd = tmp_path / "studies" / "s1"; (sd / "out" / "notarun").mkdir(parents=True)
    (sd / "out" / "notarun" / "readme.txt").write_text("hi")
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL); conn.close()
    assert backfill_study_runs(sd, spec_id="s1") == 0

def test_backfill_no_emitter_dir(tmp_path):
    sd = tmp_path / "studies" / "s1"; sd.mkdir(parents=True)
    assert backfill_study_runs(sd, spec_id="s1") == 0
