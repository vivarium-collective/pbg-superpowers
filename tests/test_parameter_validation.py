"""Tests for parameter_validation: structure introspection + author-time
parameter-override validation — the parameter-side analog of
``test_readout_validation``.

Mirroring the readout tests, the validation logic is unit-tested against
hand-built composite *specs* (the authoritative source of the settable set;
see the module docstring for why the built composite is not) and against
pre-computed ``available_parameters`` dicts for the headless path.  A minimal
static spec (the ``increase-demo`` shape from ``tests/fixtures/composites``)
and a generator spec (the ``fake_generator_pkg`` shape) stand in for real
composites, exactly as the observable tests use a hand-built state/schema.
"""
from __future__ import annotations

import pytest

from viva_superpowers.parameter_validation import (
    available_parameters,
    validate_parameter_overrides,
)


# ---------------------------------------------------------------------------
# Reusable specs — a static spec with one referenced + one inert parameter,
# and a generator spec (params flow into the builder, no placeholders).
# ---------------------------------------------------------------------------

STATIC_SPEC = {
    "name": "increase-demo",
    "parameters": {
        "rate": {"type": "float", "default": 2.0},
        "initial_level": {"type": "float", "default": 1.0},
        "inert_knob": {"type": "float", "default": 0.0},  # declared, never used
    },
    "state": {
        "increase": {
            "_type": "process",
            "address": "local:IncreaseProcess",
            "config": {"rate": "${rate}"},
        },
        "stores": {"level": "${initial_level}"},
    },
}

GENERATOR_SPEC = {
    "name": "demo",
    "builder": "fake_generator_pkg.composites:demo",
    "parameters": {"x": {"type": "int", "default": 7}},
    "state": None,
}


# ---------------------------------------------------------------------------
# available_parameters — structure introspection
# ---------------------------------------------------------------------------

def test_available_parameters_lists_settable_and_referenced():
    """settable == declared keys; referenced == those used via ${name}."""
    avail = available_parameters(STATIC_SPEC)
    assert avail["settable"] == ["inert_knob", "initial_level", "rate"]
    assert avail["referenced"] == ["initial_level", "rate"]
    assert avail["inert"] == ["inert_knob"]


def test_available_parameters_declared_carries_metadata():
    """declared mirrors the spec param defs + a referenced flag."""
    avail = available_parameters(STATIC_SPEC)
    assert avail["declared"]["rate"] == {
        "type": "float", "default": 2.0, "description": None, "referenced": True,
    }
    assert avail["declared"]["inert_knob"]["referenced"] is False


def test_available_parameters_finds_nested_placeholders():
    """A ${name} buried in a nested config dict still counts as referenced."""
    spec = {
        "name": "nested",
        "parameters": {"deep": {"type": "float", "default": 1.0}},
        "state": {"a": {"b": {"c": {"config": {"v": "${deep}"}}}}},
    }
    avail = available_parameters(spec)
    assert avail["referenced"] == ["deep"]
    assert avail["inert"] == []


def test_available_parameters_generator_marks_referenced_none():
    """A generator spec cannot be statically scanned → referenced is None,
    inert is empty, every declared param is settable."""
    avail = available_parameters(GENERATOR_SPEC)
    assert avail["settable"] == ["x"]
    assert avail["referenced"] is None
    assert avail["inert"] == []
    assert avail["declared"]["x"]["referenced"] is None


def test_available_parameters_empty_when_no_parameters():
    """A spec with no declared parameters exposes nothing settable."""
    avail = available_parameters({"name": "bare", "state": {}})
    assert avail["settable"] == []
    assert avail["referenced"] == []
    assert avail["inert"] == []
    assert avail["declared"] == {}


# ---------------------------------------------------------------------------
# validate_parameter_overrides — the three statuses
# ---------------------------------------------------------------------------

def _status(overrides, name, **kw):
    results = validate_parameter_overrides(overrides, STATIC_SPEC, **kw)
    return next(r for r in results if r["name"] == name)


def test_valid_override_is_ok():
    """A referenced, declared parameter → ok."""
    r = _status({"rate": 5.0}, "rate")
    assert r["status"] == "ok"


def test_unknown_key_is_unknown():
    """A key that is not a declared parameter → unknown (never invented);
    a real run raises KeyError on it."""
    r = _status({"nonexistent_param": 3}, "nonexistent_param")
    assert r["status"] == "unknown"
    assert "not a declared parameter" in r["detail"]
    assert "KeyError" in r["detail"]


def test_declared_but_inert_is_not_settable():
    """A declared parameter with no ${name} placeholder → not_settable
    (the run accepts it but the document is unchanged); flagged, not silent."""
    r = _status({"inert_knob": 9.0}, "inert_knob")
    assert r["status"] == "not_settable"
    assert "never referenced" in r["detail"]


def test_empty_overrides_returns_empty_list():
    """No overrides → no results (and no error)."""
    assert validate_parameter_overrides({}, STATIC_SPEC) == []
    assert validate_parameter_overrides(None, STATIC_SPEC) == []


def test_generator_declared_param_is_ok_despite_no_placeholder():
    """On a generator spec a declared param is settable (consumed by the
    builder) even though it has no ${name} placeholder → ok, not not_settable."""
    results = validate_parameter_overrides({"x": 42}, GENERATOR_SPEC)
    assert results[0]["status"] == "ok"


def test_all_overrides_returned_in_order():
    """One result per override key, order preserved, mixed statuses."""
    overrides = {"rate": 1.0, "ghost": 2, "inert_knob": 3.0}
    results = validate_parameter_overrides(overrides, STATIC_SPEC)
    assert [r["name"] for r in results] == ["rate", "ghost", "inert_knob"]
    assert [r["status"] for r in results] == ["ok", "unknown", "not_settable"]


def test_precomputed_available_path():
    """Passing available= bypasses spec introspection (headless path)."""
    avail = available_parameters(STATIC_SPEC)
    results = validate_parameter_overrides(
        {"rate": 1.0, "ghost": 2}, available=avail)
    assert {r["name"]: r["status"] for r in results} == {
        "rate": "ok", "ghost": "unknown"}


def test_requires_available_or_spec():
    """Calling with neither available nor spec is a usage error."""
    with pytest.raises(ValueError):
        validate_parameter_overrides({"rate": 1.0})
