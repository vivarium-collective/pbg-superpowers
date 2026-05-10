# bigraph-schema Discovery Convention

## TL;DR

`allocate_core()` automatically calls `discover_packages(core)`, which scans
every pip-installed distribution that declares `bigraph-schema` as a runtime
dependency. It imports each package's modules, finds all `Edge` subclasses
(including `Process` and `Step`), and registers them in `core.link_registry`
under both their fully-qualified name and their short class name. A `pbg-*`
package is auto-discoverable if it is pip-installed, declares `bigraph-schema`
as a dep, and exposes real `Process`/`Step` subclasses — no manual
`register_link()` calls required.

---

## The Contract

### Entry point

```
bigraph_schema.core.allocate_core
  └─ bigraph_schema.package.discover.discover_packages
       └─ bigraph_schema.package.discover.load_local_modules
            └─ bigraph_schema.package.discover.recursive_dynamic_import  (per-package)
                 ├─ find_edges   → registers Edge subclasses into core.link_registry
                 └─ find_types   → registers Node subclasses into core.registry
```

Source files:

- `bigraph_schema/package/discover.py` — the discovery logic (`find_edges`,
  `find_types`, `recursive_dynamic_import`, `discover_packages`)
- `bigraph_schema/core.py:allocate_core` — the public entry point

### What is an `Edge`?

`bigraph_schema.Edge` is the base class for anything that can be wired into a
bigraph. The class hierarchy relevant to `pbg-*` wrappers is:

```
bigraph_schema.Edge
  └─ process_bigraph.composite.Open
       ├─ process_bigraph.composite.Step   (event-driven / stateless)
       └─ process_bigraph.composite.Process  (time-stepped)
```

`find_edges` uses `inspect.isclass` + `issubclass(cls, Edge)` to locate these.
It skips `Edge` itself and any class whose `__module__` does not match the
module being scanned (preventing false positives from imported names).

Registration keys use the **fully-qualified name** (`pbg_foo.processes.FooProcess`)
as the primary key. The short class name (`FooProcess`) is registered as an alias
if that name is not already taken — so both keys work in composite documents.

### What is a `Node`?

`bigraph_schema.schema.Node` is the base class for custom schema types.
`find_types` discovers `Node` subclasses and registers them into
`core.registry` under their short class name. This is optional — most
`pbg-*` wrappers do not define custom `Node` subclasses.

A package may also expose a module-level `register_types(core)` function.
`recursive_dynamic_import` calls this before scanning the module for
`Edge`/`Node` subclasses, so it can register types that are expressed as
plain dicts rather than `Node` subclasses.

### How packages are found

`Core.__init__` builds `self.distributions_packages` from
`importlib.metadata.packages_distributions()` — the same metadata that `pip`
writes at install time. `load_local_modules` iterates this mapping and calls
`is_process_library(dist)`, which returns `True` when any entry in
`dist.requires` contains `"bigraph-schema"`. Only those distributions are
scanned.

---

## Worked Example: `pbg-foo`

A minimal package that exposes one `Process` and is auto-discovered.

### `pyproject.toml`

```toml
[project]
name = "pbg-foo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "bigraph-schema",
    "process-bigraph",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["pbg_foo"]
```

Two things make this package discoverable:

1. `bigraph-schema` appears in `dependencies` → `is_process_library` returns `True`.
2. The package is pip-installable → `importlib.metadata` can see it.

### `pbg_foo/__init__.py`

```python
"""pbg-foo: process-bigraph wrapper for Foo."""

from .processes import FooProcess

__all__ = ["FooProcess"]
```

Exporting via `__all__` is not strictly required for discovery (discovery
imports modules directly), but it is the conventional contract for package
consumers.

### `pbg_foo/processes.py`

```python
"""FooProcess: wraps the Foo simulator as a process-bigraph Process."""

from process_bigraph import Process


class FooProcess(Process):
    """Time-stepped wrapper for the Foo simulator.

    Inputs
    ------
    substrate : float
        Concentration fed into Foo on each step (delta-compatible: additive
        contributions from sibling processes accumulate before the step runs).

    Outputs
    -------
    product : float
        Amount of product generated this interval (emitted as a delta so
        sibling processes can write to the same port).
    """

    config_schema = {
        "rate": {"_type": "float", "_default": 0.1},
        "model_path": {"_type": "string", "_default": ""},
    }

    def inputs(self):
        return {"substrate": "float"}

    def outputs(self):
        return {"product": "float"}

    def initial_state(self):
        return {"substrate": 1.0}

    def update(self, state, interval):
        return {"product": state["substrate"] * self.config["rate"] * interval}
```

Key points:

- Inherits `process_bigraph.Process`, which inherits `bigraph_schema.Edge` →
  `find_edges` will pick it up.
- `config_schema` uses bigraph-schema dict format; values that do not vary at
  runtime belong here, not in input ports.
- Output types are bare (`"float"`) so updates accumulate additively with
  sibling processes. `overwrite[float]` would silently clobber sibling writes.
- No `register_link()` call anywhere — discovery handles it.

