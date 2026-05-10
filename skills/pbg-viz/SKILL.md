---
name: pbg-viz
description: Generate a Plotly/matplotlib visualization function from a natural-language description in the workspace's pbg-template dashboard.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: <visualization-name>
---

# /pbg-viz <visualization-name>

This skill bridges the dashboard's Visualizations tab and Claude Code: read the request, generate a Python function, save the response.

## Steps

1. Read `.pbg/viz-requests/<visualization-name>.md` from the current workspace. It contains the user's natural-language description plus workspace context (observables, simulations, phases). If the file doesn't exist, abort and tell the user to click **Create** in the dashboard first.

2. Choose a visualization library based on the description:
   - **Plotly** for interactive plots, dashboards, hover tooltips
   - **matplotlib** for static images, paper-quality figures
   - Default to **Plotly** if unclear

3. Write a Python file to `.pbg/viz-responses/<visualization-name>.py` with this structure:
   - Module docstring quoting the description
   - One function `visualize(results: dict) -> str` that returns rendered HTML (Plotly) or base64-encoded PNG (matplotlib). The `results` argument is process-bigraph emitter output: a dict keyed by emitter path tuples, with values being lists of `{observable_name: value, ...}` dicts ordered by simulation step.
   - One helper `_demo() -> str` that builds synthetic results matching the workspace's observables and calls `visualize()` — used by the dashboard preview.
   - An `if __name__ == "__main__":` block that prints `_demo()` so the user can verify with `python3 .pbg/viz-responses/<name>.py | head`.

4. Use the workspace's available observables (listed in the request file) for store paths. If the description references an observable not in the list, note it as a `# TODO: missing observable '<name>'` comment.

5. Make the function self-contained — assume `plotly` or `matplotlib` is available in the venv (process-bigraph workspaces typically have plotly installed). Don't import workspace-specific code.

6. After writing the response file, summarize for the user: what library was chosen, what the function does, how to preview (`python3 .pbg/viz-responses/<name>.py | head` for a quick check, or the dashboard's Preview button when implemented in v0.4.3).

## Example response file

```python
"""Generated visualization: baseline-trajectory

Description: A time-series of free_DnaA concentration over the baseline
simulation, with a horizontal line at the binding threshold of 50 molecules.
"""
import plotly.graph_objects as go


def visualize(results: dict) -> str:
    series = results.get(('emitter',), [])
    times = list(range(len(series)))
    free_DnaA = [s.get('free_DnaA', 0.0) for s in series]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=free_DnaA, mode='lines', name='free_DnaA'))
    fig.add_hline(y=50, line_dash='dash', line_color='red', annotation_text='Binding threshold')
    fig.update_layout(title='Baseline trajectory: free_DnaA', xaxis_title='time', yaxis_title='molecules')
    return fig.to_html(full_html=False, include_plotlyjs='cdn')


def _demo() -> str:
    fake = {('emitter',): [{'free_DnaA': 100 - i * 5} for i in range(20)]}
    return visualize(fake)


if __name__ == "__main__":
    import sys
    sys.stdout.write(_demo())
```

## Constraints

- DO NOT modify `workspace.yaml` or any committed code. The dashboard moves the file to the package on Commit.
- DO NOT install new dependencies. Use stdlib + plotly/matplotlib (already in the venv).
- Keep the function focused on the description — don't add unrelated subplots or complexity.
- The `_demo()` synthetic data should be plausible (e.g., monotonic decay, sin wave, or random walk depending on what the variable represents).
- Write the file to `.pbg/viz-responses/` (gitignored) — never to the package directory directly.
