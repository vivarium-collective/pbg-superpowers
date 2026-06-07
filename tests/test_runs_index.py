from pbg_superpowers.runs_index import emitter_type_of

def test_emitter_types():
    assert emitter_type_of("out/r/data.parquet") == "Parquet"
    assert emitter_type_of("out/r/store.zarr") == "XArray"
    assert emitter_type_of("studies/s/runs.db") == "SQLite"
    assert emitter_type_of("") == "SQLite"
    assert emitter_type_of(None) == "SQLite"
    assert emitter_type_of("out/r") == "SQLite"


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
