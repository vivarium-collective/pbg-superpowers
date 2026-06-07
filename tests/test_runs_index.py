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


def test_store_emitter_type_dir_detection(tmp_path):
    from pbg_superpowers.runs_index import _store_emitter_type
    # name hints
    (tmp_path / "run_parquet").mkdir()
    assert _store_emitter_type(tmp_path / "run_parquet") == "Parquet"
    (tmp_path / "store.zarr").mkdir()
    assert _store_emitter_type(tmp_path / "store.zarr") == "XArray"
    # content scan: a plain dir containing a parquet file
    plain = tmp_path / "plain"; plain.mkdir()
    (plain / "data.parquet").write_bytes(b"PAR1")
    assert _store_emitter_type(plain) == "Parquet"
    # content scan: a plain dir containing a .zgroup
    zg = tmp_path / "zg"; zg.mkdir()
    (zg / ".zgroup").write_text("{}", encoding="utf-8")
    assert _store_emitter_type(zg) == "XArray"
    # nothing -> None
    empty = tmp_path / "empty"; empty.mkdir()
    assert _store_emitter_type(empty) is None
    # missing path -> None
    assert _store_emitter_type(tmp_path / "nope") is None


def test_list_all_runs_dir_aware_emitter(tmp_path):
    import sqlite3, yaml
    from pbg_superpowers.run_registry import RUNS_META_DDL
    from pbg_superpowers.runs_index import list_all_runs
    (tmp_path / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp_path / "investigations" / "inv-a"
    sd = inv / "studies" / "s1"; sd.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(
        yaml.safe_dump({"name": "inv-a", "studies": ["s1"]}), encoding="utf-8")
    (sd / "study.yaml").write_text("name: s1\ninvestigation: inv-a\n", encoding="utf-8")
    # run A: emitter_path is a dir named out/r_parquet (name hint)
    (sd / "out" / "r_parquet").mkdir(parents=True)
    # run B: emitter_path dir contains data.parquet (content scan)
    rb = sd / "out" / "r_plain"; rb.mkdir(parents=True)
    (rb / "data.parquet").write_bytes(b"PAR1")
    # run C: emitter_path is a .zarr-named dir
    (sd / "out" / "r_store.zarr").mkdir(parents=True)
    db = sd / "runs.db"; conn = sqlite3.connect(db); conn.executescript(RUNS_META_DDL)
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path)"
                 " VALUES('rA','s1',1,2,'complete','out/r_parquet')")
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path)"
                 " VALUES('rB','s1',1,3,'complete','out/r_plain')")
    conn.execute("INSERT INTO runs_meta(run_id,spec_id,started_at,completed_at,status,emitter_path)"
                 " VALUES('rC','s1',1,4,'complete','out/r_store.zarr')")
    conn.commit(); conn.close()
    rows = {x["run_id"]: x for x in list_all_runs(tmp_path)}
    assert rows["rA"]["emitter_type"] == "Parquet"
    assert rows["rB"]["emitter_type"] == "Parquet"
    assert rows["rC"]["emitter_type"] == "XArray"
