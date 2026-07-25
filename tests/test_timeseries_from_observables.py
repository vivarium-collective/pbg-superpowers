"""Tests for ``TimeSeriesFromObservables`` — the self-contained Viz
class that backs declared ``visualizations[]`` in study.yaml.

Pinned behaviors:
  - Reads observable trajectories directly from a runs.db (no
    upstream bigraph plumbing required).
  - Picks units + description from study.yaml.observables when
    available.
  - Degrades gracefully: missing config, missing db, missing
    observables in the run's emitted state, missing study.yaml — each
    case surfaces an actionable HTML message instead of crashing.
  - Multi-run / multi-observable: one trace per (observable × run)
    with stable colors per observable and dash patterns to separate
    overlapping runs.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from viva_superpowers.visualizations.timeseries_from_observables import (
    TimeSeriesFromObservables,
    _build_traces,
    _label_for_run,
    _load_runs,
    _load_study_observable_meta,
    _render_html,
    _y_axis_label,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_runs_db(
    db_path: Path,
    runs: list[dict],
) -> Path:
    """Build a runs.db that mirrors the dashboard's SQLiteEmitter shape.

    Each ``run`` is ``{run_id, sim_name, params, history: [{step, time,
    state}, ...]}``. Time may live inside ``state["time"]`` or just be
    the row's ``global_time``.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE runs_meta ("
            " run_id TEXT PRIMARY KEY, "
            " sim_name TEXT, "
            " params_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE history ("
            " simulation_id TEXT, "
            " step INTEGER, "
            " global_time REAL, "
            " state TEXT)"
        )
        for r in runs:
            conn.execute(
                "INSERT INTO runs_meta VALUES (?, ?, ?)",
                (r["run_id"], r.get("sim_name"),
                 json.dumps(r.get("params") or {})),
            )
            for h in r.get("history") or []:
                conn.execute(
                    "INSERT INTO history VALUES (?, ?, ?, ?)",
                    (r["run_id"], h["step"], h.get("time", float(h["step"])),
                     json.dumps(h.get("state") or {})),
                )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _make_study_yaml(p: Path, observables: list[dict]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({
        "name": p.parent.name,
        "observables": observables,
    }))
    return p


# ---------------------------------------------------------------------------
# _load_runs
# ---------------------------------------------------------------------------


def test_load_runs_returns_empty_when_path_missing(tmp_path):
    assert _load_runs(None, []) == []
    assert _load_runs("", []) == []
    assert _load_runs(str(tmp_path / "nope.db"), []) == []


def test_load_runs_returns_empty_when_db_has_no_history(tmp_path):
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE runs_meta (run_id TEXT, sim_name TEXT, params_json TEXT)")
    conn.commit()
    conn.close()
    assert _load_runs(str(db), []) == []


def test_load_runs_pulls_observables_and_time_from_state(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "baseline", "params": {"k": 1},
        "history": [
            {"step": 0, "time": 0.0, "state": {"DnaA": 100, "ATP": 0.5}},
            {"step": 1, "time": 0.5, "state": {"DnaA": 110, "ATP": 0.6}},
            {"step": 2, "time": 1.0, "state": {"DnaA": 120, "ATP": 0.7}},
        ],
    }])
    runs = _load_runs(str(db), [])
    assert len(runs) == 1
    r = runs[0]
    assert r["run_id"] == "r-1"
    assert r["sim_name"] == "baseline"
    assert r["params"] == {"k": 1}
    assert r["observables"]["DnaA"] == [100, 110, 120]
    assert r["observables"]["ATP"] == [0.5, 0.6, 0.7]
    # Time axis falls back to global_time when state has no "time" key.
    assert r["time"] == [0.0, 0.5, 1.0]


def test_load_runs_uses_state_time_when_present(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "history": [
            {"step": 0, "time": 999.0, "state": {"time": 0.0, "DnaA": 100}},
            {"step": 1, "time": 999.0, "state": {"time": 0.5, "DnaA": 110}},
        ],
    }])
    runs = _load_runs(str(db), [])
    assert runs[0]["time"] == [0.0, 0.5]


