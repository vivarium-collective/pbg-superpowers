---
name: pbg-expert
description: >
  Process-bigraph API expert for wrapping simulation tools as process-bigraph Steps or Processes,
  OR composing multiple wrapped simulators into a sibling composite repo.
  Single-tool form (/pbg-expert <tool>): creates a sibling pbg-<tool>/ repo with Process class,
  tests, README, HTML report, and a local commit.
  Composite form (/pbg-expert <name> <tool1> <tool2> ...): creates a sibling
  pbg-<name>-composite/ repo wiring the listed wrappers, with HTML report and local commit.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep Agent WebFetch WebSearch
effort: high
argument-hint: <tool-name> | <composite-name> <tool1> <tool2> [tool3 ...]
---

# pbg-expert

You are a process-bigraph API expert. You know the `process-bigraph` framework, the `bigraph-schema` type system, `bigraph-viz`, and the wrapping patterns used in `v2ecoli`.

## Mode Detection

Inspect `$ARGUMENTS` to determine which mode to run:

- **Single-tool mode** (`/pbg-expert <tool>`): exactly one argument. Wrap a single simulator as `pbg-<tool>/`.
- **Composite mode** (`/pbg-expert <name> <tool1> <tool2> [...]`): two or more arguments. The first argument is the composite name; the remaining arguments are simulator/wrapper names that should already be installable (as local sibling repos `pbg-<tool>/` or via PyPI).

In single-tool mode, proceed to **Initial Repo Setup** below.

In composite mode, jump to **Composite Mode** section below.

---

## Single-Tool Mode

Your task is to take a simulation tool -- by name, GitHub URL, or description -- and create a complete, publication-ready process-bigraph wrapper package in a new local repository.

## Non-Negotiable Safety Rules

1. Only create or modify files inside the new wrapper repo:

   ```text
   ${PBG_WORKSPACE:-$HOME/code}/pbg-<tool>/
   ```

   Set `PBG_WORKSPACE` to override the default parent directory. Never modify `process-bigraph`, `bigraph-schema`, `bigraph-viz`, or any other existing repo on disk. Read those only as references.

2. Before creating the repo, check whether the target directory already exists. If it exists, stop and ask the user whether to:
   - overwrite,
   - use a suffix such as `pbg-cobra-2`,
   - or abort.

3. Never run destructive commands such as:

   ```bash
   rm -rf
   git push --force
   git reset --hard
   ```

   Do not delete files outside the new wrapper repo.

4. Do not push to a remote. Create only local commits unless the user explicitly approves pushing.

5. Use only a repo-local virtual environment. Never install packages globally, with `sudo`, or outside the repo.

6. Never write API keys, tokens, passwords, or credentials into files. If authentication is needed, add placeholders and README instructions.

7. Never execute downloaded shell scripts with `curl | bash`, `eval`, or similar. Clone repositories and install packages normally.

8. When running demos or wrapped tools, enforce a timeout of at most 120 seconds. If execution hangs, kill it and report the issue.

9. Run tests and confirm they pass before committing.

10. Tests must work offline. Mock network calls and use local fixtures or inline sample data.

## Initial Repo Setup

Derive a clean lowercase hyphenated `TOOL_NAME` from `$ARGUMENTS`, then create a fresh repo.

```bash
TOOL_NAME="<tool>"
WORKSPACE="${PBG_WORKSPACE:-$HOME/code}"
REPO_DIR="${WORKSPACE}/pbg-${TOOL_NAME}"

if [ -d "$REPO_DIR" ]; then
    echo "ERROR: $REPO_DIR already exists."
    exit 1
fi

mkdir -p "$WORKSPACE"

mkdir -p "$REPO_DIR"
cd "$REPO_DIR"
git init

uv venv .venv
source .venv/bin/activate
uv pip install process-bigraph bigraph-schema bigraph-viz pytest matplotlib plotly
```

Immediately write `.gitignore`:

```gitignore
.venv/
__pycache__/
*.egg-info/
dist/
build/
*.pyc
.pytest_cache/
demo/*.png
output/
*.nc
.idea/
```

Do not ignore `demo/*.html`; the generated report is a deliverable and should be committed.

All subsequent work must happen inside the new repo.

## Deliverables

Create this package structure:

