"""End-to-end integration test of the observable data path.

This is the test the v2ecoli session-2 notes (friction #18) asked for: a
single test that pins the contract between pbg-superpowers,
vivarium-dashboard, and pbg-template so a regression in any one of them
fails the suite. Friction notes #13 (mixed-type started_at sort) and
#14 (nested observable resolution) — both fixed in vivarium-dashboard
PR #40 — are the immediate regressions this protects against.

The observable round-trip has five hops:

    1. Step.outputs() declares schema
    2. Composite's emit step records selected fields per tick
    3. SQLiteEmitter writes history.state as a JSON blob
    4. gather_emitter_outputs flattens history rows into per-tick series
    5. _resolve_observable walks dotted paths into per-tick dicts
    6. build_viz_composite wires per-observable values into Visualization input ports
    7. Visualization.update / render produces HTML

Hops 1-3 are exercised by the upstream test suite (process_bigraph +
SQLiteEmitter itself). This test starts at hop 4 by writing a known
runs.db directly, then drives hops 5-7 via the same code paths the
dashboard uses in production. A regression in `_resolve_observable`,
`gather_emitter_outputs`, or `build_viz_composite` fails here.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

# This integration test crosses the pbg-superpowers ↔ vivarium-dashboard
# boundary on purpose — that's the whole point of F5. CI environments that
# don't install vivarium-dashboard (it's a sibling pip-editable dep, not on
# PyPI) skip cleanly instead of failing. Local developers with the dashboard
# installed get the full coverage. Same convention test_workspace_scaffold_snapshot
# uses for its $PBG_TEMPLATE dependency.
pytest.importorskip(
    "vivarium_dashboard",
    reason="integration test needs vivarium-dashboard installed; "
           "pip install -e ../vivarium-dashboard (sibling checkout)",
)

from process_bigraph import Composite, allocate_core

from pbg_superpowers.visualization import Visualization


# ---------------------------------------------------------------------------
# Fixtures: a known runs.db plus a Visualization that surfaces its inputs.
# ---------------------------------------------------------------------------


class _IT_NestedDemoViz(Visualization):
    """Renders the input `count` series as HTML so we can grep the value out.

    Declares `count: list[float]` so build_viz_composite collapses single-run
    series into the input port directly (instead of wrapping in another list).
    """

    def inputs(self):
        return {"count": "list[float]"}

    def update(self, state):
        vals = state.get("count") or []
        return {"html": "<demo>count=" + ",".join(str(v) for v in vals) + "</demo>"}


_IT_NestedDemoViz.__pb_kind__ = "visualization"
_IT_NestedDemoViz.__pb_aliases__ = ["_IT_NestedDemoViz"]


def _make_runs_db_with_nested_state(db_path: Path, *, run_id: str,
                                    ticks: list[dict]) -> None:
    """Populate runs.db's runs_meta + history tables.

    Each `ticks[i]` is the JSON-able state dict emitted at step i — exactly
    the shape SQLiteEmitter would write. Mimics what a Step + emitter would
    have produced without depending on either being installed correctly.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE runs_meta (
                run_id        TEXT PRIMARY KEY,
                spec_id       TEXT NOT NULL,
                label         TEXT,
                params_json   TEXT,
                started_at    REAL NOT NULL,
                completed_at  REAL,
                n_steps       INTEGER,
                status        TEXT NOT NULL,
                sim_name      TEXT,
                pid           INTEGER,
                progress_step INTEGER,
                log_path      TEXT,
                heartbeat_at  REAL
            )
        """)
        conn.execute("""
            CREATE TABLE history (
                simulation_id TEXT,
                step          INTEGER,
                global_time   REAL,
                state         TEXT
            )
        """)
        started = time.time()
        conn.execute(
            "INSERT INTO runs_meta "
            "(run_id, spec_id, label, params_json, started_at, completed_at, "
            " n_steps, status, sim_name, progress_step) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, "demo", "baseline", "{}", started, started + 1.0,
             len(ticks), "complete", "baseline", len(ticks)),
        )
        for i, state in enumerate(ticks):
            conn.execute(
                "INSERT INTO history (simulation_id, step, global_time, state) "
                "VALUES (?, ?, ?, ?)",
                (run_id, i, float(i), json.dumps(state)),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Hop-3-to-7 regression: nested observable path resolves and renders.
# ---------------------------------------------------------------------------


def test_nested_observable_path_renders_into_viz(tmp_path):
    """`listeners.demo.count` is a NESTED path. Before vivarium-dashboard
    PR #40 the gather pipeline flattened only top-level keys, so the viz
    received an empty `count` input and silently rendered a "no data"
    placeholder. Pinning the fix: a viz declaring
    `inputs_map: count: listeners.demo.count` MUST end up with the values."""
    from vivarium_dashboard.lib.investigations import render_visualizations

    study_dir = tmp_path / "ws" / "studies" / "demo"
    study_dir.mkdir(parents=True)
    db_path = study_dir / "runs.db"

    # 5 ticks of nested state — each tick has a different `count` value.
    ticks = [
        {"listeners": {"demo": {"count": float(i * 10)}}, "time": float(i)}
        for i in range(5)
    ]
    _make_runs_db_with_nested_state(db_path, run_id="run-nested", ticks=ticks)

    core = allocate_core()
    core.register_link("_IT_NestedDemoViz", _IT_NestedDemoViz)
    registry = {"_IT_NestedDemoViz": _IT_NestedDemoViz}

    spec = {
        "name": "demo",
        "visualizations": [{
            "name": "nested-demo-viz",
            "address": "local:_IT_NestedDemoViz",
            "config": {"inputs_map": {"count": "listeners.demo.count"}},
        }],
    }

    def build_and_run(viz_doc, _registry):
        composite = Composite({"state": viz_doc}, core=core)
        composite.run(1)
        html = composite.state.get("output_store")
        if isinstance(html, dict):
            html = html.get("value") or html.get("_value") or ""
        return html if isinstance(html, str) else ""

    paths = render_visualizations(
        spec, study_dir, "demo", core_registry=registry,
        build_and_run=build_and_run,
    )
    assert len(paths) == 1
    html = paths[0].read_text()

    # Every tick value MUST appear in the rendered output.
    for i in range(5):
        assert str(float(i * 10)) in html, (
            f"missing tick {i} value in rendered HTML: {html!r}"
        )
    # The viz wrapper proves the value flowed through build_viz_composite
    # rather than coming from a placeholder.
    assert "<demo>count=" in html


def test_top_level_observable_path_still_works(tmp_path):
    """The PR #40 fix added nested-path support without breaking the flat
    case. A viz pointed at a top-level key must still see the values."""
    from vivarium_dashboard.lib.investigations import render_visualizations

    study_dir = tmp_path / "ws" / "studies" / "demo-flat"
    study_dir.mkdir(parents=True)
    db_path = study_dir / "runs.db"

    ticks = [{"count": float(i * 10), "time": float(i)} for i in range(3)]
    _make_runs_db_with_nested_state(db_path, run_id="run-flat", ticks=ticks)

    core = allocate_core()
    core.register_link("_IT_NestedDemoViz", _IT_NestedDemoViz)
    registry = {"_IT_NestedDemoViz": _IT_NestedDemoViz}

    spec = {
        "name": "demo-flat",
        "visualizations": [{
            "name": "flat-demo-viz",
            "address": "local:_IT_NestedDemoViz",
            "config": {"inputs_map": {"count": "count"}},
        }],
    }

    def build_and_run(viz_doc, _registry):
        composite = Composite({"state": viz_doc}, core=core)
        composite.run(1)
        html = composite.state.get("output_store")
        if isinstance(html, dict):
            html = html.get("value") or html.get("_value") or ""
        return html if isinstance(html, str) else ""

    paths = render_visualizations(
        spec, study_dir, "demo-flat", core_registry=registry,
        build_and_run=build_and_run,
    )
    html = paths[0].read_text()
    for i in range(3):
        assert str(float(i * 10)) in html


def test_missing_observable_renders_error_stub_not_silent_blank(tmp_path):
    """A viz pointing at a nonexistent observable must surface as an error
    stub HTML (or at least an empty-data marker), not silently render
    nothing. The render_visualizations harness catches exceptions and
    writes an error stub — pinning that behavior."""
    from vivarium_dashboard.lib.investigations import render_visualizations

    study_dir = tmp_path / "ws" / "studies" / "demo-missing"
    study_dir.mkdir(parents=True)
    db_path = study_dir / "runs.db"

    ticks = [{"unrelated": 1.0, "time": float(i)} for i in range(3)]
    _make_runs_db_with_nested_state(db_path, run_id="run-missing", ticks=ticks)

    core = allocate_core()
    core.register_link("_IT_NestedDemoViz", _IT_NestedDemoViz)
    registry = {"_IT_NestedDemoViz": _IT_NestedDemoViz}

    spec = {
        "name": "demo-missing",
        "visualizations": [{
            "name": "missing-viz",
            "address": "local:_IT_NestedDemoViz",
            "config": {"inputs_map": {"count": "does.not.exist"}},
        }],
    }

    def build_and_run(viz_doc, _registry):
        composite = Composite({"state": viz_doc}, core=core)
        composite.run(1)
        html = composite.state.get("output_store")
        if isinstance(html, dict):
            html = html.get("value") or html.get("_value") or ""
        return html if isinstance(html, str) else ""

    paths = render_visualizations(
        spec, study_dir, "demo-missing", core_registry=registry,
        build_and_run=build_and_run,
    )
    html = paths[0].read_text()
    # Must not be a totally empty string — either an empty-data marker from
    # the viz's own render OR an error stub from render_visualizations.
    assert html, "missing-observable case rendered as empty string"


# ---------------------------------------------------------------------------
# Friction #13 regression: simulations_index merges runs_meta (REAL) and
# simulations (TEXT ISO) timestamps without raising str < float TypeError.
# ---------------------------------------------------------------------------


def _make_mixed_timestamp_workspace(tmp_path: Path) -> Path:
    """Build a workspace whose runs.db has BOTH a runs_meta row (REAL ts)
    AND a simulations row (TEXT ISO ts), reproducing the friction #13 case."""
    ws = tmp_path / "ws-mixed"
    study_dir = ws / "studies" / "mixed"
    study_dir.mkdir(parents=True)
    db_path = study_dir / "runs.db"
    conn = sqlite3.connect(str(db_path))
    try:
        # runs_meta with REAL started_at
        conn.execute("""
            CREATE TABLE runs_meta (
                run_id        TEXT PRIMARY KEY,
                spec_id       TEXT NOT NULL,
                label         TEXT,
                params_json   TEXT,
                started_at    REAL NOT NULL,
                completed_at  REAL,
                n_steps       INTEGER,
                status        TEXT NOT NULL,
                sim_name      TEXT,
                pid           INTEGER,
                progress_step INTEGER,
                log_path      TEXT,
                heartbeat_at  REAL
            )
        """)
        conn.execute(
            "INSERT INTO runs_meta (run_id, spec_id, started_at, status, sim_name) "
            "VALUES ('run-real', 'mixed', 1700000000.0, 'complete', 'baseline')"
        )
        # simulations (process_bigraph SQLiteEmitter schema) with TEXT ISO started_at.
        # Columns mirror what vivarium_dashboard.lib.simulations_index._read_sqlite_emitter
        # selects — drift here means the test fires a clear "schema changed"
        # signal rather than a confusing failure inside the dashboard reader.
        conn.execute("""
            CREATE TABLE simulations (
                simulation_id    TEXT PRIMARY KEY,
                name             TEXT,
                started_at       TEXT,
                completed_at     TEXT,
                elapsed_seconds  REAL,
                n_steps          INTEGER,
                emit_schema      TEXT,
                study_slug       TEXT,
                investigation_slug TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE history (
                simulation_id TEXT,
                step          INTEGER,
                global_time   REAL,
                state         TEXT
            )
        """)
        conn.execute(
            "INSERT INTO simulations (simulation_id, name, started_at, n_steps) "
            "VALUES ('run-iso', 'baseline', '2026-05-17T05:19:57Z', 5)"
        )
        conn.commit()
    finally:
        conn.close()
    return ws


