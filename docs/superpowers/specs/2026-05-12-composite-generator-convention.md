# Composite Generator convention — spec

**Date:** 2026-05-12
**Status:** approved, ready for implementation plan
**Affects:** pbg-superpowers (new convention), spatio-flux (first consumer)

## Problem

The existing `*.composite.{yaml,json}` convention represents composites as
declarative data files. That works cleanly when the composite state is
fully static, but breaks down when a composite needs to:

- Compute initial state from arithmetic (e.g. `np.linspace(0.01, 10.0, ny)`
  gradients, `np.random.uniform(...)` fields)
- Introspect a downstream process to wire itself (e.g. "what substrates does
  this dFBA model expose?")
- Build N-of-something stores in a loop
- Apply conditional structure based on a parameter

Spatio-flux's test suite has 19 composites; ~15 fall in those categories and
cannot be represented as static specs without either inlining large numeric
arrays or introducing a DSL of computation primitives into the spec format.
Both options are unappealing.

A discoverable-function convention solves this with the simplest possible
escape hatch: arbitrary Python at composite-build time.

## Solution overview

A second pbg-superpowers convention, **composite generators**, sits beside
the static-spec convention. Each generator is a Python function decorated
with `@composite_generator(...)`, taking typed kwargs and returning a
process-bigraph document dict.

```
                pbg-superpowers conventions
                ───────────────────────────
                  static specs          composite generators
                  ────────────          ────────────────────
file pattern    │ *.composite.{yaml,json}     n/a (in code)
host module     │ any pbg-* package           any pbg-* package
discovery       │ glob, no import             import + decorator registry
shape           │ data with ${param}          function (core, **kwargs) → dict
right when      │ canonical, diff-friendly    needs computation or introspection
trade-off       │ static                      requires importing host package
```

Both kinds surface in the dashboard's Composites tab via a uniform
`discover_all()` helper that tags each entry with `kind: spec | generator`.

## pbg-superpowers — convention layer

### New module: `pbg_superpowers/composite_generator.py`

```python
@dataclass
class GeneratorEntry:
    id: str                   # "<dotted_module>.<name>"
    name: str
    description: str
    parameters: dict          # {name: {type, default, description?}}
    func: Callable            # the wrapped function
    module: str               # fully-qualified module path

_REGISTRY: dict[str, GeneratorEntry] = {}

def composite_generator(*, name: str, description: str = "",
                        parameters: dict | None = None):
    """Decorator that registers a doc-building function.

    The wrapped function must accept (core=None, **kwargs) and return a
    process-bigraph state dict.

    `parameters` declares each kwarg with its type and default, in the same
    shape that *.composite.yaml uses, so the dashboard form code is shared.
    """
    def decorate(fn):
        entry = GeneratorEntry(
            id=f"{fn.__module__}.{name}",
            name=name,
            description=description,
            parameters=parameters or {},
            func=fn,
            module=fn.__module__,
        )
        _REGISTRY[entry.id] = entry
        fn._composite_generator_entry = entry
        return fn
    return decorate

def discover_generators(extra_packages: list[str] | None = None
                        ) -> dict[str, GeneratorEntry]:
    """Walk installed packages that depend on bigraph-schema and import
    them; return whatever ended up in _REGISTRY.

    Unlike discover_composites (file glob, no import), this imports every
    matching package. Memoized via _REGISTRY itself: subsequent calls
    return whatever is currently in the registry. There is no automatic
    invalidation; callers that have hot-reloaded code can clear the
    registry by calling _REGISTRY.clear() before re-importing."""

def build_generator(entry: GeneratorEntry,
                    overrides: dict | None = None,
                    core=None) -> dict:
    """Validate overrides against entry.parameters (type-check, fill
    defaults), call entry.func(core, **kwargs), return the doc."""
```

### Discovery integration: `composite_discovery.py`

Add a `discover_all(extra_search_paths=None, extra_packages=None)`
function that returns a single merged dict:

```python
{
  "spatio_flux.composites.metabolism.ecoli_core_dfba": {
    "kind": "generator", "name": "ecoli_core_dfba", "description": "...",
    "parameters": {...}, "module": "spatio_flux.composites.metabolism",
  },
  "pbg_some_pkg.composites.baseline": {
    "kind": "spec", "name": "baseline", "description": "...",
    "parameters": {...}, "path": "/path/to/baseline.composite.yaml",
  },
  ...
}
```

The existing `discover_composites` keeps working unchanged for callers that
want spec-only discovery (e.g. CI safety scans that must not import).

### Dashboard endpoint

`pbg_superpowers/_server/` `/api/composites` returns `discover_all()`
output with the `kind` field passed through. Frontend renders a subtle
`[generator]` badge so users see at-a-glance which composites require
importing the host package to run.

The per-composite Run action branches on `kind`:

- `kind: spec` → `build_composite_from_spec(spec, overrides)`
- `kind: generator` → `build_generator(entry, overrides, core=allocate_core())`
  → wrap doc in `Composite({'state': doc, ...})` → `run(...)`

Same parameter-form code applies to both because the `parameters` schema
is identical between the two conventions.

### Convention doc

New file `docs/conventions/composite_generators.md` paralleling
`docs/conventions/composites.md`. Mirrors the existing one's structure
(what / format / parameter substitution / loading / discovery / when to
use which / see also).

## spatio-flux — first consumer

### Layout

```
spatio_flux/composites/
├── __init__.py        # imports submodules so @composite_generator runs
├── metabolism.py      # 6 generators
├── spatial.py         # 3 generators
├── particles.py       # 4 generators
├── comets.py          # 4 generators
├── reference.py       # 2 generators
├── _serialize.py      # normalize_doc() for snapshot comparison
└── _snapshots/        # one *.json per generator (regression baselines)
    ├── ecoli_core_dfba.json
    └── ... (19 total)
```

Generators import building-block helpers from `spatio_flux/processes/`
(`get_dfba_process_from_registry`, `get_fields`, `get_particles_state`,
…). No new logic in helpers — composites/ is the registry surface,
processes/ stays as the building blocks.

### Generator shape

Each function follows this pattern:

```python
@composite_generator(
    name="ecoli_core_dfba",
    description="Single-cell metabolism baseline: dynamic FBA for E. coli "
                "core with external glucose/acetate and biomass over time.",
    parameters={
        "model_id": {"type": "string", "default": "ecoli core"},
        "glucose":  {"type": "float",  "default": 10.0},
        "acetate":  {"type": "float",  "default": 0.0},
    },
)
def ecoli_core_dfba(core=None, *, model_id="ecoli core",
                    glucose=10.0, acetate=0.0):
    dfba_process = get_dfba_process_from_registry(
        model_id=model_id, biomass_id="biomass", path=["fields"])
    fields = {"glucose": glucose, "acetate": acetate, "biomass": 0.1}
    for substrate in dfba_process["inputs"]["substrates"]:
        fields.setdefault(substrate, 10.0)
    return {f"{model_id} dFBA": dfba_process, "fields": fields}
```

`pyproject.toml` gains `pbg-superpowers>=0.4.16` as a runtime dependency
(the version that ships `composite_generator`).

### test_suite.py migration

`SIMULATIONS` keeps its per-test runtime metadata (`time`, `plot_func`,
`plot_config`) but the `doc_func`/`config` slots become `generator`/`overrides`:

```python
from spatio_flux.composites import REGISTRY
from pbg_superpowers.composite_generator import build_generator

SIMULATIONS = {
    'ecoli_core_dfba': {
        'generator':  'ecoli_core_dfba',
        'plot_func':  plot_dfba_single,
        'time':       60,
        'overrides':  {'glucose': 10.0, 'acetate': 0.0},
        'plot_config': {'filename': 'ecoli_core_dfba'},
    },
    ...
}
```

`description` moves into the decorator (single source of truth, visible to
the dashboard).

Old `get_*_doc` functions in test_suite.py are deleted one-at-a-time as
each generator passes its snapshot test. Migration order: simplest
composites first (metabolism), spatial/particles second, hybrid composites
last.

## Validation harness

### Serializer: `_serialize.py`

A shared `normalize_doc(doc) -> dict` walks the doc and produces a
deterministic JSON-encodable shape:

- `numpy.ndarray` → `{"__numpy__": true, "dtype": "float64", "shape": [10,20],
   "values": [[...]]}` with values rounded to 12 sig figs (round-trip
   stability across platforms)
- Any non-JSON-encodable custom object → `{"__repr__": "<ClassName>",
   "value": "<repr-string>"}` (catch-all for future use)
- Dicts / lists / scalars recurse unchanged

Both the capture tool and the pytest test go through this same function so
the comparison is symmetric.

### Capture tool: `tools/capture_baseline_doc.py`

```
$ python tools/capture_baseline_doc.py ecoli_core_dfba          # one-shot
$ python tools/capture_baseline_doc.py ecoli_core_dfba --update # regenerate
```

Implementation:
1. Imports the **old** doc_func from `test_suite.py`.
2. Calls it with the current `SIMULATIONS['<name>']['config']`.
3. Runs the result through `normalize_doc`.
4. Writes to `spatio_flux/composites/_snapshots/<name>.json`.

Once the old doc_func is deleted, `--update` falls back to calling the new
generator with default overrides — letting us intentionally bump the
snapshot after a behavior change.

### Pytest: `tests/test_composite_generators.py`

```python
@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_generator_matches_snapshot(name):
    snapshot_path = SNAPSHOTS / f"{name}.json"
    if not snapshot_path.exists():
        pytest.skip(f"no baseline for {name} yet")
    baseline = json.loads(snapshot_path.read_text())
    core = allocate_core()
    doc = build_generator(REGISTRY[name], core=core)
    assert normalize_doc(doc) == baseline
```

Runs in CI on every spatio-flux PR. Catches structural drift between the
generator's output and its recorded baseline.

### Migration workflow per composite

1. Add `@composite_generator(...)` function in
   `spatio_flux/composites/<group>.py`. **Critical invariant**: the
   generator's default parameter values must reproduce the doc that the
   old `doc_func` produced when called with the current
   `SIMULATIONS['<name>']['config']`. The pytest in step 3 enforces this,
   but it's worth stating explicitly because the kwarg shape can differ
   from the old `config` dict (e.g. old `config={'initial_fields': {...}}`
   becomes new `glucose=10.0, acetate=0.0`) — the only thing the snapshot
   test cares about is that the *output* matches.
2. Run `python tools/capture_baseline_doc.py <name>` (against the still-
   present old `doc_func`) → writes `_snapshots/<name>.json`.
3. Run `pytest -k <name>` — must pass before continuing. If it fails,
   the generator's defaults don't match the old config; adjust the
   generator (not the snapshot).
4. Switch `SIMULATIONS['<name>']` to use the new generator slot.
5. Re-run the full `python spatio_flux/experiments/test_suite.py` — confirm
   runtime behavior unchanged.
6. Delete the old `get_*_doc` from `test_suite.py`.
7. Commit. Repeat for the next composite.

## Tradeoffs accepted

- **Import-on-discovery cost.** First dashboard scan that includes
  generators imports every installed `pbg-*` package. For spatio-flux this
  pulls in `cobra`, `pymunk`, `highspy`. The dashboard caches the registry
  per server lifetime so this is once per session. If startup latency
  becomes annoying later, add a `--no-import-generators` opt-out flag.
- **Static-spec discovery stays import-free.** The "discovery never
  imports the spec's processes" property is preserved for the
  spec convention. Only the *new* generator convention requires imports.
- **Two conventions to learn.** `*.composite.{yaml,json}` and
  `@composite_generator` both produce composites. The convention doc spells
  out when to reach for each (rule of thumb: static spec unless you need
  computation or introspection).

## Scope explicitly out

- Static specs for spatio-flux's deterministic composites — even though
  the simplest 3–4 could be static JSON, going all-generator keeps the
  migration uniform. Static specs in spatio-flux can come later if needed.
- Process-bigraph upstreaming — the convention stays in pbg-superpowers
  until battle-tested. Same posture as the static-spec convention.
- Run-result (numerical) snapshots — doc snapshots only; if numerical
  drift becomes a concern, add a slower integration job later.
- Auto-generating `parameters` from function signatures — the decorator
  takes them explicitly. Tools can lint that the kwargs match the
  declarations later if useful.

## Success criteria

1. `pbg_superpowers.composite_generator` module exists with decorator,
   registry, discovery, and builder.
2. `pbg_superpowers.composite_discovery.discover_all` returns both kinds.
3. Dashboard `/api/composites` returns both kinds tagged with `kind`.
4. All 19 spatio-flux composites are migrated to `spatio_flux/composites/`.
5. `tests/test_composite_generators.py` passes for all 19 (no skipped
   baselines).
6. `python spatio_flux/experiments/test_suite.py` produces the same
   `out/report.html` results as before the migration (the existing test
   suite is itself the behavioral check).
7. Documentation: `docs/conventions/composite_generators.md` added,
   `docs/conventions/composites.md` cross-linked.