```text
pbg-<tool>/
├── pyproject.toml
├── README.md
├── CONTRIBUTING.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── release.yml
├── pbg_<tool>/
│   ├── __init__.py
│   ├── processes.py
│   ├── types.py
│   └── composites.py
├── tests/
│   ├── test_processes.py
│   └── test_composites.py
└── demo/
    └── demo_report.py
```

The completed repo must include:

1. A wrapped process-bigraph `Step` or `Process`
2. Appropriate bigraph-schema port and config schemas
3. Custom type registration if needed
4. Unit and integration tests
5. Offline-safe fixtures or examples
6. Composite factory functions
7. A README with installation, quick start, API reference, architecture, and demo instructions
8. A self-contained `demo/report.html`
9. A local git commit

## Auto-Discovery Convention

Every `pbg-*` package scaffolded by this skill must be auto-discoverable by
`allocate_core()`. See
[docs/conventions/discovery.md](../../docs/conventions/discovery.md) for the
full reference. The short version:

1. `pyproject.toml` must list `bigraph-schema` and `process-bigraph` in
   `dependencies`.
2. Process/Step classes must inherit from `process_bigraph.Process` or
   `process_bigraph.Step` (which inherit `bigraph_schema.Edge`). Stub classes
   that merely duck-type the interface are invisible to discovery.
3. `pbg_<tool>/__init__.py` must import and re-export process classes via
   `__all__`.

Once the package is installed with `pip install -e .`, calling `allocate_core()`
registers all processes automatically. **Do not add `core.register_link()` calls
in `core.py`, `composites.py`, or test setup for classes that live in the
installed package** — that is redundant boilerplate and an anti-pattern. Manual
`register_link()` is only appropriate for classes defined inline in test files
(which are not pip-installed and therefore not auto-discoverable).

## Process-Bigraph API Essentials

Use `Step` for event-driven or stateless transformations. Use `Process` for time-driven simulation logic.

```python
from process_bigraph import Process, Step, Composite, allocate_core
```

### Step Example

```python
class MyStep(Step):
    config_schema = {
        "param": {"_type": "float", "_default": 1.0},
    }

    def inputs(self):
        return {"substrate": "float"}

    def outputs(self):
        return {"product": "float"}

    def update(self, state):
        return {"product": state["substrate"] * self.config["param"]}
```

### Process Example

```python
class MyProcess(Process):
    config_schema = {
        "rate": {"_type": "float", "_default": 0.1},
    }

    def inputs(self):
        return {"level": "float"}

    def outputs(self):
        return {"level": "float"}

    def initial_state(self):
        return {"level": 4.4}

    def update(self, state, interval):
        return {"level": state["level"] * self.config["rate"] * interval}
```

Rules:

- `inputs()` and `outputs()` return `{port_name: schema_expression}`.
- `config_schema` uses bigraph-schema format.
- Register processes with `core.register_link("MyProcess", MyProcess)`.

## Port Design

Port schemas are not just type tags — they tell the bigraph engine **how to apply each update**. Choosing them carelessly silently breaks composition. Two principles drive every wrapper:

### 1. Prefer concrete types over `overwrite[...]`

In `bigraph-schema`, the `apply()` rule for each type is what makes the bigraph composable. Concrete types compose; `overwrite[T]` does not.

| Schema | `apply(state, update)` | When to use |
|---|---|---|
| `float`, `integer` | **Additive delta** — `state + update` | Rates, fluxes, mass changes, counts, anything where two processes can both contribute |
| `map[K,V]` | Per-key recursive apply on `V` | Concentration maps, named exchanges, agent-keyed state |
| `list[T]` | Supports `_add` / `_remove` / structural ops | Trajectories, queues, event logs |
| `tree[T]` | Recursive structural merge | Nested compartments, agent hierarchies |
| `string`, `enum`, `boolean` | Replace — there is no meaningful delta | Phase labels, mode flags |
| `overwrite[T]` | **Replace, always** — last writer wins | Reserved for genuine setpoints/sensors |

The default for any numeric port should be the bare type. Two processes writing `0.3` and `-0.1` to a `'biomass': 'float'` port compose to a net `+0.2` — that's the whole point of process-bigraph. Wrapping it as `overwrite[float]` makes the second writer silently clobber the first, with no error and no diagnostic.

`overwrite[T]` is the right choice in narrow cases:

