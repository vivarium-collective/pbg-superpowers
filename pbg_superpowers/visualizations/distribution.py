"""Distribution — histogram or KDE of an observable across runs."""
from __future__ import annotations
import html as _html
import json

from pbg_superpowers.visualization import Visualization


class Distribution(Visualization):
    """Plot the distribution of an observable across runs at a fixed step.

    Config keys:
      observable: str
      sources:    list[str]
      at_step:    "final" | int (step index)
      kind:       "histogram" | "kde"  (kde currently renders as histogram with smoothing)
      title:      str
    """

    def render_final(self, results: dict, *, config: dict) -> str:
        observable = config.get("observable", "")
        sources = config.get("sources") or list(results.keys())
        at_step = config.get("at_step", "final")
        kind = config.get("kind", "histogram")
        title = config.get("title", "")

        values: list[float] = []
        for sim_name in sources:
            sim = results.get(sim_name) or {}
            for run in sim.get("runs", []):
                traj = run.get("trajectory") or []
                if not traj:
                    continue
                if at_step == "final":
                    pt = traj[-1]
                else:
                    try:
                        pt = traj[int(at_step)]
                    except (IndexError, ValueError):
                        continue
                state = pt.get("state") or {}
                if observable in state:
                    values.append(state[observable])

        traces = [{
            "x": values, "type": "histogram",
            "marker": {"color": "#6366f1"},
            "opacity": 0.85,
            "name": observable,
        }]
        layout = {
            "title": {"text": _html.escape(title), "font": {"size": 14}},
            "xaxis": {"title": {"text": _html.escape(observable)}},
            "yaxis": {"title": {"text": "count"}},
            "margin": {"l": 55, "r": 15, "t": 40, "b": 40},
            "showlegend": False,
            "bargap": 0.05,
        }
        return (
            '<div id="viz" style="height:380px"></div>'
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
            '<script>Plotly.newPlot("viz", '
            + json.dumps(traces) + ", " + json.dumps(layout)
            + ", {responsive:true, displayModeBar:false});</script>"
        )
