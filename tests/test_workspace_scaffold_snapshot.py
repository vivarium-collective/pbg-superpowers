"""Golden manifest test: scaffolded workspace's file tree must match the recorded snapshot."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


PBG_TEMPLATE = Path(os.environ.get("PBG_TEMPLATE", "~/code/pbg-template")).expanduser().resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE}")


def test_scaffold_matches_manifest(tmp_path, plugin_root, fixtures_dir):
    # To regenerate MANIFEST.txt after an intentional pbg-template change:
    #     python scripts/update-scaffold-snapshot.py
    # (Honors $PBG_TEMPLATE env var; defaults to ~/code/pbg-template.)
    # Review the diff and commit.
    target = tmp_path / "ws"
    subprocess.run(
        [sys.executable, "-m", "viva_superpowers.scaffold", "workspace",
         "--name", "snap", "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    # Exclude transient pytest/python caches that may exist in the source
    # template when it's been run locally — those are gitignored upstream
    # but the scaffolder copies whatever is on disk.
    _IGNORED = ("__pycache__", ".pytest_cache")
    actual = sorted(
        "./" + str(p.relative_to(target))
        for p in target.rglob("*")
        if p.is_file()
        and not any(part in _IGNORED for part in p.relative_to(target).parts)
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
        f"  missing files:    {sorted(missing)}\n"
        f"\n"
        f"This snapshot mirrors pbg-template's tree. To resolve:\n"
        f"  - If pbg-template changed intentionally, bump the pin in\n"
        f"    tests/fixtures/workspace-baseline/PBG_TEMPLATE_REF to the new\n"
        f"    commit, then regenerate the manifest in the SAME PR:\n"
        f"        PBG_TEMPLATE=<path-to-pbg-template> \\\n"
        f"          python scripts/update-scaffold-snapshot.py\n"
        f"    Review the diff and commit MANIFEST.txt + PBG_TEMPLATE_REF.\n"
        f"  - CI pins pbg-template to PBG_TEMPLATE_REF, so this should only\n"
        f"    drift when you change the template payload or the scaffolder."
    )
