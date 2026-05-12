# Composite Generator Convention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `@composite_generator` decorator + discovery layer in pbg-superpowers, then migrate spatio-flux's 19 `doc_func`-based test composites onto it, gated by per-composite doc snapshot tests.

**Architecture:** A new pbg-superpowers convention sibling to `*.composite.{yaml,json}` static specs. Decorator records `(name, description, parameters, func)` in a process-level registry on import. Discovery walks installed `bigraph-schema`-dependent packages and imports each so decorators fire. Spatio-flux moves each old `doc_func` into a normalized `(core=None, *, **kwargs) -> dict` form under `spatio_flux/composites/<group>.py`. Each migration is gated by a structural snapshot test: capture the OLD doc, assert the NEW generator produces an equivalent doc, delete the OLD function.

**Tech Stack:** Python 3.11+, process-bigraph, bigraph-schema, pytest, hatchling. Spec at `docs/superpowers/specs/2026-05-12-composite-generator-convention.md`.

---

## File Structure

**pbg-superpowers** (`~/code/pbg-superpowers/`):
- `pbg_superpowers/composite_generator.py` — NEW. `GeneratorEntry`, `composite_generator` decorator, `_REGISTRY`, `discover_generators`, `build_generator`.
- `pbg_superpowers/composite_discovery.py` — MODIFY. Add `discover_all` that merges specs + generators with `kind` tag.
- `tests/test_composite_generator.py` — NEW. Unit tests for decorator, registry, builder, discovery.
- `tests/fixtures/fake_generator_pkg/` — NEW. Minimal installable package used by discovery tests.
- `pyproject.toml` — MODIFY. Bump version `0.4.15` → `0.4.16`.
- `docs/conventions/composite_generators.md` — NEW. Convention doc.
- `docs/conventions/composites.md` — MODIFY. Add "See also: composite_generators.md" cross-link.

**spatio-flux** (`~/code/spatio-flux/`):
- `spatio_flux/composites/__init__.py` — NEW. Imports `metabolism`, `spatial`, `particles`, `comets`, `reference` so decorators register. Re-exports `_REGISTRY` as `REGISTRY`.
- `spatio_flux/composites/metabolism.py` — NEW. 6 generators.
- `spatio_flux/composites/spatial.py` — NEW. 3 generators.
- `spatio_flux/composites/particles.py` — NEW. 4 generators.
- `spatio_flux/composites/comets.py` — NEW. 4 generators.
- `spatio_flux/composites/reference.py` — NEW. 2 generators.
- `spatio_flux/composites/_serialize.py` — NEW. `normalize_doc()` for snapshot comparison.
- `spatio_flux/composites/_snapshots/<name>.json` — NEW. 19 baseline files.
- `tools/capture_baseline_doc.py` — NEW. CLI to capture baseline snapshots.
- `tests/test_composite_generators.py` — NEW. Parametrized snapshot tests.
- `spatio_flux/experiments/test_suite.py` — MODIFY. Replace `doc_func`/`config` with `generator`/`overrides`; delete each old `get_*_doc` as its generator lands.
- `pyproject.toml` — MODIFY. Add `pbg-superpowers>=0.4.16` to runtime deps.

---

## Phase A — pbg-superpowers convention foundation

### Task A1: GeneratorEntry dataclass + decorator (TDD)

**Files:**
- Create: `pbg_superpowers/composite_generator.py`
- Test: `tests/test_composite_generator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_composite_generator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/code/pbg-superpowers && source .venv/bin/activate
pytest tests/test_composite_generator.py::test_decorator_registers_function -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pbg_superpowers.composite_generator'`.

- [ ] **Step 3: Write minimal implementation**

Create `pbg_superpowers/composite_generator.py`:

```python
"""Composite generator convention — decorator + registry.

Sibling to the *.composite.{yaml,json} static-spec convention. A composite
generator is a Python function `(core=None, **kwargs) -> dict` that builds
a process-bigraph document; the decorator records it in a module-level
registry so discovery can enumerate generators without callers having to
maintain a separate list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class GeneratorEntry:
    """One registered composite-generator function."""

    id: str                           # "<dotted_module>.<name>"
    name: str
    description: str
    parameters: dict[str, dict]       # {name: {type, default, description?}}
    func: Callable[..., dict]
    module: str


# Process-level registry. Populated by @composite_generator on import.
_REGISTRY: dict[str, GeneratorEntry] = {}


def composite_generator(
    *,
    name: str,
    description: str = "",
    parameters: dict[str, dict] | None = None,
) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Decorator: register a doc-building function.

    The wrapped function must accept ``(core=None, **kwargs) -> dict`` and
    return a process-bigraph state document (or a {state, schema} envelope).

    `parameters` declares each kwarg in the same shape that *.composite.yaml
    uses, so the dashboard's parameter-form code is shared across both
    conventions.
    """
    def decorate(fn: Callable[..., dict]) -> Callable[..., dict]:
        entry = GeneratorEntry(
            id=f"{fn.__module__}.{name}",
            name=name,
            description=description,
            parameters=parameters or {},
            func=fn,
            module=fn.__module__,
        )
        _REGISTRY[entry.id] = entry
        fn._composite_generator_entry = entry  # introspection sidecar
        return fn
    return decorate
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_composite_generator.py::test_decorator_registers_function -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/composite_generator.py tests/test_composite_generator.py
git commit -m "feat(composite_generator): add decorator and registry"
```

---

### Task A2: build_generator — parameter validation + defaults

**Files:**
- Modify: `pbg_superpowers/composite_generator.py`
- Test: `tests/test_composite_generator.py`

- [ ] **Step 1: Write failing tests for build_generator**

Append to `tests/test_composite_generator.py`:

```python
from pbg_superpowers.composite_generator import build_generator


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
    with pytest.raises(KeyError, match="bogus"):
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_composite_generator.py -v
```
Expected: `test_build_generator_*` FAIL with `ImportError: cannot import name 'build_generator'`.

- [ ] **Step 3: Implement build_generator**

Append to `pbg_superpowers/composite_generator.py`:

```python
def build_generator(
    entry: GeneratorEntry,
    overrides: dict[str, Any] | None = None,
    core: Any = None,
) -> dict:
    """Call the wrapped function with merged defaults + overrides.

    Unknown override keys raise KeyError so dashboards / callers can't
    silently smuggle in parameters that the generator doesn't declare.
    """
    overrides = overrides or {}
    unknown = set(overrides) - set(entry.parameters)
    if unknown:
        raise KeyError(
            f"unknown parameter(s) for {entry.id}: {sorted(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    for pname, pdecl in entry.parameters.items():
        if pname in overrides:
            kwargs[pname] = overrides[pname]
        elif "default" in pdecl:
            kwargs[pname] = pdecl["default"]
    return entry.func(core=core, **kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_composite_generator.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pbg_superpowers/composite_generator.py tests/test_composite_generator.py
git commit -m "feat(composite_generator): add build_generator with override validation"
```

---

### Task A3: discover_generators — walk installed packages

**Files:**
- Modify: `pbg_superpowers/composite_generator.py`
- Test: `tests/test_composite_generator.py`
- Create fixture: `tests/fixtures/fake_generator_pkg/`

- [ ] **Step 1: Write failing test**

Append to `tests/test_composite_generator.py`:

```python
import subprocess
import sys
from pathlib import Path


FIXTURE_PKG = Path(__file__).parent / "fixtures" / "fake_generator_pkg"


@pytest.fixture
def installed_fake_pkg(tmp_path):
    """pip install -e the fixture package into the current venv for the test."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-e", str(FIXTURE_PKG)],
        check=True,
    )
    yield
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "-q",
         "fake-generator-pkg"],
        check=True,
    )


def test_discover_generators_finds_decorated_function_in_installed_pkg(
        installed_fake_pkg):
    from pbg_superpowers.composite_generator import discover_generators
    # Discovery must import the package — it can't rely on the test having
    # already done so. Clear the registry first to simulate a fresh process.
    _REGISTRY.clear()
    found = discover_generators()
    expected_id = "fake_generator_pkg.composites.demo"
    assert expected_id in found
    entry = found[expected_id]
    assert entry.name == "demo"
    assert entry.parameters == {"x": {"type": "int", "default": 7}}
```

- [ ] **Step 2: Create fixture package**

Create `tests/fixtures/fake_generator_pkg/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fake-generator-pkg"
version = "0.0.1"
requires-python = ">=3.10"
dependencies = ["bigraph-schema"]

[tool.hatch.build.targets.wheel]
packages = ["fake_generator_pkg"]
```

Create `tests/fixtures/fake_generator_pkg/fake_generator_pkg/__init__.py`:

```python
from . import composites  # noqa: F401  -- import so decorators fire
```

Create `tests/fixtures/fake_generator_pkg/fake_generator_pkg/composites.py`:

```python
from pbg_superpowers.composite_generator import composite_generator


@composite_generator(
    name="demo",
    description="A fake generator used only by tests.",
    parameters={"x": {"type": "int", "default": 7}},
)
def demo(core=None, *, x=7):
    return {"x": x}
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_composite_generator.py::test_discover_generators_finds_decorated_function_in_installed_pkg -v
```
Expected: FAIL with `ImportError: cannot import name 'discover_generators'`.

- [ ] **Step 4: Implement discover_generators**

Append to `pbg_superpowers/composite_generator.py`:

```python
def discover_generators(
    extra_packages: list[str] | None = None,
) -> dict[str, GeneratorEntry]:
    """Discover composite generators from installed packages.

    Walks every installed distribution that depends on `bigraph-schema`,
    imports each top-level package so its `@composite_generator` decorators
    fire, then returns whatever ended up in `_REGISTRY`.

    Unlike `discover_composites` (file-glob, no import), this MUST import
    the host packages. Subsequent calls return the same registry; there is
    no automatic invalidation. Hot-reload callers can `_REGISTRY.clear()`
    before re-importing.
    """
    import importlib
    import importlib.metadata as md

    extra_packages = extra_packages or []
    targets: set[str] = set(extra_packages)

    for dist in md.distributions():
        deps = dist.requires or []
        if not any("bigraph-schema" in (d or "") for d in deps):
            continue
        # Find the importable top-level packages for this distribution.
        top_level_txt = dist.read_text("top_level.txt") or ""
        for line in top_level_txt.splitlines():
            mod = line.strip()
            if mod and not mod.startswith("_"):
                targets.add(mod)

    for mod_name in sorted(targets):
        try:
            importlib.import_module(mod_name)
        except ImportError:
            # Some packages have optional sub-deps; skip rather than crash
            # the whole discovery pass.
            continue

    return dict(_REGISTRY)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_composite_generator.py::test_discover_generators_finds_decorated_function_in_installed_pkg -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pbg_superpowers/composite_generator.py tests/test_composite_generator.py tests/fixtures/fake_generator_pkg/
git commit -m "feat(composite_generator): add discover_generators with installed-pkg walk"
```

---

### Task A4: discover_all — merge specs + generators with `kind` tag

**Files:**
- Modify: `pbg_superpowers/composite_discovery.py`
- Test: `tests/test_composite_generator.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_composite_generator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_composite_generator.py::test_discover_all_merges_specs_and_generators -v
```
Expected: FAIL with `ImportError: cannot import name 'discover_all'`.

