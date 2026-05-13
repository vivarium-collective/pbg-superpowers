"""Tests for pbg_superpowers.visualization.render_results.

Mirrors the shape of ``process_bigraph.emitter.gather_emitter_results``:
returns a path-keyed dict whose values are the per-viz ``{'html': str}`` dicts.
"""
from __future__ import annotations

from process_bigraph import Composite, allocate_core

from pbg_superpowers.visualization import as_visualization, render_results


# --- viz fixtures registered at module level so ``allocate_core`` discovers ---
@as_visualization(inputs={'k': 'string'}, name='_RR_EchoViz')
def update__rr_echo_viz(state):
    return {'html': '<x>' + state.get('k', '') + '</x>'}


@as_visualization(inputs={'k': 'string'}, name='_RR_LabelViz')
def update__rr_label_viz(state):
    return {'html': '<label>' + state.get('k', '') + '</label>'}


def _make_core():
    core = allocate_core()
    core.register_link('_RR_EchoViz', update__rr_echo_viz)
    core.register_link('_RR_LabelViz', update__rr_label_viz)
    return core


def _make_state_with_echo():
    return {
        'k_store': 'streamed',
        'viz1': {
            '_type': 'step',
            'address': 'local:_RR_EchoViz',
            'config': {},
            'inputs': {'k': ['k_store']},
            'outputs': {'html': ['viz_html_store']},
        },
        'viz_html_store': '',
    }


def test_render_results_replay_mode():
    """``render_results(composite, results={...})`` replays each viz's
    ``update`` directly with the provided dict, bypassing bigraph wiring."""
    composite = Composite({'state': _make_state_with_echo()}, core=_make_core())
    out = render_results(composite, results={'k': 'replay'})
    assert ('viz1',) in out
    html = out[('viz1',)]['html']
    assert 'replay' in html
    # And replay mode does NOT depend on the wiring having been run.
    assert composite.state['viz_html_store'] == ''


def test_render_results_finds_nothing_when_no_viz():
    """A composite with no Visualization instances returns an empty dict."""
    core = _make_core()
    state = {'k_store': 'hello'}  # no step/viz instance at all
    composite = Composite({'state': state}, core=core)
    out = render_results(composite)
    assert out == {}


def test_render_results_returns_path_keyed_dict():
    """Two visualizations at different paths show up as two entries."""
    core = _make_core()
    state = {
        'k_store': 'streamed',
        'viz_a': {
            '_type': 'step',
            'address': 'local:_RR_EchoViz',
            'config': {},
            'inputs': {'k': ['k_store']},
            'outputs': {'html': ['viz_a_html']},
        },
        'viz_a_html': '',
        'viz_b': {
            '_type': 'step',
            'address': 'local:_RR_LabelViz',
            'config': {},
            'inputs': {'k': ['k_store']},
            'outputs': {'html': ['viz_b_html']},
        },
        'viz_b_html': '',
    }
    composite = Composite({'state': state}, core=core)
    composite.run(1)
    out = render_results(composite)
    assert set(out.keys()) == {('viz_a',), ('viz_b',)}
    # Streaming mode reads the value the runtime wrote to the wired html
    # store after running update once per step.
    assert '<x>streamed</x>' == out[('viz_a',)]['html']
    assert '<label>streamed</label>' == out[('viz_b',)]['html']
