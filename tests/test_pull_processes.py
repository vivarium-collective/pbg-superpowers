"""Integration test: install fake-tool fixture into a scaffolded model, register
FakeProcess in core, verify list_processes reports it."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


PBG_TEMPLATE = Path(os.path.expanduser("~/code/pbg-template")).resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def test_install_fixture_wrapper_into_model(tmp_path, plugin_root, fixtures_dir):
    """Mirrors what /pbg-pull-processes does: install a wrapper, patch core.py to
    register it, then verify build_core() exposes it via list_processes()."""
    # 1. Scaffold a workspace and a model under it
    ws = tmp_path / "ws"
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", "ws", "--target", str(ws),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    model_dir = ws / "models" / "m"
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "model",
         "--model-name", "m", "--model-slug", "m", "--target", str(model_dir)],
        check=True, cwd=plugin_root,
    )
    # 2. Workspace venv + install the fake-tool fixture, the model (editable),
    #    and the plugin. The model template uses hatchling with explicit packages,
    #    so `uv pip install -e <model>` works without flat-layout discovery issues.
    subprocess.run(["uv", "venv", ".venv"], cwd=ws, check=True)
    venv_python = str(ws / ".venv" / "bin" / "python")
    fake = fixtures_dir / "pbg-fake-tool"
    subprocess.run(
        ["uv", "pip", "install",
         "-e", str(fake), "-e", str(model_dir), "-e", str(plugin_root)],
        cwd=ws, check=True,
        env={**os.environ, "VIRTUAL_ENV": str(ws / ".venv")},
    )
    # 3. Patch the model's core.py to register FakeProcess via the plugin's
    #    introspectable adapter. We use a minimal `_Core` stub so the test does
    #    not depend on a real process_bigraph install.
    (model_dir / "pbg_m" / "core.py").write_text(textwrap.dedent("""\
        from pbg_fake_tool import FakeProcess


        class _Core:
            def __init__(self):
                self._links = {}
                self._types = {}

            def register_link(self, name, cls):
                self._links[name] = cls

            def list_processes(self):
                return list(self._links.keys())

            def list_types(self):
                return list(self._types.keys())

            def access(self, name):
                return self._types.get(name, {})


        def build_core():
            core = _Core()
            core.register_link("FakeProcess", FakeProcess)
            return core
    """))
    # 4. Verify build_core() registers FakeProcess via the plugin's introspector
    out = subprocess.run(
        [venv_python, "-c",
         "from pbg_m.core import build_core; "
         "from pbg_superpowers.core_introspection import list_processes; "
         "print(list_processes(build_core()))"],
        check=True, capture_output=True, text=True,
    )
    assert "FakeProcess" in out.stdout
