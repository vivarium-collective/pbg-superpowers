"""Back-compat shim — moved to process_bigraph.visualization (Phase 1)."""
from process_bigraph.visualization import *          # noqa: F401,F403
from process_bigraph.visualization import (           # noqa: F401 - explicit: names not in __all__ that consumers use
    Visualization, _is_new_style, as_visualization, render_results,
    _get_path, _read_last_html,
)
