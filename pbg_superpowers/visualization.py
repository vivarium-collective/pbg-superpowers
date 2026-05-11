"""Visualization Step base class — discoverable AND wireable into Composites.

A Visualization is a process_bigraph.Step whose job is to consume observable
streams (via inputs() — the same pattern Emitters use) and produce a rendered
HTML/PNG via update() returning {'html': ...} (or whatever outputs() declares).

Subclasses MUST override:
- inputs():  declare which observables this viz consumes
- update():  return a dict matching outputs(); typically {'html': '<rendered>'}

Subclasses MAY override:
- outputs():  default is {'html': 'string'}; extend if you also emit PNG, JSON, etc.
- config_schema: extend the default {'title': string}
- __init__: set up internal state (e.g., self.history = []) for accumulating
  per-step values across update() calls

Render timing convention: Visualizations re-render the full trajectory each
update() call. Subclasses accumulate state in instance attributes (self.history,
self.frames, etc.) and produce a fresh figure each step. Plotly + matplotlib
both handle the resulting recomputation fine for typical workspace sims.

Discovery: Visualization extends Step extends Edge, so subclasses are picked
up by bigraph_schema.package.discover and registered in core.link_registry
alongside Emitter and Process subclasses. The dashboard filters them via
issubclass checks (see docs/conventions/visualizations.md).
"""
from __future__ import annotations
from typing import Any

from process_bigraph import Step


class Visualization(Step):
    """Base class for renderable visualization Steps.

    Subclasses must implement inputs() and update(). Default outputs() exposes
    an 'html' string port that Composites can wire to a store.
    """

    config_schema = {
        'title': {'_type': 'string', '_default': ''},
    }

    def inputs(self) -> dict[str, Any]:
        """Subclasses MUST override.

        Returns a dict of {wire_name: type} declaring the observables this viz
        consumes. The composite spec wires these to store paths.

        Example:
            return {'free_DnaA': 'float', 'oriC_state': 'string'}
        """
        return {}

    def outputs(self) -> dict[str, Any]:
        """Default: 'html' string output. Subclasses MAY extend.

        Example: subclass that also emits a PNG path
            return {'html': 'string', 'png_path': 'string'}
        """
        return {'html': 'string'}

    def update(self, state: dict, interval: float = 1.0) -> dict:
        """Subclasses MUST override.

        `state` is a dict keyed by inputs() wire names; values are the current
        store values via the wires declared in the composite spec.

        Return a dict matching outputs() — typically {'html': '<rendered HTML>'}.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement update(state, interval). "
            f"Subclasses of Visualization override update() to consume per-step "
            f"state and return {{'html': '<rendered figure>'}}. See "
            f"pbg_superpowers.visualization.Visualization for the contract."
        )

    @classmethod
    def is_visualization(cls) -> bool:
        """Marker for dashboard filtering: distinguish viz Steps from Emitters etc.

        Use: `[c for c in core.link_registry.values() if hasattr(c, 'is_visualization') and c.is_visualization()]`
        """
        return True