def test_load_runs_filters_by_sources(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [
        {"run_id": "r-1", "sim_name": "baseline", "params": {},
         "history": [{"step": 0, "state": {"DnaA": 1}}]},
        {"run_id": "r-2", "sim_name": "low-te", "params": {},
         "history": [{"step": 0, "state": {"DnaA": 2}}]},
    ])
    runs = _load_runs(str(db), ["baseline"])
    assert [r["run_id"] for r in runs] == ["r-1"]


def test_load_runs_tolerates_malformed_state_rows(tmp_path):
    """A row with non-JSON state shouldn't break the entire load."""
    db = tmp_path / "runs.db"
    _make_runs_db(db, [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "history": [{"step": 0, "state": {"DnaA": 100}}],
    }])
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO history VALUES (?, ?, ?, ?)",
        ("r-1", 1, 1.0, "{not valid json"),
    )
    conn.commit()
    conn.close()
    runs = _load_runs(str(db), [])
    # The good row landed; the malformed one was skipped.
    assert runs[0]["observables"]["DnaA"] == [100]


# ---------------------------------------------------------------------------
# _load_study_observable_meta
# ---------------------------------------------------------------------------


def test_load_study_observable_meta_returns_units(tmp_path):
    yp = _make_study_yaml(tmp_path / "studies" / "s" / "study.yaml", [
        {"name": "DnaA", "units": "molecules", "description": "free DnaA"},
        {"name": "ATP", "units": "fraction"},
    ])
    meta = _load_study_observable_meta(str(yp))
    assert meta["DnaA"]["units"] == "molecules"
    assert meta["DnaA"]["description"] == "free DnaA"
    assert meta["ATP"]["units"] == "fraction"


def test_load_study_observable_meta_reads_non_ascii_under_ascii_locale(tmp_path, monkeypatch):
    """study.yaml is UTF-8; the loader must decode it explicitly so a bare-CLI
    render under an ASCII default locale doesn't crash on non-ASCII prose."""
    yp = tmp_path / "studies" / "s" / "study.yaml"
    yp.parent.mkdir(parents=True)
    yp.write_text(
        "observables:\n"
        "  - name: area\n"
        "    units: µm²\n"            # µm²
        "    description: grows → large\n"  # grows → large
        "    store_path: area\n",
        encoding="utf-8",
    )
    # Emulate an ASCII-default-locale machine: Path.read_text() with no explicit
    # encoding decodes as ASCII (and would raise on the µ/→ bytes). The fix
    # passes encoding="utf-8", so parsing must still succeed.
    import pathlib
    _real_read_text = pathlib.Path.read_text

    def _ascii_default(self, encoding=None, errors=None, newline=None):
        return _real_read_text(self, encoding=encoding or "ascii", errors=errors)

    monkeypatch.setattr(pathlib.Path, "read_text", _ascii_default)

    meta = _load_study_observable_meta(str(yp))
    assert meta["area"]["units"] == "µm²"
    assert "→" in meta["area"]["description"]


def test_load_study_observable_meta_returns_empty_for_missing_file(tmp_path):
    assert _load_study_observable_meta(str(tmp_path / "missing.yaml")) == {}
    assert _load_study_observable_meta(None) == {}
    assert _load_study_observable_meta("") == {}


def test_load_study_observable_meta_tolerates_malformed_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("{not valid yaml: [")
    assert _load_study_observable_meta(str(p)) == {}


def test_load_study_observable_meta_skips_non_dict_observables(tmp_path):
    p = tmp_path / "studies" / "s" / "study.yaml"
    p.parent.mkdir(parents=True)
    p.write_text(yaml.safe_dump({
        "observables": ["bare-string", {"no-name-key": True},
                        {"name": "DnaA", "units": "molecules"}],
    }))
    meta = _load_study_observable_meta(str(p))
    assert list(meta) == ["DnaA"]


