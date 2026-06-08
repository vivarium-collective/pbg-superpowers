"""Read/write accessors over the per-study runs.db `runs_meta` table — the
authoritative record of which runs belong to a study and which is latest.

`runs_meta.params_json` is the run-config provenance slot: a runner records
the decision-relevant knobs (applied perturbations, cache fingerprint, seed,
generations, ...) via :func:`register_run`, and any downstream consumer reads
them back with :func:`get_run_params`. The run_id is the run's
``experiment_id`` (the top parquet partition key), so a figure that carries
its run_id can always be traced back to the exact config that produced it.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

# Minimal DDL for tests + first-time creation. Real DBs are migrated by the
# dashboard's composite_runs connect()/_migrate_runs_meta which ALTERs in
# nullable columns (incl. emitter_path, added in the dashboard phase).
RUNS_META_DDL = """
CREATE TABLE IF NOT EXISTS runs_meta (
    run_id        TEXT PRIMARY KEY,
    spec_id       TEXT NOT NULL,
    label         TEXT,
    params_json   TEXT,
    started_at    REAL NOT NULL,
    completed_at  REAL,
    n_steps       INTEGER,
    status        TEXT NOT NULL,
    sim_name      TEXT,
    generation_id TEXT,
    emitter_path  TEXT
);
"""

_COLS = ("run_id", "spec_id", "started_at", "completed_at", "status",
         "generation_id", "emitter_path")


def latest_run(runs_db: Path) -> dict | None:
    """Newest run row by COALESCE(completed_at, started_at), or None.

    Tolerates older DBs missing the generation_id / emitter_path columns
    (those keys are simply omitted from the returned dict)."""
    runs_db = Path(runs_db)
    if not runs_db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{runs_db}?mode=ro", uri=True, timeout=1.0)
        try:
            have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
            cols = [c for c in _COLS if c in have]
            row = conn.execute(
                f"SELECT {', '.join(cols)} FROM runs_meta "
                "ORDER BY COALESCE(completed_at, started_at) DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        return dict(zip(cols, row)) if row else None
    except sqlite3.Error:
        return None


def register_run(
    runs_db: Path,
    run_id: str,
    *,
    spec_id: str | None = None,
    status: str | None = None,
    params: dict | None = None,
    started_at: float | None = None,
    completed_at: float | None = None,
    emitter_path: str | None = None,
    generation_id: str | None = None,
) -> None:
    """Upsert a ``runs_meta`` row for ``run_id``, writing ``params`` as
    ``params_json`` (the run-config provenance slot).

    Creates the DB + table if absent. ``spec_id`` defaults to ``run_id`` on
    first insert (the column is NOT NULL); ``status`` defaults to ``"recorded"``.
    On re-register (same run_id) only the supplied fields are overwritten —
    passing ``params`` again replaces the stored config; passing ``None``
    leaves the existing value intact. This makes the runner safe to call once
    up-front (status ``running`` + full config) and again at completion
    (status ``complete``) without losing the recorded config.

    ``params`` is JSON-serialised; non-JSON values fall back to ``str``.
    """
    runs_db = Path(runs_db)
    runs_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(runs_db), timeout=5.0)
    try:
        conn.executescript(RUNS_META_DDL)
        have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
        existing = conn.execute(
            "SELECT run_id FROM runs_meta WHERE run_id=?", (run_id,)
        ).fetchone()
        params_json = (
            json.dumps(params, default=str, sort_keys=True)
            if params is not None else None
        )
        now = time.time()
        if existing is None:
            cols = ["run_id", "spec_id", "started_at", "status"]
            vals = [run_id, spec_id or run_id,
                    started_at if started_at is not None else now,
                    status or "recorded"]
            optional = {
                "params_json": params_json,
                "completed_at": completed_at,
                "emitter_path": emitter_path,
                "generation_id": generation_id,
            }
            for col, val in optional.items():
                if val is not None and col in have:
                    cols.append(col)
                    vals.append(val)
            conn.execute(
                f"INSERT INTO runs_meta ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})", vals)
        else:
            sets: list[str] = []
            vals = []
            updates = {
                "spec_id": spec_id,
                "status": status,
                "params_json": params_json,
                "started_at": started_at,
                "completed_at": completed_at,
                "emitter_path": emitter_path,
                "generation_id": generation_id,
            }
            for col, val in updates.items():
                if val is not None and col in have:
                    sets.append(f"{col}=?")
                    vals.append(val)
            if sets:
                vals.append(run_id)
                conn.execute(
                    f"UPDATE runs_meta SET {', '.join(sets)} WHERE run_id=?", vals)
        conn.commit()
    finally:
        conn.close()


def get_run_params(runs_db: Path, run_id: str) -> dict | None:
    """Return the recorded ``params_json`` for ``run_id`` as a dict, or
    ``None`` if the run / DB / column is absent or the JSON is empty.

    Read-only and exception-tolerant (mirrors :func:`latest_run`)."""
    runs_db = Path(runs_db)
    if not runs_db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{runs_db}?mode=ro", uri=True, timeout=1.0)
        try:
            have = {r[1] for r in conn.execute("PRAGMA table_info(runs_meta)")}
            if "params_json" not in have:
                return None
            row = conn.execute(
                "SELECT params_json FROM runs_meta WHERE run_id=?", (run_id,)
            ).fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return None
        return json.loads(row[0])
    except (sqlite3.Error, json.JSONDecodeError):
        return None