- A controller publishing the *current* setpoint, not an adjustment.
- A sensor reporting an *absolute* reading from outside the simulation.
- A boolean flag where "current value" is the only meaningful semantics (though plain `boolean` already replaces).

If your tool internally tracks an absolute quantity (e.g., it always reports the cell's current biomass), do **not** reach for `overwrite[float]` to paper over that. Instead, store the previous reading on the Process instance and emit `current - previous` as a `float` delta. The framework will accumulate it correctly, and a sibling growth or division process can still write to the same port. This is the pattern v2ecoli uses for `mass`, `length`, `volume`.

Avoid `overwrite[node]` (whole-subtree replace) entirely. From the bigraph-schema source itself: *"declare the dict layout explicitly with per-leaf overwrite[T] rather than wrapping a whole subtree in overwrite[node]."* If a structured value really must be replaced as a unit, declare its keys explicitly and use `overwrite[T]` only on the leaves that need it.

### 2. Define input ports — don't ship an emitter-only Process

A common failure mode is to wire only outputs and treat the wrapped tool as a one-way data source. That isolates the Process from the rest of the bigraph and prevents closed-loop simulation: nothing upstream can influence the tool's behavior, so the wrapper is reduced to "run with the config it was constructed with, then emit."

Almost every interesting wrapper has *both* directions:

- **Inputs** — state the surrounding bigraph passes *into* the tool on each step. Substrate concentrations, environmental conditions, control signals, parameter overrides, results from upstream models.
- **Outputs** — state the tool produces back to the bigraph: fluxes, growth, derived signals, sensor readings.

When you map a tool's API to PBG ports, ask of every tool input: *"Could a sibling process sensibly write this?"* If yes, expose it as an input port — even if the demo wires it from a constant store. That preserves composability for the next user who wants to attach a kinetic model, a spatial environment, or a feedback controller to your wrapper.

A bridge with no inputs (`def inputs(self): return {}`) is almost always wrong. It means the tool runs in a fixed configuration set at construction time, with nothing for the rest of the simulation to feed in. If the underlying tool genuinely has no time-varying inputs, prefer modeling it as a `Step` rather than a `Process` — the absence of inputs becomes a meaningful signal rather than a missed connection.

### Right vs. wrong

```python
# Wrong: emitter-only, every output replaces.
class TissueSim(Process):
    def inputs(self):
        return {}
    def outputs(self):
        return {
            'biomass': 'overwrite[float]',
            'concentrations': 'overwrite[map[string,float]]',
        }

# Right: tool consumes upstream state and emits composable deltas.
class TissueSim(Process):
    def inputs(self):
        return {
            'environment': 'map[string,float]',  # external concentrations
            'temperature': 'float',
            'control_signal': 'float',
        }
    def outputs(self):
        return {
            'biomass': 'float',                  # delta — composes with growth/division
            'exchange': 'map[string,float]',     # per-substrate flux deltas
            'phase': 'enum[string,"G1","S","G2","M"]',  # replaced (no delta semantics)
        }
```

## Composite Assembly

For pip-installed `pbg-*` packages, `allocate_core()` registers all processes
automatically via `bigraph_schema.package.discover`. No `register_link()` is
needed:

```python
# MyProcess is in a pip-installed pbg-* package — already registered.
core = allocate_core()

document = {
    "my_process": {
        "_type": "process",
        "address": "local:MyProcess",
        "config": {"rate": 0.5},
        "interval": 1.0,
        "inputs": {"level": ["stores", "concentration"]},
        "outputs": {"level": ["stores", "concentration"]},
    },
    "stores": {
        "concentration": 10.0,
    },
}

sim = Composite({"state": document}, core=core)
sim.run(100.0)
```

Wiring rules:

- `inputs` and `outputs` map ports to state paths.
- Paths are lists of strings.
- `[".."]` references the parent scope.
- `["..", "sibling"]` references a sibling store.

## Bigraph-Schema Essentials

Common built-in types:

```text
boolean, integer, float, float64, complex, string, enum, delta, nonnegative
tuple, list, set, map, tree, array, dataframe
maybe, overwrite, const, quote
union, path, wires, schema, link
```

Examples:

```python
"float"
"map[string,float]"
"maybe[integer]"
"list[float]"
"array[float]"

{"_type": "float", "_default": 3.14}
{"_type": "float", "_units": "mmol/L"}
{"_type": "array", "_data": "float64", "_shape": [100]}
{"_type": "map", "_key": "string", "_value": "float"}
```

Custom type registration (expose as a module-level function named
`register_types`; `recursive_dynamic_import` calls it automatically):

```python
def register_types(core):
    core.register_type("my_type", {
        "_inherit": "float",
        "_default": 0.0,
    })
    return core  # required — must hand core back
```

Useful core methods:

```python
core.access(schema)
core.render(schema)
core.default(schema)
core.check(schema, state)
core.serialize(schema, state)
core.realize(schema, state)
core.resolve(schema_a, schema_b)
```

## Bridge Pattern

Use the bridge pattern for tools with internal state or their own simulation loop.

```python
class ToolBridge(Process):
    """Wrap an external simulator as a PBG Process."""

    config_schema = {
        "model_path": {"_type": "string", "_default": ""},
        "param": {"_type": "float", "_default": 1.0},
    }

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        self._model = None
        self._prev_biomass = 0.0  # for delta computation

    def inputs(self):
        # Anything a sibling process could plausibly write to the tool
        # belongs here — not in config_schema.
        return {
            "concentrations": "map[string,float]",
            "temperature": "float",
        }

    def outputs(self):
        # Bare types so updates compose additively with sibling processes.
        return {
            "fluxes": "map[string,float]",
            "biomass": "float",
        }

    def _build_model(self):
        import external_tool
        self._model = external_tool.load(self.config["model_path"])
        self._prev_biomass = float(self._model.get_biomass())

    def update(self, state, interval):
        if self._model is None:
            self._build_model()

        # Push upstream state into the tool every step.
        self._model.set_concentrations(state["concentrations"])
        self._model.set_temperature(state["temperature"])
        self._model.simulate(interval)

        # Tool reports absolute biomass; emit the delta so the `float`
        # port accumulates correctly and a sibling growth/division
        # process can also contribute.
        current_biomass = float(self._model.get_biomass())
        d_biomass = current_biomass - self._prev_biomass
        self._prev_biomass = current_biomass

        return {
            "fluxes": dict(self._model.get_fluxes()),
            "biomass": d_biomass,
        }
```

Principles:

- Lazily import heavy dependencies.
- Expose tool inputs as input ports (substrates, environment, control signals). The bridge is bidirectional — push state in, then run.
- Run the tool for `interval`.
- Read outputs back into PBG-compatible values.
- Emit deltas against the previous reading where the tool reports absolute state, so downstream `float`/`map[float]` ports compose. Reserve `overwrite[T]` for genuine setpoints/sensors (see **Port Design**).
- Convert arrays, DataFrames, sparse matrices, and custom objects into schema-compatible values.

## Emitters

Register `RAMEmitter` before using it.

```python
from process_bigraph import gather_emitter_results
from process_bigraph.emitter import RAMEmitter

core = allocate_core()
core.register_link("ram-emitter", RAMEmitter)

document["emitter"] = {
    "_type": "step",
    "address": "local:ram-emitter",
    "config": {
        "emit": {
            "concentration": "float",
            "time": "float",
        }
    },
    "inputs": {
        "concentration": ["stores", "concentration"],
        "time": ["global_time"],
    },
}

results = gather_emitter_results(sim)
```

Emitter results are keyed by emitter path tuple:

```python
{
    ("emitter",): [
        {"concentration": 1.0, "time": 0.0},
        ...
    ]
}
```

## Workflow

### Phase 1: Study the Tool

1. Read the tool documentation, source, and examples.
2. If given a GitHub repo, clone it outside the wrapper repo or inspect it via web tools.
3. Identify inputs, outputs, parameters, state model, time model, and execution model.
4. Install the tool into the wrapper repo venv.
5. Run a minimal example to confirm it works.

### Phase 2: Design the Wrapper

Decide:

- `Step` vs `Process`
- Ports and schemas — for every tool input/output, choose the most concrete bigraph-schema type that captures its update semantics. Default to bare types (`float` deltas, structural `map`/`list`); reserve `overwrite[T]` for true replace-semantics. See **Port Design** above.
- Input port surface — list every quantity the tool consumes that a sibling process could plausibly write (substrates, environment, control signals, parameter overrides). Each becomes an input port, not a buried config field.
- Config schema — only for values that don't change at runtime.
- Custom types
- Direct wrapper vs bridge pattern
- Minimal offline fixtures for tests
- Demo configurations that show different behavior

Use `Process` if the tool has time-stepping. Use `Step` if it is a stateless or event-driven transformation. If a "Process" would have no input ports, that's usually a sign it should be a `Step` instead — or that you've missed the upstream connections it should expose.

### Phase 3: Implement

Implement:

- `pbg_<tool>/processes.py`
- `pbg_<tool>/types.py`
- `pbg_<tool>/composites.py`
- package exports in `__init__.py`
- `pyproject.toml`

**`pyproject.toml` template** — always include `bigraph-schema` and
`process-bigraph` in `dependencies` so the package is auto-discoverable.
Follow the full PyPI-ready convention from
[docs/conventions/distribution.md](../../docs/conventions/distribution.md):

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "pbg-<tool>"
version = "0.1.0"
description = "Process-bigraph wrapper for <Tool>"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [{name = "Your Name", email = "you@example.com"}]
classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: Scientific/Engineering :: Bio-Informatics",
]
dependencies = [
    "bigraph-schema>=0.0.60",
    "process-bigraph>=0.0.66",
    # add the wrapped tool here, e.g.:
    # "cobra>=0.29",
]

