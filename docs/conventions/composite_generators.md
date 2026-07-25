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
from viva_superpowers.composite_generator import composite_generator


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

### Default emitter(s)

A generator can declare the observation sink(s) its composite ships with via
`emitters`, the same way `visualizations` declares canonical plots. Each entry
is a lightweight selection — **not** a full process-node spec:

```python
@composite_generator(
    name="baseline",
    emitters=[{
        "address": "local:ParquetEmitter",       # registered emitter link
        "config": {"out_dir": "out/parquet"},     # base config, merged in
        "paths": ["bulk", "listeners.mass"],       # optional: observable paths
    }],
)
def baseline(core=None): ...
```

| Key | Type | Description |
|---|---|---|
| `address` | string (required) | Registered emitter link, e.g. `local:ParquetEmitter` |
| `config` | object (optional) | Base config merged into the emitter step |
| `paths` | list[string] (optional) | Dotted observable store-paths to wire |

The emit-schema and topology are deliberately **not** part of this
declaration — the generator (or the workspace's emitter-resolution code)
computes them, because they often depend on the composite's runtime shape.
`emitters` only answers *which* sink to install and with *what* base config.

This is the standalone analogue of the dashboard's run-time observable
injection (which builds an emitter from `spec.yaml.observables`). When a
workspace builds the composite **outside** that flow, it reads these defaults
via `emitter_defaults(fn_or_entry)` so the composite still has a sink. Any
external override the workspace keeps (e.g. v2ecoli's
`set_parquet_emitter_override`) takes precedence; the declared default fills
in when none is set. Resolution order, as wired in v2ecoli's baseline:

```
1. external parquet override  (set_parquet_emitter_override)
2. external sqlite override   (set_emitter_override)
3. external null override     (set_null_emitter_override)
4. generator-declared default (entry.emitters)   <-- this convention
5. RAMEmitter fallback
```

```python
from viva_superpowers.composite_generator import emitter_defaults

emitter_defaults(baseline)        # [{"address": "local:ParquetEmitter", ...}]
emitter_defaults(some_entry)      # same, from a GeneratorEntry
emitter_defaults(object())        # [] — safe on non-generators
```

## Discovery

```python
from viva_superpowers.composite_generator import discover_generators

entries = discover_generators()
# {"my_pkg.composites.metabolism.my_composite": <GeneratorEntry>, ...}
```

`discover_generators` imports every installed distribution that depends on
`bigraph-schema`. To merge generators with static specs for a uniform
dashboard surface:

```python
from viva_superpowers.composite_discovery import discover_all

merged = discover_all(extra_search_paths=[Path("my_workspace/composites")])
# Each entry has a `kind: "spec" | "generator"` tag.
```

## Building and running

```python
from viva_superpowers.composite_generator import build_generator

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

## Default state and the Composite Explorer

The Explorer renders a generator's wiring from a *resolved default state*. The
workbench looks for it in this order:

1. the spec's declared `default_state_ref` artifact,
2. a committed `reports/composite-state/<id>.json` in the workspace,
3. a live build of the generator via the workspace env worker.

Because of (3), a brand-new generator needs **no** artifact for the live
dashboard — open the Explorer and it builds. Commit an artifact when the state
must be available *without* a build: the published read-only bundle serves
static state, and CI hosts usually lack the heavy build inputs (a ParCa cache, a
licensed solver) that the generator needs.

Two rules for whatever regenerates those artifacts:

- **Never write an artifact whose `state` is null.** A resolver that cannot
  produce wiring returns a *200 payload* with `state: null` and
  `wiring_status: "unavailable"`. Serializing that payload verbatim writes a
  plausible-looking file whose only content is the failure — and since the
  resolver reads that same file back at step (2), the Explorer then reports
  "default state for generator '<x>' is not generated yet" forever, with a
  committed artifact making the gap look filled. Fail the regeneration instead;
  a missing artifact is honest and step (3) still covers the live UI.
  `pbg-template` ships `tests/test_composite_state_artifacts.py` to enforce this.
- **Emit the alias id too.** Discovery canonicalizes `<module>.<name>` to
  `<module>` when the module stem already is the name, but the workspace
  manifest still advertises both forms and pop-out URLs are built from whichever
  string the caller holds. Write the artifact under both ids, or the
  un-canonicalized one renders empty.

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
- `viva_superpowers.composite_generator` — module reference.
- Example use: `spatio_flux.composites.*` — 19 generators across 5 group
  modules.