def test_simulations_index_handles_mixed_timestamp_sources(tmp_path):
    """Friction #13 (vivarium-dashboard PR #40 part 1): the moment a
    workspace's runs.db has both runs_meta (REAL ts) and simulations (TEXT
    ISO ts) rows, the sort key would raise `TypeError: str < float` and
    the whole Simulations tab went empty. Pin the fix."""
    from vivarium_dashboard.lib.simulations_index import list_simulations

    ws = _make_mixed_timestamp_workspace(tmp_path)

    # Must not raise. Must return both rows. Must sort them deterministically
    # (newer first — the TEXT ISO is 2026, so it wins over the 2023 REAL).
    rows = list_simulations(ws)
    ids = [r["run_id"] for r in rows]
    assert "run-real" in ids
    assert "run-iso" in ids
    # Newer-first: the 2026 ISO row comes before the 2023 REAL row.
    assert ids.index("run-iso") < ids.index("run-real")


# ---------------------------------------------------------------------------
# Discovery tests — ensure the cross-repo imports themselves don't break.
# ---------------------------------------------------------------------------


def test_dashboard_lib_imports_resolve():
    """Smoke test: every dashboard library symbol this file relies on must
    import cleanly. If vivarium-dashboard renames or moves any of these,
    this test fires first instead of a confusing AttributeError deep inside
    one of the round-trip tests."""
    from vivarium_dashboard.lib.investigations import (  # noqa: F401
        _resolve_observable, build_viz_composite,
        gather_emitter_outputs, render_visualizations,
    )
    from vivarium_dashboard.lib.simulations_index import (  # noqa: F401
        list_simulations,
    )


def test_pbg_runner_exposes_run_context():
    """Smoke test: pbg_superpowers.runner.pbg_runner is the canonical
    context manager workspaces use to populate runs_meta. If its signature
    drifts, this fires before downstream tests that depend on it."""
    import inspect
    from pbg_superpowers.runner import pbg_runner, RunContext

    sig = inspect.signature(pbg_runner)
    # Pin the keyword-only contract — name changes here mean every workspace's
    # runner script breaks.
    for required in ("study", "name"):
        assert required in sig.parameters, (
            f"pbg_runner kwarg '{required}' dropped — workspaces will break"
        )

    # RunContext fields the dashboard reads via gather_emitter_outputs.
    for required in ("run_id", "db_path", "emitter_config"):
        assert hasattr(RunContext, "__dataclass_fields__"), (
            "RunContext must remain a dataclass"
        )
        assert required in RunContext.__dataclass_fields__, (
            f"RunContext field '{required}' dropped"
        )
