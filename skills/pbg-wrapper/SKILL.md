---
name: pbg-wrapper
description: Wrap a simulator as a process-bigraph Process INSIDE the current workspace, with no sibling repo, no HTML report, no PR. Lightweight counterpart to /pbg-expert for incremental experimentation.
arguments:
  - name: tool
    description: Name of the simulator to wrap (e.g. tellurium, smoldyn, cobra). Used as the Process class name (CamelCased) and the file name (lowercased).
    required: true
---

# /pbg-wrapper <tool>

Lightweight in-workspace wrap of a single simulator. Produces ONE Python file under `pbg_<slug>/processes/<tool>.py` containing a `process_bigraph.Process` subclass, plus a stub test under `tests/test_<tool>.py`. Nothing else.

For the heavy version (sibling repo, README, HTML report, PR), use `/pbg-expert <tool>` instead.

## When to use this

- You want to try wrapping a simulator quickly to see if its API fits
- You're prototyping a Process that will eventually live in a sibling pbg-* package, but you're not sure yet
- You want the Process to live inside the workspace for now and possibly extract it later
- You're using the dashboard's active-branch workstream model and want this wrap to land as one of many commits in the same PR

## Steps

1. Verify a workspace is present (`workspace.yaml` exists at CWD).
2. Determine the workspace's Python package directory from `workspace.yaml.package_path` (default: `pbg_<workspace_name_underscored>`).
3. Create `pbg_<slug>/processes/` if missing (touch its `__init__.py` to make it a package).
4. Write `pbg_<slug>/processes/<tool>.py` with:
   - Module docstring naming the simulator + a TODO for the real implementation
   - Import: `from process_bigraph import Process`
   - Class `<Tool>Process(Process)` with:
     - `config_schema = {}` (extend as needed)
     - `def inputs(self)` returning a sketch of expected input ports
     - `def outputs(self)` returning a sketch of expected output ports
     - `def update(self, state, interval)` returning a placeholder (e.g. echo state)
     - Real implementation marked with `# TODO:` so the user can fill it in
5. Write `tests/test_<tool>.py` with a minimal smoke test:
   - Import the class
   - Instantiate with default config
   - Assert `inputs()` and `outputs()` return dicts
6. Do NOT commit. The dashboard's active-branch workstream is the canonical commit surface — this skill leaves the working tree dirty so the user (or the dashboard) commits when ready.

## Output

Print a short summary:
- File created: `pbg_<slug>/processes/<tool>.py`
- Test stub: `tests/test_<tool>.py`
- "Working tree is now dirty — commit via the dashboard's active workstream (Push button) or `git add -A && git commit`."

## Example

`/pbg-wrapper tellurium` in a workspace named `chromosome-rep1` produces:

```
pbg_chromosome_rep1/processes/tellurium.py    # contains TelluriumProcess
tests/test_tellurium.py                       # smoke test
```

## Constraints

- Does NOT install the simulator (`tellurium`, `smoldyn`, etc.) into the venv — that's a separate step (Registry tab → catalog install, or manual `uv pip install`).
- Does NOT modify `workspace.yaml`. The Process lives in Python code, not in workspace metadata.
- Does NOT create a sibling repo, README, or HTML report. Use `/pbg-expert <tool>` for that.
- Does NOT auto-commit. The active workstream commits when the user pushes via the dashboard.
