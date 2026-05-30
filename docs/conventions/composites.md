# Composite Spec Convention

## What is a composite spec?

A composite spec is a **declarative, data-first** description of a process-bigraph
`Composite`. It lives in a `*.composite.yaml` or `*.composite.json` file inside an
installed package. It declares the composite's state document and optional
configurable parameters.

Composites are DATA (state documents), while processes are CODE (subclasses of
`Edge`/`Process`). Keeping composites as plain files means they can be:

- **Inspected** without running Python
- **Diffed** in git like any structured text
- **Discovered** by glob without importing any package-specific code
- **Versioned** independently of the processes they reference

## Format

```yaml
# REQUIRED:
name: my-composite          # unique within the spec file (used for display and IDs)
state:                      # the composite state dict (passed to Composite({'state': ...}))
  process_a:
    _type: process
    address: "local:MyProcess"
    config:
      rate: "${rate}"       # parameter substitution (full placeholder — preserves type)
    inputs:
      level: ["stores", "level"]
    outputs:
      level: ["stores", "level"]
    interval: 1.0
  stores:
    level: "${initial_level}"

# OPTIONAL:
description: "Human-readable description of what this composite models."
requires:
  processes: [MyProcess, RAMEmitter]   # must be in core.link_registry at build time
  types: []                            # custom type names in core.registry
parameters:
  rate:
    type: float       # one of: float, int, string, str, bool
    default: 1.0
    description: "Multiplicative factor applied each step"
  initial_level:
    type: float
    default: 0.0
```

### Required fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Non-empty identifier for the composite |
| `state` | dict | The composite state document passed to `Composite({'state': ...})` |

### Optional fields

| Field | Type | Description |
|---|---|---|
| `description` | string | Human-readable summary |
| `tags` | list[str] | Semantic category labels for dashboard filtering (see taxonomy below) |
| `requires.processes` | list[str] | Process class names that must be in `core.link_registry` |
| `requires.types` | list[str] | Custom type names that must be in `core.registry` |
| `parameters` | dict | Named parameters with `type`, `default`, and optional `description` |

### Tags

The optional `tags:` field is a flat list of lowercase strings used by the dashboard's
card-browse toolbar to filter and group composites. Tags are free-form, but the
following values form the recommended taxonomy so chips cluster meaningfully across packages.

Recommended values: `agent-based`, `binding-kinetics`, `cells`, `cellular-potts`,
`chromosome`, `coarse-grained`, `cytoskeleton`, `demo`, `dna`, `fba`, `geometry`,
`kinetics`, `lammps`, `mass-transfer`, `mechanics`, `membranes`, `mesoscale`,
`molecular-dynamics`, `multi-cell`, `ode`, `packing`, `particles`, `pde`,
`polymers`, `reaction-diffusion`, `rule-based`, `sbml`, `systems-biology`,
`tissue`, `vcell`, `visualization`, `whole-cell`.

Example:

```yaml
name: dnaa-binding-baseline
description: "Minimal DnaA-oriC binding kinetics using v2ecoli's DnaABinder."
tags: [chromosome, binding-kinetics, dna]
requires:
  processes: [DnaABinder, RAMEmitter]
```

## Parameter substitution

Any leaf string value in `state` may contain `${name}` placeholders that reference
declared parameters. There are two substitution modes:

### Full placeholder — type-preserving

If the **entire** leaf value is `"${name}"`, the placeholder is replaced with the
parameter's typed value:

```yaml
parameters:
  rate:
    type: float
    default: 1.0
state:
  process_a:
    config:
      rate: "${rate}"   # replaced with Python float 1.0, not the string "1.0"
```

This matters because process-bigraph validates config types. Always use full
placeholders when referencing numeric or boolean parameters inside `config:`.

### Inline placeholder — string interpolation

When `${name}` is embedded within a larger string, the result is always a string:

```yaml
parameters:
  strain:
    type: string
    default: wt
state:
  label: "experiment-${strain}-run1"   # becomes "experiment-wt-run1"
```

### Rules

- Parameter names must be valid Python identifiers: `[a-zA-Z_][a-zA-Z0-9_]*`
- Malformed braces or invalid names are left as-is (no error at parse time)
- Missing parameters (referenced in state but not declared) raise `KeyError` at
  substitution time
- Missing defaults with no override raise `KeyError` at substitution time

## Loading and building

```python
from pathlib import Path
from pbg_superpowers.composite_spec import load_spec, build_composite_from_spec

spec = load_spec(Path("my_package/composites/baseline.composite.yaml"))

# Build with defaults
composite = build_composite_from_spec(spec)

# Build with parameter overrides
composite = build_composite_from_spec(spec, overrides={"rate": 0.5})

# Bring your own core (e.g. after registering custom types)
from process_bigraph import allocate_core
core = allocate_core()
composite = build_composite_from_spec(spec, overrides={"rate": 0.5}, core=core)

# Run and gather results
composite.run(10)
from process_bigraph import gather_emitter_results
results = gather_emitter_results(composite)
```

`build_composite_from_spec` will raise `RuntimeError` if any process listed in
`requires.processes` is absent from the registry, giving a clear error before
the Composite tries to wire up any ports.

## Discovery

`discover_composites` walks all installed distributions that depend on
`bigraph-schema` and globs for `*.composite.{yaml,yml,json}` under each
importable package directory:

```python
from pbg_superpowers.composite_discovery import discover_composites

# Discover from all installed packages
specs = discover_composites()
# {"pbg_chromosome_rep1.composites.baseline": <spec dict>, ...}

# Also search workspace-local directories
from pathlib import Path
specs = discover_composites(extra_search_paths=[Path("composites/")])
```

Spec IDs follow the pattern `<pkg_name>.<subpath>.<file_stem>` — e.g.
`pbg_chromosome_rep1.composites.baseline` for the file
`pbg_chromosome_rep1/composites/baseline.composite.yaml`.

Discovery **never imports the spec's processes** — it only reads files. This
keeps it safe to call at startup or in CI without needing every simulator
installed.

## Why this lives in pbg-superpowers (for now)

The convention is intentionally framework-level, but it belongs in
`pbg-superpowers` until it stabilizes. Once battle-tested across several pbg-*
packages, the plan is to propose it upstream to `process-bigraph` as an optional
discovery layer alongside the existing class-based registration.

## When to use a spec file vs a Python function

| Situation | Use |
|---|---|
| The composite is a canonical scenario users will reuse or share | `*.composite.yaml` spec |
| The composite structure is generated procedurally | Python function |
| You want it discoverable across packages without importing | spec file |
| You need complex logic (conditionals, loops) to wire ports | Python function |
| You want to diff composite changes in PRs | spec file |
| The composite is a test helper or one-off | Python function |

## JSON Schema

A machine-readable schema for the format lives at:
`pbg_superpowers/schemas/composite-spec.schema.json`

This can be used for editor autocompletion (add it as a YAML/JSON schema
association in VS Code or PyCharm).

## See also

- [Composite Generator Convention](composite_generators.md) — the
  function-based sibling for composites that need to compute initial state
  or introspect processes at build time.
- [Process discovery convention](discovery.md) — how processes (code) are discovered
- `/pbg-expert --lightweight <name> <tools…>` skill — writes in-workspace composite
  generator Python files (`@composite_generator`-decorated functions).
