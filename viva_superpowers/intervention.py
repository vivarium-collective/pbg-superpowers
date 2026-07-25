"""Back-compat shim: the Intervention process moved to ``pbg-basic-processes``.

The reusable ``Intervention`` process now lives in the standalone,
auto-registering ``pbg-basic-processes`` package (alongside ``Clock`` and
``MathExpressionStep``). It auto-registers into every workspace ``core`` via
bigraph-schema package discovery, exactly like the framework emitters.

This module re-exports the public surface so existing call sites
(``from viva_superpowers.intervention import ...`` — e.g. ``ablation.py``) keep
working unchanged. Prefer importing from ``pbg_basic_processes`` in new code.
"""
from pbg_basic_processes.intervention import (  # noqa: F401
    Intervention,
    register_intervention,
    intervention_node,
)

__all__ = ["Intervention", "register_intervention", "intervention_node"]