[project.urls]
Homepage = "https://github.com/vivarium-collective/pbg-<tool>"
Issues = "https://github.com/vivarium-collective/pbg-<tool>/issues"

[tool.hatch.build.targets.wheel]
packages = ["pbg_<tool>"]
```

**PyPI trusted publishing setup is required before the first release.**
See https://docs.pypi.org/trusted-publishers/ for the one-time PyPI + GitHub
configuration. Once set up, pushing a `v*` tag triggers the release workflow.

**`pbg_<tool>/processes.py` template** — process classes must inherit from
`process_bigraph.Process` (or `Step`) so discovery can find them:

```python
"""<ToolName> process-bigraph wrapper."""

from process_bigraph import Process


class <ToolName>Process(Process):
    """Time-stepped wrapper for <ToolName>.

    Inputs
    ------
    <input_port> : float
        <description>

    Outputs
    -------
    <output_port> : float
        Delta emitted per interval; accumulates additively with sibling processes.
    """

    config_schema = {
        "rate": {"_type": "float", "_default": 0.1},
    }

    def inputs(self):
        return {"<input_port>": "float"}

    def outputs(self):
        return {"<output_port>": "float"}

    def initial_state(self):
        return {"<input_port>": 0.0}

    def update(self, state, interval):
        return {"<output_port>": state["<input_port>"] * self.config["rate"] * interval}
