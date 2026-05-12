"""Visualization Step base class — single contract: update(state) → {'html': str}.

Visualization is a process_bigraph.Step. Subclasses declare typed input ports
via ``inputs()`` and produce HTML via ``update(state)``. The bigraph runtime
type-checks the wiring when the Visualization is placed inside a Composite.

Two use modes both call the same ``update`` method:

1. **Streaming** — wired into a user's simulation Composite. ``update(state)``
   is called once per step with a per-step state dict; the Visualization
   accumulates internally and produces a fresh HTML each step.

2. **Post-hoc dispatch** — used by the Investigations dashboard. The
   orchestrator builds a small Composite per visualization with an input
   store pre-populated from the SQLiteEmitter's recorded trajectory, the
   Visualization Step wired to that store, and an output store of type
   ``'string'``. ``composite.run(1)`` fires ``update(state)`` once; the HTML
   is written to ``investigations/<name>/viz/<viz>.html``.

Discovery: Visualization extends Step extends Edge, so subclasses are
auto-discovered via ``bigraph_schema.package.discover`` and registered in
``core.link_registry``.
"""
from __future__ import annotations
from typing import Any

from process_bigraph import Step


class Visualization(Step):
    """Base class for renderable Visualization Steps.

    Subclasses MUST implement ``update(state) -> {'html': str}`` and SHOULD
    override ``inputs()`` to declare typed input ports using the bigraph-
    schema type system (e.g., ``{'level': 'list[float]'}``).
    """

    config_schema = {
        'title': {'_type': 'string', '_default': ''},
    }

    def inputs(self) -> dict[str, Any]:
        """Typed input ports — keys are port names; values are bigraph-schema
        type strings. Subclasses override.
        """
        return {}

    def outputs(self) -> dict[str, Any]:
        """All visualizations expose a single ``html`` string port."""
        return {'html': 'string'}

    def update(self, state: dict) -> dict:
        """Consume the input state and return ``{'html': '<rendered>'}``."""
        raise NotImplementedError(
            f'{type(self).__name__} must implement update(state) -> '
            f"{{'html': str}}."
        )

    @classmethod
    def is_visualization(cls) -> bool:
        """Marker for dashboard filtering: distinguishes viz Steps from Emitters."""
        return True


def as_visualization(inputs, name=None, demo=None, aliases=None):
    """Decorator: convert an ``update_*`` pure function into a Visualization subclass.

    The function must be named ``update_<viz_name>`` and accept
    ``state: dict`` -> ``{'html': str}``.

    Args:
        inputs:  typed input port map (same shape as Visualization.inputs()).
                 Keys are port names; values are bigraph-schema type strings.
        name:    class name override (default: derived from function name).
        demo:    sample state dict (or callable returning one) for dashboard previews.
        aliases: extra registration aliases for bigraph-schema discovery.

    Returns the synthesized Visualization subclass, ready to be registered by
    ``bigraph_schema.discover_packages()`` when the enclosing module is walked.
    """
    def decorator(func):
        if not func.__name__.startswith("update_"):
            raise AssertionError(
                f"as_visualization expects a function named update_<viz_name>; "
                f"got '{func.__name__}'"
            )
        viz_name = name or func.__name__[len("update_"):]
        _demo = demo

        class FunctionVisualization(Visualization):
            def inputs(self):
                return inputs

            def outputs(self):
                return {'html': 'string'}

            def update(self, state):
                return func(state)

            @classmethod
            def demo(cls):
                if callable(_demo):
                    return _demo()
                return dict(_demo or {})

        FunctionVisualization.__name__ = viz_name
        FunctionVisualization.__qualname__ = viz_name
        FunctionVisualization.__module__ = func.__module__
        FunctionVisualization.__doc__ = func.__doc__
        FunctionVisualization.__pb_kind__ = "visualization"
        FunctionVisualization.__pb_aliases__ = [viz_name] + list(aliases or [])
        FunctionVisualization.__pb_wrapped__ = func
        return FunctionVisualization
    return decorator
