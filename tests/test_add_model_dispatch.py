"""Integration test: scaffolded workspace + scaffolded model can be combined as a submodule.

This does NOT exercise the full /pbg-add-model SKILL.md flow (which involves gh CLI
and human walkthrough). It verifies that the artifacts produced by Tasks 10 and 13
compose correctly via `git submodule add`.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest


PBG_TEMPLATE = Path(os.path.expanduser("~/code/pbg-template")).resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=test@test", "-c", "user.name=test", *args],
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
    _git("commit", "-q", "-m", "init", cwd=target)


def _scaffold_model(target: Path, plugin_root: Path, *, name: str, slug: str):
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "model",
         "--model-name", name, "--model-slug", slug,
         "--target", str(target)],
        check=True, cwd=plugin_root,
    )
    _git("init", "-q", cwd=target)
    _git("add", "-A", cwd=target)
    _git("commit", "-q", "-m", "init", cwd=target)


def test_workspace_can_consume_model_as_submodule(tmp_path, plugin_root):
    ws = tmp_path / "ws"
    model = tmp_path / "model-ecoli-rep"
    _scaffold_workspace(ws, plugin_root)
    _scaffold_model(model, plugin_root, name="ecoli-rep", slug="ecoli_rep")
    # Add as submodule via local path. `protocol.file.allow=always` is required
    # for local-path submodules in modern git.
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always",
         "-c", "user.email=test@test", "-c", "user.name=test",
         "submodule", "add", str(model), "models/ecoli-rep"],
        cwd=ws, check=True,
    )
    # The submodule directory now contains the scaffolded model
    assert (ws / "models" / "ecoli-rep" / "pyproject.toml").exists()
    assert (ws / "models" / "ecoli-rep" / "pbg_ecoli_rep" / "core.py").exists()
    # `.gitmodules` records the submodule
    assert "models/ecoli-rep" in (ws / ".gitmodules").read_text()


def test_skill_manifest_picks_up_pbg_add_model(plugin_root):
    """After Task 14 lands, the manifest test should parametrize 4 skills."""
    skills = sorted((plugin_root / "skills").glob("*/SKILL.md"))
    names = {p.parent.name for p in skills}
    assert "pbg-add-model" in names
