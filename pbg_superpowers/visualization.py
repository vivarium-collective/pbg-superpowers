"""Visualization Step base class — discoverable, renderable.

A Visualization is a process-bigraph Step whose job is to render emitter
output (typically a gathered trajectory) into HTML or a PNG. By subclassing
Step, Visualization participates in bigraph-schema's discovery: any
installed package containing a Visualization subclass auto-registers it in
`core.link_registry` when `allocate_core()` runs.

This puts visualizations on the same footing as Emitters / Processes /
Types for discovery + tracking, while keeping their semantics simple:
- update() defaults to a no-op (visualizations don't transform sim state)
- render(results) is the actual work, called by the dashboard post-run

A subclass may opt INTO incremental rendering by overriding update().
"""
from __future__ import annotations
from typing import Any

from process_bigraph import Step


class Visualization(Step):
    """Base class for renderable visualization Steps.

    Subclasses must implement `render(results) -> str | bytes`.

    Example:

        class DnaATrajectory(Visualization):
            config_schema = {
                'title':     {'_type': 'string', '_default': 'DnaA over time'},
                'threshold': {'_type': 'float',  '_default': 50.0},
            }

            def render(self, results):
                import plotly.graph_objects as go
                series = results.get(('emitter',), [])
                ys = [s.get('free_DnaA', 0.0) for s in series]
                fig = go.Figure(go.Scatter(y=ys, mode='lines'))
                fig.add_hline(y=self.config['threshold'], line_dash='dash')
                fig.update_layout(title=self.config['title'])
                return fig.to_html(full_html=False, include_plotlyjs='cdn')
    """

    config_schema = {
        'title': {'_type': 'string', '_default': ''},
    }

    def inputs(self) -> dict[str, Any]:
        """Default: no inputs. Subclasses can declare wiring if they want."""
        return {}

    def outputs(self) -> dict[str, Any]:
        """Default: no outputs."""
        return {}

    def update(self, state: dict, interval: float) -> dict:
        """Default no-op. Visualizations render post-simulation, not per-step."""
        return {}

    def render(self, results: dict) -> str:
        """Render gathered emitter results. Return HTML (str) or base64 PNG.

        Subclasses MUST override.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement render(results)"
        )

    @classmethod
    def is_visualization(cls) -> bool:
        """Marker for dashboard filtering: distinguish viz Steps from Emitters etc.

        Use: `[c for c in core.link_registry.values() if hasattr(c, 'is_visualization') and c.is_visualization()]`
        """
        return True
