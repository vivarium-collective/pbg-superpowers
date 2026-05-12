"""Visualization Step base class — final-mode (default) + opt-in streaming.

A Visualization is a process_bigraph.Step. Subclasses always implement
``render_final(results, config)`` (called once at end of an Investigation,
given the full results dict). Subclasses MAY also implement ``update()``
for per-step streaming mode by setting ``supports_streaming = True``.

Discovery: Visualization extends Step extends Edge, so subclasses are
auto-discovered via bigraph_schema.package.discover and registered in
``core.link_registry`` alongside Emitters / Processes / Types.
"""
from __future__ import annotations
from typing import Any

from process_bigraph import Step


class Visualization(Step):
    """Base class for renderable Visualization Steps.

    Subclasses MUST implement ``render_final(results, *, config)``.
    Subclasses MAY implement ``update(state, interval)`` and set
    ``supports_streaming = True`` for per-step rendering inside Composites.
    """

    supports_streaming: bool = False

    config_schema = {
        'title': {'_type': 'string', '_default': ''},
    }

    def inputs(self) -> dict[str, Any]:
        """Default empty. Streaming subclasses override to declare consumed
        observables via wires (per the existing Composite Step contract)."""
        return {}

    def outputs(self) -> dict[str, Any]:
        """Default: single ``html`` string output. Used by both modes."""
        return {'html': 'string'}

    def render_final(self, results: dict, *, config: dict) -> str:
        """Render the visualization once given the full results dict.

        ``results`` shape:
            {<sim_name>: {"runs": [{"run_id", "params", "trajectory"}, ...]}, ...}

        ``config`` is whatever the Investigation spec passed under ``config:``,
        plus a special ``_overlays`` key that the orchestrator injects with
        resolved overlay payloads (experimental-points, reference-range,
        cross-investigation-series).

        Returns a self-contained HTML fragment (Plotly figure typically).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement render_final(results, *, config). "
            f"See pbg_superpowers.visualization.Visualization for the contract."
        )

    def update(self, state: dict, interval: float = 1.0) -> dict:
        """Optional per-step rendering for streaming mode.

        Default returns ``{'html': ''}`` (no-op) so that Visualization
        subclasses that only do final-mode rendering still satisfy the
        Step contract when accidentally wired into a Composite.
        """
        return {'html': ''}

    @classmethod
    def is_visualization(cls) -> bool:
        """Marker for dashboard filtering."""
        return True
