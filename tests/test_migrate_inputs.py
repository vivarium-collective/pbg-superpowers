from pathlib import Path
import yaml
from pbg_superpowers.migrate_inputs import plan_inputs_migration

def _ws(tmp):
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    (tmp / "datasets").mkdir()
    return tmp

def _inv(tmp, slug, studies):
    d = tmp / "investigations" / slug
    (d / "studies").mkdir(parents=True)
    (d / "investigation.yaml").write_text(
        yaml.safe_dump({"name": slug, "studies": studies}), encoding="utf-8")
    for s in studies:
        sd = d / "studies" / s; sd.mkdir(parents=True, exist_ok=True)
        (sd / "study.yaml").write_text(f"name: {s}\n", encoding="utf-8")
    return d

def test_single_use_dataset_assigned(tmp_path):
    ws = _ws(tmp_path)
    (ws / "datasets" / "beulig.csv").write_text("x")
    inv = _inv(ws, "inv-a", ["s1"])
    # s1 references beulig
    (inv / "studies" / "s1" / "study.yaml").write_text(
        "name: s1\nnotes: validate against beulig.csv\n", encoding="utf-8")
    _inv(ws, "inv-b", ["s2"])
    plan = plan_inputs_migration(ws)
    assert "beulig.csv" in [Path(p).name for p in plan["assignments"].get("inv-a", [])]
    assert "beulig.csv" not in [Path(p).name for items in
                                {k: v for k, v in plan["assignments"].items() if k != "inv-a"}.values()
                                for p in items]

def test_multi_use_dataset_stays_global(tmp_path):
    ws = _ws(tmp_path)
    (ws / "datasets" / "shared.csv").write_text("x")
    a = _inv(ws, "inv-a", ["s1"]); b = _inv(ws, "inv-b", ["s2"])
    (a / "studies" / "s1" / "study.yaml").write_text("name: s1\nx: shared.csv\n", encoding="utf-8")
    (b / "studies" / "s2" / "study.yaml").write_text("name: s2\nx: shared.csv\n", encoding="utf-8")
    plan = plan_inputs_migration(ws)
    assert "shared.csv" in [Path(p).name for p in plan["global"]]
    assert all("shared.csv" not in [Path(p).name for p in items]
               for items in plan["assignments"].values())

def test_unused_dataset_stays_global(tmp_path):
    ws = _ws(tmp_path)
    (ws / "datasets" / "orphan.csv").write_text("x")
    _inv(ws, "inv-a", ["s1"])
    plan = plan_inputs_migration(ws)
    assert "orphan.csv" in [Path(p).name for p in plan["global"]]
