"""Reconcile a study's runs.db into study.yaml and expose the canonical outcome
surface. Mechanical run fields are code-owned; authored outcomes/prose are preserved.
Increment A: record + single-source. (Evaluation of measure/pass_if is Increment B.)"""
from __future__ import annotations

from pathlib import Path

from . import study_io, run_registry

_COMPLETE = {"complete", "completed", "ran", "done"}


def _runs_of(spec_or_runs) -> list[dict]:
    if isinstance(spec_or_runs, list):
        runs = spec_or_runs
    else:
        runs = (spec_or_runs or {}).get("runs") or []
    return [r for r in runs if isinstance(r, dict)]


def canonical_run(spec_or_runs) -> dict | None:
    """The run whose outcomes are authoritative: an explicit `canonical: true`
    (last one wins), else the newest completed run by `timestamp`, else the last
    run, else None."""
    runs = _runs_of(spec_or_runs)
    if not runs:
        return None
    flagged = [r for r in runs if r.get("canonical") is True]
    if flagged:
        return flagged[-1]
    completed = [r for r in runs if str(r.get("status", "")).lower() in _COMPLETE]
    if completed:
        return max(completed, key=lambda r: r.get("timestamp") or "")
    return runs[-1]


def canonical_outcomes(spec_or_runs) -> dict:
    """The canonical run's `outcomes` dict (empty if none)."""
    run = canonical_run(spec_or_runs)
    return (run or {}).get("outcomes") or {}


# ---------------------------------------------------------------------------
# Run reconciliation
# ---------------------------------------------------------------------------

# Code-owned mechanical fields written from runs.db
_MECHANICAL = ("status", "kind", "emitter", "seeds", "params", "timestamp", "commit")


def _emitter_kind(emitter_path: str | None) -> str:
    p = (emitter_path or "").lower()
    if not p:
        return "unknown"
    if p.endswith(".db") or "sqlite" in p:
        return "sqlite"
    if "parquet" in p:
        return "parquet"
    if "zarr" in p or "xarray" in p:
        return "xarray"
    return "unknown"


def _mechanical_record(db_row: dict) -> dict:
    emitter_path = db_row.get("emitter_path")
    emitter: dict = {"kind": _emitter_kind(emitter_path)}
    if emitter_path is not None:
        emitter["store"] = emitter_path
    rec = {
        "name": db_row.get("run_id"),
        "status": db_row.get("status"),
        "timestamp": db_row.get("completed_at") or db_row.get("started_at"),
        "emitter": emitter,
    }
    if db_row.get("generation_id") is not None:
        rec["generation_id"] = db_row.get("generation_id")
    params = db_row.get("params") or db_row.get("params_json")
    if params:
        rec["params"] = params
    return {k: v for k, v in rec.items() if v is not None}


def record_runs(study_dir) -> dict:
    """Merge the study's runs.db rows into study.yaml's runs[] by run name.
    Updates only mechanical fields; preserves authored outcomes/prose and all
    YAML comments via ruamel round-trip write. Idempotent.
    Returns {"added": n, "updated": n}."""
    study_dir = Path(study_dir)
    study_yaml = study_dir / "study.yaml"
    spec = study_io.load_yaml_mapping(study_yaml)
    db_rows = run_registry.list_runs(study_dir / "runs.db")

    runs = spec.get("runs")
    if not isinstance(runs, list):
        runs = []
    by_name = {r["name"]: r for r in runs if isinstance(r, dict) and r.get("name")}

    # Count-only pass on the plain-loaded spec (no mutation here).
    added = updated = 0
    for row in db_rows:
        rec = _mechanical_record(row)
        name = rec.get("name")
        if not name:
            continue
        if name in by_name:
            target = by_name[name]
            changed = any(k in rec and target.get(k) != rec[k] for k in _MECHANICAL)
            if changed:
                updated += 1
        else:
            added += 1

    if added or updated:
        _write_runs_preserving_comments(study_yaml, db_rows)
    return {"added": added, "updated": updated}


def _write_runs_preserving_comments(study_yaml: Path, db_rows: list[dict]) -> None:
    """Apply db_rows into study_yaml using ruamel round-trip so YAML comments
    and formatting are preserved.  Only mechanical fields are touched on
    existing entries; new entries are appended as plain dicts."""
    from io import StringIO

    from ruamel.yaml import YAML

    ryaml = YAML()
    ryaml.preserve_quotes = True
    ryaml.width = 4096  # avoid line-wrap reflow on long prose values

    rt_spec = ryaml.load(study_yaml.read_text())
    if rt_spec is None:
        rt_spec = {}

    rt_runs = rt_spec.get("runs")
    if not isinstance(rt_runs, list):
        rt_runs = []
        rt_spec["runs"] = rt_runs

    rt_by_name = {r["name"]: r for r in rt_runs if isinstance(r, dict) and r.get("name")}

    for row in db_rows:
        rec = _mechanical_record(row)
        name = rec.get("name")
        if not name:
            continue
        if name in rt_by_name:
            target = rt_by_name[name]
            for k in _MECHANICAL:
                if k in rec:
                    target[k] = rec[k]
        else:
            rt_runs.append(rec)
            rt_by_name[name] = rec

    buf = StringIO()
    ryaml.dump(rt_spec, buf)
    study_io.atomic_write(study_yaml, buf.getvalue())


def sync(study_dir) -> dict:
    """Reconcile runs (record_runs) AND compute code verdicts (compute_outcomes)
    AND auto-populate simulation_set (populate_simulation_set).

    compute_outcomes and populate_simulation_set are both best-effort: errors
    are captured (never raised) so record_runs always completes.
    """
    summary = record_runs(study_dir)
    try:
        from .study_evaluator import compute_outcomes
        summary["computed"] = compute_outcomes(study_dir)
    except ImportError as exc:
        summary["computed"] = {"skipped": f"evaluator extra unavailable: {exc}"}
    except Exception as exc:  # noqa: BLE001
        summary["computed"] = {"error": str(exc)}
    try:
        from .simulation_set import populate_simulation_set
        summary["simulation_set"] = populate_simulation_set(study_dir)
    except Exception as exc:  # noqa: BLE001
        summary["simulation_set"] = {"error": str(exc)}
    return summary


def main(argv=None) -> int:
    import argparse
    from .workspace_paths import WorkspacePaths
    ap = argparse.ArgumentParser(description="Reconcile study runs.db into study.yaml")
    ap.add_argument("--workspace", default=".")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--study", help="study slug")
    grp.add_argument("--all", action="store_true", help="every study in the workspace")
    args = ap.parse_args(argv)

    paths = WorkspacePaths.load(Path(args.workspace))
    if args.all:
        dirs = list(paths.iter_study_dirs())
    else:
        dirs = [paths.study_dir(args.study)]

    total = {"added": 0, "updated": 0}
    for d in dirs:
        s = record_runs(d)
        total["added"] += s["added"]; total["updated"] += s["updated"]
        print(f"{d.name}: added={s['added']} updated={s['updated']}")
    print(f"TOTAL added={total['added']} updated={total['updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
