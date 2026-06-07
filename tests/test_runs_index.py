from pbg_superpowers.runs_index import emitter_type_of

def test_emitter_types():
    assert emitter_type_of("out/r/data.parquet") == "Parquet"
    assert emitter_type_of("out/r/store.zarr") == "XArray"
    assert emitter_type_of("studies/s/runs.db") == "SQLite"
    assert emitter_type_of("") == "SQLite"
    assert emitter_type_of(None) == "SQLite"
    assert emitter_type_of("out/r") == "SQLite"


def test_list_all_runs_tags_and_includes_parquet(tmp_path):
    import sqlite3, yaml
    from pbg_superpowers.run_registry import RUNS_META_DDL
    from pbg_superpowers.runs_index import list_all_runs
    (tmp_path / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp_path / "investigations" / "inv-a"
    sd = inv / "studies" / "s1"; sd.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(
        yaml.safe_dump({"name": "inv-a", "studies": ["s1"]}), encoding="utf-8")
    (sd / "study.yaml").write_text("name: s1\ninvestigation: inv-a\n", encoding="utf-8")
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL)
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path)"
                 " VALUES('r1','s1',1,2,'complete','out/r1/data.parquet')")
    conn.commit(); conn.close()
    rows = list_all_runs(tmp_path)
    r = [x for x in rows if x["run_id"] == "r1"][0]
    assert r["investigation"] == "inv-a"
    assert r["study"] == "s1"
    assert r["emitter_type"] == "Parquet"
