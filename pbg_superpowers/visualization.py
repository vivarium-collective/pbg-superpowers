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
