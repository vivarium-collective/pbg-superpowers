"""Demo Visualization Steps that ship with pbg-superpowers.

Generic, composite-agnostic plotters that any user composite can wire in
without needing to author its own viz class.

Three classes are registered into ``core.link_registry`` via
``bigraph_schema.discover_packages`` along with every other Visualization in
the package:

- ``DemoTimeSeriesPlot`` — accumulates one scalar per step into a buffer,
  renders a single Plotly line of value vs step. Inputs: ``value: float``.
  Wire ``value`` to any scalar store in your composite.
- ``DemoMultiTimeSeriesPlot`` — accumulates a list of floats per step, one
  line per element. Inputs: ``values: list[float]``.
- ``DemoListLinePlot`` — stateless variant that expects ``time`` and
  ``value`` as full ``list[float]`` trajectories at render time. Useful
  when the input store is already a list (e.g. fed by an upstream
  trajectory-accumulating Step).

Names are prefixed ``Demo`` to avoid colliding with the existing
:class:`pbg_superpowers.visualizations.time_series.TimeSeriesPlot`, which
has a richer (but composite-agnostic-incompatible) input contract using
``observable`` rather than the more general ``value`` port used here.
"""
from __future__ import annotations
import json

from .visualization import Visualization, as_visualization


_PALETTE = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899']


def _plotly_html(traces, layout, height=280):
    return (
        f'<div id="viz" style="height:{height}px"></div>'
        '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
        '<script>Plotly.newPlot("viz", ' + json.dumps(traces) + ', '
        + json.dumps(layout) + ', {responsive:true, displayModeBar:false});</script>'
    )


class DemoTimeSeriesPlot(Visualization):
    """Accumulate a scalar ``value`` per step; render value-vs-step line plot.

    Wire ``inputs: {value: [path, to, scalar, store]}``. Each ``update`` call
    appends the current scalar to an internal buffer and returns a fresh
    Plotly HTML snapshot containing the trajectory so far.
    """

    def inputs(self):
        return {'value': 'float'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._values: list[float] = []

    def update(self, state):
        # Re-initialise the buffer lazily so the class survives clone/pickling
        # paths that bypass ``__init__``.
        if not hasattr(self, '_values') or self._values is None:
            self._values = []
        v = state.get('value')
        if v is not None:
            try:
                self._values.append(float(v))
            except (TypeError, ValueError):
                pass
        xs = list(range(len(self._values)))
        traces = [{
            'x': xs,
            'y': list(self._values),
            'mode': 'lines+markers',
            'line': {'color': _PALETTE[0], 'width': 2},
        }]
        layout = {
            'margin': {'l': 48, 'r': 12, 't': 28, 'b': 36},
            'xaxis': {'title': {'text': 'step'}},
            'yaxis': {'title': {'text': 'value'}},
            'height': 280,
        }
        return {'html': _plotly_html(traces, layout)}

    @classmethod
    def demo(cls):
        return {'value': 1.0}

    @classmethod
    def is_visualization(cls) -> bool:
        return True


# Class-level alias metadata so bigraph-schema discovery registers the short
# name ``DemoTimeSeriesPlot`` (and any extras) in ``core.link_registry``.
DemoTimeSeriesPlot.__pb_kind__ = 'visualization'
DemoTimeSeriesPlot.__pb_aliases__ = ['DemoTimeSeriesPlot']


class DemoMultiTimeSeriesPlot(Visualization):
    """Accumulate a ``list[float]`` per step; render one line per element.

    Wire ``inputs: {values: [path, to, list_store]}``. Each step appends the
    current snapshot to an internal history; the rendered HTML shows one line
    per element index across all collected steps.
    """

    config_schema = {
        'title': {'_type': 'string', '_default': ''},
        'labels': {'_type': 'list[string]', '_default': []},
    }

    def inputs(self):
        return {'values': 'list[float]'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history: list[list[float]] = []

    def update(self, state):
        if not hasattr(self, '_history') or self._history is None:
            self._history = []
        values = state.get('values') or []
        # Coerce to a plain list of floats per row.
        row: list[float] = []
        for x in values:
            try:
                row.append(float(x))
            except (TypeError, ValueError):
                continue
        self._history.append(row)

        # Transpose history -> [series][step]
        n_series = max((len(r) for r in self._history), default=0)
        labels = (getattr(self, 'config', None) or {}).get('labels') or []
        traces = []
        for s in range(n_series):
            ys = [r[s] if s < len(r) else None for r in self._history]
            traces.append({
                'x': list(range(len(self._history))),
                'y': ys,
                'mode': 'lines',
                'name': labels[s] if s < len(labels) else f'series_{s}',
                'line': {'color': _PALETTE[s % len(_PALETTE)], 'width': 2},
            })
        layout = {
            'margin': {'l': 48, 'r': 12, 't': 28, 'b': 36},
            'xaxis': {'title': {'text': 'step'}},
            'height': 280,
            'showlegend': True,
        }
        return {'html': _plotly_html(traces, layout)}

    @classmethod
    def demo(cls):
        return {'values': [1.0, 2.0]}

    @classmethod
    def is_visualization(cls) -> bool:
        return True


DemoMultiTimeSeriesPlot.__pb_kind__ = 'visualization'
DemoMultiTimeSeriesPlot.__pb_aliases__ = ['DemoMultiTimeSeriesPlot']


@as_visualization(
    inputs={'time': 'list[float]', 'value': 'list[float]'},
    name='DemoListLinePlot',
    demo={'time': [0.0, 1.0, 2.0, 3.0, 4.0], 'value': [1.0, 1.5, 2.1, 2.8, 3.4]},
)
def update_demo_list_line_plot(state):
    """Stateless: render full ``time``/``value`` trajectories as one line.

    Intended for replay/post-hoc use where the input store already holds the
    full trajectory list. In streaming use, wire to a scalar-accumulating
    upstream Step or use :class:`DemoTimeSeriesPlot` instead.
    """
    time = state.get('time') or []
    value = state.get('value') or []
    traces = [{
        'x': list(time),
        'y': list(value),
        'mode': 'lines',
        'line': {'color': '#3b82f6', 'width': 2},
    }]
    layout = {
        'margin': {'l': 48, 'r': 12, 't': 28, 'b': 36},
        'xaxis': {'title': {'text': 'time'}},
        'yaxis': {'title': {'text': 'value'}},
        'height': 280,
    }
    return {'html': _plotly_html(traces, layout)}
