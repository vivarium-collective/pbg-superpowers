# Bespoke runner-script convention

## When to write one

A **bespoke runner** is a hand-written `studies/<slug>/sims/run_*.py` (or `scripts/run_*.py`) that owns its own composite construction, emitter wiring, and simulation loop. Use one when the dashboard's in-process baseline/variant flow doesn't fit — e.g.:

- Division-spanning multi-generation sims (each generation needs its own composite + lineage handoff)
- Calibration harnesses (build the cache, run repeatedly, vary one parameter)
- External-tool wrappers (Cobaya, SLURM, IPython kernel handoffs)
- Parquet rerun pipelines (workspaces that pre-date the parquet shim and want the same script to drive both emitter types)

If the runner can be expressed as a composite + `parameter_overrides`, use `/pbg-study run-baseline` / `run-variant` instead — those go through the dashboard, surface the run in `runs.db` automatically, and integrate with the auto-renderer.

## The pattern

Every bespoke runner should:

1. **Accept `--emitter parquet|sqlite`** with a workspace default. The default constant references `workspace.yaml.runtime.default_emitter` in a comment so the lookup chain is self-documenting:

    ```python
    DEFAULT_EMITTER = "parquet"   # workspace default per workspace.yaml.runtime.default_emitter

    p = argparse.ArgumentParser()
    p.add_argument(
        "--emitter", choices=["parquet", "sqlite"], default=DEFAULT_EMITTER,
        help=(
            f"Emitter to capture history with (default: {DEFAULT_EMITTER}, "
            "the workspace default per workspace.yaml.runtime.default_emitter)."
        ),
    )
    ```

    Why: switching emitters used to require hand-editing the runner. Friction note 2026-05-27 #2 logged hand-editing 6 dnaa runners to migrate from sqlite to parquet. With this flag the migration is a CLI tweak.

2. **Dispatch on `args.emitter`** to the matching context manager from `v2ecoli/composites/_helpers.py`:

    ```python
    from v2ecoli.composites._helpers import sqlite_emitter, parquet_emitter

    if args.emitter == "sqlite":
        cm = sqlite_emitter(file_path=..., simulation_id=..., simulation_name=...)
    elif args.emitter == "parquet":
        cm = parquet_emitter(out_dir=..., experiment_id=..., study_slug=..., investigation_slug=...)
    else:
        raise ValueError(f"unknown emitter {args.emitter!r}; expected sqlite|parquet")

    with cm as emit:
        composite = build_composite(...)
        emit.bind(composite)             # ParquetEmitterContext only — see below
        composite.update({}, args.duration_sec)
    # parquet: auto-flushed on exit (success based on exception state)
    # sqlite:  flushed by SQLiteEmitter.__del__ when the composite goes out of scope
    ```

3. **`emit.bind(composite)` on the parquet path.** PR #88 (`fix(parquet): auto-flush bound composite on context exit`) added a `ParquetEmitterContext` that auto-flushes on exit when a composite is bound. Without `.bind()`, the trailing partial batch + `success/` sentinel are lost — only the `configuration/` parquet lands. The `sqlite_emitter` path doesn't need this; `SQLiteEmitter.__del__` flushes unconditionally.

4. **Workspace-root paths** for `out_path`, hive `out_dir`, and the runner script itself. Runners expect CWD = workspace root (so `out/cache/`, `studies/...`, etc. resolve). The `/pbg-study run-script` skill enforces this by `cd <workspace-root> && python <script> <args...>`.

5. **`canonical_runs:` entry on `study.yaml`** so `/pbg-study run-script <slug>` can find the runner:

    ```yaml
    canonical_runs:
      - name: cell-cycle
        script: studies/<slug>/sims/run_baseline.py
        args: ['4020', '60', 'studies/<slug>/parquet-runs/cell-cycle.json']
        label: "one cell cycle (4020s @ 60s)"
        default: true
      - name: smoke
        script: studies/<slug>/sims/run_baseline.py
        args: ['60', '10', 'studies/<slug>/parquet-runs/smoke.json']
        label: "60s @ 10s smoke"
    ```

    See [`canonical_runs:` in vivarium-dashboard-model.md](../concepts/vivarium-dashboard-model.md#canonical-run-recipe-bespoke-scripts).

## Reference implementation

The pattern was first applied in [v2ecoli's `multiscale-bioprocess/scripts/run_mbp_tracked.py`](https://github.com/vivarium-collective/v2ecoli) (commits `7def72f`, `6c842d1`). It's the canonical example — when in doubt, mirror its structure.

The dnaa-biology session's runners (`studies/dnaa-0*/sims/run_*.py`) currently hardcode the emitter — that's the next migration target, tracked as a follow-up to friction #2.

## What this doesn't cover

- **No scaffolder yet.** This document is convention for hand-writers. A future `/pbg-study scaffold-runner <slug> <entry-name>` would emit a Jinja template with the pattern pre-filled and add the matching `canonical_runs:` entry; not built. Until then, copy from the mbp runner.
- **No `run_multigen_{sqlite,parquet}` helpers documented here.** The mbp runner imports them from `v2ecoli/library/{sqlite_run,parquet_run}.py` — workspace-specific wrappers for division-spanning runs. Not a general framework concern.
- **No emitter-override at the dashboard level.** `workspace.yaml.runtime.default_emitter` is read by individual runners, not by the dashboard's `/api/study-run-baseline` (which uses its own in-process emitter wiring). If/when bespoke runners and dashboard-managed runners need to share an emitter override, lift the lookup into a shared helper.
