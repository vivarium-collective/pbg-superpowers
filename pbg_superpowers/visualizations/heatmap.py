"""Heatmap — 2D parameter sweep, color = reduced observable."""
from __future__ import annotations
import html as _html
import json

from pbg_superpowers.visualization import Visualization
from pbg_superpowers.visualizations.param_vs_observable import _reduce


class Heatmap(Visualization):
    """Plot a 2D parameter sweep as a color matrix.

    Config keys:
      sweep:      str  — name of the simulation block (must be a 2D sweep)
      x_param:    str
      y_param:    str
      observable: str
      reduce:     final | mean | max | min | integral
      title:      str
    """

    def render_final(self, results: dict, *, config: dict) -> str:
        sweep_name = config.get("sweep", "")
        x_param = config.get("x_param", "")
        y_param = config.get("y_param", "")
        observable = config.get("observable", "")
        how = config.get("reduce", "final")
        title = config.get("title", "")

        sim = results.get(sweep_name) or {}
        runs = sim.get("runs", [])

        # Collect (x, y) -> reduced(observable)
        cell: dict[tuple, float] = {}
        x_vals: set = set()
        y_vals: set = set()
        for run in runs:
            params = run.get("params") or {}
            if x_param not in params or y_param not in params:
                continue
            traj = run.get("trajectory") or []
            values = [pt["state"][observable]
                      for pt in traj
                      if observable in (pt.get("state") or {})]
            if not values:
                continue
            x, y = params[x_param], params[y_param]
            x_vals.add(x); y_vals.add(y)
            cell[(x, y)] = _reduce(values, how)

        x_sorted = sorted(x_vals)
        y_sorted = sorted(y_vals)
        z = [[cell.get((x, y)) for x in x_sorted] for y in y_sorted]

        traces = [{
            "z": z, "x": x_sorted, "y": y_sorted, "type": "heatmap",
            "colorscale": "Viridis",
            "colorbar": {"title": observable + " (" + how + ")"},
        }]
        layout = {
            "title": {"text": _html.escape(title), "font": {"size": 14}},
            "xaxis": {"title": {"text": _html.escape(x_param)}},
            "yaxis": {"title": {"text": _html.escape(y_param)}},
            "margin": {"l": 55, "r": 60, "t": 40, "b": 40},
        }
        return (
            '<div id="viz" style="height:420px"></div>'
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
            '<script>Plotly.newPlot("viz", '
            + json.dumps(traces) + ", " + json.dumps(layout)
            + ", {responsive:true, displayModeBar:false});</script>"
        )
