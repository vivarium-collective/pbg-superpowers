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
`entry.parameters` and raises `ValueError` otherwise. Defaults from
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