# ---------------------------------------------------------------------------
# _build_traces
# ---------------------------------------------------------------------------


def test_build_traces_one_per_observable_when_single_run():
    runs = [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "time": [0, 1, 2],
        "observables": {"DnaA": [100, 110, 120], "ATP": [0.5, 0.6, 0.7]},
    }]
    traces = _build_traces(runs, ["DnaA", "ATP"])
    assert len(traces) == 2
    assert traces[0]["name"] == "DnaA"
    assert traces[1]["name"] == "ATP"
    # Different colors for different observables.
    assert traces[0]["line"]["color"] != traces[1]["line"]["color"]
    # Single run → solid line, no run-label suffix.
    assert traces[0]["line"]["dash"] == "solid"


def test_build_traces_multi_run_distinguishes_with_dash_patterns():
    runs = [
        {"run_id": "r-1", "params": {"te": 10},
         "time": [0, 1], "observables": {"DnaA": [100, 110]}},
        {"run_id": "r-2", "params": {"te": 20},
         "time": [0, 1], "observables": {"DnaA": [200, 220]}},
    ]
    traces = _build_traces(runs, ["DnaA"])
    assert len(traces) == 2
    # Same color (same observable), different dash patterns.
    assert traces[0]["line"]["color"] == traces[1]["line"]["color"]
    assert traces[0]["line"]["dash"] != traces[1]["line"]["dash"]
    # Names include the run label.
    assert "te=10" in traces[0]["name"]
    assert "te=20" in traces[1]["name"]


def test_build_traces_skips_observables_missing_in_run():
    runs = [{
        "run_id": "r-1", "params": {},
        "time": [0, 1], "observables": {"DnaA": [100, 110]},
    }]
    # ATP isn't in the run; no trace generated for it.
    traces = _build_traces(runs, ["DnaA", "ATP"])
    names = [t["name"] for t in traces]
    assert "DnaA" in names
    assert not any("ATP" in n for n in names)


def test_build_traces_synthesizes_x_when_time_missing():
    runs = [{
        "run_id": "r-1", "params": {},
        "observables": {"DnaA": [10, 20, 30]},
    }]
    traces = _build_traces(runs, ["DnaA"])
    assert traces[0]["x"] == [0, 1, 2]


# ---------------------------------------------------------------------------
# _label_for_run
# ---------------------------------------------------------------------------


def test_label_for_run_prefers_params():
    assert _label_for_run({"params": {"te": 20, "fc": 0.7}}, 0) == "fc=0.7, te=20"


def test_label_for_run_falls_back_to_sim_name_then_run_id():
    assert _label_for_run({"params": {}, "sim_name": "calibration"}, 0) == "calibration"
    # Falls through to last 6 chars of run_id when params empty + sim_name is "default".
    assert _label_for_run({"params": {}, "sim_name": "default",
                           "run_id": "abc123def"}, 0) == "123def"


# ---------------------------------------------------------------------------
# _y_axis_label
# ---------------------------------------------------------------------------


def test_y_axis_label_includes_units_when_one_observable():
    meta = {"DnaA": {"units": "molecules"}}
    assert _y_axis_label(meta, ["DnaA"]) == "DnaA (molecules)"


def test_y_axis_label_uses_bare_name_when_units_missing():
    assert _y_axis_label({}, ["DnaA"]) == "DnaA"


def test_y_axis_label_shared_units_collapse_to_single_label():
    meta = {"DnaA": {"units": "fraction"}, "ATP": {"units": "fraction"}}
    assert _y_axis_label(meta, ["DnaA", "ATP"]) == "fraction"


def test_y_axis_label_mixed_units_returns_generic():
    meta = {"DnaA": {"units": "molecules"}, "ATP": {"units": "fraction"}}
    assert _y_axis_label(meta, ["DnaA", "ATP"]) == "value"


