"""Back-compat shim — moved to process_bigraph.visualizations.time_series (Phase 1)."""
from process_bigraph.visualizations.time_series import *          # noqa: F401,F403
from process_bigraph.visualizations.time_series import (           # noqa: F401 - explicit: names not in __all__ that consumers use
    TimeSeriesPlot, _PALETTE, _html,
)