- [ ] **Step 3: Read current composite_discovery.py to find a clean insertion point**

```bash
grep -n "^def " /Users/eranagmon/code/pbg-superpowers/pbg_superpowers/composite_discovery.py
```

Note the bottom of the file. The new function goes after `discover_composites`.

- [ ] **Step 4: Implement discover_all**

Append to `pbg_superpowers/composite_discovery.py`:

```python
def discover_all(
    extra_search_paths: list[Path] | None = None,
    extra_packages: list[str] | None = None,
) -> dict[str, dict]:
    """Return both static specs and composite generators, tagged with ``kind``.

    Spec entries get ``kind: spec`` and pass through the existing spec
    payload. Generator entries get ``kind: generator`` and a compact dict
    {name, description, parameters, module} so dashboards can render them
    without holding a reference to the live function object.

    Discovery imports the host packages of every generator (see
    :func:`pbg_superpowers.composite_generator.discover_generators`). If
    you need the no-import safety property, call ``discover_composites``
    directly.
    """
    from pbg_superpowers.composite_generator import discover_generators

    specs = discover_composites(extra_search_paths=extra_search_paths)
    out: dict[str, dict] = {
        sid: {"kind": "spec", **s} for sid, s in specs.items()
    }
    for gid, entry in discover_generators(
            extra_packages=extra_packages).items():
        out[gid] = {
            "kind": "generator",
            "name": entry.name,
            "description": entry.description,
            "parameters": entry.parameters,
            "module": entry.module,
        }
    return out
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_composite_generator.py::test_discover_all_merges_specs_and_generators -v
```
Expected: PASS.

- [ ] **Step 6: Run full test_composite_generator.py to make sure nothing broke**

```bash
pytest tests/test_composite_generator.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add pbg_superpowers/composite_discovery.py tests/test_composite_generator.py
git commit -m "feat(composite_discovery): add discover_all merging specs + generators"
```

---

### Task A5: Bump pbg-superpowers version to 0.4.16

**Files:**
- Modify: `pbg_superpowers/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

In `/Users/eranagmon/code/pbg-superpowers/pyproject.toml`, change:

```
version = "0.4.15"
```
to:
```
version = "0.4.16"
```

- [ ] **Step 2: Verify version assertion test still passes after bump**

The test in `tests/test_workspace_scaffold.py::test_scaffold_workspace_yaml_validates` hardcodes `"0.4.15"`. Update both `pbg-template/template-init.sh` (PLUGIN_VERSION) and the test assertion in the same commit, or relax the test. Use the same path established in commit `151620c`:

```bash
# In ~/code/pbg-template/template-init.sh, change:
#   PLUGIN_VERSION="0.4.15"
# to:
#   PLUGIN_VERSION="0.4.16"

# In ~/code/pbg-superpowers/tests/test_workspace_scaffold.py, change:
#   assert ws["plugin_version"] == "0.4.15"
# to:
#   assert ws["plugin_version"] == "0.4.16"
```

- [ ] **Step 3: Run the full pbg-superpowers test suite**

```bash
cd ~/code/pbg-superpowers && source .venv/bin/activate
pytest -q
```
Expected: all PASS (135 + ~7 new tests from A1-A4).

- [ ] **Step 4: Commit both repos**

```bash
cd ~/code/pbg-superpowers
git add pyproject.toml tests/test_workspace_scaffold.py
git commit -m "chore: bump to 0.4.16 (composite_generator convention)"

cd ~/code/pbg-template
git add template-init.sh
git commit -m "template: bump scaffolded plugin_version to 0.4.16"
```

---

## Phase B — spatio-flux scaffolding + pilot

### Task B1: Add pbg-superpowers dependency to spatio-flux

**Files:**
- Modify: `~/code/spatio-flux/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

In `/Users/eranagmon/code/spatio-flux/pyproject.toml`, add `pbg-superpowers>=0.4.16` to `dependencies`:

```toml
dependencies = [
    "bigraph-schema",
    "process-bigraph[ray,server-rest,ec2-ssm]",
    "bigraph-viz",
    "cobra",
    "highspy",
    "imageio",
    "ipython",
    "matplotlib",
    "pbg-superpowers>=0.4.16",
    "pymunk",
    "scipy",
]
```

- [ ] **Step 2: Install pbg-superpowers in editable mode (for local dev)**

