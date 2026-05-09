"""Tests for `pbg-scaffold import-model` across all three modes."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


PBG_TEMPLATE = Path(os.path.expanduser("~/code/pbg-template")).resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    )


def _scaffold_workspace(target: Path, plugin_root: Path):
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", "ws", "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    _git("init", "-q", cwd=target)
    _git("add", "-A", cwd=target)
    _git("commit", "-qm", "init", cwd=target)


def _make_external_repo(target: Path):
    """Create a tiny git repo to use as a fake external import source."""
    target.mkdir()
    (target / "README.md").write_text("# fake external repo\n")
    _git("init", "-q", cwd=target)
    _git("add", "-A", cwd=target)
    _git("commit", "-qm", "init", cwd=target)


def _import(plugin_root, ws, *, name, source, ref, mode, description=None):
    args = [sys.executable, "-m", "pbg_superpowers.scaffold", "import-model",
            "--workspace", str(ws),
            "--name", name, "--source", str(source),
            "--ref", ref, "--mode", mode]
    if description:
        args += ["--description", description]
    return subprocess.run(args, check=True, cwd=plugin_root, capture_output=True, text=True)


def test_fork_source_registers_catalog_only(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    _scaffold_workspace(ws, plugin_root)
    _import(plugin_root, ws, name="seed", source="https://example.com/x.git",
            ref="main", mode="fork-source", description="seed model")
    data = yaml.safe_load((ws / "workspace.yaml").read_text())
    assert data["imports"]["seed"]["mode"] == "fork-source"
    assert "path" not in data["imports"]["seed"] or data["imports"]["seed"].get("path") is None
    # No checkout happened
    assert not (ws / "external").exists()
    assert not (ws / "models" / "seed").exists()


def test_reference_adds_submodule_under_external(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    ext = tmp_path / "external-source"
    _make_external_repo(ext)
    _scaffold_workspace(ws, plugin_root)
    _import(plugin_root, ws, name="ref-x", source=ext, ref="main", mode="reference")

    data = yaml.safe_load((ws / "workspace.yaml").read_text())
    assert data["imports"]["ref-x"]["mode"] == "reference"
    assert data["imports"]["ref-x"]["path"] == "external/ref-x"
    assert (ws / "external" / "ref-x" / "README.md").exists()
    assert ".gitmodules" in [p.name for p in ws.iterdir()]
    gm = (ws / ".gitmodules").read_text()
    assert "external/ref-x" in gm


def test_in_place_adds_submodule_under_models_and_marks_external(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    ext = tmp_path / "external-source"
    _make_external_repo(ext)
    _scaffold_workspace(ws, plugin_root)
    _import(plugin_root, ws, name="upstream-model", source=ext, ref="main", mode="in-place")

    data = yaml.safe_load((ws / "workspace.yaml").read_text())
    assert data["imports"]["upstream-model"]["mode"] == "in-place"
    assert data["imports"]["upstream-model"]["path"] == "models/upstream-model"
    assert (ws / "models" / "upstream-model" / "README.md").exists()
    # external: true marker on the model
    assert data["models"]["upstream-model"]["external"] is True
    assert data["models"]["upstream-model"]["submodule_path"] == "models/upstream-model"


def test_register_duplicate_fails(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    _scaffold_workspace(ws, plugin_root)
    _import(plugin_root, ws, name="x", source="s", ref="r", mode="fork-source")
    r = subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "import-model",
         "--workspace", str(ws), "--name", "x", "--source", "s", "--ref", "r",
         "--mode", "fork-source"],
        cwd=plugin_root, capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "already registered" in (r.stdout + r.stderr).lower()