def test_y_axis_label_no_units_returns_empty():
    meta = {"DnaA": {}, "ATP": {}}
    assert _y_axis_label(meta, ["DnaA", "ATP"]) == ""


# ---------------------------------------------------------------------------
# _render_html — happy path + degraded paths
# ---------------------------------------------------------------------------


def test_render_html_happy_path_includes_plotly_and_traces(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "default", "params": {"te": 20},
        "history": [
            {"step": 0, "state": {"DnaA": 100, "time": 0.0}},
            {"step": 1, "state": {"DnaA": 110, "time": 0.5}},
        ],
    }])
    yp = _make_study_yaml(tmp_path / "studies" / "s" / "study.yaml", [
        {"name": "DnaA", "units": "molecules"},
    ])
    html = _render_html({
        "observables": ["DnaA"],
        "title": "DnaA over time",
        "_runs_db_path": str(db),
        "_study_yaml_path": str(yp),
    })
    assert "plotly" in html.lower()
    assert "DnaA over time" in html
    # Y-axis title includes units.
    assert "molecules" in html
    # Trace values are inlined as JSON in the script block.
    assert "100" in html and "110" in html


def test_render_html_no_observables_in_config():
    html = _render_html({"_runs_db_path": "/nowhere.db"})
    assert "no observables declared" in html.lower()


def test_render_html_missing_runs_db_gives_actionable_message():
    html = _render_html({
        "observables": ["DnaA"],
        "_runs_db_path": "/definitely/not/here.db",
    })
    assert "no run data yet" in html.lower()
    assert "baseline" in html.lower()  # mentions the fix


def test_render_html_observables_not_in_run_state(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "history": [{"step": 0, "state": {"OtherThing": 1}}],
    }])
    html = _render_html({
        "observables": ["DnaA"],
        "_runs_db_path": str(db),
    })
    # The "no matching observable" branch surfaces the requested name
    # so the operator can spot the typo or emitter-config mismatch.
    assert "were found in any run" in html.lower()
    assert "DnaA" in html


def test_render_html_renders_without_study_yaml(tmp_path):
    """Study YAML is optional — units just get omitted."""
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "history": [
            {"step": 0, "state": {"DnaA": 1}},
            {"step": 1, "state": {"DnaA": 2}},
        ],
    }])
    html = _render_html({
        "observables": ["DnaA"],
        "_runs_db_path": str(db),
        # _study_yaml_path omitted
    })
    assert "plotly" in html.lower()


# ---------------------------------------------------------------------------
# Visualization class integration
# ---------------------------------------------------------------------------


def test_visualization_class_declares_no_inputs():
    """Self-contained — the renderer skips inputs_map plumbing."""
    inst = TimeSeriesFromObservables.__new__(TimeSeriesFromObservables)
    assert inst.inputs() == {}


def test_visualization_class_update_returns_html(tmp_path):
    db = _make_runs_db(tmp_path / "runs.db", [{
        "run_id": "r-1", "sim_name": "default", "params": {},
        "history": [
            {"step": 0, "state": {"DnaA": 1}},
            {"step": 1, "state": {"DnaA": 2}},
        ],
    }])
    inst = TimeSeriesFromObservables.__new__(TimeSeriesFromObservables)
    inst.config = {
        "observables": ["DnaA"],
        "_runs_db_path": str(db),
    }
    result = inst.update({})
    assert isinstance(result, dict)
    assert "html" in result
    assert "plotly" in result["html"].lower()


def test_visualization_class_update_tolerates_missing_config(tmp_path):
    inst = TimeSeriesFromObservables.__new__(TimeSeriesFromObservables)
    # No .config attribute set at all (matches a fresh __new__ instance
    # that the demo path may produce before assignment).
    result = inst.update({})
    assert "no observables declared" in result["html"].lower()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_class_is_exported_from_visualizations_package():
    from viva_superpowers import visualizations
    assert "TimeSeriesFromObservables" in visualizations.__all__
    assert visualizations.TimeSeriesFromObservables is TimeSeriesFromObservables
