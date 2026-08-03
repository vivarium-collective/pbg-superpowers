"""Back-compat shim — moved to process_bigraph.config_helpers (Phase 1)."""
from process_bigraph.config_helpers import *          # noqa: F401,F403
from process_bigraph.config_helpers import (           # explicit: names not in __all__ that consumers use
    normalize_config_list, _from_dict, _as_index,
)
