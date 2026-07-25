"""viva_superpowers.workbench — manage the interactive vivarium-workbench server.

Canonical module for the ``/pbg-workbench`` skill (formerly ``/pbg-dashboard``).
The implementation lives in :mod:`viva_superpowers.dashboard`, which keeps its own
``python -m viva_superpowers.dashboard`` entry point as a back-compat alias; this
module re-exports it so ``python -m viva_superpowers.workbench`` works and reads
coherently with the renamed skill.
"""
from __future__ import annotations

from viva_superpowers.dashboard import (  # noqa: F401  (public re-exports)
    main,
    open_url,
    restart,
    start,
    status,
    stop,
)

__all__ = ["main", "start", "stop", "status", "open_url", "restart"]


if __name__ == "__main__":
    raise SystemExit(main())