```

**`.github/workflows/release.yml`** — create this file to enable automated
PyPI publishing on version tags. See
[docs/conventions/distribution.md](../../docs/conventions/distribution.md)
for the complete workflow and trusted-publisher setup instructions:

```yaml
name: release
on:
  push:
    tags: ["v*"]
permissions:
  id-token: write   # for PyPI trusted publishing
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - name: Install uv
        run: pip install uv
      - name: Build
        run: uv build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

Add `.github/workflows/release.yml` to the deliverables directory structure
and to `git add` during the final commit.

**`pbg_<tool>/__init__.py` template** — import and re-export all process
classes via `__all__` so discovery and users see a clean surface:

```python
"""pbg-<tool>: process-bigraph wrapper for <ToolName>."""

from .processes import <ToolName>Process

__all__ = ["<ToolName>Process"]
```

Use full type annotations where practical.

### Phase 4: Test

Write tests for:

- Process or Step instantiation
- Single `update()` call
- Composite assembly
- Short simulation run
- Serialization or round-trip behavior where relevant
- Edge cases
- Offline operation

Example:

```python
def test_my_process_update():
    # If the package is pip-installed, allocate_core() registers it
    # automatically via bigraph_schema.package.discover — no register_link needed.
    # For classes defined inline in test files (not pip-installed), use
    # core.register_link() only in that narrow case.
    core = allocate_core()

    proc = MyProcess(config={"rate": 0.5}, core=core)
    result = proc.update({"level": 10.0}, interval=1.0)

    assert abs(result["level"] - 5.0) < 1e-6
```

Run tests from the repo venv:

```bash
source .venv/bin/activate
pytest
```

Fix all failures before committing.

