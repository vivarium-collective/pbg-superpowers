# Visualization convention

Visualizations are `process_bigraph.Step` subclasses, specifically
extending `pbg_superpowers.visualization.Visualization`. They are real
Steps wireable into Composite specs — not just discoverable
post-simulation renderers.

## Why a Step?

- **Auto-discovery**: any pbg-* package containing a Visualization subclass
  registers automatically when `allocate_core()` runs. No manual
  `register_link` calls needed.
- **Uniform tracking**: visualizations appear in `core.link_registry`
  alongside Emitters / Processes — the dashboard's Registry tab can list
  them under a dedicated section.
- **Wireable into Composites**: a Visualization is a real Step with
  `inputs()` and `outputs()`, so it can be wired into a Composite spec
  alongside Processes and Emitters. Its `html` output port carries the
  latest rendered HTML into a store each step.

## The base class

```python
from pbg_superpowers.visualization import Visualization
```

Subclasses MUST override `inputs()` and `update(state, interval)`:

```python
class DnaATrajectory(Visualization):
    config_schema = {
        'title':     {'_type': 'string', '_default': 'DnaA over time'},
        'threshold': {'_type': 'float',  '_default': 50.0},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []   # accumulate per-step values

    def inputs(self):
        # Declare which observables this viz consumes.
        return {'free_DnaA': 'float'}

    def update(self, state, interval):
        # Accumulate + re-render full trajectory each step.
        self.history.append(state.get('free_DnaA', 0.0))
        import plotly.graph_objects as go
        fig = go.Figure(go.Scatter(y=self.history, mode='lines'))
        fig.add_hline(
            y=self.config.get('threshold', 50.0),
            line_dash='dash',
            annotation_text='threshold',
        )
        fig.update_layout(title=self.config.get('title', 'DnaA over time'))
        return {'html': fig.to_html(full_html=False, include_plotlyjs='cdn')}
```

`outputs()` defaults to `{'html': 'string'}`. Override if you also want
to emit a PNG path, JSON, or other formats.

## Render timing convention

Visualizations re-render the full trajectory each `update()` call. Subclasses
accumulate state in instance attributes (`self.history`, `self.frames`, etc.)
and produce a fresh figure each step. Plotly and matplotlib both handle the
resulting recomputation fine for typical workspace simulations.

## Canonical registration: subclass `Visualization`

There is **one canonical way** to register a Visualization: subclass
`pbg_superpowers.visualization.Visualization` directly. Every shipped
Visualization in `pbg_superpowers.visualizations.*` follows this pattern,
and every Visualization in real workspaces (v2ecoli) does too.

The legacy `@as_visualization(...)` decorator continues to work for
back-compat but emits a `DeprecationWarning` at decoration time. New
code should not use it. Reasons:

- The decorator registers TWO names per class (PascalCase from `name=`
  AND the snake_case `update_<x>` suffix), forcing the workspace lint
  to grep for both forms when resolving `local:Foo` addresses.
- Subclassing makes the input/output contract explicit at the class
  definition site instead of buried in decorator kwargs.
- Subclassing supports the new-style `accumulate()` / `render()` split
  (see "Render timing convention" above); the decorator only emits the
  legacy update-every-tick form.

## Canonical address: `local:<ClassName>`

There is **one canonical way** to reference a Visualization from a
Composite spec or `study.yaml.visualizations[].address`: the
`local:<ClassName>` form. Every v2ecoli study uses this. The
`pbg-superpowers` workspace lint validates `local:Foo` addresses by
scanning every `<package>/visualizations/` subtree for a matching
`class Foo` declaration.

Dotted module-path addresses (`pkg.module.ClassName`) are *technically*
accepted by the dashboard's `build_viz_composite`, but they're not used
in any production study and the lint can't validate them without
importing arbitrary workspace code. Prefer `local:` for everything you
declare in `study.yaml`; reserve dotted paths for cross-package
references where the canonical-form discovery wouldn't reach.

## The three render paths

The dashboard exposes **three disjoint ways** to drive a Visualization
class. Picking the wrong path is the most common cause of "viz renders
empty" reports (see mem3dg-readdy friction log #5 for the full
investigation that produced this section). Pick the path that matches
your data shape — the constraints are load-bearing.

### Path A — inline composite Step

The viz is wired into the composite `state` as a `_type: step` with
declared `inputs:` pointing at simulation stores. `composite.run(steps)`
calls `update(state)` once per tick with per-step scalar values.

- **Used for**: live in-simulation overlays; vizzes that write back
  into a store other processes consume.
- **Carries**: scalar-per-step values only.
- **Constraint**: declared inputs MUST match the upstream store
  types. `'float'` against a `Float` store works; `'list[float]'`
  against a `Float` store fails composite init with
  `cannot resolve types: Float vs List[Float]`.
- **Maintain history yourself** — the viz only sees one tick at a
  time, so multi-step charts need `self.history` accumulation
  between calls.

### Path B — auto-render from runs.db via typed wire (most common)

After a run completes,
`vivarium_workbench.lib.investigations.render_visualizations` builds a
**fresh single-step composite** per viz: one tiny composite containing
the viz Step plus an `inputs_store` populated from the SQLiteEmitter's
`runs.db`. The viz receives `state` with each port populated by a
per-port resolved series.

Dispatch table (`build_viz_composite` in `lib/investigations.py`):

