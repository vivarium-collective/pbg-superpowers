"""Tests for the reusable Intervention process (pbg_superpowers.intervention)."""
import pytest

from bigraph_schema import allocate_core
from process_bigraph import Composite

from pbg_superpowers.intervention import (
    Intervention, register_intervention, intervention_node,
)


def _run(node, x0=10.0, steps=3):
    core = allocate_core()
    # Safe to call even if allocate_core already auto-registered Intervention
    # (installed Process subclasses are auto-discovered, like emitters).
    register_intervention(core)
    comp = Composite({'state': {'x': float(x0), 'iv': node}}, core=core)
    comp.run(steps)
    return comp.state['x']


def test_register_is_idempotent_and_safe():
    core = allocate_core()
    # First call may be True (we registered) or False (already auto-registered);
    # either way a second call must be a no-op False and never raise.
    register_intervention(core)
    assert register_intervention(core) is False
    assert 'Intervention' in (getattr(core, 'link_registry', {}) or {})


def test_set_clamps_to_value():
    assert _run(intervention_node(['x'], mode='set', value=3.0)) == pytest.approx(3.0)


def test_knockout_zeroes_target():
    assert _run(intervention_node(['x'], mode='knockout')) == pytest.approx(0.0)


def test_scale_multiplies():
    # one step: 8 * 0.5 = 4
    assert _run(intervention_node(['x'], mode='scale', value=0.5), x0=8.0, steps=1) == pytest.approx(4.0)


def test_add_bolus_per_step():
    # +2 each step for 3 steps from 0 -> 6
    assert _run(intervention_node(['x'], mode='add', value=2.0), x0=0.0, steps=3) == pytest.approx(6.0)


def test_window_gates_the_intervention():
    # set->5 only during elapsed t in [1,2); persists after.
    assert _run(intervention_node(['x'], mode='set', value=5.0, window=[1, 2]),
                x0=0.0, steps=4) == pytest.approx(5.0)


def test_window_inactive_leaves_target_untouched():
    # window [5,6) never reached in 3 steps -> stays at x0
    assert _run(intervention_node(['x'], mode='set', value=99.0, window=[5, 6]),
                x0=7.0, steps=3) == pytest.approx(7.0)


def test_intervention_node_shape():
    n = intervention_node(['nutrient'], mode='set', value=0.0)
    assert n['_type'] == 'process'
    assert n['address'] == 'local:Intervention'
    assert n['inputs']['target'] == ['nutrient']
    assert n['outputs']['target'] == ['nutrient']
    assert n['config']['mode'] == 'set'


def test_config_schema_present():
    assert 'mode' in Intervention.config_schema
    assert 'window' in Intervention.config_schema


def test_decouple_freezes_at_first_active_value():
    # decouple holds the target at its value when the intervention first became
    # active. With no other process moving x, that's just the initial value.
    assert _run(intervention_node(['x'], mode='decouple'), x0=12.0, steps=3) == pytest.approx(12.0)


def test_remove_is_alias_for_decouple():
    assert _run(intervention_node(['x'], mode='remove'), x0=4.0, steps=2) == pytest.approx(4.0)


def test_invert_drives_to_negative_current():
    # one step: delta = -2*5 = -10 -> x = -5
    assert _run(intervention_node(['x'], mode='invert'), x0=5.0, steps=1) == pytest.approx(-5.0)
