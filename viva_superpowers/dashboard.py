"""viva_superpowers.dashboard — back-compat alias for viva_superpowers.workbench.

The dashboard→workbench rename moved the implementation into
:mod:`viva_superpowers.workbench` (the canonical module, matching the
``/viva-workbench`` skill). This module re-exports its public API so that
``python -m viva_superpowers.dashboard`` and ``from viva_superpowers.dashboard
import …`` keep working during the deprecation window. Prefer
``viva_superpowers.workbench``.
"""
from __future__ import annotations

from viva_superpowers.workbench import (  # noqa: F401  (public re-exports)
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
