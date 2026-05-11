---
name: pbg-composer
description: Compose multiple wrapped simulators into a Composite document INSIDE the current workspace. Lightweight counterpart to /pbg-expert <name> <tools…> which creates a sibling composite repo.
arguments:
  - name: name
    description: Name for the composite (used as file name and class/function name).
    required: true
  - name: tools
    description: Two or more wrapper packages already installed in the workspace venv (e.g. pbg_tellurium pbg_cobra).
    required: true
---

# /pbg-composer <name> <tools…>

Compose two or more already-installed pbg-* wrappers into a Composite document inside the current workspace. Produces ONE Python module under `pbg_<slug>/composites/<name>.py` containing a `build_composite()` function that returns a `process_bigraph.Composite`, plus a stub test. Nothing else.

For the heavy version (new sibling pbg-`<name>`-composite repo + HTML report + PR), use `/pbg-expert <name> <tools…>` instead.

## When to use this

- You have two or more wrapper packages installed (via the dashboard's Registry catalog or `/pbg-wrapper`)
- You want to compose them into a runnable model inside your current workspace
- You'll iterate on the composite shape (wires, parameters) and don't want a sibling repo yet

## Steps

1. Verify a workspace is present (`workspace.yaml` exists at CWD).
2. Verify each `<tool>` argument resolves to an importable package (e.g. `pbg_tellurium`). If not, report which are missing and instruct the user to install via the Registry tab.
3. Determine `pbg_<slug>` from `workspace.yaml.package_path`.
4. Create `pbg_<slug>/composites/` + `__init__.py` if missing.
5. Write `pbg_<slug>/composites/<name>.py` with:
   - Module docstring naming the composite and its participants
   - Imports for each tool's Process class (use `__all__` or known process names from the package)
   - A `build_composite(core=None) -> Composite` function that:
     - Calls `allocate_core()` if `core` is None
     - Builds a state dict referencing each Process at a path (e.g. `simulation/tellurium`, `simulation/cobra`)
     - Wires the processes via shared stores (best-effort guess based on `inputs()`/`outputs()` of each Process — leave wires as `# TODO` if ambiguous)
     - Adds a `RAMEmitter` capturing the shared stores
     - Returns `Composite({'state': state}, core=core)`
   - An `if __name__ == "__main__":` block that runs `build_composite().run(10)` and prints a summary
6. Write `tests/test_<name>_composite.py` with a minimal smoke test:
   - Call `build_composite()`
   - Assert the resulting object is a `Composite`
   - Run for 1 timestep and verify no exception
7. Do NOT commit. Working tree is dirty; the dashboard's active workstream commits when ready.

## Output

Print:
- File created: `pbg_<slug>/composites/<name>.py`
- Test stub: `tests/test_<name>_composite.py`
- TODOs left for ambiguous wires
- "Run from terminal: `python -m pbg_<slug>.composites.<name>`"

## Example

`/pbg-composer metabolism pbg_cobra pbg_tellurium` in `chromosome-rep1`:

```
pbg_chromosome_rep1/composites/metabolism.py    # build_composite() returns Composite
tests/test_metabolism_composite.py              # smoke test
```

## Constraints

- Requires the wrapper packages to be already installed in the workspace venv.
- Does NOT install them — direct the user to Registry tab → catalog install if missing.
- Best-effort wire inference; ambiguous wires get `# TODO:` comments instead of guesses.
- Does NOT create a sibling repo, README, or report. Use `/pbg-expert <name> <tools…>` for that.
- Does NOT auto-commit.
