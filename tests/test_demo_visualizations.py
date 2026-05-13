"""Tests for the demo Visualization classes shipped with pbg-superpowers."""
from pbg_superpowers._demo_visualizations import (
    DemoTimeSeriesPlot,
    DemoMultiTimeSeriesPlot,
    update_demo_list_line_plot as DemoListLinePlot,
)
from pbg_superpowers.visualization import Visualization


def test_time_series_plot_renders_a_single_step():
    inst = DemoTimeSeriesPlot.__new__(DemoTimeSeriesPlot)
    inst._values = []
    out = inst.update({'value': 2.5})
    assert 'html' in out
    assert 'Plotly' in out['html']
    assert 'value' in out['html']
    # one point accumulated
    assert inst._values == [2.5]


def test_time_series_plot_accumulates_across_steps():
    inst = DemoTimeSeriesPlot.__new__(DemoTimeSeriesPlot)
    inst._values = []
    for v in (1.0, 2.0, 3.0):
        out = inst.update({'value': v})
    assert inst._values == [1.0, 2.0, 3.0]
    # Last rendered HTML should embed all three values via Plotly trace
    assert 'Plotly' in out['html']


def test_time_series_plot_handles_missing_value():
    inst = DemoTimeSeriesPlot.__new__(DemoTimeSeriesPlot)
    inst._values = []
    out = inst.update({})
    assert 'html' in out
    assert 'Plotly' in out['html']
    assert inst._values == []


def test_time_series_plot_handles_non_numeric_value():
    inst = DemoTimeSeriesPlot.__new__(DemoTimeSeriesPlot)
    inst._values = []
    out = inst.update({'value': 'oops'})
    # Non-numeric is silently dropped; html still renders.
    assert inst._values == []
    assert 'Plotly' in out['html']


def test_multi_time_series_plot_renders():
    inst = DemoMultiTimeSeriesPlot.__new__(DemoMultiTimeSeriesPlot)
    inst._history = []
    inst.config = {'labels': ['A', 'B']}
    inst.update({'values': [1.0, 2.0]})
    out = inst.update({'values': [1.5, 1.8]})
    assert 'html' in out
    assert 'Plotly' in out['html']
    assert 'A' in out['html']
    assert 'B' in out['html']
    assert inst._history == [[1.0, 2.0], [1.5, 1.8]]


def test_multi_time_series_plot_default_labels():
    inst = DemoMultiTimeSeriesPlot.__new__(DemoMultiTimeSeriesPlot)
    inst._history = []
    inst.config = {'labels': []}
    out = inst.update({'values': [1.0, 2.0]})
    assert 'series_0' in out['html']
    assert 'series_1' in out['html']


def test_demo_list_line_plot_renders():
    inst = object.__new__(DemoListLinePlot)
    out = inst.update({'time': [0.0, 1.0, 2.0], 'value': [1.0, 2.0, 3.0]})
    assert 'html' in out
    assert 'Plotly' in out['html']
    assert 'value' in out['html']


def test_demo_classes_are_visualizations():
    assert issubclass(DemoTimeSeriesPlot, Visualization)
    assert issubclass(DemoMultiTimeSeriesPlot, Visualization)
    assert issubclass(DemoListLinePlot, Visualization)


def test_demo_classes_have_pb_aliases():
    assert 'DemoTimeSeriesPlot' in DemoTimeSeriesPlot.__pb_aliases__
    assert 'DemoMultiTimeSeriesPlot' in DemoMultiTimeSeriesPlot.__pb_aliases__
    assert 'DemoListLinePlot' in DemoListLinePlot.__pb_aliases__


def test_demo_state_dicts_present():
    assert DemoTimeSeriesPlot.demo() == {'value': 1.0}
    assert DemoMultiTimeSeriesPlot.demo() == {'values': [1.0, 2.0]}
    assert DemoListLinePlot.demo() == {
        'time': [0.0, 1.0, 2.0, 3.0, 4.0],
        'value': [1.0, 1.5, 2.1, 2.8, 3.4],
    }
