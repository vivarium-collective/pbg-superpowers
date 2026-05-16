#!/usr/bin/env python3
"""Maintainer-facing CLI for auditing a single pbg-* repo.

Replaces the user-invocable /pbg-package skill (removed in v0.9.0). The
underlying audit logic still lives in pbg_superpowers.package_audit; this
script is the convenience entry point.

Usage:
    python scripts/audit-pbg-repo.py <repo-path-or-name> [--no-install]

Forms accepted for <repo-path-or-name>:
    pbg-smoldyn          shallow-clone vivarium-collective/pbg-smoldyn to a tmp dir, audit, clean up
    ~/code/pbg-cobra     audit a local checkout in-place
    ./pbg-cobra          relative path; audited in-place

Exit code:
    0  no FAIL checks (WARN is OK)
    1  one or more FAIL checks
    2  could not locate or clone the target repo

For the catalog-wide audit (every pbg-* repo in pbg-template's catalog), use
`scripts/audit-pbg-catalog.py` instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the local pbg_superpowers package importable without an editable install.
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from pbg_superpowers.package_audit import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
