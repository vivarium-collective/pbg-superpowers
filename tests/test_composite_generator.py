"""Tests for pbg_superpowers.composite_generator."""
import shutil
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


def test_decorator_accepts_default_n_steps():
    @composite_generator(
        name="dn", description="", parameters={}, default_n_steps=200,
    )
    def builder(core=None):
        return {}

    entry = _REGISTRY[f"{builder.__module__}.dn"]
    assert entry.default_n_steps == 200


def test_decorator_default_n_steps_optional():
    @composite_generator(name="dn-opt", description="", parameters={})
    def builder(core=None):
        return {}

    entry = _REGISTRY[f"{builder.__module__}.dn-opt"]
    assert entry.default_n_steps is None


def test_decorator_accepts_visualizations():
    """``visualizations`` ships canonical Study-spec viz entries with the
    composite; dashboards can merge them into a Study without the author
    having to hand-author each."""
    viz_list = [
        {
            "name": "level-trace",
            "address": "local:TimeSeriesPlot",
            "config": {"observable": "level"},
        },
        {
            "name": "topology",
            "address": "local:NetworkVisualization",
            "config": {},
        },
    ]

    @composite_generator(
        name="vz",
        description="",
        parameters={},
        visualizations=viz_list,
    )
    def builder(core=None):
        return {}

    entry = _REGISTRY[f"{builder.__module__}.vz"]
    assert entry.visualizations == viz_list
    # Defensive copy — mutating the caller's list shouldn't change the entry.
    viz_list.append({"name": "intruder"})
    assert len(entry.visualizations) == 2


def test_decorator_visualizations_optional():
    @composite_generator(name="vz-opt", description="", parameters={})
    def builder(core=None):
        return {}

    entry = _REGISTRY[f"{builder.__module__}.vz-opt"]
    assert entry.visualizations == []


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


def _install_cmd(action: str, target: str) -> list[str]:
    """Build a pip install/uninstall command that targets ``sys.executable``.

    Prefers ``uv pip --python <sys.executable>`` because it (a) pins the
    target interpreter explicitly — bare ``uv pip`` would otherwise pick
    the project's ``.venv`` instead of the pyenv interpreter that's
    actually running pytest — and (b) doesn't require pip to be present
    in the target env, which matters in CI where ``uv venv`` creates a
    pip-less ``.venv``.

    Falls back to ``sys.executable -m pip`` when ``uv`` isn't on PATH,
    for contributors who run tests without uv installed.
    """
    if shutil.which("uv"):
        if action == "install":
            return ["uv", "pip", "install", "--python", sys.executable,
                    "-q", "-e", target]
        return ["uv", "pip", "uninstall", "--python", sys.executable, target]
    if action == "install":
        return [sys.executable, "-m", "pip", "install", "-q", "-e", target]
    return [sys.executable, "-m", "pip", "uninstall", "-q", "-y", target]


@pytest.fixture
def installed_fake_pkg():
    """Install the fixture package into the running test interpreter's env.

    Uses ``uv pip install --python sys.executable`` so the install lands
    in the same environment that runs the test, regardless of whether
    that env has pip available (CI's ``uv venv`` does not) and regardless
    of whether ``uv``'s default target ``.venv`` differs from
    ``sys.executable`` (e.g. running under pyenv locally). Falls back to
    ``sys.executable -m pip`` if uv is not installed.

    Also patches ``sys.path`` directly so the editable ``.pth`` file
    added by hatchling takes effect inside the already-running process
    (``site`` only processes ``.pth`` files at startup).
    """
    subprocess.run(_install_cmd("install", str(FIXTURE_PKG)), check=True)
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
    subprocess.run(_install_cmd("uninstall", "fake-generator-pkg"), check=True)


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


def test_discover_all_merges_specs_and_generators(tmp_path, installed_fake_pkg):
    # Create a tiny static spec in a tmp dir so discover_composites picks it up
    spec_file = tmp_path / "baseline.composite.yaml"
    spec_file.write_text("name: baseline\nstate: {}\n")

    from pbg_superpowers.composite_discovery import discover_all
    _REGISTRY.clear()
    merged = discover_all(extra_search_paths=[tmp_path])

    # Spec entry tagged spec
    spec_keys = [k for k, v in merged.items() if v.get("kind") == "spec"]
    assert any(k.endswith(".baseline") for k in spec_keys)

    # Generator entry tagged generator
    gen_id = "fake_generator_pkg.composites.demo"
    assert gen_id in merged
    assert merged[gen_id]["kind"] == "generator"
    assert merged[gen_id]["name"] == "demo"
    # default_n_steps is always propagated (None when the generator omits it).
    assert "default_n_steps" in merged[gen_id]
    # visualizations is always propagated as a list (empty when the generator
    # omits it) so dashboard callers can rely on the key existing.
    assert merged[gen_id].get("visualizations") == []
