---
name: pbg-viz
description: Generate a Plotly/matplotlib Visualization subclass from a natural-language description in the workspace's pbg-template dashboard.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: <visualization-name>
---

# /pbg-viz <visualization-name>

This skill bridges the dashboard's Visualizations tab and Claude Code: read the request, generate a `Visualization` subclass, save the response.

## Steps

1. Read `.pbg/viz-requests/<visualization-name>.md` from the current workspace. It contains the user's natural-language description plus workspace context (observables, simulations, phases). If the file doesn't exist, abort and tell the user to click **Create** in the dashboard first.

2. Choose a visualization library based on the description:
   - **Plotly** for interactive plots, dashboards, hover tooltips
   - **matplotlib** for static images, paper-quality figures
   - Default to **Plotly** if unclear

3. Write a Python file to `.pbg/viz-responses/<visualization-name>.py` with this structure:
   - Module docstring quoting the description
   - A class `<ClassName>(Visualization)` (convert kebab-name to PascalCase) that extends `pbg_superpowers.visualization.Visualization`. The class implements `render(self, results: dict) -> str`, which returns rendered HTML (Plotly) or base64-encoded PNG (matplotlib). The `results` argument is process-bigraph emitter output: a dict keyed by emitter path tuples, with values being lists of `{observable_name: value, ...}` dicts ordered by simulation step.
   - A `config_schema` dict on the class declaring configurable fields (title, thresholds, etc.).
   - One helper `_demo() -> str` that builds synthetic results and calls `<ClassName>().render(fake)` — used by the dashboard preview.
   - An `if __name__ == "__main__":` block that prints `_demo()` so the user can verify with `python3 .pbg/viz-responses/<name>.py | head`.

4. Use the workspace's available observables (listed in the request file) for store paths. If the description references an observable not in the list, note it as a `# TODO: missing observable '<name>'` comment.

5. Make the class self-contained — assume `plotly` or `matplotlib` is available in the venv (process-bigraph workspaces typically have plotly installed). Don't import workspace-specific code.

6. After writing the response file, summarize for the user: what library was chosen, what the class does, how to preview (`python3 .pbg/viz-responses/<name>.py | head` for a quick check, or the dashboard's Preview button).

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
    }

    def render(self, results: dict) -> str:
        series = results.get(('emitter',), [])
        times = list(range(len(series)))
        free_DnaA = [s.get('free_DnaA', 0.0) for s in series]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=times, y=free_DnaA, mode='lines', name='free_DnaA'))
        fig.add_hline(
            y=self.config['threshold'],
            line_dash='dash', line_color='red',
            annotation_text='Binding threshold',
        )
        fig.update_layout(
            title=self.config['title'],
            xaxis_title='time',
            yaxis_title='molecules',
        )
        return fig.to_html(full_html=False, include_plotlyjs='cdn')


def _demo() -> str:
    """Render synthetic data so the dashboard preview button works."""
    fake = {('emitter',): [{'free_DnaA': 100 - i * 5} for i in range(20)]}
    return BaselineTrajectory().render(fake)


if __name__ == "__main__":
    import sys
    sys.stdout.write(_demo())
```

## Constraints

- DO NOT modify `workspace.yaml` or any committed code. The dashboard moves the file to the package on Commit.
- DO NOT install new dependencies. Use stdlib + plotly/matplotlib (already in the venv).
- Keep the class focused on the description — don't add unrelated subplots or complexity.
- The `_demo()` synthetic data should be plausible (e.g., monotonic decay, sin wave, or random walk depending on what the variable represents).
- Write the file to `.pbg/viz-responses/` (gitignored) — never to the package directory directly.
- Class names: convert kebab-case to PascalCase (e.g., `dna-replication-plot` → `DnaReplicationPlot`).

## Migrating v0.4.2 function-form visualizations

If a workspace has existing visualizations written as module-level
`def visualize(results)` functions (the v0.4.2 shape), you can convert them
by wrapping in a Visualization subclass:

```python
# Before (v0.4.2 form):
def visualize(results):
    series = results.get(('emitter',), [])
    # ... build fig ...
    return fig.to_html(...)

# After (v0.4.11+ form):
from pbg_superpowers.visualization import Visualization

class Visualize(Visualization):
    def render(self, results):
        series = results.get(('emitter',), [])
        # ... build fig (same logic) ...
        return fig.to_html(...)
```

The class form gets:
- Auto-discovery via `bigraph_schema.package.discover` (appears in `core.link_registry`)
- `config_schema` declared parameters (no more magic globals)
- Dashboard's Registry tab tracks it alongside Emitters / Processes / Types

See [docs/conventions/visualizations.md](../../docs/conventions/visualizations.md) for the full reference.
