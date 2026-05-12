"""Tests for pbg_superpowers.composite_generator."""
import subprocess
import sys
from pathlib import Path

import pytest

from pbg_superpowers.composite_generator import (
    build_generator, composite_generator, GeneratorEntry, _REGISTRY,
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


def _make_entry(parameters, body):
    @composite_generator(name="t", description="", parameters=parameters)
    def _fn(core=None, **kw):
        return body(**kw)
    entry_id = f"{_fn.__module__}.t"
    return _REGISTRY[entry_id]


def test_build_generator_applies_defaults():
    entry = _make_entry(
        {"rate": {"type": "float", "default": 0.25}},
        lambda **kw: {"got": kw},
    )
    assert build_generator(entry) == {"got": {"rate": 0.25}}


def test_build_generator_applies_overrides():
    entry = _make_entry(
        {"rate": {"type": "float", "default": 0.25}},
        lambda **kw: {"got": kw},
    )
    assert build_generator(entry, overrides={"rate": 9.0}) == {"got": {"rate": 9.0}}


def test_build_generator_rejects_unknown_overrides():
    entry = _make_entry(
        {"rate": {"type": "float", "default": 0.25}},
        lambda **kw: {"got": kw},
    )
    with pytest.raises(ValueError, match="bogus"):
        build_generator(entry, overrides={"bogus": 1})


def test_build_generator_passes_core_when_present():
    seen = {}

    @composite_generator(name="t2", description="", parameters={})
    def builder(core=None):
        seen["core"] = core
        return {}

    entry = _REGISTRY[f"{builder.__module__}.t2"]
    sentinel = object()
    build_generator(entry, core=sentinel)
    assert seen["core"] is sentinel


FIXTURE_PKG = Path(__file__).parent / "fixtures" / "fake_generator_pkg"


@pytest.fixture
def installed_fake_pkg():
    """Install the fixture package into the current venv for the test.

    Uses ``uv pip`` (the project's package manager) because the venv is
    managed by uv and does not bundle pip.

    Also patches ``sys.path`` directly so the editable ``.pth`` file added
    by hatchling takes effect inside the already-running process (``site``
    only processes ``.pth`` files at startup).
    """
    subprocess.run(
        ["uv", "pip", "install", "-q", "-e", str(FIXTURE_PKG)],
        check=True,
    )
    # Editable installs write a .pth file that is only processed at Python
    # startup. Manually add the package root so importlib can find it now.
    pkg_root = str(FIXTURE_PKG)
    inserted = pkg_root not in sys.path
    if inserted:
        sys.path.insert(0, pkg_root)
    import importlib
    importlib.invalidate_caches()
    yield
    # Teardown: remove from sys.path and evict from sys.modules so subsequent
    # tests (or re-runs) don't see stale state.
    if inserted and pkg_root in sys.path:
        sys.path.remove(pkg_root)
    for mod_name in list(sys.modules):
        if mod_name == "fake_generator_pkg" or mod_name.startswith("fake_generator_pkg."):
            del sys.modules[mod_name]
    importlib.invalidate_caches()
    subprocess.run(
        ["uv", "pip", "uninstall", "-q", "fake-generator-pkg"],
        check=True,
    )


def test_discover_generators_finds_decorated_function_in_installed_pkg(
        installed_fake_pkg):
    from pbg_superpowers.composite_generator import discover_generators
    # Discovery must import the package — it can't rely on the test having
    # already done so.
    found = discover_generators()
    expected_id = "fake_generator_pkg.composites.demo"
    assert expected_id in found
    entry = found[expected_id]
    assert entry.name == "demo"
    assert entry.parameters == {"x": {"type": "int", "default": 7}}
