import json
from pathlib import Path

from viva_superpowers.run_registry import register_run
from viva_superpowers import provenance


# --- figure -> run_id ------------------------------------------------------

def test_run_id_from_meta_prefers_run_id_key(tmp_path):
    meta = tmp_path / "fig.png.meta.json"
    meta.write_text(json.dumps({"run_id": "exp_x", "source_run_id": "legacy"}))
    assert provenance.run_id_from_meta(meta) == "exp_x"


def test_run_id_from_meta_falls_back_to_source_run(tmp_path):
    meta = tmp_path / "fig.png.meta.json"
    meta.write_text(json.dumps({"source_run_id": "legacy_run"}))
    assert provenance.run_id_from_meta(meta) == "legacy_run"


def test_resolve_run_id_from_png_sibling_meta(tmp_path):
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG")
    (tmp_path / "fig.png.meta.json").write_text(json.dumps({"run_id": "exp_y"}))
    rid, meta = provenance.resolve_run_id(str(png))
    assert rid == "exp_y"
    assert meta == Path(str(png) + ".meta.json")


def test_resolve_run_id_bare_id(tmp_path):
    rid, meta = provenance.resolve_run_id("just_a_run_id")
    assert rid == "just_a_run_id"
    assert meta is None


# --- run_id -> params via registry -----------------------------------------

def test_lookup_params_from_explicit_runs_db(tmp_path):
    db = tmp_path / "runs.db"
    cfg = {"perturbations": {"TU00259[c]": 1.7e-3}, "seed": 1, "generations": 8}
    register_run(db, "exp_z", params=cfg, status="complete")
    params, source = provenance.lookup_params("exp_z", runs_db=db)
    assert source == "registry"
    assert params == cfg


def test_lookup_params_searches_workspace(tmp_path):
    study = tmp_path / "studies" / "dnaa-1"
    study.mkdir(parents=True)
    db = study / "runs.db"
    cfg = {"seed": 3}
    register_run(db, "exp_w", params=cfg)
    params, source = provenance.lookup_params("exp_w", workspace=tmp_path)
    assert source == "registry"
    assert params == cfg


def test_lookup_params_not_found(tmp_path):
    params, source = provenance.lookup_params("nope", workspace=tmp_path)
    assert params is None
    assert source == "not-found"


# --- run_id -> params via parquet fallback ---------------------------------

def test_parquet_configuration_fallback(tmp_path):
    rid = "dnaa_run"
    cfg_root = (tmp_path / "out" / rid / rid / "configuration"
                / f"experiment_id={rid}")
    part = cfg_root / "variant=0" / "lineage_seed=7" / "generation=3"
    part.mkdir(parents=True)
    (part / "data.parquet").write_bytes(b"PAR1")
    params, source = provenance.lookup_params(rid, workspace=tmp_path)
    assert source == "parquet"
    assert params["experiment_id"] == rid
    assert params["lineage_seeds"] == ["7"]
    assert params["generations"] == ["3"]


# --- end-to-end CLI --------------------------------------------------------

def test_main_text_output(tmp_path, capsys):
    db = tmp_path / "runs.db"
    register_run(db, "exp_cli",
                 params={"perturbations": {"TU00259[c]": 1.7e-3}, "seed": 1},
                 status="complete")
    rc = provenance.main(["exp_cli", "--runs-db", str(db),
                          "--workspace", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run_id: exp_cli" in out
    assert "TU00259[c] = 0.0017" in out
    assert "source: registry" in out


def test_main_json_output(tmp_path, capsys):
    db = tmp_path / "runs.db"
    register_run(db, "exp_json", params={"seed": 5}, status="complete")
    rc = provenance.main(["exp_json", "--runs-db", str(db), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "exp_json"
    assert payload["params"]["seed"] == 5


def test_main_unresolvable_meta(tmp_path, capsys):
    rc = provenance.main([str(tmp_path / "missing.png")])
    assert rc == 2
    assert "could not resolve" in capsys.readouterr().out.lower()
