"""Back-compat shim — moved to process_bigraph.visualizations.timeseries_from_observables (Phase 1)."""
from process_bigraph.visualizations.timeseries_from_observables import *          # noqa: F401,F403
from process_bigraph.visualizations.timeseries_from_observables import (           # explicit: names not in __all__ that consumers use
    TimeSeriesFromObservables, _PALETTE, _html,
    _load_study_observable_meta, _load_runs, _label_for_run,
    _build_traces, _y_axis_label, _render_html,
)
