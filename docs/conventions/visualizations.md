# Visualization convention

Visualizations are `process_bigraph.Step` subclasses, specifically
extending `pbg_superpowers.visualization.Visualization`. As of v0.4.15,
they are real Steps wireable into Composite specs — not just discoverable
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
