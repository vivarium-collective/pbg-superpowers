"""Back-compat shim — moved to process_bigraph.composite_generator (Phase 1)."""
from process_bigraph.composite_generator import *          # noqa: F401,F403
from process_bigraph.composite_generator import (           # noqa: F401 - explicit: names not in __all__ that consumers use
    GeneratorEntry, _RegistryView, _REGISTRY, _cs, _entry_for,
    composite_generator, _validate_emitters, emitter_defaults,
    _emitter_node_from_decl, install_default_emitters,
    apply_core_extensions, build_generator, _import_bigraph_packages,
    discover_generators,
)
