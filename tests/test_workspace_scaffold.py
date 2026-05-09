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
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE} (set up Task 9 first)")


def _scaffold(tmp_path, plugin_root, name="demo-ws"):
    target = tmp_path / name
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", name, "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    return target


def test_scaffold_creates_expected_files(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root)
    must_exist = [
        "workspace.yaml",
        "pyproject.toml",
        "README.md",
        ".gitignore",
        ".claude/settings.json",
        "docs/decisions.yaml",
        "datasets/_index.yaml",
        "references/papers.bib",
        "references/claims.yaml",
        "experiments/_runs.yaml",
        "reports/index.html",
        "scripts/lint-workspace.py",
        ".pbg/schemas/workspace.schema.json",
        ".pbg/schemas/phase.schema.json",
    ]
    for p in must_exist:
        assert (target / p).exists(), f"missing: {p}"

    # template-init.sh should have self-deleted
    assert not (target / "template-init.sh").exists()
    # .j2 files should have been rendered (and removed)
    assert not list(target.rglob("*.j2"))
    # .git from the source should have been stripped
    assert not (target / ".git").exists()


def test_scaffold_workspace_yaml_validates(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root, name="my-research")
    ws = yaml.safe_load((target / "workspace.yaml").read_text())
    assert ws["name"] == "my-research"
    assert ws["schema_version"] == 1
    assert ws["plugin_version"] == "0.1.0"
    assert ws["stages"]["workspace_bootstrap"]["status"] == "complete"


def test_lint_passes_on_freshly_scaffolded(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root)
    r = subprocess.run(
        [sys.executable, "scripts/lint-workspace.py"],
        cwd=target, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"lint failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "OK" in r.stdout
