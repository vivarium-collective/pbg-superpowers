"""Backfill the run DB from on-disk emitter artifacts.

Bespoke scripts (ensemble sweeps, ABC pilots) often persist XArray (zarr) or
Parquet stores under ``.pbg/runs/<run_id>/`` without ever recording a row in
``.pbg/composite-runs.db``. The Simulations DB then shows almost nothing even
though the work ran. This module walks ``.pbg/runs`` for emitter stores and
registers each missing run into the ``simulations`` table (the one the
dashboard reads, which carries ``study_slug`` / ``investigation_slug`` for
association), and completes any stale ``running`` rows whose process is long
gone.

Idempotent: a run already present in the DB is skipped. Safe to re-run.

CLI:
    python -m pbg_superpowers.backfill_runs --workspace <ws> [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

# A run is "stale running" if its row says running but it hasn't progressed in
# this long — its launching process is assumed dead, so we complete it.
_STALE_RUNNING_S = 3600.0


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _discover_emitter_runs(workspace: Path) -> list[dict]:
    """One dict per ``.pbg/runs/<run_id>/`` dir holding a zarr or parquet
    store (at any of the common depths). Returns run_id, emitter, n_leaves,
    started/completed (mtime)."""
    runs_dir = workspace / ".pbg" / "runs"
    if not runs_dir.is_dir():
        return []
    out: list[dict] = []
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        zarrs = (list(run_dir.glob("store.zarr"))
                 + list(run_dir.glob("*/store.zarr"))
                 + list(run_dir.glob("*/*/store.zarr")))
        pqs = (list(run_dir.glob("**/configuration"))
               if not zarrs else [])
        emitter = "xarray" if zarrs else ("parquet" if pqs else None)
        if emitter is None:
            continue
        try:
            mtime = run_dir.stat().st_mtime
        except OSError:
            mtime = None
        out.append({
            "run_id": run_dir.name,
            "emitter": emitter,
            "n_leaves": len(zarrs) if zarrs else len(pqs),
            "started_at": mtime,
            "completed_at": mtime,
        })
    return out


def _study_investigation_map(workspace: Path) -> dict[str, str]:
    """Map study_slug -> investigation_slug by reading every
    ``investigations/<slug>/investigation.yaml`` ``studies[]``."""
    out: dict[str, str] = {}
    inv_dir = workspace / "investigations"
    if not inv_dir.is_dir():
        return out
    for invf in sorted(inv_dir.glob("*/investigation.yaml")):
        try:
            inv = yaml.safe_load(invf.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        islug = inv.get("name") or invf.parent.name
        for s in (inv.get("studies") or []):
            slug = s if isinstance(s, str) else (s or {}).get("study")
            if slug:
                out[slug] = islug
    return out


def _resolve_study(run_id: str, study_slugs: list[str]) -> str | None:
    """Best-effort: the study slug sharing the most leading dash-segments with
    run_id (e.g. ``pdmp-03-abc-2d`` -> ``pdmp-03-inference`` via ``pdmp-03``)."""
    rid_segs = run_id.split("-")
    best, best_n = None, 0
    for slug in study_slugs:
        n = 0
        for a, b in zip(rid_segs, slug.split("-")):
            if a == b:
                n += 1
            else:
                break
        # Require at least 2 shared leading segments (e.g. "pdmp-03").
        if n >= 2 and n > best_n:
            best, best_n = slug, n
    return best


def backfill(workspace: Path, *, dry_run: bool = False) -> dict:
    workspace = Path(workspace)
    db = workspace / ".pbg" / "composite-runs.db"
    result = {"inserted": [], "completed_stale": [], "skipped": [], "db": str(db)}
    if not db.is_file():
        result["error"] = f"no run DB at {db}"
        return result

    inv_map = _study_investigation_map(workspace)
    study_slugs = list(inv_map.keys())
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        tbls = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "simulations" not in tbls:
            result["error"] = "no simulations table"
            return result
        sim_cols = {r[1] for r in conn.execute("PRAGMA table_info(simulations)")}
        existing = {r[0] for r in conn.execute("SELECT simulation_id FROM simulations")}

        # 1) Complete stale 'running' rows (completed_at NULL).
        now = datetime.now(tz=timezone.utc).timestamp()
        for r in conn.execute(
                "SELECT simulation_id, started_at FROM simulations "
                "WHERE completed_at IS NULL"):
            sid = r["simulation_id"]
            if not dry_run:
                conn.execute(
                    "UPDATE simulations SET completed_at=? WHERE simulation_id=?",
                    (_iso(now), sid))
            result["completed_stale"].append(sid)

        # 2) Insert missing emitter runs.
        for run in _discover_emitter_runs(workspace):
            rid = run["run_id"]
            if rid in existing:
                result["skipped"].append(rid)
                continue
            study = _resolve_study(rid, study_slugs)
            invslug = inv_map.get(study) if study else None
            cols = ["simulation_id", "name", "started_at", "completed_at"]
            vals = [rid, rid, _iso(run["started_at"]), _iso(run["completed_at"])]
            if "study_slug" in sim_cols:
                cols.append("study_slug"); vals.append(study)
            if "investigation_slug" in sim_cols:
                cols.append("investigation_slug"); vals.append(invslug)
            if "metadata" in sim_cols:
                cols.append("metadata")
                vals.append(f'{{"emitter":"{run["emitter"]}","ensemble_size":{run["n_leaves"]},"backfilled":true}}')
            if not dry_run:
                conn.execute(
                    f"INSERT INTO simulations ({','.join(cols)}) "
                    f"VALUES ({','.join('?' * len(cols))})", vals)
            result["inserted"].append({
                "run_id": rid, "emitter": run["emitter"],
                "study": study, "investigation": invslug,
                "ensemble_size": run["n_leaves"]})
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=".", help="workspace root")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    res = backfill(Path(args.workspace), dry_run=args.dry_run)
    if res.get("error"):
        print("ERROR:", res["error"])
        return 1
    print(f"DB: {res['db']}")
    print(f"completed stale 'running' rows: {len(res['completed_stale'])} {res['completed_stale']}")
    print(f"skipped (already in DB): {len(res['skipped'])}")
    print(f"inserted: {len(res['inserted'])}")
    for r in res["inserted"]:
        print(f"  + {r['emitter']:7} {r['run_id']:24} -> {r['study']} / {r['investigation']} (ensemble={r['ensemble_size']})")
    if args.dry_run:
        print("(dry-run — no writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