| Declared port type     | What `inputs_store[port]` receives    |
|------------------------|----------------------------------------|
| `'float'`              | **last** scalar only (`series[-1]`)   |
| `'list[float]'`        | full series for the one run            |
| `'list[list[float]]'`  | list-of-runs (each a per-tick series)  |
| anything else          | first run's full series (best effort)  |

- **Used for**: any post-run chart over scalar-per-step observables.
  The natural default.
- **Carries**: anything that fits the dispatch table.
  - 1D scalar series (`'list[float]'`) ✓
  - Per-tick lists of scalars (`'list[list[float]]'`) ✓
  - **NOT** 3-level-nested arrays (per-tick `list[points][3]` for
    positions). The schema engine treats inner lists as element
    scalars and discards them. For nested coordinate data use Path C.
- **`update()` is called ONCE** with the full series already aggregated.
  History accumulation is irrelevant; handle bulk-input form. This
  makes a single class incompatible with Path A unless you defensively
  detect both shapes — don't try.

### Path C — direct `runs.db` read

The viz's `inputs()` returns `{}`. No dashboard wiring. In `update()`,
the viz opens `<workspace>/studies/<slug>/runs.db` directly via
`sqlite3`, pulls every per-step state for the latest simulation, and
embeds the result in the rendered HTML.

- **Used for**: nested coordinate arrays (positions, vertex sets,
  matrices) the typed wire would truncate. 3D viewers especially.
- **Carries**: anything in `runs.db`. SQLiteEmitter writes the full
  state JSON per step, including 3-level-nested arrays.
- **Resolve the runs.db path** in this order:
  1. `config.study_slug` — explicit, set per-study in `study.yaml`.
     Recommended pattern; immune to multi-run-in-flight races.
  2. Most-recently-modified `runs.db` under `studies/*/runs.db`.
     Fine for the dashboard's sequential render flow.
- **Anything NOT captured in `runs.db`** (e.g. static Mem3DG mesh
  topology computed at process construction and never re-emitted) must
  be reconstructed by re-instantiating the underlying process.

### Decision tree

```
What does the viz need?
├─ Per-step scalar history of one or more observables
│   → Path B (declare 'list[float]' inputs, accept the full series)
│
├─ Per-step nested arrays (positions, vertex sets, matrices, [N][3]…)
│   → Path C (empty inputs(), read runs.db directly, embed in HTML)
│
└─ Live in-simulation overlay (writes back to a wire other processes consume)
    → Path A (inline Step, scalar inputs only)
```

### Authoring rules (do / don't)

**Always**
- Declare `inputs()` with a type from Path B's dispatch table. Unknown
  type strings raise `'str' object does not support item assignment`
  during composite init.
- Handle empty input gracefully — return an `'html'` payload with an
  inline error message rather than raising. Other vizzes still render.
- Use `stable_div_id()` for DOM ids, not `id(self)` (mem3dg-readdy
  friction #28 — the auto-render path can instantiate the same class
  twice in one page and collide on `id()`).
- Embed JS as a plain string with `str.replace()` for substitutions,
  not as an f-string. F-string brace-escaping (`{{`/`}}`) is invisible
  in Python and invalid JS in the browser (mem3dg-readdy friction #31).

**Never**
- Mix Path A and Path B in one class without shape detection. Pick one.
- Trust `__init__` side effects under Path B. The dashboard does
  `viz_class.__new__(viz_class).inputs()` to introspect declared ports
  without instantiating, so `__init__` may be skipped. Initialize
  state lazily in `update()`.

## Wiring into a Composite spec

A Visualization can be included in a composite spec as a Step, wired to
stores exactly like Emitters:

```yaml
state:
  binder: {_type: process, address: local:DnaABinder, ...}
  stores:
    free_DnaA: 100.0
    viz_html: ""
  viz:
    _type: step
    address: "local:DnaATrajectory"
    config: {threshold: 50.0}
    inputs:
      free_DnaA: [stores, free_DnaA]
    outputs:
      html: [stores, viz_html]
```

After `sim.run()`, `stores.viz_html` holds the latest rendered HTML from
the final simulation step.

## Filtering Visualizations from a Core registry

The dashboard uses this pattern to list registered visualizations:

```python
from pbg_superpowers.visualization import Visualization

viz_classes = {
    name: cls for name, cls in core.link_registry.items()
    if isinstance(cls, type)
       and issubclass(cls, Visualization)
       and cls is not Visualization
}
```

The `is_visualization()` classmethod marker is also available:

```python
viz_classes = {
    name: cls for name, cls in core.link_registry.items()
    if isinstance(cls, type) and getattr(cls, 'is_visualization', lambda: False)()
}
```

## When to use `/pbg-viz`

`/pbg-viz <name>` generates a Visualization subclass from a
natural-language description (the lifecycle written to
`.pbg/viz-requests/<name>.md` by the dashboard). The generated file lives
at `.pbg/viz-responses/<name>.py` until committed to the package.

See [/pbg-viz SKILL.md](../../skills/pbg-viz/SKILL.md).

## When not to use a Visualization Step

If you're writing a one-off plotting script (not something to register and
reuse), a plain function is still fine. The Visualization class is for
visualizations that need to appear in the dashboard's Registry tab, be
reusable across workspaces, and optionally be wired into Composite specs.
