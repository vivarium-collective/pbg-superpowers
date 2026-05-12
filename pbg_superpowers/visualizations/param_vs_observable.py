"""ParamVsObservable — sweep parameter vs reduced observable value."""
from __future__ import annotations
import html as _html
import json
import statistics
from typing import Any

from pbg_superpowers.visualization import Visualization


def _reduce(values: list[float], how: str) -> float:
    if not values:
        return float("nan")
    if how == "final":
        return values[-1]
    if how == "mean":
        return statistics.fmean(values)
    if how == "max":
        return max(values)
    if how == "min":
        return min(values)
    if how == "integral":
        # Trapezoidal sum assuming unit step spacing
        return sum((values[i] + values[i + 1]) / 2 for i in range(len(values) - 1))
    return values[-1]  # default to final


class ParamVsObservable(Visualization):
    """Plot sweep parameter values vs a reduced observable across runs.

    Config keys:
      sweep:        str  — name of the simulation block (must be kind=sweep or seeds)
      sweep_param:  str  — parameter name to plot on x-axis
      observable:   str  — observable name to extract from each trajectory
      reduce:       str  — final | mean | max | min | integral
      title:        str  — optional
    """

    def render_final(self, results: dict, *, config: dict) -> str:
        sweep_name = config.get("sweep", "")
        param = config.get("sweep_param", "")
        observable = config.get("observable", "")
        how = config.get("reduce", "final")
        title = config.get("title", "")

        sim = results.get(sweep_name) or {}
        runs = sim.get("runs", [])

        xs, ys = [], []
        for run in runs:
            params = run.get("params") or {}
            if param not in params:
                continue
            traj = run.get("trajectory") or []
            values = [
                pt["state"].get(observable)
                for pt in traj if observable in (pt.get("state") or {})
            ]
            values = [v for v in values if v is not None]
            if not values:
                continue
            xs.append(params[param])
            ys.append(_reduce(values, how))

        # Sort by x for a clean line
        if xs:
            pairs = sorted(zip(xs, ys))
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]

        traces = [{
            "x": xs, "y": ys, "type": "scatter", "mode": "lines+markers",
            "name": observable,
            "line": {"color": "#6366f1", "width": 2},
            "marker": {"color": "#6366f1", "size": 8},
        }]
        layout = {
            "title": {"text": _html.escape(title), "font": {"size": 14}},
            "xaxis": {"title": {"text": _html.escape(param)}},
            "yaxis": {"title": {"text": _html.escape(observable) + " (" + how + ")"}},
            "margin": {"l": 55, "r": 15, "t": 40, "b": 40},
            "showlegend": False,
        }
        return (
            '<div id="viz" style="height:380px"></div>'
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
            '<script>Plotly.newPlot("viz", '
            + json.dumps(traces) + ", " + json.dumps(layout)
            + ", {responsive:true, displayModeBar:false});</script>"
        )
