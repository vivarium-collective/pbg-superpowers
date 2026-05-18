"""Runner-side bookkeeping for v2-style study runners.

A ``pbg_runner(...)`` context manager wraps a study's per-sim runner so it
writes a ``runs_meta`` row at start, configures a SQLiteEmitter pointed at
``studies/<study>/runs.db``, and marks completion (or ``orphaned`` on
crash) at end. Pairs with ``vivarium_dashboard.lib.composite_runs``: the
schema this module bootstraps is exactly what the dashboard's auto-viz
panel reads, so any run wrapped this way shows up automatically.

Goal: a study runner that previously wrote raw JSON to ``out/<study>/``
and was invisible to the dashboard becomes::

    from pbg_superpowers.runner import pbg_runner

    with pbg_runner(study='dnaa-01-expression-dynamics',
                    name='baseline-seed0',
                    params={'seed': 0}) as run:
        # run.emitter_config is ready to hand to whatever emitter-setup
        # mechanism the workspace prefers (v2ecoli's set_emitter_override,
        # vivarium_dashboard.inject_sqlite_emitter, etc.).
        with workspace_emitter(**run.emitter_config):
            composite = build_composite('baseline', ...)
            composite.run(duration)
            run.n_steps = composite.step_count

On exit, ``runs_meta.status`` becomes ``'complete'`` (or ``'orphaned'`` if
an exception escaped the block). The SQLiteEmitter the runner installs
fills the sibling ``history`` table — same db, same simulation_id.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Schema (mirrors vivarium_dashboard.lib.composite_runs)
# ---------------------------------------------------------------------------
# We keep an in-tree copy to avoid a runtime dep on vivarium-dashboard: the
# dashboard's connect() does the same bootstrap, so a runs.db produced here
# is byte-compatible. If the dashboard later evolves the schema we mirror
# the new columns via the same ALTER pattern.

_SCHEMA_RUNS_META = """
CREATE TABLE IF NOT EXISTS runs_meta (
    run_id        TEXT PRIMARY KEY,
    spec_id       TEXT NOT NULL,
    label         TEXT,
    params_json   TEXT,
    started_at    REAL NOT NULL,
    completed_at  REAL,
    n_steps       INTEGER,
    status        TEXT NOT NULL,
    sim_name      TEXT
);
"""

_INDEX_RUNS_META = """
CREATE INDEX IF NOT EXISTS idx_runs_meta_spec ON runs_meta(spec_id);
"""

_NEW_COLUMNS = {
    "sim_name": "TEXT",
    "pid": "INTEGER",
    "progress_step": "INTEGER",
    "log_path": "TEXT",
    "heartbeat_at": "REAL",
}


def _bootstrap(conn: sqlite3.Connection) -> None:
    conn.execute(_SCHEMA_RUNS_META)
    conn.execute(_INDEX_RUNS_META)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs_meta)")}
    for col, sqltype in _NEW_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE runs_meta ADD COLUMN {col} {sqltype}")
    conn.commit()


def _generate_run_id(spec_id: str, params: dict | None, ts: float) -> str:
    """Same shape as composite_runs.generate_run_id: spec_id__<int-ts>__<6hex>."""
    payload = json.dumps(
        {"spec_id": spec_id, "params": params or {}, "ts": int(ts)},
        sort_keys=True,
    )
    short = hashlib.sha1(payload.encode()).hexdigest()[:6]
    return f"{spec_id}__{int(ts)}__{short}"


def _find_workspace_root(start: Path | None = None) -> Path | None:
    cur = Path(start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        if (d / "workspace.yaml").is_file():
            return d
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    """Yielded by ``pbg_runner``. Mutable; the runner sets ``n_steps`` etc.

    Fields:
      run_id:         deterministic run id; also the SQLiteEmitter simulation_id.
      db_path:        path to studies/<study>/runs.db (the file being written).
      emitter_config: kwargs ready to pass to a workspace's SQLiteEmitter setup.
                      Always populated with file_path/db_file/simulation_id/name.
      n_steps:        runner should set this before exit to the actual step count.
      _conn:          private; the open sqlite connection.
    """
    run_id: str
    db_path: Path
    emitter_config: dict[str, Any]
    n_steps: int = 0
    _conn: sqlite3.Connection | None = field(default=None, repr=False)

    def heartbeat(self, progress_step: int) -> None:
        """Update progress_step + heartbeat_at; cheap, safe to call often."""
        if self._conn is None:
            return
        self._conn.execute(
            "UPDATE runs_meta SET progress_step=?, heartbeat_at=? WHERE run_id=?",
            (progress_step, time.time(), self.run_id),
        )
        self._conn.commit()


@contextlib.contextmanager
def pbg_runner(
    *,
    study: str,
    name: str,
    spec_id: str | None = None,
    params: dict | None = None,
    workspace_root: str | Path | None = None,
    db_file: str | Path | None = None,
    subsample: int = 1,
) -> Iterator[RunContext]:
    """Open studies/<study>/runs.db, register a run, yield a RunContext.

    ``study`` is the study slug (e.g. ``'dnaa-01-expression-dynamics'``).
    ``name`` is the simulation_set entry name (e.g. ``'baseline-seed0'``);
    the dashboard groups runs by ``sim_name`` so make it readable.

    ``spec_id`` defaults to ``study`` — same field the dashboard uses to
    group runs under a study card. Override only if you have a separate
    composite spec (e.g. a variant id) you want to track.

    If ``workspace_root`` is None, walks up from cwd looking for
    ``workspace.yaml``. If ``db_file`` is None, defaults to
    ``<workspace_root>/studies/<study>/runs.db``.

    On normal exit, the run row is marked ``'complete'``. On exception, it
    is marked ``'orphaned'`` and the exception is re-raised.
    """
    if workspace_root is None:
        workspace_root = _find_workspace_root()
        if workspace_root is None:
            raise RuntimeError(
                "pbg_runner: no workspace_root given and no workspace.yaml "
                "found walking up from cwd; pass workspace_root explicitly "
                "or run from inside a workspace.")
    workspace_root = Path(workspace_root).resolve()

    if db_file is None:
        db_file = workspace_root / "studies" / study / "runs.db"
    db_path = Path(db_file).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    sid = spec_id or study
    run_id = _generate_run_id(sid, params, started_at)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _bootstrap(conn)

    conn.execute(
        "INSERT INTO runs_meta "
        "(run_id, spec_id, label, params_json, started_at, status, "
        " n_steps, sim_name, progress_step) "
        "VALUES (?, ?, ?, ?, ?, 'running', 0, ?, 0)",
        (run_id, sid, name, json.dumps(params or {}), started_at, name),
    )
    conn.commit()

    emitter_config: dict[str, Any] = {
        "file_path": str(db_path.parent),
        "db_file": db_path.name,
        "simulation_id": run_id,
        "name": name,
    }
    if subsample != 1:
        emitter_config["subsample"] = subsample

    ctx = RunContext(
        run_id=run_id,
        db_path=db_path,
        emitter_config=emitter_config,
        _conn=conn,
    )

    status = "complete"
    try:
        yield ctx
    except BaseException:
        status = "orphaned"
        raise
    finally:
        try:
            conn.execute(
                "UPDATE runs_meta "
                "SET completed_at=?, n_steps=?, status=? WHERE run_id=?",
                (time.time(), ctx.n_steps, status, run_id),
            )
            conn.commit()
        finally:
            conn.close()


__all__ = ["pbg_runner", "RunContext"]
