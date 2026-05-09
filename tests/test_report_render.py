import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from pbg_superpowers.report import render_workspace_report, render_model_report


PBG_TEMPLATE = Path(os.path.expanduser("~/code/pbg-template")).resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def _scaffold_workspace(target: Path, plugin_root: Path):
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", "demo-ws", "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )


def test_render_workspace_report_smoke(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    _scaffold_workspace(ws, plugin_root)
    out = render_workspace_report(ws, today="2026-05-09")
    assert out.exists()
    html = out.read_text()
    assert "demo-ws" in html
    assert "Workspace dashboard" in html
    # Assets copied
    assets = ws / "reports" / "assets"
    assert (assets / "style.css").exists()
    assert (assets / "render-helpers.js").exists()


def test_render_model_report_with_registry(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    _scaffold_workspace(ws, plugin_root)
    # Register a model in workspace.yaml + scaffold the model dir so reports/assets/ resolves
    wsdata = yaml.safe_load((ws / "workspace.yaml").read_text())
    wsdata["models"] = {
        "ecoli-rep": {
            "submodule_path": "models/ecoli-rep", "remote": "x",
            "pbg_processes": ["pbg-cobra"],
            "stages": {"add_model": {"status": "complete", "pr": 2}},
            "phases": [{"n": 1, "name": "DnaA accumulation",
                        "status": "complete", "pr": 8, "gate_passed": True}],
        }
    }
    (ws / "workspace.yaml").write_text(yaml.safe_dump(wsdata, sort_keys=False))
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "model",
         "--model-name", "ecoli-rep", "--model-slug", "ecoli_rep",
         "--target", str(ws / "models" / "ecoli-rep")],
        check=True, cwd=plugin_root,
    )
    out = render_model_report(
        ws, "ecoli-rep",
        registry={"processes": ["FakeProcess"], "types": ["my_type"]},
        pbg_doc={"stores": {"x": 1.0}},
        today="2026-05-09",
    )
    assert out.exists()
    html = out.read_text()
    assert "FakeProcess" in html
    assert "my_type" in html
    assert "Phase tracker" in html
    assert "Composite document" in html
    # Per-model assets copied
    assets = ws / "models" / "ecoli-rep" / "reports" / "assets"
    assert (assets / "style.css").exists()
