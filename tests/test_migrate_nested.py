"""Flat -> nested study migration (investigation-centric structure, Phase 1)."""
import subprocess

import yaml

from pbg_superpowers.migrate_nested import plan_migration, migrate


def _flat_ws(tmp):
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp / "investigations" / "inv-a"
    inv.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(
        "name: inv-a\nstudies:\n  - s1\n  - s2\n", encoding="utf-8")
    for s in ("s1", "s2"):
        d = tmp / "studies" / s
        d.mkdir(parents=True)
        (d / "study.yaml").write_text(f"name: {s}\ninvestigation: inv-a\n", encoding="utf-8")
    # an orphan study not owned by any investigation
    d = tmp / "studies" / "orphan"
    d.mkdir(parents=True)
    (d / "study.yaml").write_text("name: orphan\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp, check=True)
    return tmp


def test_plan_maps_studies_to_owning_investigation(tmp_path):
    ws = _flat_ws(tmp_path)
    plan = plan_migration(ws)
    moves = {m["slug"]: m["dest"] for m in plan["moves"]}
    assert moves["s1"].endswith("investigations/inv-a/studies/s1")
    assert moves["s2"].endswith("investigations/inv-a/studies/s2")
    assert "orphan" in [o["slug"] for o in plan["orphans"]]


def test_migrate_moves_and_is_idempotent(tmp_path):
    ws = _flat_ws(tmp_path)
    migrate(ws)
    assert (ws / "investigations" / "inv-a" / "studies" / "s1" / "study.yaml").is_file()
    assert not (ws / "studies" / "s1").exists()
    assert (ws / "studies" / "orphan").exists()  # orphan left in place
    layout = (yaml.safe_load((ws / "workspace.yaml").read_text()) or {}).get("layout", {})
    assert "studies" not in layout  # top-level studies key dropped
    res2 = migrate(ws)  # idempotent
    assert res2["moves"] == []


def test_migrate_preserves_git_history(tmp_path):
    ws = _flat_ws(tmp_path)
    migrate(ws)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "commit", "-qm", "migrate"], cwd=ws, check=True)
    log = subprocess.run(
        ["git", "log", "--follow", "--oneline",
         "investigations/inv-a/studies/s1/study.yaml"],
        cwd=ws, capture_output=True, text=True).stdout
    assert "init" in log  # history followed across the move
