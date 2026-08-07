"""Back-compat shim — moved to process_bigraph.composite_discovery (Phase 1)."""
from process_bigraph.composite_discovery import *          # noqa: F401,F403
from process_bigraph.composite_discovery import (           # noqa: F401 - explicit: names not in __all__ that consumers use
    _GLOB_PATTERNS, _is_bigraph_schema_lib, discover_composites,
    discover_all, _make_spec_id,
)
