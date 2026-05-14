---
name: pbg-viz
description: Generate a Plotly/matplotlib Visualization subclass from a natural-language description in the workspace's pbg-template dashboard.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: <visualization-name>
---

# /pbg-viz <visualization-name>

This skill bridges the dashboard's Visualizations tab and Claude Code: read the request, generate a `Visualization` subclass, save the response.

## v0.4.15 contract change — update() replaces render()

As of v0.4.15, Visualizations are real Steps wired into Composites — not
post-simulation side channels. The primary method is now `update(state, interval)`
(the standard Step contract), not a separate `render(results)`.

- `inputs()` declares which observables this viz consumes. The composite spec
  wires each name to a store path (exactly like Emitters).
- `update(state, interval)` runs each simulation step: accumulate history
  internally, re-render the full trajectory, return `{'html': '...'}`.
- `outputs()` exposes an `html` string port that a Composite can wire to a store.

After `sim.run()`, the `stores.viz_html` value is the latest rendered HTML.

**Breaking change:** Workspaces with v0.4.11 `render()`-based visualization
subclasses must be manually upgraded to the `update()` shape — see the
migration section below. pbg-superpowers is in development; breaking changes
are acceptable but must be explicit.

## Steps

1. Read `.pbg/viz-requests/<visualization-name>.md` from the current workspace. It contains the user's natural-language description plus workspace context (observables, simulations). If the file doesn't exist, abort and tell the user to click **Create** in the dashboard first.

2. Choose a visualization library based on the description:
   - **Plotly** for interactive plots, dashboards, hover tooltips
   - **matplotlib** for static images, paper-quality figures
   - Default to **Plotly** if unclear

3. Write a Python file to `.pbg/viz-responses/<visualization-name>.py` with this structure:
   - Module docstring quoting the description
   - A class `<ClassName>(Visualization)` (convert kebab-name to PascalCase) that extends `pbg_superpowers.visualization.Visualization`.
   - The class implements `inputs(self)` declaring consumed observables and `update(self, state, interval)` returning `{'html': '<rendered>'}`.
   - A `config_schema` dict on the class declaring configurable fields (title, thresholds, etc.).
   - `__init__` that calls `super().__init__()` and sets up `self.history = []` for per-step accumulation.

4. Use the workspace's available observables (listed in the request file) for `inputs()` wire names and `state` key lookups in `update()`. If the description references an observable not in the list, note it as a `# TODO: missing observable '<name>'` comment.

5. Make the class self-contained — assume `plotly` or `matplotlib` is available in the venv (process-bigraph workspaces typically have plotly installed). Don't import workspace-specific code.

6. After writing the response file, summarize for the user: what library was chosen, what the class does, and how to preview (wire into a tiny test composite with synthetic data, or use the dashboard's Preview button).

## Example response file

```python
"""Generated visualization: baseline-trajectory

Description: A time-series of free_DnaA concentration over the baseline
simulation, with a horizontal line at the binding threshold of 50 molecules.
"""
from pbg_superpowers.visualization import Visualization
import plotly.graph_objects as go


class BaselineTrajectory(Visualization):
    """Time-series of free_DnaA concentration with a binding-threshold line."""

    config_schema = {
        'title':     {'_type': 'string', '_default': 'Baseline trajectory: free_DnaA'},
        'threshold': {'_type': 'float',  '_default': 50.0},
        # additional config fields the viz wants (e.g., colors, axis labels)
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []   # accumulate per-step values

    def inputs(self):
        # Declare which observables this viz consumes. The composite spec
        # wires each name to a store path.
        return {
            'free_DnaA': 'float',
            # 'oriC_state': 'string',
        }

    def update(self, state, interval):
        # Accumulate this step's observable values.
        self.history.append(state.get('free_DnaA', 0.0))

        # Re-render the full trajectory each step.
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=self.history,
            mode='lines',
            name='free_DnaA',
        ))
        fig.add_hline(
            y=self.config.get('threshold', 50.0),
            line_dash='dash', line_color='red',
            annotation_text='Binding threshold',
        )
        fig.update_layout(
            title=self.config.get('title', 'Baseline trajectory: free_DnaA'),
            xaxis_title='step',
            yaxis_title='molecules',
        )
        return {'html': fig.to_html(full_html=False, include_plotlyjs='cdn')}
```

The dashboard preview works by wiring this viz into a tiny test composite
with synthetic data and reading `stores.viz_html` after the run.

## Constraints

- DO NOT modify `workspace.yaml` or any committed code. The dashboard moves the file to the package on Commit.
- DO NOT install new dependencies. Use stdlib + plotly/matplotlib (already in the venv).
- Keep the class focused on the description — don't add unrelated subplots or complexity.
- Write the file to `.pbg/viz-responses/` (gitignored) — never to the package directory directly.
- Class names: convert kebab-case to PascalCase (e.g., `dna-replication-plot` → `DnaReplicationPlot`).
- Do NOT generate a standalone `_demo()` function or `if __name__ == "__main__":` block. The v0.4.15 preview pattern uses composite wiring with synthetic data, not a standalone runner.

## Migrating v0.4.2 function-form visualizations

If a workspace has existing visualizations written as module-level
`def visualize(results)` functions (the v0.4.2 shape), convert them
to the v0.4.15 update()-based class:

```python
# Before (v0.4.2 form):
def visualize(results):
    series = results.get(('emitter',), [])
    # ... build fig ...
    return fig.to_html(...)

# After (v0.4.15 form):
from pbg_superpowers.visualization import Visualization

class Visualize(Visualization):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []

    def inputs(self):
        return {'value': 'float'}    # the observable(s) this viz consumes

    def update(self, state, interval):
        self.history.append(state['value'])
        # ... build fig from self.history ...
        return {'html': fig.to_html(...)}
```

## Migrating v0.4.11 render()-based visualizations

If a visualization was generated against v0.4.11 (separate render() method),
convert to update():

```python
# Before (v0.4.11):
class Foo(Visualization):
    def render(self, results):
        series = results.get(('emitter',), [])
        # ... build fig ...
        return fig.to_html(...)

# After (v0.4.15):
class Foo(Visualization):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []

    def inputs(self):
        return {'value': 'float'}    # the observable(s) this viz consumes

    def update(self, state, interval):
        self.history.append(state['value'])
        # ... build fig from self.history ...
        return {'html': fig.to_html(...)}
```

The key shift: visualizations now consume per-step state via wires (just
like Emitters); they accumulate internally if they need history. The old
`render(results)` pattern (post-simulation batch call) is gone — there is
no longer a `render()` method on the base class.

**Note:** pbg-superpowers is in active development. This is a deliberate
breaking change. Workspaces with v0.4.11 render()-based subclasses require
manual upgrade; they will receive a `NotImplementedError` at runtime until
updated to the `update()` shape.

See [docs/conventions/visualizations.md](../../docs/conventions/visualizations.md) for the full reference.
