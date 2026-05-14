#!/usr/bin/env python3
"""Regenerate tests/fixtures/workspace-baseline/MANIFEST.txt.

The snapshot test (tests/test_workspace_scaffold_snapshot.py) compares a
freshly-scaffolded workspace's file tree against this manifest. When
pbg-template's payload changes intentionally, run this script to bring
the manifest in sync — one command, no hand-editing.

Usage:
    python scripts/update-scaffold-snapshot.py [--template-source PATH]

Defaults --template-source to $PBG_TEMPLATE or ~/code/pbg-template.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "tests" / "fixtures" / "workspace-baseline" / "MANIFEST.txt"
IGNORE_PARTS = ("__pycache__", ".pytest_cache")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--template-source",
        default=os.environ.get("PBG_TEMPLATE", "~/code/pbg-template"),
        help="Path or git URL of pbg-template (default: $PBG_TEMPLATE or ~/code/pbg-template).",
    )
    ap.add_argument("--workspace-name", default="snap")
    args = ap.parse_args()

    template_source = str(Path(os.path.expanduser(args.template_source)).resolve())

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "ws"
        subprocess.run(
            [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
             "--name", args.workspace_name,
             "--target", str(target),
             "--template-source", template_source],
            check=True, cwd=REPO_ROOT,
        )
        files = sorted(
            "./" + str(p.relative_to(target))
            for p in target.rglob("*")
            if p.is_file()
            and not any(part in IGNORE_PARTS for part in p.relative_to(target).parts)
        )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("\n".join(files) + "\n")
    print(f"wrote {len(files)} entries to {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
