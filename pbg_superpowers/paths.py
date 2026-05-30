"""Workspace-root discovery helpers.

The canonical way for a workspace script to locate its own root:

    from pbg_superpowers.paths import workspace_root

    WS = workspace_root()              # auto-detects caller's file
    runs_db = WS / "studies" / "s1" / "runs.db"

`workspace_root()` walks up from the caller's source file (or the
explicit `start` path) until it finds a directory containing
`workspace.yaml`. This lets scripts in `studies/<slug>/`, `viz/`,
`reports/`, etc. resolve workspace-relative paths without hardcoding
absolute directory names.
"""

from __future__ import annotations

import sys
from pathlib import Path


WORKSPACE_MARKER = "workspace.yaml"


def _walk_for_marker(cur: Path) -> Path | None:
    """Walk up from directory `cur` to the nearest ancestor with the marker."""
    while True:
        if (cur / WORKSPACE_MARKER).is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def workspace_root(start: Path | str | None = None) -> Path:
    """Return the nearest ancestor directory containing workspace.yaml.

    If `start` is None, the caller's source file is used as the starting
    point (via sys._getframe). Pass an explicit Path for non-script
    callers (REPL, tests, etc.).

    Raises FileNotFoundError if no workspace.yaml is found at or above
    the starting directory.
    """
    if start is None:
        caller_file = sys._getframe(1).f_code.co_filename
        cur = Path(caller_file).resolve().parent
    else:
        s = Path(start).resolve()
        cur = s if s.is_dir() else s.parent

    found = _walk_for_marker(cur)
    if found is None:
        raise FileNotFoundError(
            f"No {WORKSPACE_MARKER} found at or above {start or caller_file}"
        )
    return found


def find_workspace_root(
    start: Path | str, *, missing_ok: bool = False
) -> Path | None:
    """Explicit-start workspace-root lookup for module (non-script) callers.

    The single source of truth behind the historical copies in
    ``study_findings``/``study_narrative``/``investigation_close``/``runner``.
    Unlike :func:`workspace_root`, ``start`` is required (no ``_getframe``
    magic) and a file path walks up from its parent directory.

    Raises ``FileNotFoundError`` when no ``workspace.yaml`` is found, unless
    ``missing_ok=True`` (then returns ``None`` — the runner's contract).
    """
    s = Path(start).resolve()
    cur = s if s.is_dir() else s.parent
    found = _walk_for_marker(cur)
    if found is None and not missing_ok:
        raise FileNotFoundError(
            f"No {WORKSPACE_MARKER} found at or above {start}"
        )
    return found
