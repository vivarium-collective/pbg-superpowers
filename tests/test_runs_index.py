from pbg_superpowers.runs_index import emitter_type_of

def test_emitter_types():
    assert emitter_type_of("out/r/data.parquet") == "Parquet"
    assert emitter_type_of("out/r/store.zarr") == "XArray"
    assert emitter_type_of("studies/s/runs.db") == "SQLite"
    assert emitter_type_of("") == "SQLite"
    assert emitter_type_of(None) == "SQLite"
    assert emitter_type_of("out/r") == "SQLite"
