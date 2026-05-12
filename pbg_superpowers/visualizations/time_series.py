"""TimeSeriesPlot — observable(s) vs time, one line per run."""
from __future__ import annotations
import html as _html
import json
from typing import Any

from pbg_superpowers.visualization import Visualization


_PALETTE = ['#6366f1', '#10b981', '#f43f5e', '#f59e0b',
            '#8b5cf6', '#06b6d4', '#84cc16', '#ec4899']


class TimeSeriesPlot(Visualization):
    """Plot one observable across N runs, one trace per run.

    Config keys:
      observable: str — name of the observable to plot (read from trajectory state)
      sources:    list[str] — which simulations to include (sim names from spec)
      title:      str — optional chart title

    Special config (set by orchestrator, not by user):
      _overlays:  list[dict] — overlay payloads to render alongside primary traces
    """

    def render_final(self, results: dict, *, config: dict) -> str:
        observable = config.get("observable", "")
        sources = config.get("sources") or list(results.keys())
        title = config.get("title", "")
        overlays = config.get("_overlays") or []

        traces: list[dict] = []
        color_idx = 0
        for sim_name in sources:
            sim = results.get(sim_name) or {}
            for run in sim.get("runs", []):
                xs, ys = [], []
                for pt in run.get("trajectory", []):
                    state = pt.get("state") or {}
                    if observable not in state:
                        continue
                    xs.append(pt.get("time"))
                    ys.append(state[observable])
                if not xs:
                    continue
                label = run.get("run_id", "")
                params = run.get("params") or {}
                if params:
                    label = ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
                traces.append({
                    "x": xs, "y": ys, "type": "scatter", "mode": "lines",
                    "name": label, "line": {"color": _PALETTE[color_idx % len(_PALETTE)],
                                            "width": 2},
                })
                color_idx += 1

        shapes: list[dict] = []
        annotations: list[dict] = []
        for ov in overlays:
            kind = ov.get("kind")
            if kind == "reference-range":
                y_min, y_max = ov.get("y_min"), ov.get("y_max")
                if y_min is not None and y_max is not None:
                    shapes.append({
                        "type": "rect", "xref": "paper", "yref": "y",
                        "x0": 0, "x1": 1, "y0": y_min, "y1": y_max,
                        "fillcolor": "#fef3c7", "opacity": 0.3, "line": {"width": 0},
                    })
                    annotations.append({
                        "xref": "paper", "yref": "y", "x": 0.02, "y": y_max,
                        "text": _html.escape(ov.get("label", "reference range")),
                        "showarrow": False, "font": {"size": 11, "color": "#92400e"},
                    })
            elif kind == "experimental-points":
                pts = ov.get("points") or []
                if pts:
                    traces.append({
                        "x": [p["x"] for p in pts],
                        "y": [p["y"] for p in pts],
                        "type": "scatter", "mode": "markers",
                        "name": ov.get("label", "experimental"),
                        "marker": {"color": "#000", "size": 8, "symbol": "circle-open"},
                    })
            elif kind == "cross-investigation-series":
                xs = ov.get("x") or []
                ys = ov.get("y") or []
                if xs and ys:
                    traces.append({
                        "x": xs, "y": ys, "type": "scatter", "mode": "lines",
                        "name": ov.get("label", "cross-investigation"),
                        "line": {"color": "#94a3b8", "width": 1.5, "dash": "dash"},
                    })
            elif kind == "warning":
                annotations.append({
                    "xref": "paper", "yref": "paper", "x": 0.5, "y": 1.04,
                    "text": "⚠ overlay: " + _html.escape(ov.get("message", "")),
                    "showarrow": False, "font": {"size": 10, "color": "#991b1b"},
                })

        layout = {
            "title": {"text": _html.escape(title), "font": {"size": 14}},
            "xaxis": {"title": {"text": "time"}},
            "yaxis": {"title": {"text": _html.escape(observable)}},
            "margin": {"l": 55, "r": 15, "t": 40, "b": 40},
            "legend": {"orientation": "h", "y": -0.2},
            "shapes": shapes,
            "annotations": annotations,
        }
        return (
            '<div id="viz" style="height:380px"></div>'
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
            '<script>Plotly.newPlot("viz", '
            + json.dumps(traces) + ", " + json.dumps(layout)
            + ", {responsive:true, displayModeBar:false});</script>"
        )
