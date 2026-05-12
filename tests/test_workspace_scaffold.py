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
        "references/papers.bib",
        "references/claims.yaml",
        "experiments/_runs.yaml",
        "reports/index.html",
        "scripts/lint-workspace.py",
        ".pbg/schemas/workspace.schema.json",
    ]
    for p in must_exist:
        assert (target / p).exists(), f"missing: {p}"

    # template-init.sh should have self-deleted
    assert not (target / "template-init.sh").exists()
    # init-time .j2 files should have been rendered (and removed); the dashboard's
    # runtime templates under scripts/_templates/ are intentionally preserved.
    leftover_j2 = [p for p in target.rglob("*.j2") if "scripts/_templates" not in str(p)]
    assert not leftover_j2, f"unexpected .j2 leftovers: {leftover_j2}"
    # .git from the source should have been stripped
    assert not (target / ".git").exists()


def test_scaffold_workspace_yaml_validates(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root, name="my-research")
    ws = yaml.safe_load((target / "workspace.yaml").read_text())
    assert ws["name"] == "my-research"
    assert ws["schema_version"] == 2
    assert ws["plugin_version"] == "0.4.16"


def test_lint_passes_on_freshly_scaffolded(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root)
    r = subprocess.run(
        [sys.executable, "scripts/lint-workspace.py"],
        cwd=target, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"lint failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "OK" in r.stdout
