"""Tests for pbg_superpowers.visualization.Visualization (v2: update(state) only)."""
import pytest

from process_bigraph import Step
from pbg_superpowers.visualization import Visualization


class _Echo(Visualization):
    """Test subclass that echoes the input as html."""

    def inputs(self):
        return {'msg': 'string'}

    def update(self, state):
        return {'html': '<p>' + state.get('msg', '') + '</p>'}


def test_visualization_is_step_subclass():
    assert issubclass(Visualization, Step)


def test_visualization_base_update_raises_not_implemented():
    inst = object.__new__(Visualization)
    with pytest.raises(NotImplementedError, match='update'):
        inst.update({})


def test_visualization_outputs_default_html():
    inst = object.__new__(Visualization)
    assert inst.outputs() == {'html': 'string'}


def test_visualization_inputs_default_empty():
    inst = object.__new__(Visualization)
    assert inst.inputs() == {}


def test_subclass_update_returns_html_dict():
    inst = object.__new__(_Echo)
    out = inst.update({'msg': 'hello'})
    assert out == {'html': '<p>hello</p>'}


def test_visualization_marker_classmethod():
    assert _Echo.is_visualization() is True


from pbg_superpowers.visualization import as_visualization


def test_as_visualization_synthesizes_subclass():
    @as_visualization(inputs={'x': 'list[float]'}, name='MyViz', demo={'x': [1.0, 2.0]})
    def update_my_viz(state):
        return {'html': '<p>x=' + str(state['x']) + '</p>'}

    assert issubclass(update_my_viz, Visualization)
    assert update_my_viz.__name__ == 'MyViz'
    assert update_my_viz.__pb_kind__ == 'visualization'
    assert 'MyViz' in update_my_viz.__pb_aliases__
    inst = object.__new__(update_my_viz)
    assert inst.inputs() == {'x': 'list[float]'}
    assert inst.outputs() == {'html': 'string'}
    assert inst.update({'x': [1.0, 2.0]}) == {'html': '<p>x=[1.0, 2.0]</p>'}


def test_as_visualization_demo_dict():
    @as_visualization(inputs={'x': 'list[float]'},
                      demo={'x': [3.0, 4.0]})
    def update_demo_dict(state):
        return {'html': str(state['x'])}

    assert update_demo_dict.demo() == {'x': [3.0, 4.0]}


def test_as_visualization_demo_callable():
    @as_visualization(inputs={'x': 'list[float]'},
                      demo=lambda: {'x': [5.0, 6.0]})
    def update_demo_callable(state):
        return {'html': str(state['x'])}

    assert update_demo_callable.demo() == {'x': [5.0, 6.0]}


def test_as_visualization_function_name_validation():
    with pytest.raises(AssertionError, match='update_'):
        @as_visualization(inputs={})
        def bad_name(state):
            return {'html': ''}


def test_as_visualization_default_name_from_function():
    @as_visualization(inputs={'x': 'list[float]'})
    def update_inferred_name(state):
        return {'html': ''}

    assert update_inferred_name.__name__ == 'inferred_name'
    assert 'inferred_name' in update_inferred_name.__pb_aliases__


def test_as_visualization_aliases():
    @as_visualization(inputs={}, name='Primary', aliases=['alt1', 'alt2'])
    def update_aliased(state):
        return {'html': ''}

    assert 'Primary' in update_aliased.__pb_aliases__
    assert 'alt1' in update_aliased.__pb_aliases__
    assert 'alt2' in update_aliased.__pb_aliases__