---

## Verifying Discovery Works

After `pip install -e .` (or any standard install):

```python
from process_bigraph import allocate_core

core = allocate_core()

# Short name registered as alias:
assert "FooProcess" in core.link_registry

# Fully-qualified name is the primary key:
assert "pbg_foo.processes.FooProcess" in core.link_registry

# The registered value is the class itself:
cls = core.link_registry["FooProcess"]
assert cls.__name__ == "FooProcess"
```

You can also inspect discovered processes without running a simulation:

```python
from pbg_superpowers.core_introspection import list_processes

procs = list_processes(core)
assert "FooProcess" in procs
```

---

## Common Gotchas

### Stub classes are not discovered

```python
# NOT discovered — does not inherit Edge or Process:
class FooProcess:
    def update(self, state, interval): ...

# Discovered:
from process_bigraph import Process
class FooProcess(Process):
    def update(self, state, interval): ...
```

`find_edges` uses `issubclass(cls, Edge)` — duck-typed classes that happen to
have the same method signatures are invisible to it.

### Editable installs work fine

```bash
pip install -e /path/to/pbg-foo
```

`importlib.metadata` records editable installs the same way as regular ones
(via a `.pth` file or `direct_url.json`). Discovery sees them identically.

### Missing optional dependencies are silently skipped

If a submodule within your package imports an optional dependency that is not
installed (e.g., a `protocols/ray.py` that does `import ray`), `ImportError`
is caught inside `recursive_dynamic_import` and that submodule is skipped.
Discovery continues scanning the rest of the package. Your other processes
are still registered. You do not need to guard optional imports with
`try/except` in your processes module itself.

### Source-tree-only packages are NOT discovered

A directory on `sys.path` with a `pbg_foo/` folder is not enough.
`importlib.metadata` only knows about installed distributions. If the package
is not pip-installed (even as `-e`), `discover_packages` will not find it.

This also means: running tests via `pytest` from the source tree without
first running `pip install -e .` will not trigger discovery for that package.
The `pyproject.toml` + `pip install -e .` step is mandatory.

### Do not call `register_link()` manually for auto-discoverable classes

```python
# Anti-pattern — unnecessary and redundant for compliant packages:
core = allocate_core()
core.register_link("FooProcess", FooProcess)

# Correct — nothing extra needed:
core = allocate_core()
# FooProcess is already in core.link_registry
```

Manual `register_link()` in test setup is fine for classes defined inline in
test files (those are not pip-installed and thus not auto-discoverable). For
production `pbg-*` packages it is unnecessary boilerplate.

---

## What This Means for Workflows

### `allocate_core()` in scaffolded workspaces

The `pbg_<slug>/core.py` file generated by `/pbg-workspace` calls
`allocate_core()` and may add workspace-local type registrations. It does
**not** need (and should not have) `register_link()` calls for any compliant
`pbg-*` dependency — those are handled by discovery at `allocate_core()` time.

```python
# pbg_mymodel/core.py — correct pattern:
from process_bigraph import allocate_core

def build_core():
    core = allocate_core()
    # Only register workspace-local types that aren't in pip-installed packages:
    core.register_type("my_local_type", {"_inherit": "float", "_default": 0.0})
    return core
```

### Dashboard "Install" button

The pbg-template dashboard's **Imports** panel has an "Install" button per
imported `pbg-*` package. Clicking it runs:

```bash
pip install -e <path-to-pbg-package>
```

After that install, the next call to `allocate_core()` (e.g., running tests
or restarting the server) will pick up the new package's processes
automatically — no manual wiring required.

### The `register_types(core)` hook

If your package needs to register custom schema types that are expressed as
plain dicts (rather than `Node` subclasses), expose a module-level function:

```python
# pbg_foo/types.py
def register_types(core):
    core.register_type("foo_concentration", {
        "_inherit": "float",
        "_default": 0.0,
        "_units": "mmol/L",
    })
    return core  # must return core
```

`recursive_dynamic_import` calls `register_types(core)` automatically when it
encounters the function in a module. The `return core` is required — the
function must hand the (possibly mutated) core back.

---

## Reference

| Symbol | Location | Role |
|---|---|---|
| `allocate_core` | `bigraph_schema/core.py:1622` | Public entry point; caches base core |
| `discover_packages` | `bigraph_schema/package/discover.py:167` | Top-level discovery call |
| `load_local_modules` | `bigraph_schema/package/discover.py:127` | Iterates installed dists |
| `recursive_dynamic_import` | `bigraph_schema/package/discover.py:59` | Per-module import + scan |
| `find_edges` | `bigraph_schema/package/discover.py:11` | Finds `Edge` subclasses |
| `find_types` | `bigraph_schema/package/discover.py:31` | Finds `Node` subclasses |
| `is_process_library` | `bigraph_schema/package/discover.py:120` | Checks `bigraph-schema` dep |
| `Edge` | `bigraph_schema/edge.py:18` | Base class for processes/steps |
| `Node` | `bigraph_schema/schema.py:30` | Base class for custom types |
