"""Tests for the 5 default Visualization classes (v2: update(state))."""
from pbg_superpowers.visualizations import TimeSeriesPlot


def _trajectory_state():
    """One run's trajectory of ``observable`` and ``time``."""
    return {
        'observable': [1.0, 2.0, 4.0, 8.0],
        'time': [0.0, 1.0, 2.0, 3.0],
    }


def _multi_run_state():
    """Two runs' trajectories — orchestrator passes list-of-lists for sweeps."""
    return {
        'observable': [[1.0, 2.0, 4.0], [3.0, 6.0, 12.0]],
        'time': [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]],
        '_run_labels': ['rate=1.0', 'rate=3.0'],
    }


def test_time_series_plot_single_run():
    inst = object.__new__(TimeSeriesPlot)
    inst.config = {'title': 'Test'}
    html = inst.update(_trajectory_state())
    assert 'html' in html
    assert 'Plotly.newPlot' in html['html']
    assert 'Test' in html['html']


def test_time_series_plot_multi_run():
    inst = object.__new__(TimeSeriesPlot)
    inst.config = {'title': ''}
    html = inst.update(_multi_run_state())
    assert 'Plotly.newPlot' in html['html']
    assert 'rate=1.0' in html['html']
    assert 'rate=3.0' in html['html']
