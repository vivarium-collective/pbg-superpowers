# Visualization convention

Visualizations are `process_bigraph.Step` subclasses, specifically
extending `pbg_superpowers.visualization.Visualization`. This makes them
discoverable via the same mechanism that finds Emitters and Processes:
`bigraph_schema.package.discover_packages`, called by `allocate_core()`.

## Why a Step?

- **Auto-discovery**: any pbg-* package containing a Visualization subclass
  registers automatically when `allocate_core()` runs. No manual
  `register_link` calls needed.
- **Uniform tracking**: visualizations appear in `core.link_registry`
  alongside Emitters / Processes — the dashboard's Registry tab can list
  them under a dedicated section.
- **Optional integration with Composites**: a Visualization is a Step, so
  it CAN be wired into a Composite document and run incrementally. Most
  use cases don't need this — render() is called post-simulation.

## The base class

```python
from pbg_superpowers.visualization import Visualization
```

Subclasses MUST override `render(self, results: dict) -> str | bytes`:

```python
class DnaATrajectory(Visualization):
    config_schema = {
        'title':     {'_type': 'string', '_default': 'DnaA over time'},
        'threshold': {'_type': 'float',  '_default': 50.0},
    }

    def render(self, results: dict) -> str:
        # Walk `results` (emitter output), build figure, return HTML.
        ...
```

`update()` defaults to a no-op. Override only if you want the
visualization to do something during simulation (e.g., write frames for
an animation).

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

## When to use `/pbg-viz`

`/pbg-viz <name>` generates a Visualization subclass from a
natural-language description (the lifecycle written to
`.pbg/viz-requests/<name>.md` by the dashboard). The generated file lives
at `pbg_<workspace>/visualizations/<name>.py`.

See [/pbg-viz SKILL.md](../../skills/pbg-viz/SKILL.md).

## When not to use a Visualization Step

If you're writing a one-off plotting script (not something to register and
reuse), a plain function is still fine. The Visualization class is for
visualizations that need to appear in the dashboard's Registry tab and be
reusable across workspaces.
