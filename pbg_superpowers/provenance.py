"""Trace a figure (or a bare run_id) back to the exact config that produced it.

The provenance model (see v2e-invest docs/conventions/run-provenance.md):

* ``experiment_id`` (the top parquet partition key) *is* the run id.
* The runner records a ``run_config`` dict into the per-study runs.db
  ``runs_meta.params_json`` slot via
  :func:`pbg_superpowers.run_registry.register_run`.
* Each rendered figure carries that ``run_id`` in its ``.meta.json``.
* This module is the lookup: figure -> run_id -> registry params, with a
  fallback to the on-disk parquet ``configuration`` partition when the
  registry has no row (e.g. pre-existing runs that predate the provenance
  system).

CLI::

    python -m pbg_superpowers.provenance <figure.png | .meta.json | run_id> \\
        [--runs-db PATH] [--workspace DIR] [--json]

Resolution order for the params:
  1. If ``--runs-db`` is given, look there.
  2. Else search ``<workspace>/**/runs.db`` for a row with that run_id.
  3. Else fall back to the parquet ``configuration`` partition under the
     run dir (``out/<run_id>/<run_id>/configuration/experiment_id=<run_id>/``)
     if discoverable, reporting whatever config columns it carries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .run_registry import get_run_params


# ---------------------------------------------------------------------------
# figure -> run_id
# ---------------------------------------------------------------------------

def run_id_from_meta(meta_path: Path) -> str | None:
    """Read a chart ``.meta.json`` and return its canonical ``run_id``.

    Prefers the explicit ``run_id`` key (written by the provenance-aware
    render scripts); falls back to ``source_run_id`` / ``source_run`` (the
    legacy free-text run hint)."""
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("run_id", "source_run_id", "source_run"):
        val = meta.get(key)
        if val:
            return str(val)
    return None


def resolve_run_id(target: str) -> tuple[str | None, Path | None]:
    """Map a CLI target (figure path, meta path, or bare run_id) to a run_id.

    Returns ``(run_id, meta_path_or_None)``. A target ending in an image
    extension is mapped to its sibling ``<fig>.meta.json``; a ``.meta.json``
    is read directly; anything else is treated as a literal run_id.
    """
    p = Path(target)
    if target.endswith(".meta.json"):
        return run_id_from_meta(p), p
    if p.suffix.lower() in (".png", ".svg", ".pdf", ".jpg", ".jpeg"):
        meta = Path(str(p) + ".meta.json")
        if meta.is_file():
            return run_id_from_meta(meta), meta
        return None, meta
    # Bare run_id.
    return target, None


# ---------------------------------------------------------------------------
# run_id -> params
# ---------------------------------------------------------------------------

def _find_runs_db_with(run_id: str, workspace: Path) -> Path | None:
    """Find a ``runs.db`` under ``workspace`` that has a ``runs_meta`` row for
    ``run_id``. Returns the first match (or None)."""
    import sqlite3
    for db in sorted(workspace.glob("**/runs.db")):
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
            try:
                have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
                if "run_id" not in have:
                    continue
                hit = conn.execute(
                    "SELECT 1 FROM runs_meta WHERE run_id=?", (run_id,)
                ).fetchone()
            finally:
                conn.close()
            if hit:
                return db
        except sqlite3.Error:
            continue
    return None


def _params_from_parquet_config(run_id: str, workspace: Path) -> dict | None:
    """Fallback: read the run's parquet ``configuration`` partition and return
    a minimal config dict. We don't parse parquet bytes (avoid a hard pyarrow
    dep here); we report the partition keys (experiment_id, variant,
    lineage_seed, generation) that the partition path encodes, which already
    answers seed / experiment questions for pre-provenance runs."""
    candidates = list(workspace.glob(
        f"**/{run_id}/configuration/experiment_id={run_id}"))
    if not candidates:
        # also accept out/<run_id>/<run_id>/configuration/...
        candidates = list(workspace.glob(
            f"**/configuration/experiment_id={run_id}"))
    if not candidates:
        return None
    cfg_root = candidates[0]
    out: dict = {"_source": "parquet-configuration-partition",
                 "experiment_id": run_id,
                 "configuration_path": str(cfg_root)}
    seeds, gens, variants = set(), set(), set()
    for part in cfg_root.glob("**/generation=*"):
        for seg in part.parts:
            if seg.startswith("lineage_seed="):
                seeds.add(seg.split("=", 1)[1])
            elif seg.startswith("generation="):
                gens.add(seg.split("=", 1)[1])
            elif seg.startswith("variant="):
                variants.add(seg.split("=", 1)[1])
    if seeds:
        out["lineage_seeds"] = sorted(seeds)
    if gens:
        try:
            out["generations"] = sorted(gens, key=int)
        except ValueError:
            out["generations"] = sorted(gens)
    if variants:
        out["variants"] = sorted(variants)
    return out


def lookup_params(
    run_id: str,
    *,
    runs_db: Path | None = None,
    workspace: Path | None = None,
) -> tuple[dict | None, str]:
    """Resolve ``run_id`` -> config params dict. Returns ``(params, source)``
    where ``source`` is one of ``registry`` / ``parquet`` / ``not-found``."""
    if runs_db is not None:
        params = get_run_params(runs_db, run_id)
        if params is not None:
            return params, "registry"
    ws = workspace or Path.cwd()
    db = _find_runs_db_with(run_id, ws)
    if db is not None:
        params = get_run_params(db, run_id)
        if params is not None:
            return params, "registry"
    pq = _params_from_parquet_config(run_id, ws)
    if pq is not None:
        return pq, "parquet"
    return None, "not-found"


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _render_text(run_id: str, params: dict | None, source: str) -> str:
    lines = [f"run_id: {run_id}", f"source: {source}"]
    if params is None:
        lines.append("  (no recorded config found — registry has no row and "
                     "no parquet configuration partition was located)")
        return "\n".join(lines)
    pert = params.get("perturbations")
    if pert:
        lines.append("perturbations (applied):")
        for k, v in (pert.items() if isinstance(pert, dict) else []):
            lines.append(f"  {k} = {v}")
    for key in ("seed", "generations", "max_min", "cache_dir",
                "cache_fingerprint", "resume_dill", "critical_mass_scale",
                "dnaA_synth_prob_from_cache"):
        if key in params:
            lines.append(f"{key}: {params[key]}")
    # Any remaining keys not already shown.
    shown = {"perturbations", "seed", "generations", "max_min", "cache_dir",
             "cache_fingerprint", "resume_dill", "critical_mass_scale",
             "dnaA_synth_prob_from_cache"}
    extra = {k: v for k, v in params.items() if k not in shown}
    if extra:
        lines.append("other:")
        for k, v in extra.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target",
                    help="a figure (.png/.svg), a chart .meta.json, or a bare run_id")
    ap.add_argument("--runs-db", default=None, type=Path,
                    help="explicit per-study runs.db to look in")
    ap.add_argument("--workspace", default=None, type=Path,
                    help="workspace root to search for runs.db / parquet "
                         "configuration partitions (default: cwd)")
    ap.add_argument("--json", action="store_true",
                    help="emit the resolved config as JSON")
    args = ap.parse_args(argv)

    run_id, meta_path = resolve_run_id(args.target)
    if run_id is None:
        msg = {"error": "could not resolve run_id", "target": args.target,
               "meta_path": str(meta_path) if meta_path else None}
        if args.json:
            print(json.dumps(msg, indent=2))
        else:
            print(f"ERROR: could not resolve run_id from {args.target!r}")
            if meta_path and not meta_path.is_file():
                print(f"  (no meta file at {meta_path})")
        return 2

    params, source = lookup_params(
        run_id, runs_db=args.runs_db, workspace=args.workspace)

    if args.json:
        print(json.dumps(
            {"run_id": run_id, "source": source, "params": params,
             "meta_path": str(meta_path) if meta_path else None},
            indent=2, default=str))
    else:
        print(_render_text(run_id, params, source))
    return 0 if params is not None else 1


if __name__ == "__main__":
    sys.exit(main())
