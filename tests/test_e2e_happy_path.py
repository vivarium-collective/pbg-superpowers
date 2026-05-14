"""End-to-end happy path:
  scaffold workspace -> scaffold model -> install wrapper -> register process ->
  snapshot registry -> render reports.

This synthesizes what every stage skill does in production, using the
programmatic helpers directly (no Agent dispatches, no walkthroughs)."""
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml


PBG_TEMPLATE = Path(os.path.expanduser("~/code/pbg-template")).resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=test@test", "-c", "user.name=test", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    )


@pytest.mark.timeout(60)
def test_full_flow_scaffold_to_reports(tmp_path, plugin_root, fixtures_dir):
    ws = tmp_path / "ws"

    # 1. Scaffold workspace + git init
    _run([sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
          "--name", "demo", "--target", str(ws),
          "--template-source", str(PBG_TEMPLATE)], cwd=plugin_root)
    _git("init", "-q", cwd=ws)
    _git("add", "-A", cwd=ws)
    _git("commit", "-qm", "init workspace", cwd=ws)

    # 2. Scaffold model + git init
    model = ws / "models" / "m"
    _run([sys.executable, "-m", "pbg_superpowers.scaffold", "model",
          "--model-name", "m", "--model-slug", "m",
          "--target", str(model)], cwd=plugin_root)

    # 3. Update workspace.yaml with the model entry (this is what /pbg-add-model does)
    wsdata = yaml.safe_load((ws / "workspace.yaml").read_text())
    wsdata["models"] = {
        "m": {
            "submodule_path": "models/m", "remote": "local",
            "pbg_processes": ["pbg-fake-tool"],
            "stages": {
                "add_model": {"status": "complete", "pr": 1},
                "pull_processes": {"status": "complete", "pr": 2},
                "data": {"status": "complete", "pr": 3},
                "expert_input": {"status": "complete", "pr": 4},
                "baseline": {"status": "complete", "pr": 5},
            },
        }
    }
    (ws / "workspace.yaml").write_text(yaml.safe_dump(wsdata, sort_keys=False))

    # Add .gitmodules so lint-workspace.py can verify submodule cross-refs
    (ws / ".gitmodules").write_text(textwrap.dedent("""\
        [submodule "models/m"]
            path = models/m
            url = local
    """))

    # 4. Workspace venv + install fake-tool, model, plugin
    _run(["uv", "venv", ".venv"], cwd=ws)
    venv_env = {**os.environ, "VIRTUAL_ENV": str(ws / ".venv")}
    fake = fixtures_dir / "pbg-fake-tool"
    _run(["uv", "pip", "install",
          "-e", str(fake), "-e", str(model), "-e", str(plugin_root),
          "pytest"],
         cwd=ws, env=venv_env)

    # 5. Register FakeProcess in core.py (simulates /pbg-pull-processes)
    (model / "pbg_m" / "core.py").write_text(textwrap.dedent("""\
        from pbg_fake_tool import FakeProcess


        class _Core:
            def __init__(self): self._links = {}; self._types = {}
            def register_link(self, n, c): self._links[n] = c
            def list_processes(self): return list(self._links.keys())
            def list_types(self): return list(self._types.keys())
            def access(self, n): return self._types.get(n, {})


        def build_core():
            c = _Core()
            c.register_link("FakeProcess", FakeProcess)
            return c
    """))

    # 6. Persist registry snapshot (simulates /pbg-baseline step 5)
    venv_python = str(ws / ".venv" / "bin" / "python")
    _run([venv_python, "-c",
          "import json; from pbg_m.core import build_core; "
          "from pbg_superpowers.core_introspection import registry_snapshot; "
          "open('tests/registry-snapshot.json','w').write(json.dumps(registry_snapshot(build_core())))"],
         cwd=model)
    snap = json.loads((model / "tests" / "registry-snapshot.json").read_text())
    assert snap["processes"] == ["FakeProcess"]

    # 13. Render reports (simulates /pbg-report step)
    _run([venv_python, "-c",
          "from pathlib import Path; "
          "from pbg_superpowers.report import render_workspace_report, render_model_report; "
          "from pbg_superpowers.core_introspection import registry_snapshot; "
          "from pbg_m.core import build_core; "
          "render_workspace_report(Path('.'), today='2026-05-09'); "
          "render_model_report(Path('.'), 'm', registry_snapshot(build_core()), today='2026-05-09')"],
         cwd=ws)

    # 14. Assertions on the rendered reports
    assert (ws / "reports" / "index.html").exists()
    assert (ws / "models" / "m" / "reports" / "index.html").exists()
    workspace_html = (ws / "reports" / "index.html").read_text()
    assert "demo" in workspace_html
    assert "models/m/reports/index.html" in workspace_html  # link to per-model report
    model_html = (ws / "models" / "m" / "reports" / "index.html").read_text()
    assert "FakeProcess" in model_html

    # 15. lint-workspace.py passes -- workspace yaml + cross-references valid
    r = _run([venv_python, "scripts/lint-workspace.py"], cwd=ws)
    assert "OK" in r.stdout
