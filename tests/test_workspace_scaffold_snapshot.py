"""Golden manifest test: scaffolded workspace's file tree must match the recorded snapshot."""
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


def test_scaffold_matches_manifest(tmp_path, plugin_root, fixtures_dir):
    target = tmp_path / "ws"
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", "snap", "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    actual = sorted(
        "./" + str(p.relative_to(target))
        for p in target.rglob("*")
        if p.is_file() and "__pycache__" not in str(p.relative_to(target))
    )
    expected = sorted(
        line.strip()
        for line in (fixtures_dir / "workspace-baseline" / "MANIFEST.txt").read_text().splitlines()
        if line.strip()
    )
    extras = set(actual) - set(expected)
    missing = set(expected) - set(actual)
    assert not extras and not missing, (
        f"workspace tree drifted from snapshot.\n"
        f"  unexpected files: {sorted(extras)}\n"
        f"  missing files:    {sorted(missing)}"
    )