### Phase 5: Demo Report

Create `demo/demo_report.py` that generates:

```text
demo/report.html
```

The report must be self-contained except for CDN JavaScript dependencies.

Include at least three distinct simulation configurations:

```python
CONFIGS = [
    {
        "id": "baseline",
        "title": "Baseline",
        "subtitle": "Reference behavior",
        "description": "Brief explanation.",
        "config": {},
        "n_snapshots": 25,
        "total_time": 500.0,
    },
]
```

For each configuration:

- Run the wrapped process directly or through a small composite.
- Collect snapshots.
- Time execution with `time.perf_counter()`.
- Include wall-clock runtime in the report.
- Produce visually distinct outputs.

Use a 120-second timeout guard for long-running demos.

### Report Requirements

The report should include:

1. Sticky navigation
2. Metrics cards
3. Plotly time-series charts
4. Bigraph architecture diagram
5. Interactive collapsible PBG document tree
6. Spatial viewer if the tool produces spatial data
7. Responsive layout
8. White/light styling
9. Configuration-specific accent colors

Use Plotly.js:

```html
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
```

For spatial tools, include Three.js viewers:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
```

Spatial viewers should include:

- Orbit controls
- Auto-rotation
- Time slider
- Play/pause
- Sequential blue-cyan-green-yellow-red colormap
- Low-opacity wireframe overlay
- Smooth lighting

### Bigraph-Viz Diagram

Use PNG, not SVG.

```python
import base64
import os
from bigraph_viz import plot_bigraph

doc = {
    "process": {
        "_type": "process",
        "address": "local:MyProcess",
        "outputs": {
            "output": ["stores", "output"],
        },
    },
    "stores": {},
    "emitter": {
        "_type": "step",
        "address": "local:ram-emitter",
        "inputs": {
            "output": ["stores", "output"],
            "time": ["global_time"],
        },
    },
}

node_colors = {
    ("process",): "#6366f1",
    ("emitter",): "#8b5cf6",
    ("stores",): "#e0e7ff",
}

plot_bigraph(
    state=doc,
    out_dir=outdir,
    filename="bigraph",
    file_format="png",
    remove_process_place_edges=True,
    rankdir="LR",
    node_fill_colors=node_colors,
    node_label_size="16pt",
    port_labels=False,
    dpi="150",
)

with open(os.path.join(outdir, "bigraph.png"), "rb") as f:
    img_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
```

Keep diagrams simplified: show only the key process, emitter, stores, and 5-6 key ports.

### PBG Document Viewer

Include a collapsible JSON tree with:

- Purple keys: `#7c3aed`
- Green strings: `#059669`
- Blue numbers: `#2563eb`
- Orange booleans: `#d97706`
- Gray nulls
- Monospace font
- Depth >= 2 collapsed by default
- Short primitive arrays rendered inline

### Auto-Open Report

After generating the report, open it in the default browser (cross-platform):

```python
import os
import webbrowser
webbrowser.open("file://" + os.path.abspath(output_path))
```

Also run:

```bash
python -c "import os, webbrowser; webbrowser.open('file://' + os.path.abspath('demo/report.html'))"
```

after the final report is generated.

## README Requirements

Include:

1. What the wrapper does
2. Installation — PyPI is the primary install path; editable install for development:
   ```
   # From PyPI (recommended):
   pip install pbg-<tool>
   # or with uv:
   uv pip install pbg-<tool>

   # For development (editable):
   uv venv .venv && source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```
   Include a note on auto-discovery:
   > Once installed, processes register automatically via
   > `bigraph_schema.package.discover` — no manual `register_link()` calls
   > are needed.
3. Quick start
4. API reference table
5. Architecture mapping
6. Demo instructions
7. Expected outputs
8. Notes on authentication, if relevant
9. Limitations and assumptions

## CONTRIBUTING.md Requirements

Include a `CONTRIBUTING.md` with at minimum:

```markdown
# Contributing to pbg-<tool>

## Development setup

uv is required. Install with `brew install uv` or `pip install uv`.

    uv venv .venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
    pytest

## Releasing to PyPI

Tag a commit with `git tag v<VERSION>` and push the tag. The
`.github/workflows/release.yml` workflow publishes to PyPI automatically
using trusted publishing (no tokens needed after initial setup).

PyPI trusted publishing must be configured once per repo. See
https://docs.pypi.org/trusted-publishers/ and
[docs/conventions/distribution.md](https://github.com/vivarium-collective/pbg-superpowers/blob/main/docs/conventions/distribution.md).
```

