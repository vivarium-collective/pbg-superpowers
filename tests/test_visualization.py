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
