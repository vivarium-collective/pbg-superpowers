"""Integration tests for `viva-scaffold model`."""
import subprocess
import sys
from pathlib import Path

import pytest


def _scaffold_model(target: Path, plugin_root: Path,
                    name: str = "ecoli-replication", slug: str = "ecoli_replication"):
    subprocess.run(
        [sys.executable, "-m", "viva_superpowers.scaffold", "model",
         "--model-name", name, "--model-slug", slug,
         "--target", str(target)],
        check=True, cwd=plugin_root,
    )


def test_scaffold_creates_expected_files(tmp_path, plugin_root):
    target = tmp_path / "models" / "ecoli-replication"
    _scaffold_model(target, plugin_root)
    must_exist = [
        "pyproject.toml", "README.md", ".gitignore",
        "viva_ecoli_replication/__init__.py",
        "viva_ecoli_replication/core.py",
        "viva_ecoli_replication/wiring.py",
        "viva_ecoli_replication/adapters.py",
        "viva_ecoli_replication/stubs.py",
        "viva_ecoli_replication/document.py",
        "viva_ecoli_replication/types.py",
        "tests/__init__.py",
        "tests/test_assembly.py",
        "tests/test_adapters.py",
        "tests/test_run.py",
        "tests/test_core_integration.py",
        "tests/registry-snapshot.json",
        "reports/index.html",
        "reports/assets/.keep",
    ]
    for p in must_exist:
        assert (target / p).exists(), f"missing: {p}"
    # No .j2 files left
    assert not list(target.rglob("*.j2"))
    # Placeholder dir has been renamed
    assert not (target / "viva_<model>").exists()


def test_placeholder_substitution(tmp_path, plugin_root):
    target = tmp_path / "m"
    _scaffold_model(target, plugin_root, name="ecoli-replication", slug="ecoli_replication")
    pyproj = (target / "pyproject.toml").read_text()
    assert "name = \"viva_ecoli_replication\"" in pyproj
    assert "ecoli-replication" in pyproj  # description uses model_name
    core = (target / "viva_ecoli_replication" / "core.py").read_text()
    # Placeholders gone
    assert "{{" not in core and "}}" not in core


def test_refuses_non_empty_target(tmp_path, plugin_root):
    target = tmp_path / "m"
    target.mkdir()
    (target / "existing").write_text("hello")
    with pytest.raises(subprocess.CalledProcessError):
        _scaffold_model(target, plugin_root)