Since 0.4.16 isn't on PyPI yet, link the local clone:

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
uv pip install -e ~/code/pbg-superpowers
```

- [ ] **Step 3: Sanity check the import works**

```bash
python -c "from pbg_superpowers.composite_generator import composite_generator, build_generator, discover_generators; print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add pbg-superpowers>=0.4.16 for composite_generator"
```

---

### Task B2: Scaffold `spatio_flux/composites/` package + shared constants

**Why a shared-constants module:** the generator modules need `SQUARE_BINS`,
`SQUARE_BOUNDS`, `DEFAULT_DIFFUSION`, `DEFAULT_ADVECTION`, `DEFAULT_BINS`,
`DEFAULT_BOUNDS`, `DEFAULT_BINS_SMALL`, `DEFAULT_INITIAL_MIN_MAX`, and the
helper `get_newtonian_particles_process`. All of these currently live in
`test_suite.py`. After migration, `test_suite.py` imports from
`spatio_flux.composites` (to look up generators), so `composites/*.py`
cannot import from `test_suite.py` without circular imports. Extract them
to `spatio_flux/composites/_constants.py` first.

**Files:**
- Create: `spatio_flux/composites/__init__.py`
- Create: `spatio_flux/composites/_constants.py`
- Create: `spatio_flux/composites/metabolism.py`
- Create: `spatio_flux/composites/spatial.py`
- Create: `spatio_flux/composites/particles.py`
- Create: `spatio_flux/composites/comets.py`
- Create: `spatio_flux/composites/reference.py`
- Modify: `spatio_flux/experiments/test_suite.py` (re-export from _constants for backward compat)

- [ ] **Step 1: Extract shared constants to `_constants.py`**

Create `spatio_flux/composites/_constants.py`:

```python
"""Shared constants and helpers used by composite generators.

These lived in test_suite.py before the migration. They're extracted here
so generator modules don't have to import from test_suite.py — which would
be a circular import, because test_suite.py imports from this package to
look up generators.

test_suite.py re-exports these names for backward compatibility with any
external caller that imported them from there.
"""
from __future__ import annotations

# Standard small lattice used by particle / kinetics composites
SQUARE_BOUNDS = (50.0, 50.0)
SQUARE_BINS = (10, 10)

# Standard non-square lattice used by diffusion composites
DEFAULT_BOUNDS = (40.0, 80.0)
DEFAULT_BINS = (10, 20)
DEFAULT_BINS_SMALL = (2, 4)

DEFAULT_ADVECTION = (0.0, 0.2)
DEFAULT_DIFFUSION = 0.5
DEFAULT_ADD_RATE = 0.1
DEFAULT_ADD_BOUNDARY = ['top', 'left', 'right']
DEFAULT_REMOVE_BOUNDARY = ['left', 'right']
DEFAULT_INITIAL_MIN_MAX = {
    'glucose': (10, 10),
    'acetate': (0, 0),
    'dissolved biomass': (0, 0.1),
}


def get_newtonian_particles_process(config=None):
    """Helper that wraps a Pymunk newtonian-particles process address."""
    return {
        '_type': 'process',
        'address': 'local:PymunkParticleMovement',
        'config': config,
        'inputs':  {'particles': ['particles']},
        'outputs': {'particles': ['particles']},
    }
```

In `spatio_flux/experiments/test_suite.py`, replace the inline definitions
with a re-export so external callers and the legacy doc_funcs still work
during the migration. Near the top of the file, after the existing imports
and BEFORE the `SQUARE_BOUNDS = ...` block, add:

```python
from spatio_flux.composites._constants import (  # noqa: F401
    SQUARE_BOUNDS, SQUARE_BINS,
    DEFAULT_BOUNDS, DEFAULT_BINS, DEFAULT_BINS_SMALL,
    DEFAULT_ADVECTION, DEFAULT_DIFFUSION,
    DEFAULT_ADD_RATE, DEFAULT_ADD_BOUNDARY, DEFAULT_REMOVE_BOUNDARY,
    DEFAULT_INITIAL_MIN_MAX,
    get_newtonian_particles_process,
)
```

Then DELETE the original definitions of those names from test_suite.py
(the `SQUARE_BOUNDS = ...` lines, the `DEFAULT_*` block, and the
`def get_newtonian_particles_process(...)` function).

- [ ] **Step 2: Create empty group modules**

Create each of `metabolism.py`, `spatial.py`, `particles.py`, `comets.py`, `reference.py` with just a module docstring:

```python
"""Composite generators — <group> group. See spec at
docs/superpowers/specs/2026-05-12-composite-generator-convention.md."""
```

- [ ] **Step 3: Create __init__.py that imports each submodule**

Create `spatio_flux/composites/__init__.py`:

```python
"""spatio-flux composite generators.

Importing this package triggers ``@composite_generator`` registration for
every composite in every submodule. The dashboard's ``discover_generators``
call relies on this.
"""
from pbg_superpowers.composite_generator import _REGISTRY as REGISTRY

# Trigger decorator side-effects in every submodule.
from . import metabolism  # noqa: F401
from . import spatial     # noqa: F401
from . import particles   # noqa: F401
from . import comets      # noqa: F401
from . import reference   # noqa: F401

__all__ = ["REGISTRY"]
```

- [ ] **Step 4: Verify the import doesn't crash AND test_suite.py still runs**

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
python -c "import spatio_flux.composites; print(list(spatio_flux.composites.REGISTRY))"
```
Expected: `[]` (registry empty, but no errors).

```bash
python spatio_flux/experiments/test_suite.py --tests monod_kinetics --output /tmp/check_b2
```
Expected: `✅ Completed: monod_kinetics` — confirms the re-exports work
and the legacy `doc_func` chain still runs.

- [ ] **Step 5: Commit**

```bash
git add spatio_flux/composites/ spatio_flux/experiments/test_suite.py
git commit -m "scaffold: spatio_flux/composites/ package + shared _constants extraction"
```

---

### Task B3: `_serialize.py` — normalize_doc for snapshot comparison

**Files:**
- Create: `spatio_flux/composites/_serialize.py`
- Test: `tests/test_composite_generators.py` (just the serializer for now)

- [ ] **Step 1: Write failing test**

Create `tests/test_composite_generators.py`:

```python
"""Snapshot regression tests for composite generators.

Each registered generator's default-built doc must match its baseline JSON
snapshot under spatio_flux/composites/_snapshots/.
"""
import math
import numpy as np
import pytest

from spatio_flux.composites._serialize import normalize_doc


def test_normalize_doc_passes_scalars_through():
    doc = {"a": 1, "b": "x", "c": True, "d": None, "e": 1.5}
    assert normalize_doc(doc) == doc


def test_normalize_doc_encodes_numpy_arrays():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    result = normalize_doc({"f": arr})
    assert result == {
        "f": {
            "__numpy__": True,
            "dtype": "float64",
            "shape": [2, 2],
            "values": [[1.0, 2.0], [3.0, 4.0]],
        }
    }


def test_normalize_doc_rounds_floats_to_12_sig_figs():
    # 1/3 has infinite digits; the encoder must round so cross-platform
    # roundtrips are stable.
    arr = np.array([1.0 / 3.0], dtype=np.float64)
    result = normalize_doc({"f": arr})
    rounded = result["f"]["values"][0]
    # 12 sig figs of 0.333... — last digit may differ across machines if
    # we didn't round, but with rounding it's deterministic.
    assert rounded == float(f"{1.0/3.0:.12g}")


def test_normalize_doc_recurses_into_lists():
    arr = np.array([7], dtype=np.int64)
    result = normalize_doc({"xs": [1, "two", arr]})
    assert result["xs"][0] == 1
    assert result["xs"][1] == "two"
    assert result["xs"][2]["__numpy__"] is True


def test_normalize_doc_repr_falls_back_for_unencodable_objects():
    class Weird:
        def __repr__(self):
            return "Weird()"

    result = normalize_doc({"thing": Weird()})
    assert result == {
        "thing": {"__repr__": "Weird", "value": "Weird()"},
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_composite_generators.py -v
```
Expected: collection error (`No module named 'spatio_flux.composites._serialize'`).

- [ ] **Step 3: Implement _serialize.py**

Create `spatio_flux/composites/_serialize.py`:

```python
"""Normalize a process-bigraph doc into a deterministic JSON-encodable
shape so snapshot tests can compare structurally.

Decisions:
- numpy arrays serialize as ``{"__numpy__": true, "dtype", "shape", "values"}``
  with float values rounded to 12 significant figures. Round-trip stability
  across platforms is more important than full float64 precision; the
  snapshots are for *structural* regression, not numerical analysis.
- Unencodable custom objects fall back to a ``__repr__`` envelope so the
  snapshot still reflects their presence and class.
- Dicts, lists, tuples, and JSON scalars recurse / pass through.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

_FLOAT_SIG_FIGS = 12


def _round_float(x: float) -> float:
    """Round to 12 significant figures via decimal string formatting."""
    if not isinstance(x, float):
        x = float(x)
    if x == 0.0 or not (x == x and x not in (float("inf"), float("-inf"))):
        return x
    return float(f"{x:.{_FLOAT_SIG_FIGS}g}")


def normalize_doc(node: Any) -> Any:
    """Recursively normalize ``node`` into a JSON-comparable structure."""
    if isinstance(node, dict):
        return {k: normalize_doc(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [normalize_doc(v) for v in node]
    if isinstance(node, np.ndarray):
        return {
            "__numpy__": True,
            "dtype": str(node.dtype),
            "shape": list(node.shape),
            "values": _array_to_lists(node),
        }
    if isinstance(node, (np.integer,)):
        return int(node)
    if isinstance(node, (np.floating,)):
        return _round_float(float(node))
    if isinstance(node, float):
        return _round_float(node)
    # Pass through everything else that's JSON-encodable as-is.
    try:
        json.dumps(node)
        return node
    except TypeError:
        return {"__repr__": type(node).__name__, "value": repr(node)}


def _array_to_lists(arr: np.ndarray) -> list:
    """Convert an ndarray to nested lists, rounding floats."""
    if arr.dtype.kind == "f":
        return [_round_float(x) for x in arr.flatten().tolist()] if arr.ndim == 1 \
            else [_array_to_lists(sub) for sub in arr]
    return arr.tolist()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_composite_generators.py -v
```
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add spatio_flux/composites/_serialize.py tests/test_composite_generators.py
git commit -m "feat(composites): normalize_doc serializer for snapshot tests"
```

---

### Task B4: Capture-baseline CLI

**Files:**
- Create: `tools/capture_baseline_doc.py`
- Create directory: `spatio_flux/composites/_snapshots/`

- [ ] **Step 1: Create the snapshots dir with a .gitkeep**

```bash
mkdir -p ~/code/spatio-flux/spatio_flux/composites/_snapshots
touch ~/code/spatio-flux/spatio_flux/composites/_snapshots/.gitkeep
```

- [ ] **Step 2: Implement the CLI**

Create `tools/capture_baseline_doc.py`:

```python
#!/usr/bin/env python3
"""Capture a baseline composite-generator doc snapshot.

Usage::

    python tools/capture_baseline_doc.py <name>          # one-shot capture
    python tools/capture_baseline_doc.py <name> --update # regenerate from new generator

Capture mode (default) calls the OLD ``doc_func`` (from test_suite.py's
SIMULATIONS dict) with its currently-declared config and writes a
normalized JSON snapshot under
``spatio_flux/composites/_snapshots/<name>.json``.

After a composite has been ported and its old ``doc_func`` deleted, use
``--update`` to regenerate the snapshot from the NEW generator with default
parameters. This is the intentional "I changed the generator, accept the
new shape" knob.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from process_bigraph import allocate_core

from spatio_flux.composites._serialize import normalize_doc

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO_ROOT / "spatio_flux" / "composites" / "_snapshots"


def _capture_from_old(name: str) -> dict:
    """Call the legacy doc_func in SIMULATIONS with its declared config."""
    from spatio_flux.experiments.test_suite import SIMULATIONS  # local import
    sim = SIMULATIONS[name]
    core = allocate_core()
    doc = sim["doc_func"](core=core, config=sim.get("config", {}))
    return doc


def _capture_from_new(name: str) -> dict:
    """Call the registered composite_generator with default parameters."""
    from spatio_flux.composites import REGISTRY
    from pbg_superpowers.composite_generator import build_generator
    # Find the entry whose name matches.
    matches = [e for e in REGISTRY.values() if e.name == name]
    if not matches:
        raise SystemExit(
            f"no registered composite_generator named '{name}'. "
            f"Known: {sorted(e.name for e in REGISTRY.values())}"
        )
    if len(matches) > 1:
        raise SystemExit(
            f"multiple registered generators named '{name}': {matches!r}"
        )
    core = allocate_core()
    return build_generator(matches[0], core=core)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("name", help="composite name (e.g. ecoli_core_dfba)")
    p.add_argument(
        "--update", action="store_true",
        help="regenerate the snapshot from the NEW generator (after the "
             "old doc_func has been deleted)",
    )
    args = p.parse_args()

    if args.update:
        doc = _capture_from_new(args.name)
    else:
        doc = _capture_from_old(args.name)

    normalized = normalize_doc(doc)
    out_path = SNAPSHOT_DIR / f"{args.name}.json"
    out_path.write_text(json.dumps(normalized, indent=2, sort_keys=True))
    print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Smoke-test the CLI (still calls the OLD doc_func at this point)**

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
python tools/capture_baseline_doc.py ecoli_core_dfba
```
Expected: `wrote spatio_flux/composites/_snapshots/ecoli_core_dfba.json`. The file exists and is valid JSON.

- [ ] **Step 4: Verify it's valid JSON**

```bash
python -c "import json; json.load(open('spatio_flux/composites/_snapshots/ecoli_core_dfba.json'))" && echo OK
```
Expected: `OK`.

- [ ] **Step 5: Commit (do NOT commit the captured snapshot yet — that lands with B6 alongside the generator)**

```bash
rm spatio_flux/composites/_snapshots/ecoli_core_dfba.json
git add tools/capture_baseline_doc.py spatio_flux/composites/_snapshots/.gitkeep
git commit -m "tools: capture_baseline_doc.py CLI for generator snapshots"
```

---

### Task B5: Snapshot test harness

**Files:**
- Modify: `tests/test_composite_generators.py`

- [ ] **Step 1: Append parametrized snapshot test**

Append to `tests/test_composite_generators.py`:

```python
import json
from pathlib import Path

from process_bigraph import allocate_core

import spatio_flux.composites  # noqa: F401 -- ensures registry is populated
from spatio_flux.composites import REGISTRY
from pbg_superpowers.composite_generator import build_generator


SNAPSHOT_DIR = (
    Path(__file__).resolve().parent.parent
    / "spatio_flux" / "composites" / "_snapshots"
)


def _names() -> list[str]:
    return sorted(e.name for e in REGISTRY.values())


@pytest.mark.parametrize("name", _names() or ["__noop__"])
def test_generator_matches_snapshot(name):
    if name == "__noop__":
        pytest.skip("no composite generators registered yet")
    snapshot_path = SNAPSHOT_DIR / f"{name}.json"
    if not snapshot_path.exists():
        pytest.skip(f"no baseline snapshot for '{name}'")
    baseline = json.loads(snapshot_path.read_text())
    [entry] = [e for e in REGISTRY.values() if e.name == name]
    core = allocate_core()
    doc = build_generator(entry, core=core)
    assert normalize_doc(doc) == baseline
```

- [ ] **Step 2: Run the harness — should skip everything (no generators yet)**

```bash
pytest tests/test_composite_generators.py::test_generator_matches_snapshot -v
```
Expected: one skipped test (`__noop__`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_composite_generators.py
git commit -m "test: parametrized snapshot harness for composite generators"
```

---

### Task B6: Pilot migration — `ecoli_core_dfba`

This task establishes the per-composite migration workflow. Tasks C1-C5 follow this same pattern with each composite's specific code.

**Files:**
- Modify: `spatio_flux/composites/metabolism.py`
- Create: `spatio_flux/composites/_snapshots/ecoli_core_dfba.json`
- Modify: `spatio_flux/experiments/test_suite.py`

- [ ] **Step 1: Add the generator function**

In `spatio_flux/composites/metabolism.py`, after the docstring:

```python
from pbg_superpowers.composite_generator import composite_generator

from spatio_flux.processes import get_dfba_process_from_registry


@composite_generator(
    name="ecoli_core_dfba",
    description=(
        "Single-cell metabolism baseline: dynamic FBA for E. coli core with "
        "external glucose/acetate and biomass over time (no space, no particles)."
    ),
    parameters={
        "model_id":       {"type": "string", "default": "ecoli core"},
        "glucose":        {"type": "float",  "default": 10.0},
        "acetate":        {"type": "float",  "default": 0.0},
        "biomass":        {"type": "float",  "default": 0.1},
    },
)
def ecoli_core_dfba(core=None, *, model_id="ecoli core",
                    glucose=10.0, acetate=0.0, biomass=0.1):
    """Port of test_suite.get_dfba_single_doc for model_id='ecoli core'.

    The original function defaulted unspecified substrates to 10.0 by
    walking the dFBA process's substrate list. We preserve that behavior:
    callers can override glucose/acetate explicitly; any other substrate
    the model declares is filled in with 10.0.
    """
    dfba_process = get_dfba_process_from_registry(
        model_id=model_id, biomass_id="biomass", path=["fields"])
    initial_fields = {"glucose": glucose, "acetate": acetate, "biomass": biomass}
    for substrate in dfba_process["inputs"]["substrates"]:
        initial_fields.setdefault(substrate, 10.0)
    return {f"{model_id} dFBA": dfba_process, "fields": initial_fields}
```

- [ ] **Step 2: Capture the baseline from the OLD doc_func**

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
python tools/capture_baseline_doc.py ecoli_core_dfba
```
Expected: `wrote spatio_flux/composites/_snapshots/ecoli_core_dfba.json`.

- [ ] **Step 3: Run the snapshot test — MUST pass**

```bash
pytest tests/test_composite_generators.py::test_generator_matches_snapshot -v -k ecoli_core_dfba
```
Expected: PASS.

If it fails, the generator's default kwargs don't reproduce the old doc. Adjust the generator (not the snapshot) and re-run. The diff between expected and actual in the pytest output tells you what to fix.

- [ ] **Step 4: Switch test_suite.py SIMULATIONS to use the new generator**

In `spatio_flux/experiments/test_suite.py`:

Add imports near the top (after existing process imports):

```python
from spatio_flux.composites import REGISTRY as COMPOSITE_REGISTRY
from pbg_superpowers.composite_generator import build_generator
```

Change the `ecoli_core_dfba` entry in `SIMULATIONS`:

```python
'ecoli_core_dfba': {
    'generator':   'ecoli_core_dfba',
    'plot_func':   plot_dfba_single,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {'model_id': 'ecoli core',
                    'glucose': 10.0, 'acetate': 0.0},
    'plot_config': {'filename': 'ecoli_core_dfba'},
},
```

In the `main()` function, change the doc-building line. Current line ~1232:
```python
doc = sim_info['doc_func'](core=core, config=config)
```
becomes:
```python
if 'generator' in sim_info:
    entry = next(e for e in COMPOSITE_REGISTRY.values()
                 if e.name == sim_info['generator'])
    doc = build_generator(entry, overrides=sim_info.get('overrides', {}), core=core)
else:
    config = sim_info.get('config', {})
    doc = sim_info['doc_func'](core=core, config=config)
```

This branch lets old (`doc_func`) and new (`generator`) entries coexist for the rest of the migration.

- [ ] **Step 5: Re-run the test_suite to confirm runtime behavior unchanged**

```bash
python spatio_flux/experiments/test_suite.py --tests ecoli_core_dfba --output /tmp/check_b6
```
Expected: "✅ Completed: ecoli_core_dfba" with the same elapsed/output structure as before.

- [ ] **Step 6: Delete the old doc_func for this composite from test_suite.py**

Remove the `get_dfba_single_doc` function only if no other SIMULATIONS entry still references it. Since `ecoli_dfba` and `yeast_dfba` ALSO use `get_dfba_single_doc`, leave it in place for now — it will be deleted in the C-tasks when those two also land.

- [ ] **Step 7: Commit**

```bash
git add spatio_flux/composites/metabolism.py \
        spatio_flux/composites/_snapshots/ecoli_core_dfba.json \
        spatio_flux/experiments/test_suite.py
git commit -m "feat(composites): migrate ecoli_core_dfba to @composite_generator

First composite ported under the new convention. test_suite.py now branches
on 'generator' vs 'doc_func' so the remaining 18 can coexist during
migration. Snapshot test gates the port."
```

---

## Phase C — Migrate remaining 18 composites

For each composite in this phase, follow the same 7-step workflow as B6:
1. Add `@composite_generator` function to the relevant module
2. `python tools/capture_baseline_doc.py <name>`
3. `pytest -k <name>` — must pass
4. Update `SIMULATIONS[<name>]` to use `generator`/`overrides`
5. Run `python spatio_flux/experiments/test_suite.py --tests <name>` — should succeed
6. Delete the old `get_*_doc` if no other entry references it
7. Commit

Each sub-task below specifies just the new generator code (steps 1, 4) and which old doc_func to delete (step 6). Steps 2/3/5/7 are mechanical and identical across composites.

### Task C1: metabolism.py — port 5 remaining

**File:** `spatio_flux/composites/metabolism.py`

- [ ] **Step 1: Add `monod_kinetics` generator**

```python
from spatio_flux.processes import get_monod_kinetics_process_from_config
from spatio_flux.processes.monod_kinetics import MODEL_REGISTRY_KINETICS


@composite_generator(
    name="monod_kinetics",
    description=(
        "Field-only baseline: Monod uptake/growth on a well-mixed substrate "
        "pool (no spatial lattice, no particles). Use to sanity-check "
        "kinetics + mass balance."
    ),
    parameters={
        "model_id": {"type": "string", "default": "overflow_metabolism"},
        "interval": {"type": "float",  "default": 0.1},
        "glucose":  {"type": "float",  "default": 10.0},
        "acetate":  {"type": "float",  "default": 0.0},
        "biomass":  {"type": "float",  "default": 0.1},
    },
)
def monod_kinetics(core=None, *, model_id="overflow_metabolism",
                   interval=0.1, glucose=10.0, acetate=0.0, biomass=0.1):
    model_config = MODEL_REGISTRY_KINETICS[model_id]()
    return {
        "monod_kinetics": get_monod_kinetics_process_from_config(
            model_config=model_config, interval=interval),
        "fields": {"glucose": glucose, "acetate": acetate, "biomass": biomass},
    }
```

Update SIMULATIONS entry:
```python
'monod_kinetics': {
    'generator':   'monod_kinetics',
    'plot_func':   plot_kinetics_single,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {'model_id': 'overflow_metabolism'},
    'plot_config': {'filename': 'monod_kinetics'},
},
```

Run capture + test + test_suite. Commit:
```bash
git commit -m "feat(composites): migrate monod_kinetics"
```

- [ ] **Step 2: Add `ecoli_dfba` generator**

```python
@composite_generator(
    name="ecoli_dfba",
    description=(
        "Single-cell metabolism (large model): dynamic FBA using iAF1260 "
        "with tracked extracellular fields (glucose/formate) and biomass. "
        "Stress-tests solver + exchange wiring."
    ),
    parameters={
        "model_id": {"type": "string", "default": "ecoli"},
        "glucose":  {"type": "float",  "default": 10.0},
        "formate":  {"type": "float",  "default": 5.0},
        "biomass":  {"type": "float",  "default": 0.1},
    },
)
def ecoli_dfba(core=None, *, model_id="ecoli",
               glucose=10.0, formate=5.0, biomass=0.1):
    dfba_process = get_dfba_process_from_registry(
        model_id=model_id, biomass_id="biomass", path=["fields"])
    initial_fields = {"glucose": glucose, "formate": formate, "biomass": biomass}
    for substrate in dfba_process["inputs"]["substrates"]:
        initial_fields.setdefault(substrate, 10.0)
    return {f"{model_id} dFBA": dfba_process, "fields": initial_fields}
```

SIMULATIONS entry:
```python
'ecoli_dfba': {
    'generator':   'ecoli_dfba',
    'plot_func':   plot_dfba_single,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {'model_id': 'ecoli', 'glucose': 10.0, 'formate': 5.0},
    'plot_config': {'filename': 'ecoli_dfba'},
},
```

Capture/test/commit:
```bash
git commit -m "feat(composites): migrate ecoli_dfba"
```

- [ ] **Step 3: Add `yeast_dfba` generator**

```python
@composite_generator(
    name="yeast_dfba",
    description=(
        "Single-cell metabolism (yeast): dynamic FBA using iMM904 with "
        "extracellular glucose and biomass. Cross-model check of the dFBA "
        "pipeline."
    ),
    parameters={
        "model_id": {"type": "string", "default": "yeast"},
        "glucose":  {"type": "float",  "default": 5.0},
        "biomass":  {"type": "float",  "default": 0.1},
    },
)
def yeast_dfba(core=None, *, model_id="yeast", glucose=5.0, biomass=0.1):
    dfba_process = get_dfba_process_from_registry(
        model_id=model_id, biomass_id="biomass", path=["fields"])
    initial_fields = {"glucose": glucose, "biomass": biomass}
    for substrate in dfba_process["inputs"]["substrates"]:
        initial_fields.setdefault(substrate, 10.0)
    return {f"{model_id} dFBA": dfba_process, "fields": initial_fields}
```

SIMULATIONS:
```python
'yeast_dfba': {
    'generator':   'yeast_dfba',
    'plot_func':   plot_dfba_single,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {'model_id': 'yeast', 'glucose': 5.0},
    'plot_config': {'filename': 'yeast_dfba'},
},
```

Capture/test/commit (include the deletion of the corresponding old
`get_*_doc` from `test_suite.py` in this commit). After this composite lands, `get_dfba_single_doc` has no remaining callers — **delete it** from test_suite.py in the same commit:
```bash
git commit -m "feat(composites): migrate yeast_dfba; drop get_dfba_single_doc"
```

- [ ] **Step 4: Add `community_dfba` generator**

This one builds dFBA processes for every model in `MODEL_REGISTRY_DFBA` plus a Monod kinetic process. No external parameters needed today.

```python
from spatio_flux.processes import MODEL_REGISTRY_DFBA, get_field_names


@composite_generator(
    name="community_dfba",
    description=(
        "Multi-agent well-mixed community: several independent dFBA "
        "instances share the same extracellular pools, creating competition / "
        "cross-feeding dynamics without space."
    ),
    parameters={
        "dt":                {"type": "float",  "default": 1.0},
        "kinetic_model_id":  {"type": "string", "default": "acetate_only"},
        "initial_biomass":   {"type": "float",  "default": 0.1},
        "glucose":           {"type": "float",  "default": 10.0},
        "acetate":           {"type": "float",  "default": 0.0},
    },
)
def community_dfba(core=None, *, dt=1.0, kinetic_model_id="acetate_only",
                   initial_biomass=0.1, glucose=10.0, acetate=0.0):
    model_ids = list(MODEL_REGISTRY_DFBA.keys())
    dfbas = {
        f"{model_id} dFBA": get_dfba_process_from_registry(
            model_id=model_id, biomass_id=model_id, path=["fields"],
            interval=dt)
        for model_id in MODEL_REGISTRY_DFBA
    }
    biomasses = {organism: initial_biomass for organism in model_ids}
    kinetic_biomass_id = "monod biomass"
    biomasses[kinetic_biomass_id] = initial_biomass
    kinetic_model_config = MODEL_REGISTRY_KINETICS[kinetic_model_id]()
    field_names = get_field_names(MODEL_REGISTRY_DFBA)
    more_fields = {m: 0.1 for m in field_names if m not in ("glucose", "acetate")}
    return {
        **dfbas,
        "monod_kinetics": get_monod_kinetics_process_from_config(
            model_config=kinetic_model_config,
            biomass_id=kinetic_biomass_id, interval=dt),
        "fields": {"glucose": glucose, "acetate": acetate,
                   **more_fields, **biomasses},
    }
```

SIMULATIONS:
```python
'community_dfba': {
    'generator':   'community_dfba',
    'plot_func':   plot_community_dfba,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {},
    'plot_config': {'filename': 'community_dfba'},
},
```

Capture/test/commit + delete `get_community_dfba_doc`:
```bash
git commit -m "feat(composites): migrate community_dfba; drop get_community_dfba_doc"
```

- [ ] **Step 5: Add `dfba_kinetics_community` generator**

```python
@composite_generator(
    name="dfba_kinetics_community",
    description=(
        "Hybrid community (well-mixed): mixes Monod-kinetic agents with "
        "dFBA agents in a shared environment. Demonstrates heterogeneous "
        "process composition under one schema."
    ),
    parameters={
        "dfba_model_id":      {"type": "string", "default": "ecoli core"},
        "kinetic_model_id":   {"type": "string", "default": "acetate_only"},
        "dfba_biomass_id":    {"type": "string", "default": "dfba biomass"},
        "kinetic_biomass_id": {"type": "string", "default": "kinetic biomass"},
        "glucose":            {"type": "float",  "default": 10.0},
        "acetate":            {"type": "float",  "default": 0.0},
        "initial_biomass":    {"type": "float",  "default": 0.01},
    },
)
def dfba_kinetics_community(core=None, *,
                            dfba_model_id="ecoli core",
                            kinetic_model_id="acetate_only",
                            dfba_biomass_id="dfba biomass",
                            kinetic_biomass_id="kinetic biomass",
                            glucose=10.0, acetate=0.0, initial_biomass=0.01):
    kinetic_config = MODEL_REGISTRY_KINETICS[kinetic_model_id]()
    return {
        "dFBA": get_dfba_process_from_registry(
            model_id=dfba_model_id, biomass_id=dfba_biomass_id,
            path=["fields"]),
        "monod_kinetics": get_monod_kinetics_process_from_config(
            model_config=kinetic_config, biomass_id=kinetic_biomass_id),
        "fields": {
            "glucose": glucose,
            "acetate": acetate,
            dfba_biomass_id: initial_biomass,
            kinetic_biomass_id: initial_biomass,
        },
    }
```

SIMULATIONS:
```python
'dfba_kinetics_community': {
    'generator':   'dfba_kinetics_community',
    'plot_func':   plot_dfba_kinetics_community,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {},
    'plot_config': {'filename': 'dfba_kinetics_community'},
},
```

Capture/test/commit + delete `get_dfba_kinetics_community_doc`:
```bash
git commit -m "feat(composites): migrate dfba_kinetics_community; drop legacy doc_func"
```

---

### Task C2: spatial.py — port 3 generators

**File:** `spatio_flux/composites/spatial.py`

Add at top:
```python
import numpy as np
from pbg_superpowers.composite_generator import composite_generator

from spatio_flux.processes import (
    MODEL_REGISTRY_DFBA, get_fields, get_fields_with_schema,
    get_spatial_many_dfba, get_spatial_dFBA_process,
    get_diffusion_advection_process,
)
from spatio_flux.composites._constants import (
    DEFAULT_BINS, DEFAULT_BOUNDS, DEFAULT_BINS_SMALL,
    DEFAULT_ADVECTION, DEFAULT_DIFFUSION,
)
```

`build_model_grid` is defined inside `test_suite.py` and is small. Copy it
into `spatio_flux/composites/_constants.py` as part of the C2 work (the
same Step 1 commit) so spatial.py can import it from there without
circularity. Delete the test_suite.py copy in the same commit.

- [ ] **Step 1: Add `spatial_many_dfba` generator**

```python
@composite_generator(
    name="spatial_many_dfba",
    description=(
        "Spatial microenvironment (sitewise dFBA): a lattice where each site "
        "runs its own dFBA instance. Useful for validating lattice indexing "
        "+ per-site state isolation."
    ),
    parameters={
        "model_id": {"type": "string", "default": "ecoli core"},
        "n_bins":   {"type": "object", "default": list(DEFAULT_BINS_SMALL)},
    },
)
def spatial_many_dfba(core=None, *, model_id="ecoli core",
                      n_bins=list(DEFAULT_BINS_SMALL)):
    n_bins_t = tuple(n_bins)
    mol_ids = ["glucose", "acetate", "dissolved biomass"]
    initial_min_max = {"glucose": (0, 20), "acetate": (0, 0),
                       "dissolved biomass": (0, 0.1)}
    return {
        "fields": get_fields_with_schema(
            n_bins=n_bins_t, mol_ids=mol_ids, initial_min_max=initial_min_max),
        "spatial_dFBA": get_spatial_many_dfba(
            model_id=model_id, mol_ids=mol_ids, n_bins=n_bins_t),
    }
```

⚠ NOTE on numpy random state: `get_fields` uses `np.random.uniform` (global
RNG). The OLD `doc_func` did too, with no seeding. The snapshot will only
match if numpy's PRNG state is the same at capture time AND at test time.

**Action required before this task:** add `np.random.seed(0)` to BOTH
`_capture_from_old` AND `_capture_from_new` in `tools/capture_baseline_doc.py`
(top of each function), and add a `np.random.seed(0)` fixture in
`tests/test_composite_generators.py`:

```python
@pytest.fixture(autouse=True)
def _seed_numpy():
    """Snapshots were captured with seed 0; pin the global RNG for tests."""
    np.random.seed(0)
```

Commit those fixture/seed changes BEFORE running `capture_baseline_doc.py`
for any RNG-touching generator. Then capture/test/commit as usual.

Update SIMULATIONS, run capture/test/commit. Delete `get_spatial_many_dfba_doc`:
```python
'spatial_many_dfba': {
    'generator':   'spatial_many_dfba',
    'plot_func':   plot_spatial_many_dfba,
    'time':        DEFAULT_RUNTIME_LONG,
    'overrides':   {'model_id': 'ecoli core'},
    'plot_config': {'filename': 'spatial_many_dfba'},
},
```
```bash
git commit -m "feat(composites): migrate spatial_many_dfba; drop legacy doc_func"
```

- [ ] **Step 2: Add `spatial_dfba_process` generator**

```python
@composite_generator(
    name="spatial_dfba_process",
    description=(
        "Spatial microenvironment (vectorized dFBA): one spatial dFBA "
        "process updates all lattice sites as a single structured state. "
        "Demonstrates batched execution + field coupling."
    ),
    parameters={
        "n_bins": {"type": "object", "default": [5, 6]},
    },
)
def spatial_dfba_process(core=None, *, n_bins=[5, 6]):
    n_bins_t = tuple(n_bins)
    mol_ids = ["glucose", "acetate", "glycolate", "ammonium", "formate",
               "glutamate", "serine", "dissolved biomass"]
    initial_min_max = {
        "glucose": (10, 10), "glycolate": (10, 10), "ammonium": (10, 10),
        "formate": (10, 10), "glutamate": (10, 10), "serine": (0, 0),
        "acetate": (0, 0), "dissolved biomass": (0.1, 0.1),
    }
    fields = get_fields(n_bins_t, mol_ids, initial_min_max, {})
    bins_x, bins_y = n_bins_t
    horizontal_gradient = np.linspace(0, 20, bins_x).reshape(1, -1)
    fields["glucose"] = np.repeat(horizontal_gradient, bins_y, axis=0)
    model_positions = {
        "ecoli core": [(x, 0) for x in range(bins_x)],
        "ecoli":      [(x, 1) for x in range(bins_x)],
        "cdiff":      [(x, 2) for x in range(bins_x)],
        "pputida":    [(x, 3) for x in range(bins_x)],
        "yeast":      [(x, 4) for x in range(bins_x)],
        "llactis":    [(x, 5) for x in range(bins_x)],
    }
    model_grid = build_model_grid(n_bins=n_bins_t,
                                  model_positions=model_positions)
    return {
        "fields": fields,
        "spatial_dFBA": get_spatial_dFBA_process(config={
            "n_bins": n_bins_t,
            "models": MODEL_REGISTRY_DFBA,
            "model_grid": model_grid,
            "mol_ids": mol_ids,
        }),
    }
```

SIMULATIONS update + capture/test/commit. Delete `get_spatial_dfba_process_doc`
AND the orphan `build_model_grid` from test_suite.py (it was moved to
`_constants.py` in this task's preamble):
```bash
git commit -m "feat(composites): migrate spatial_dfba_process; drop legacy doc_func"
```

- [ ] **Step 3: Add `diffusion_process` generator**

Uses the global `np.random.uniform` — same as the old `doc_func`. Snapshot
matching relies on the seed-0 fixture from Step 2 of this task; if you
haven't already added that to `tools/capture_baseline_doc.py` and the
test fixture, do it now.

```python
@composite_generator(
    name="diffusion_process",
    description=(
        "Field transport primitive: finite-volume diffusion/advection on a "
        "2D lattice. Use to validate boundary conditions, stability, and "
        "transport timescales."
    ),
    parameters={
        "n_bins": {"type": "object", "default": list(DEFAULT_BINS)},
        "bounds": {"type": "object", "default": list(DEFAULT_BOUNDS)},
    },
)
def diffusion_process(core=None, *, n_bins=list(DEFAULT_BINS),
                      bounds=list(DEFAULT_BOUNDS)):
    n_bins_t, bounds_t = tuple(n_bins), tuple(bounds)
    mol_ids = ["glucose", "dissolved biomass"]
    advection_coeffs = {"dissolved biomass": DEFAULT_ADVECTION}
    diffusion_coeffs = {
        "glucose": DEFAULT_DIFFUSION / 10,
        "dissolved biomass": DEFAULT_DIFFUSION / 10,
    }
    glc_field = np.random.uniform(
        low=0.1, high=2, size=(n_bins_t[1], n_bins_t[0]))
    biomass_field = np.zeros((n_bins_t[1], n_bins_t[0]))
    biomass_field[4:5, :] = 10
    return {
        "fields": {"dissolved biomass": biomass_field,
                   "glucose": glc_field},
        "diffusion": get_diffusion_advection_process(
            bounds=bounds_t, n_bins=n_bins_t, mol_ids=mol_ids,
            diffusion_coeffs=diffusion_coeffs,
            advection_coeffs=advection_coeffs),
    }
```

SIMULATIONS update + capture/test/commit. Delete `get_diffusion_process_doc`:
```bash
git commit -m "feat(composites): migrate diffusion_process; drop legacy doc_func"
```

---

### Task C3: particles.py — port 4 generators

**File:** `spatio_flux/composites/particles.py`

Imports:
```python
import numpy as np
from pbg_superpowers.composite_generator import composite_generator

from spatio_flux.processes import (
    get_fields, get_particles_state, get_newtonian_particles_state,
    get_brownian_movement_process, get_boundaries_process,
    get_particle_exchange_process, get_particle_divide_process,
    get_kinetic_particle_composition, get_dfba_particle_composition,
    DIVISION_MASS_THRESHOLD, MODEL_REGISTRY_KINETICS,
)
from spatio_flux.composites._constants import (
    SQUARE_BINS, SQUARE_BOUNDS, DEFAULT_DIFFUSION, DEFAULT_ADVECTION,
    get_newtonian_particles_process,
)
```

- [ ] **Step 1: Add `brownian_particles` generator**

```python
@composite_generator(
    name="brownian_particles",
    description=(
        "Particle-only baseline: Brownian motion of agents with mass in "
        "continuous space (no fields, no metabolism). Checks integrator + "
        "particle state schema."
    ),
    parameters={
        "n_bins":         {"type": "object", "default": list(SQUARE_BINS)},
        "bounds":         {"type": "object", "default": list(SQUARE_BOUNDS)},
        "n_particles":    {"type": "int",    "default": 1},
        "time_interval":  {"type": "float",  "default": 0.1},
        "diffusion_rate": {"type": "float",  "default": DEFAULT_DIFFUSION},
        "add_rate":       {"type": "float",  "default": 0.01},
    },
)
def brownian_particles(core=None, *, n_bins=list(SQUARE_BINS),
                       bounds=list(SQUARE_BOUNDS), n_particles=1,
                       time_interval=0.1, diffusion_rate=DEFAULT_DIFFUSION,
                       add_rate=0.01):
    bounds_t = tuple(bounds)
    return {
        "state": {
            "particles": get_particles_state(
                n_particles=n_particles, bounds=bounds_t),
            "brownian_movement": get_brownian_movement_process(
                bounds=bounds_t, diffusion_rate=diffusion_rate,
                interval=time_interval),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="brownian_movement",
                bounds=bounds_t, add_rate=add_rate),
        },
    }
```

Capture/test/commit (include the deletion of the corresponding old
`get_*_doc` from `test_suite.py` in this commit). Delete `get_brownian_particles_alone_doc`:
```bash
git commit -m "feat(composites): migrate brownian_particles; drop legacy doc_func"
```

- [ ] **Step 2: Add `br_particles_kinetics` generator**

```python
@composite_generator(
    name="br_particles_kinetics",
    description=(
        "Particle–field coupling (kinetics): Brownian agents sample local "
        "lattice concentrations and apply Monod-style exchange, modifying "
        "both particle mass and fields."
    ),
    parameters={
        "model_id":                 {"type": "string", "default": "overflow_metabolism"},
        "division_mass_threshold":  {"type": "float",  "default": DIVISION_MASS_THRESHOLD},
    },
)
def br_particles_kinetics(core=None, *, model_id="overflow_metabolism",
                          division_mass_threshold=DIVISION_MASS_THRESHOLD):
    initial_min_max = {"glucose": (5.0, 10.0), "acetate": (0, 0)}
    particle_config = MODEL_REGISTRY_KINETICS[model_id]()
    mol_ids = list(initial_min_max.keys())
    n_bins, bounds = SQUARE_BINS, SQUARE_BOUNDS
    return {
        "state": {
            "fields": get_fields(
                n_bins=n_bins, mol_ids=mol_ids,
                initial_min_max=initial_min_max),
            "particles": get_particles_state(n_particles=1, bounds=bounds),
            "brownian_movement": get_brownian_movement_process(
                bounds=bounds, diffusion_rate=DEFAULT_DIFFUSION / 2,
                advection_rate=(0, 0)),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="brownian_movement",
                bounds=bounds, add_rate=0.0),
            "particle_exchange": get_particle_exchange_process(
                n_bins=n_bins, bounds=bounds),
            "particle_division": get_particle_divide_process(
                division_mass_threshold=division_mass_threshold),
        },
        "schema": get_kinetic_particle_composition(core=core,
                                                   config=particle_config),
    }
```

Capture/test/commit (include the deletion of the corresponding old
`get_*_doc` from `test_suite.py` in this commit).

- [ ] **Step 3: Add `br_particles_dfba` generator**

```python
@composite_generator(
    name="br_particles_dfba",
    description=(
        "Particle-embedded metabolism: Brownian agents carry internal dFBA; "
        "uptake/secretion couples to fields and biomass accumulates into "
        "particle mass/size."
    ),
    parameters={
        "particle_model_id":        {"type": "string", "default": "ecoli core"},
        "division_mass_threshold":  {"type": "float",  "default": DIVISION_MASS_THRESHOLD},
        "add_rate":                 {"type": "float",  "default": 0.1},
    },
)
def br_particles_dfba(core=None, *, particle_model_id="ecoli core",
                      division_mass_threshold=DIVISION_MASS_THRESHOLD,
                      add_rate=0.1):
    mol_ids = ["glucose", "acetate"]
    bounds, n_bins = SQUARE_BOUNDS, SQUARE_BINS
    nx, ny = n_bins
    acetate_field = np.zeros((ny, nx), dtype=float)
    glc_y = np.linspace(0.01, 10.0, ny, dtype=float)[:, None]
    glc_field = np.repeat(glc_y, nx, axis=1)
    initial_fields = {"glucose": glc_field, "acetate": acetate_field}
    return {
        "state": {
            "fields": get_fields(n_bins=n_bins, mol_ids=mol_ids,
                                 initial_fields=initial_fields),
            "particles": get_particles_state(n_particles=1, bounds=bounds),
            "brownian_movement": get_brownian_movement_process(
                bounds=bounds, diffusion_rate=DEFAULT_DIFFUSION,
                advection_rate=DEFAULT_ADVECTION),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="brownian_movement",
                bounds=bounds, add_rate=add_rate),
            "particle_exchange": get_particle_exchange_process(
                n_bins=n_bins, bounds=bounds),
            "particle_division": get_particle_divide_process(
                division_mass_threshold=division_mass_threshold),
        },
        "schema": get_dfba_particle_composition(model_file=particle_model_id),
    }
```

Capture/test/commit (include the deletion of the corresponding old
`get_*_doc` from `test_suite.py` in this commit).

- [ ] **Step 4: Add `newtonian_particles` generator**

```python
@composite_generator(
    name="newtonian_particles",
    description=(
        "Physics-only baseline (Pymunk): rigid-body particles with "
        "collisions/crowding in continuous space. Use to validate contact "
        "dynamics + boundary enforcement."
    ),
    parameters={
        "n_particles": {"type": "int", "default": 1},
        "gravity":     {"type": "float", "default": -0.2},
        "elasticity":  {"type": "float", "default": 0.1},
        "add_rate":    {"type": "float", "default": 0.02},
    },
)
def newtonian_particles(core=None, *, n_particles=1, gravity=-0.2,
                        elasticity=0.1, add_rate=0.02):
    bounds = SQUARE_BOUNDS
    physics = {
        "gravity": gravity, "elasticity": elasticity, "bounds": bounds,
        "jitter_per_second": 0.5, "damping_per_second": 0.998,
    }
    return {
        "state": {
            "particles": get_newtonian_particles_state(
                n_particles=n_particles, bounds=bounds),
            "newtonian_particles": get_newtonian_particles_process(
                config=physics),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="newtonian_particles",
                bounds=bounds, add_rate=add_rate),
        },
    }
```

Capture/test/commit + delete `get_newtonian_particles_doc` from test_suite.py:
```bash
git commit -m "feat(composites): migrate newtonian_particles; drop legacy doc_func"
```

---

### Task C4: comets.py — port 4 generators

**File:** `spatio_flux/composites/comets.py`

Imports:
```python
import numpy as np
from pbg_superpowers.composite_generator import composite_generator

from spatio_flux.processes import (
    MODEL_REGISTRY_DFBA, MODEL_REGISTRY_KINETICS, DIVISION_MASS_THRESHOLD,
    get_fields, get_fields_with_schema, get_particles_state,
    get_newtonian_particles_state, get_brownian_movement_process,
    get_boundaries_process, get_particle_exchange_process,
    get_particle_divide_process, get_diffusion_advection_process,
    get_spatial_many_dfba, get_spatial_dFBA_process, get_spatial_many_kinetics,
    get_kinetic_particle_composition, get_dfba_particle_composition,
)
from spatio_flux.composites._constants import (
    SQUARE_BINS, SQUARE_BOUNDS, DEFAULT_DIFFUSION, DEFAULT_ADVECTION,
    DEFAULT_INITIAL_MIN_MAX, get_newtonian_particles_process,
)
```

- [ ] **Step 1: Add `comets_diffusion` generator**

Port of `get_comets_doc`. Body unchanged; the `dissolved_model_id` becomes a kwarg.

```python
@composite_generator(
    name="comets_diffusion",
    description=(
        "Two-phase coupling (no particles): spatial dFBA on a lattice with "
        "advection–diffusion of substrates + biomass. The classic COMETS "
        "field-only scenario."
    ),
    parameters={
        "dissolved_model_id": {"type": "string", "default": "ecoli core"},
    },
)
def comets_diffusion(core=None, *, dissolved_model_id="ecoli core"):
    mol_ids = ["glucose", "acetate", "dissolved biomass"]
    n_bins, bounds = SQUARE_BINS, SQUARE_BOUNDS
    diffusion_coeffs = {"glucose": 0.0, "acetate": 1e-1,
                        "dissolved biomass": 1e-2}
    advection_coeffs = {"dissolved biomass": DEFAULT_ADVECTION}
    nx, ny = n_bins
    shape = (ny, nx)
    acetate_field = np.zeros(shape, dtype=float)
    glc_y = np.linspace(0.01, 10.0, ny, dtype=float)[:, None]
    glc_field = np.repeat(glc_y, nx, axis=1)
    biomass_field = np.zeros(shape, dtype=float)
    x0 = nx // 2
    biomass_field[0:1, x0 - 1:x0 + 1] = 0.1
    initial_fields = {
        "dissolved biomass": biomass_field,
        "glucose": glc_field, "acetate": acetate_field,
    }
    spatial_dfba = get_spatial_many_dfba(
        model_id=dissolved_model_id, mol_ids=mol_ids,
        n_bins=n_bins, path=["fields"])
    return {
        **spatial_dfba,
        "fields": get_fields_with_schema(
            n_bins=n_bins, mol_ids=mol_ids, initial_fields=initial_fields),
        "diffusion": get_diffusion_advection_process(
            bounds=bounds, n_bins=n_bins, mol_ids=mol_ids,
            advection_coeffs=advection_coeffs,
            diffusion_coeffs=diffusion_coeffs),
    }
```

Note: SIMULATIONS currently has this entry named `comets_diffusion` but pointing to `get_comets_doc`. Keep the name.

Capture/test/commit + delete `get_comets_doc`.

- [ ] **Step 2: Add `comets_br_particles_kinetics` generator**

```python
@composite_generator(
    name="comets_br_particles_kinetics",
    description=(
        "Three-way coupling: spatial dFBA fields + Brownian particle "
        "agents that run Monod kinetics locally + diffusion. End-to-end "
        "smoke test of the COMETS-style composite stack with kinetic agents."
    ),
    parameters={
        "division_mass_threshold": {"type": "float", "default": DIVISION_MASS_THRESHOLD},
        "dissolved_model_id":      {"type": "string", "default": "ecoli core"},
        "kinetic_model_id":        {"type": "string", "default": "overflow_metabolism"},
        "n_particles":             {"type": "int",   "default": 1},
        "add_rate":                {"type": "float", "default": 0.1},
    },
)
def comets_br_particles_kinetics(
        core=None, *, division_mass_threshold=DIVISION_MASS_THRESHOLD,
        dissolved_model_id="ecoli core",
        kinetic_model_id="overflow_metabolism",
        n_particles=1, add_rate=0.1):
    mol_ids = ["glucose", "acetate", "dissolved biomass"]
    particle_config = MODEL_REGISTRY_KINETICS[kinetic_model_id]()
    n_bins, bounds = SQUARE_BINS, SQUARE_BOUNDS
    fields = get_fields(
        n_bins=n_bins, mol_ids=mol_ids,
        initial_min_max=DEFAULT_INITIAL_MIN_MAX)
    n_grid = (n_bins[1], n_bins[0])
    fields["dissolved biomass"] = np.zeros(n_grid)
    fields["dissolved biomass"][0, int(n_grid[0] / 4):int(3 * n_grid[0] / 4)] = 0.1
    spatial_dFBA_config = {
        "n_bins": n_bins, "models": MODEL_REGISTRY_DFBA, "mol_ids": mol_ids,
    }
    return {
        "state": {
            "fields": fields,
            "particles": get_particles_state(
                n_particles=n_particles, bounds=bounds,
                mass_range=(1e0, 1e1)),
            "spatial_dFBA": get_spatial_dFBA_process(
                config=spatial_dFBA_config, model_id=dissolved_model_id),
            "diffusion": get_diffusion_advection_process(
                bounds=bounds, n_bins=n_bins, mol_ids=mol_ids),
            "brownian_movement": get_brownian_movement_process(
                bounds=bounds, advection_rate=DEFAULT_ADVECTION,
                diffusion_rate=DEFAULT_DIFFUSION),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="brownian_movement",
                bounds=bounds, add_rate=add_rate),
            "particle_exchange": get_particle_exchange_process(
                n_bins=n_bins, bounds=bounds),
            "particle_division": get_particle_divide_process(
                division_mass_threshold=division_mass_threshold),
        },
        "schema": get_kinetic_particle_composition(core, config=particle_config),
    }
```

Capture/test/commit + delete `get_comets_br_particles_kinetics_doc`.

- [ ] **Step 3: Add `comets_br_particles_dfba` generator**

Body matches `get_comets_br_particles_dfba_doc`:

```python
@composite_generator(
    name="comets_br_particles_dfba",
    description=(
        "Full COMETS-style spatial composite: lattice dFBA + advection–"
        "diffusion + Brownian particles with internal dFBA + division. "
        "End-to-end coupled scenario."
    ),
    parameters={
        "particle_model_id":       {"type": "string", "default": "ecoli core"},
        "dissolved_model_id":      {"type": "string", "default": "ecoli core"},
        "division_mass_threshold": {"type": "float",  "default": 3},
        "n_particles":             {"type": "int",    "default": 1},
        "add_rate":                {"type": "float",  "default": 0.3},
    },
)
def comets_br_particles_dfba(
        core=None, *, particle_model_id="ecoli core",
        dissolved_model_id="ecoli core", division_mass_threshold=3,
        n_particles=1, add_rate=0.3):
    mol_ids = ["glucose", "acetate", "dissolved biomass"]
    bounds, n_bins = SQUARE_BOUNDS, SQUARE_BINS
    nx, ny = n_bins
    shape = (ny, nx)
    acetate_field = np.zeros(shape, dtype=float)
    glc_y = np.linspace(0.01, 10.0, ny, dtype=float)[:, None]
    glc_field = np.repeat(glc_y, nx, axis=1)
    biomass_field = np.zeros(shape, dtype=float)
    x0, x1 = nx // 4, 3 * nx // 4
    biomass_field[0:1, x0:x1] = 0.1
    initial_fields = {"dissolved biomass": biomass_field,
                      "glucose": glc_field, "acetate": acetate_field}
    advection_coeffs = {"dissolved biomass": DEFAULT_ADVECTION}
    spatial_dfba = get_spatial_many_dfba(
        n_bins=n_bins, model_id=dissolved_model_id,
        mol_ids=mol_ids, path=["fields"])
    state = {
        **spatial_dfba,
        "fields": get_fields_with_schema(
            n_bins=n_bins, mol_ids=mol_ids, initial_fields=initial_fields),
        "diffusion": get_diffusion_advection_process(
            bounds=bounds, n_bins=n_bins, mol_ids=mol_ids,
            advection_coeffs=advection_coeffs),
        "particles": get_particles_state(n_particles=n_particles, bounds=bounds),
        "brownian_movement": get_brownian_movement_process(
            bounds=bounds, advection_rate=(0, -0.2),
            diffusion_rate=DEFAULT_DIFFUSION),
        "enforce_boundaries": get_boundaries_process(
            particle_process_name="brownian_movement",
            bounds=bounds, add_rate=add_rate),
        "particle_exchange": get_particle_exchange_process(
            n_bins=n_bins, bounds=bounds),
        "particle_division": get_particle_divide_process(
            division_mass_threshold=division_mass_threshold),
    }
    return {
        "state": state,
        "schema": get_dfba_particle_composition(model_file=particle_model_id),
    }
```

Capture/test/commit + delete `get_comets_br_particles_dfba_doc`.

- [ ] **Step 4: Add `comets_nt_particles_dfba` generator**

Port of `get_newtonian_particle_comets_doc`:

```python
@composite_generator(
    name="comets_nt_particles_dfba",
    description=(
        "Mechanochemical + metabolic coupling: Pymunk particles move/"
        "collide while COMETS fields diffuse; particles run metabolism "
        "(via exchange) against local concentrations."
    ),
    parameters={
        "particle_model_id":  {"type": "string", "default": "ecoli core"},
        "dissolved_model_id": {"type": "string", "default": "ecoli core"},
        "n_particles":        {"type": "int",    "default": 2},
        "bounds":             {"type": "object", "default": list(SQUARE_BOUNDS)},
        "n_bins":             {"type": "object",
                                "default": [n * 2 for n in SQUARE_BINS]},
    },
)
def comets_nt_particles_dfba(
        core=None, *, particle_model_id="ecoli core",
        dissolved_model_id="ecoli core", n_particles=2,
        bounds=list(SQUARE_BOUNDS),
        n_bins=[n * 2 for n in SQUARE_BINS]):
    bounds_t, n_bins_t = tuple(bounds), tuple(n_bins)
    mol_ids = ["glucose", "acetate", "dissolved biomass"]
    initial_min_max = {"glucose": (0.5, 2), "acetate": (0, 0),
                       "dissolved biomass": (0, 0.1)}
    advection_coeffs = {"dissolved biomass": DEFAULT_ADVECTION}
    fields = get_fields(n_bins=n_bins_t, mol_ids=mol_ids,
                        initial_min_max=initial_min_max)
    particle_config = {
        "gravity": -1.0, "elasticity": 0.1, "bounds": bounds_t,
        "jitter_per_second": 1e-1, "damping_per_second": 1e-1,
    }
    return {
        "state": {
            "fields": fields,
            "diffusion": get_diffusion_advection_process(
                bounds=bounds_t, n_bins=n_bins_t, mol_ids=mol_ids,
                advection_coeffs=advection_coeffs),
            "spatial_kinetics": get_spatial_many_kinetics(
                model_id="single_substrate_assimilation",
                n_bins=n_bins_t, mol_ids=mol_ids),
            "particles": get_newtonian_particles_state(
                n_particles=n_particles, bounds=bounds_t),
            "newtonian_particles": get_newtonian_particles_process(
                config=particle_config),
            "particle_exchange": get_particle_exchange_process(
                n_bins=n_bins_t, bounds=bounds_t),
            "particle_division": get_particle_divide_process(
                division_mass_threshold=0.5),
            "enforce_boundaries": get_boundaries_process(
                particle_process_name="newtonian_particles",
                bounds=bounds_t, boundary_to_add=("top",),
                add_rate=0.01, mass_range=(1e-3, 1e-2)),
        },
        "schema": get_dfba_particle_composition(model_file=particle_model_id),
    }
```

Capture/test/commit + delete `get_newtonian_particle_comets_doc`.

---

### Task C5: reference.py — port 2 generators

Both `spatioflux_reference_demo` and `reference_demo_x2y2` use the same `get_reference_composite_doc` with different `n_bins`. The new generator takes `n_bins` as a parameter; the two SIMULATIONS entries pass different overrides.

**File:** `spatio_flux/composites/reference.py`

```python
from pbg_superpowers.composite_generator import composite_generator

from spatio_flux.processes import (
    get_fields, get_newtonian_particles_state,
    get_diffusion_advection_process, get_spatial_many_kinetics,
    get_particle_exchange_process, get_particle_divide_process,
    get_boundaries_process, get_community_dfba_particle_composition,
)
from spatio_flux.composites._constants import (
    SQUARE_BINS, SQUARE_BOUNDS, get_newtonian_particles_process,
)


@composite_generator(
    name="spatioflux_reference_demo",
    description=(
        "SpatioFlux demonstration reference composite: Newtonian motile "
        "particles + particle–field exchange + internal multi-dFBA + "
        "Monod/diffusion fields + mass-aggregated division."
    ),
    parameters={
        "bounds":      {"type": "object", "default": list(SQUARE_BOUNDS)},
        "n_bins":      {"type": "object", "default": list(SQUARE_BINS)},
        "depth":       {"type": "float",  "default": 1 / 25},
        "n_particles": {"type": "int",    "default": 1},
    },
)
def spatioflux_reference_demo(
        core=None, *, bounds=list(SQUARE_BOUNDS),
        n_bins=list(SQUARE_BINS), depth=1 / 25, n_particles=1):
    bounds_t, n_bins_t = tuple(bounds), tuple(n_bins)
    division_mass_threshold = 0.4
    add_rate = 0.0
    initial_submasses = {"ecoli_1": 0.1, "ecoli_2": 0.1}
    glucose_level = 5.0
    biomass_id = "dissolved biomass"
    mol_ids = ["glucose", "acetate", biomass_id]
    initial_min_max = {
        "glucose": (glucose_level, glucose_level),
        "acetate": (0.0, 0.0),
        biomass_id: (0.1, 0.2),
    }
    diffusion_coeffs = {"glucose": 1e-1, "acetate": 1e-1, biomass_id: 1e-1}
    diffusion_boundary_config = {
        "default": {"x": {"type": "periodic"},
                    "y": {"type": "neumann"}},
        "glucose": {"top": {"type": "dirichlet", "value": glucose_level}},
        "acetate": {"bottom": {"type": "dirichlet", "value": glucose_level}},
    }
    physics_cfg = {"gravity": -1.0, "elasticity": 0.1, "bounds": bounds_t,
                   "jitter_per_second": 1e-2, "damping_per_second": 0.95,
                   "friction": 0.9}
    models = {
        "ecoli_1": {
            "model_file": "textbook",
            "substrate_update_reactions": {
                "glucose": "EX_glc__D_e", "acetate": "EX_ac_e"},
            "kinetic_params": {"glucose": (0.1, 2), "acetate": (1.0, 0.1)},
            "bounds": {
                "EX_o2_e": {"lower": -2, "upper": None},
                "ATPM": {"lower": 3, "upper": 3},
            },
        },
        "ecoli_2": {
            "model_file": "textbook",
            "substrate_update_reactions": {
                "glucose": "EX_glc__D_e", "acetate": "EX_ac_e"},
            "kinetic_params": {"glucose": (1.0, 0.1), "acetate": (0.01, 1)},
            "bounds": {
                "EX_o2_e": {"lower": -2, "upper": None},
                "ATPM": {"lower": 1, "upper": 1},
            },
        },
    }
    fields = get_fields(n_bins=n_bins_t, mol_ids=mol_ids,
                        initial_min_max=initial_min_max)
    particles = get_newtonian_particles_state(
        n_particles=n_particles, bounds=bounds_t)
    for pid, internal in particles.items():
        internal["sub_masses"] = initial_submasses.copy()
    diffusion = get_diffusion_advection_process(
        bounds=bounds_t, n_bins=n_bins_t, mol_ids=mol_ids,
        diffusion_coeffs=diffusion_coeffs, advection_coeffs={},
        boundary_conditions=diffusion_boundary_config)
    spatial_kinetics = get_spatial_many_kinetics(
        model_id="low_yield_glucose_overflow", biomass_id=biomass_id,
        n_bins=n_bins_t, mol_ids=mol_ids, path=["fields"])
    newtonian = get_newtonian_particles_process(config=physics_cfg)
    particle_division = get_particle_divide_process(
        division_mass_threshold=division_mass_threshold,
        submass_split_mode="random")
    enforce_boundaries = get_boundaries_process(
        particle_process_name="newtonian_particles",
        bounds=bounds_t, add_rate=add_rate)
    particle_exchange = get_particle_exchange_process(
        n_bins=n_bins_t, bounds=bounds_t, depth=depth)
    schema = get_community_dfba_particle_composition(models=models)
    return {
        "state": {
            **spatial_kinetics,
            "fields": fields,
            "diffusion": diffusion,
            "particles": particles,
            "particle_exchange": particle_exchange,
            "particle_division": particle_division,
            "enforce_boundaries": enforce_boundaries,
            "newtonian_particles": newtonian,
        },
        "schema": schema,
    }


# reference_demo_x2y2 is the same generator with doubled grid resolution —
# expose it as a SECOND entry to keep the SIMULATIONS catalog identical to
# what existed before. The body lives in spatioflux_reference_demo; this
# wrapper just declares the alternate default.

@composite_generator(
    name="reference_demo_x2y2",
    description="Different resolution for the spatio-flux reference demo",
    parameters={
        "bounds":      {"type": "object", "default": list(SQUARE_BOUNDS)},
        "n_bins":      {"type": "object",
                        "default": [n * 2 for n in SQUARE_BINS]},
        "depth":       {"type": "float",  "default": 1 / 25},
        "n_particles": {"type": "int",    "default": 1},
    },
)
def reference_demo_x2y2(core=None, **kwargs):
    return spatioflux_reference_demo(core=core, **kwargs)
```

SIMULATIONS updates:
```python
'spatioflux_reference_demo': {
    'generator':   'spatioflux_reference_demo',
    'plot_func':   plot_newtonian_particle_comets,
    'time':        120,
    'overrides':   {'n_bins': list(SQUARE_BINS)},
    'plot_config': {'filename': 'spatioflux_reference_demo',
                    'particles_row': 'separate', 'n_snapshots': 8},
},
'reference_demo_x2y2': {
    'generator':   'reference_demo_x2y2',
    'plot_func':   plot_newtonian_particle_comets,
    'time':        120,
    'overrides':   {'n_bins': [n * 2 for n in SQUARE_BINS]},
    'plot_config': {'filename': 'reference_demo_x2y2',
                    'particles_row': 'separate', 'n_snapshots': 8},
},
```

Capture/test/commit + delete `get_reference_composite_doc`.

- [ ] **Step 1: Run the FULL spatio-flux test suite at the end of Phase C**

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
python spatio_flux/experiments/test_suite.py --output /tmp/check_full
```
Expected: all 19 tests complete with the same `✅ Completed` lines as before the migration. Visual check `/tmp/check_full/report.html` for parity with the pre-migration report.

- [ ] **Step 2: Run the full pytest suite**

```bash
pytest -q
```
Expected: all PASS, including the 19 parametrized snapshot tests.

- [ ] **Step 3: Sanity check — `test_suite.py` has no more `get_*_doc` functions**

```bash
grep -n "^def get_.*_doc\b" spatio_flux/experiments/test_suite.py
```
Expected: no matches (or only `get_newtonian_particles_process` which is a helper, not a doc-builder).

- [ ] **Step 4: Final Phase C commit**

```bash
git commit --allow-empty -m "feat(composites): Phase C complete — 19 composites on @composite_generator"
```

---

## Phase D — Dashboard endpoint

### Task D1: Update `/api/composites` to surface generators

**Files:**
- Modify: pbg-superpowers server file that defines the `/api/composites` route. (Find it first.)

- [ ] **Step 1: Locate the endpoint**

```bash
cd ~/code/pbg-superpowers
grep -rn "api/composites\|/composites" pbg_superpowers/_server/ server/ 2>/dev/null | head -10
```

The route lives wherever the grep points. Note the file path.

- [ ] **Step 2: Replace the `discover_composites` call with `discover_all`**

In the file from Step 1, find the handler that returns composites. It likely looks like:

```python
from pbg_superpowers.composite_discovery import discover_composites

def list_composites():
    return discover_composites(extra_search_paths=...)
```

Change it to:

```python
from pbg_superpowers.composite_discovery import discover_all

def list_composites():
    return discover_all(extra_search_paths=...)
```

Each entry now includes `kind: 'spec' | 'generator'`. Spec entries pass through unchanged; generator entries include `name`, `description`, `parameters`, and `module`.

- [ ] **Step 3: Add an integration test for the endpoint**

If a test for the endpoint exists, add a case verifying both kinds appear. If not, skip — the unit test in A4 already covers `discover_all`.

- [ ] **Step 4: Smoke-test the dashboard**

```bash
cd ~/code/spatio-flux && source .venv/bin/activate
# (In a real workspace) start the server and check the Composites tab.
# Expected: 19 spatio-flux composites with a [generator] badge.
```

- [ ] **Step 5: Commit**

```bash
cd ~/code/pbg-superpowers
git add <endpoint_file>
git commit -m "feat(server): /api/composites returns both spec and generator entries"
```

---

## Phase E — Documentation

### Task E1: Convention doc + cross-link

**Files:**
- Create: `pbg-superpowers/docs/conventions/composite_generators.md`
- Modify: `pbg-superpowers/docs/conventions/composites.md` (add cross-link)

- [ ] **Step 1: Write the convention doc**

Create `docs/conventions/composite_generators.md`:

````markdown
# Composite Generator Convention

## What is a composite generator?

A composite generator is a Python function decorated with
`@composite_generator(...)` that builds a process-bigraph document at call
time. It lives in any installed `bigraph-schema`-dependent package and is
discovered by importing the host package — unlike the static
`*.composite.{yaml,json}` convention, which is discovered without imports.

Generators exist for the same reason that "config files" sometimes graduate
to "config programs": when the composite needs to *compute* something —
random initial fields, introspected substrate lists, conditionally-built
processes — a function is the simplest expression of that intent.

## When to use a generator vs. a static spec

| Situation | Use |
|---|---|
| The composite's state is fully known up-front | static spec |
| Initial state contains numpy arrays computed from kwargs | generator |
| You need to introspect a downstream process before wiring | generator |
| You want CI to scan for composites without importing simulators | static spec |
| The composite is procedurally generated (loops, conditionals) | generator |
| You want to diff structural changes in PRs | static spec |

Default to static spec if either works. Reach for a generator only when the
static form would require inlining large arrays or extending the spec
format with a DSL.

## Decorator API

```python
from pbg_superpowers.composite_generator import composite_generator


@composite_generator(
    name="my_composite",
    description="A worked example showing the contract.",
    parameters={
        "rate":  {"type": "float",  "default": 1.0,
                  "description": "Multiplicative factor"},
        "model": {"type": "string", "default": "default"},
    },
)
def my_composite(core=None, *, rate=1.0, model="default"):
    return {
        "my_process": {
            "_type": "process",
            "address": "local:MyProcess",
            "config": {"rate": rate, "model_id": model},
            "inputs":  {"level": ["stores", "level"]},
            "outputs": {"level": ["stores", "level"]},
            "interval": 1.0,
        },
        "stores": {"level": 0.0},
    }
```

### Required signature

- **First positional arg:** `core=None` — a `process-bigraph` Core, or
  `None` when the dashboard / discovery probes the function without a
  type-registered core.
- **All other args:** keyword-only (`*, ...`) with defaults matching the
  decorator's `parameters` declaration.
- **Return:** a state dict, OR a `{state: ..., schema: ...}` envelope when
  the composite needs custom typed schema.

### Parameter declarations

Same shape as the static-spec format:

| Key | Type | Description |
|---|---|---|
| `type` | string | One of `float`, `int`, `string`, `bool`, `object` |
| `default` | matching `type` | Used when the caller doesn't override |
| `description` | string (optional) | Surfaced in dashboard form labels |

## Discovery

```python
from pbg_superpowers.composite_generator import discover_generators

entries = discover_generators()
# {"my_pkg.composites.metabolism.my_composite": <GeneratorEntry>, ...}
```

`discover_generators` imports every installed distribution that depends on
`bigraph-schema`. To merge generators with static specs for a uniform
dashboard surface:

```python
from pbg_superpowers.composite_discovery import discover_all

merged = discover_all(extra_search_paths=[Path("my_workspace/composites")])
# Each entry has a `kind: "spec" | "generator"` tag.
```

## Building and running

```python
from pbg_superpowers.composite_generator import build_generator

entry = discover_generators()["my_pkg.composites.my_composite"]
doc = build_generator(entry, overrides={"rate": 2.5})
# doc is the dict your function returned; pass it to Composite(...) as usual.
```

`build_generator` validates that every key in `overrides` is declared in
`entry.parameters` and raises `KeyError` otherwise. Defaults from
`parameters` fill in anything the caller didn't override.

## Auto-registration

Importing the host package must trigger every `@composite_generator` in
that package. The standard pattern is a top-level `__init__.py` that
imports each submodule for side effects:

```python
# my_pkg/composites/__init__.py
from . import metabolism  # noqa: F401
from . import spatial     # noqa: F401
```

If a generator decorator never runs, its entry never makes it into
`_REGISTRY`, and discovery won't find it.

## Trade-offs

- **Discovery imports.** This is the biggest difference from static specs.
  Generators require importing every candidate package, including
  transitive deps. For workspaces consuming heavy simulators (cobra,
  pymunk, …) this adds noticeable startup cost. The dashboard caches the
  registry per server lifetime.
- **No in-place editing.** Unlike a YAML/JSON spec, a generator changes
  require an edit-test-commit cycle in Python.
- **No git-diff at the data layer.** You diff function bodies, not state
  documents. For canonical composites that's a downside; use a static
  spec instead.

## See also

- [Composite Spec Convention](composites.md) — the data-first sibling.
- `pbg_superpowers.composite_generator` — module reference.
- Example use: `spatio_flux.composites.*` — 19 generators across 5 group
  modules.
````

- [ ] **Step 2: Add cross-link in `composites.md`**

In `docs/conventions/composites.md`, find the "See also" section near the end and add:

```markdown
- [Composite Generator Convention](composite_generators.md) — the
  function-based sibling for composites that need to compute initial state
  or introspect processes at build time.
```

- [ ] **Step 3: Commit**

```bash
cd ~/code/pbg-superpowers
git add docs/conventions/composite_generators.md docs/conventions/composites.md
git commit -m "docs: composite_generator convention + cross-link from composites.md"
```

---

## Final checklist

- [ ] All 19 generators registered in `spatio_flux.composites.REGISTRY`
- [ ] All 19 snapshot files in `spatio_flux/composites/_snapshots/`
- [ ] `pytest -q` green in both repos
- [ ] `python spatio_flux/experiments/test_suite.py` produces equivalent
      `out/report.html` to pre-migration runs
- [ ] No `get_*_doc` functions remain in `test_suite.py`
- [ ] Dashboard `/api/composites` returns 19 entries with `kind: generator`
      when serving the spatio-flux workspace
- [ ] `docs/conventions/composite_generators.md` exists; `composites.md`
      cross-links to it
- [ ] `pbg-superpowers` is at version `0.4.16`; `pbg-template` template-
      init.sh matches; `test_workspace_scaffold.py` assertion matches

When all boxes are checked: tag and release pbg-superpowers v0.4.16 to PyPI
so spatio-flux can switch from editable install back to PyPI dependency:

```bash
cd ~/code/pbg-superpowers
git tag v0.4.16 && git push --tags
# (release.yml workflow publishes to PyPI on tag push)
```
