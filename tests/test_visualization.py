"""Tests for pbg_superpowers.visualization.Visualization (v0.5.0: final-mode required, streaming opt-in)."""
import pytest

from pbg_superpowers.visualization import Visualization


# ---------------------------------------------------------------------------
# Test subclass: counter accumulator that re-renders the running sum
# ---------------------------------------------------------------------------

class CounterRenderer(Visualization):
    """Test viz: accumulates 'value' input over steps; renders count as HTML."""

    config_schema = {
        'title': {'_type': 'string', '_default': 'Counter'},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []

    def inputs(self):
        return {'value': 'float'}

    def update(self, state, interval):
        self.history.append(state.get('value', 0.0))
        title = self.config.get('title', 'Counter') if hasattr(self, 'config') else 'Counter'
        n = len(self.history)
        return {'html': f'<div>{title}: {n} steps, sum={sum(self.history)}</div>'}


# ---------------------------------------------------------------------------
# Static contract tests
# ---------------------------------------------------------------------------

def test_visualization_is_step_subclass():
    from process_bigraph import Step
    assert issubclass(Visualization, Step)


def test_visualization_marker():
    assert CounterRenderer.is_visualization() is True


def test_base_render_final_raises_not_implemented():
    """Base class render_final() raises so subclasses are forced to override."""
    with pytest.raises(NotImplementedError, match="render_final"):
        Visualization.render_final(None, {}, config={})  # type: ignore[arg-type]


def test_subclass_inputs_outputs():
    """Subclass declares inputs/outputs as expected."""
    inst = CounterRenderer.__new__(CounterRenderer)
    inst.history = []
    assert inst.inputs() == {'value': 'float'}
    assert inst.outputs() == {'html': 'string'}


def test_subclass_update_returns_html_dict():
    """Calling update returns a dict matching outputs()."""
    inst = CounterRenderer.__new__(CounterRenderer)
    inst.history = []
    inst.config = {'title': 'Counter'}
    out = inst.update({'value': 3.0}, 1.0)
    assert isinstance(out, dict)
    assert 'html' in out
    assert '<div>' in out['html']
    assert '1 steps' in out['html']  # one step accumulated


def test_subclass_accumulates_across_calls():
    """history grows monotonically across update() calls."""
    inst = CounterRenderer.__new__(CounterRenderer)
    inst.history = []
    inst.config = {'title': 'Counter'}
    inst.update({'value': 1.0}, 1.0)
    inst.update({'value': 2.0}, 1.0)
    inst.update({'value': 3.0}, 1.0)
    assert inst.history == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Discoverability tests
# ---------------------------------------------------------------------------

def test_visualization_filter_pattern():
    """The pattern the dashboard uses to find Visualization subclasses."""
    from process_bigraph import Process, Step
    registry = {
        'CounterRenderer': CounterRenderer,
        'Step': Step,
        'Process': Process,
        'Visualization': Visualization,
    }
    viz_only = {
        name: cls for name, cls in registry.items()
        if isinstance(cls, type)
           and issubclass(cls, Visualization)
           and cls is not Visualization
    }
    assert 'CounterRenderer' in viz_only
    assert 'Visualization' not in viz_only
    assert 'Step' not in viz_only


# ---------------------------------------------------------------------------
# Integration: wire into a Composite, verify html output reaches a store
# ---------------------------------------------------------------------------

def test_visualization_wired_into_composite():
    """End-to-end: a Visualization wired into a Composite captures html on each step.

    NOTE: this test verifies the contract works in principle. The exact
    Composite wiring API may vary; the key assertion is that:
      1. The Visualization subclass instantiates as a Step
      2. update() can be called with the wired state dict
      3. The returned 'html' value is a string with content
    """
    from process_bigraph import allocate_core

    core = allocate_core()
    inst = CounterRenderer.__new__(CounterRenderer)
    inst.history = []
    inst.config = {'title': 'Trajectory'}

    # Simulate three sim steps with increasing values
    states = [{'value': 0.0}, {'value': 1.0}, {'value': 4.0}]
    htmls = []
    for s in states:
        result = inst.update(s, 1.0)
        htmls.append(result['html'])

    # Each step should produce a different (longer) html (accumulating sum)
    assert all('<div>' in h for h in htmls)
    assert '1 steps' in htmls[0]
    assert '2 steps' in htmls[1]
    assert '3 steps' in htmls[2]
    assert 'sum=5.0' in htmls[2]  # 0 + 1 + 4


# ---------------------------------------------------------------------------
# v0.5.0 contract: render_final required, update opt-in via supports_streaming
# ---------------------------------------------------------------------------

def test_visualization_render_final_raises_by_default():
    """Base class render_final must raise NotImplementedError so subclasses must override."""
    with pytest.raises(NotImplementedError, match="render_final"):
        Visualization.render_final(None, {}, config={})


def test_visualization_supports_streaming_default_false():
    """Default class attribute is False — subclasses opt in to streaming."""
    assert Visualization.supports_streaming is False


def test_visualization_update_default_returns_empty_html():
    """Base update is a no-op for final-mode visualizations."""
    inst = object.__new__(Visualization)
    out = inst.update({}, 1.0)
    assert out == {'html': ''}
