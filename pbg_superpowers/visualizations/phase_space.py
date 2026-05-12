"""PhaseSpace — two observables plotted against each other."""
from __future__ import annotations
import html as _html
import json

from pbg_superpowers.visualization import Visualization


_PALETTE = ['#6366f1', '#10b981', '#f43f5e', '#f59e0b',
            '#8b5cf6', '#06b6d4', '#84cc16', '#ec4899']


class PhaseSpace(Visualization):
    """Plot two observables against each other (XY trajectory).

    Config keys:
      x_observable: str
      y_observable: str
      sources:      list[str]
      title:        str
    """

    def render_final(self, results: dict, *, config: dict) -> str:
        x_obs = config.get("x_observable", "")
        y_obs = config.get("y_observable", "")
        sources = config.get("sources") or list(results.keys())
        title = config.get("title", "")

        traces = []
        color_idx = 0
        for sim_name in sources:
            sim = results.get(sim_name) or {}
            for run in sim.get("runs", []):
                xs, ys = [], []
                for pt in run.get("trajectory") or []:
                    state = pt.get("state") or {}
                    if x_obs in state and y_obs in state:
                        xs.append(state[x_obs])
                        ys.append(state[y_obs])
                if not xs:
                    continue
                params = run.get("params") or {}
                label = ", ".join(f"{k}={v}" for k, v in sorted(params.items())) \
                        or run.get("run_id", "")
                traces.append({
                    "x": xs, "y": ys, "type": "scatter", "mode": "lines+markers",
                    "name": label,
                    "line": {"color": _PALETTE[color_idx % len(_PALETTE)], "width": 2},
                    "marker": {"size": 5},
                })
                color_idx += 1

        layout = {
            "title": {"text": _html.escape(title), "font": {"size": 14}},
            "xaxis": {"title": {"text": _html.escape(x_obs)}},
            "yaxis": {"title": {"text": _html.escape(y_obs)}},
            "margin": {"l": 55, "r": 15, "t": 40, "b": 40},
            "legend": {"orientation": "h", "y": -0.2},
        }
        return (
            '<div id="viz" style="height:380px"></div>'
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
            '<script>Plotly.newPlot("viz", '
            + json.dumps(traces) + ", " + json.dumps(layout)
            + ", {responsive:true, displayModeBar:false});</script>"
        )