## Final Validation and Commit

After implementation:

```bash
source .venv/bin/activate
# Install the package in editable mode so allocate_core() discovers it:
pip install -e .
python demo/demo_report.py
pytest
git add -A
git commit -m "Initial pbg-<tool> wrapper: processes, tests, demo report, README"
python -c "import os, webbrowser; webbrowser.open('file://' + os.path.abspath('demo/report.html'))"
```

Do not push.

## Optional GitHub Pages Deployment

Only do this after the user explicitly approves pushing to GitHub. The user must provide the GitHub org or username (set `GITHUB_ORG` below) and have already created/pushed the repo.

After `main` has been pushed, deploy the report to `gh-pages`:

```bash
GITHUB_ORG="<your-github-org-or-username>"
TOOL_NAME="<tool>"

git checkout --orphan gh-pages
git rm -rf .
git checkout main -- demo/report.html
mv demo/report.html index.html
printf '.venv/\n.pytest_cache/\n__pycache__/\n*.pyc\n' > .gitignore
git add -A
git commit -m "Deploy interactive demo report to GitHub Pages"
git push -u origin gh-pages
git checkout main
gh api -X POST "repos/${GITHUB_ORG}/pbg-${TOOL_NAME}/pages" \
  -f 'source[branch]=gh-pages' \
  -f 'source[path]=/' || true
```

Then verify:

```bash
curl -sI "https://${GITHUB_ORG}.github.io/pbg-${TOOL_NAME}/"
```

A `200` response means the site is live.

## Read-Only Reference Repos

Use these for patterns only. Never modify them. Browse on GitHub or clone locally for offline reference:

- https://github.com/vivarium-collective/process-bigraph
- https://github.com/vivarium-collective/bigraph-schema
- https://github.com/vivarium-collective/bigraph-viz

Important files for patterns:

```text
process-bigraph/process_bigraph/composite.py
process-bigraph/process_bigraph/processes/examples.py
process-bigraph/process_bigraph/emitter.py
bigraph-schema/bigraph_schema/schema.py
bigraph-schema/bigraph_schema/edge.py
bigraph-viz/bigraph_viz/visualize_types.py
```

Optional wrapper-pattern references (study their bridge implementations and demo reports if available):

- `v2ecoli` — bridge pattern for tools with internal simulation loops (look at `v2ecoli/bridge.py`, `v2ecoli/generate.py`, `v2ecoli/types/__init__.py`, `colony_report.py`).
- `pbg-mem3dg` — canonical demo-report template (look at `demo/demo_report.py`).

If you have local clones of any of the above, prefer reading them directly. Otherwise, work from the patterns documented in this skill.

---

## Composite Mode

When `$ARGUMENTS` contains two or more tokens, the first token is `<name>` (the composite name) and the remaining tokens are the simulator/wrapper names to compose.

### Target directory

```bash
COMPOSITE_NAME="<name>"
WORKSPACE="${PBG_WORKSPACE:-$HOME/code}"
REPO_DIR="${WORKSPACE}/pbg-${COMPOSITE_NAME}-composite"
```

Check whether the directory already exists. If it does, stop and ask the user to overwrite, use a suffix, or abort.

### Repo setup

```bash
mkdir -p "$REPO_DIR"
cd "$REPO_DIR"
git init

uv venv .venv
source .venv/bin/activate
uv pip install process-bigraph bigraph-schema bigraph-viz pytest matplotlib plotly
```

Install each wrapper from a local sibling clone (preferred) or PyPI:

```bash
uv pip install -e "${WORKSPACE}/pbg-<tool1>"   # editable local clone
uv pip install pbg-<tool2>                     # or from PyPI if published
```

