"""Tests for pbg_superpowers.composite_generator."""
import pytest

from pbg_superpowers.composite_generator import (
    composite_generator, GeneratorEntry, _REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Each test starts with an empty registry."""
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_decorator_registers_function():
    @composite_generator(
        name="my-composite",
        description="A test composite.",
        parameters={"rate": {"type": "float", "default": 1.0}},
    )
    def builder(core=None, *, rate=1.0):
        return {"stores": {"level": rate}}

    # Function is registered with its module-qualified id
    entry_id = f"{builder.__module__}.my-composite"
    assert entry_id in _REGISTRY
    entry = _REGISTRY[entry_id]
    assert isinstance(entry, GeneratorEntry)
    assert entry.name == "my-composite"
    assert entry.description == "A test composite."
    assert entry.parameters == {"rate": {"type": "float", "default": 1.0}}
    assert entry.func is builder
    # Wrapped function is unchanged-ish: callable with same signature
    assert builder(rate=2.0) == {"stores": {"level": 2.0}}
    # Sidecar on the function for introspection
    assert builder._composite_generator_entry is entry