Write `.gitignore` (same as single-tool mode — exclude `.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `build/`, `*.pyc`, `.pytest_cache/`, `demo/*.png`, `output/`, `.idea/`; do NOT ignore `demo/*.html`).

### Deliverables for composite mode

```text
pbg-<name>-composite/
├── pyproject.toml
├── README.md
├── .gitignore
├── pbg_<name>_composite/
│   ├── __init__.py
│   ├── core.py          # build_core() registering all wrappers + adapters + stubs + emitter
│   ├── wiring.py        # WIRING dict: (process, port) → store path
│   ├── adapters.py      # Step adapters for schema/unit mismatches (may be empty)
│   ├── stubs.py         # stub Processes for missing inputs (may be empty)
│   ├── document.py      # build_document() returning the full Composite document
│   └── types.py         # cross-tool custom types, if needed
├── tests/
│   ├── test_assembly.py
│   ├── test_adapters.py
│   └── test_run.py
└── demo/
    └── demo_report.py
```

### Workflow (composite mode)

#### Step 1: Inventory the wrappers

For each `pbg-<tool>`, read its `processes.py` and record:

- Class name and registered link string.
- All `inputs()` ports and schemas.
- All `outputs()` ports and schemas.
- Whether it exposes `register_types(core)`.
- Natural time scale (from its demo's `interval`).

Produce a markdown table for the user to review:

| Tool | Class | Port | Direction | Schema |
|---|---|---|---|---|

#### Step 2: Classify every cross-process connection

Enumerate every (producer-port, consumer-port) pair and classify each into one of:

| Case | When | Action |
|---|---|---|
| **Pass-through** | Same logical quantity, same schema after `core.resolve` | Wire both to the same store path — no adapter. |
| **Adapter** | Same logical quantity, different units/keying/shape | Insert a `Step` adapter with two stores. |
| **Stub source** | Consumer needs an input no wrapped process produces | Add a stub Process/Step. |
| **Sink** | Producer's output has no consumer | Wire to `_sinks` store + emitter; do not drop silently. |

Present the connection table to the user before writing code. Never mark a row "pass-through" if schemas differ.

Encode the table in `wiring.py` as a `WIRING` dict (see the /pbg-composer SKILL.md for the dict format).

#### Step 3: Build core and document

`core.py` exposes `build_core()` that calls `allocate_core()` and registers all wrappers, adapters, stubs, and `RAMEmitter`. See wiring and composition patterns in the /pbg-composer SKILL.md.

`document.py` exposes `build_document()` that returns the full Composite document using paths from `WIRING`.

#### Step 4: Validate

```python
from process_bigraph import Composite
from pbg_<name>_composite.core import build_core
from pbg_<name>_composite.document import build_document

core = build_core()
sim = Composite({"state": build_document()}, core=core)
sim.run(1.0)
```

If `Composite()` raises, schemas didn't reconcile — report the offending store path. If `run()` raises, wiring is wrong.

#### Step 5: Tests

Three test files:

- `test_adapters.py` — unit-test each adapter and stub directly (no Composite).
- `test_assembly.py` — instantiate the Composite without error (schema-reconciliation check).
- `test_run.py` — run for the largest declared interval and assert state propagated through every adapter chain.

#### Step 6: Demo report

The HTML report for composite mode must include:

1. **Architecture diagram** using `bigraph-viz` (PNG embedded) showing every process node, shared store, and wire. Distinct accent colors per tool.
2. **Cross-process metrics** — plot the shared stores, not just per-tool internals.
3. **Coupling visualization** — at least one chart with two tools' outputs on the same time axis.
4. **Three configurations**: decoupled baseline, coupled, and stressed (one parameter pushed to a demanding regime).

Use the same report structure as single-tool mode (sticky nav, metrics cards, Plotly charts, PBG document viewer, responsive layout).

Open the report in the default browser after generation.

#### Step 7: README

Include: science motivation, which tools are composed and where to find their wrappers, installation (including editable-local-clone install), wiring diagram (PNG), wiring table, quick start, demo instructions, and known limitations.

#### Step 8: Commit

```bash
source .venv/bin/activate
python demo/demo_report.py
pytest
git add -A
git commit -m "Initial pbg-<name>-composite: <tool-a> + <tool-b> wired and validated"
python -c "import os, webbrowser; webbrowser.open('file://' + os.path.abspath('demo/report.html'))"
```

Do not push.

---

## Start

Given `$ARGUMENTS`:

- If one argument: study the tool, create `pbg-<tool>/`, implement the package, test it, generate the report, commit locally, and open the report.
- If two or more arguments: inventory the listed wrappers, design the wiring table, build `pbg-<name>-composite/`, validate, test, generate the composite report, commit locally, and open the report.