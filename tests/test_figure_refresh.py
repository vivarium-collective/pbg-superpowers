"""Tests for viva_superpowers.figure_refresh (auto-refresh figures from a run)."""
from __future__ import annotations

from pathlib import Path

from viva_superpowers.figure_refresh import (
    latest_run_dir,
    refresh_study_figures,
    study_figure_refresh_commands,
)


def _ws(tmp_path, cmds, with_run=True):
    ws = tmp_path / "ws"
    (ws / "studies" / "s" / "parquet-runs").mkdir(parents=True)
    (ws / "workspace.yaml").write_text(
        "schema_version: 2\nname: w\npackage_path: pkg\n")
    fr = "\n".join(f"  - {c!r}" for c in cmds)
    (ws / "studies" / "s" / "study.yaml").write_text(
        "name: s\nfigure_refresh:\n" + fr + "\n")
    if with_run:
        (ws / "studies" / "s" / "parquet-runs" / "r1").mkdir()
    return ws


def test_dry_run_substitutes_placeholders(tmp_path):
    import sys
    ws = _ws(tmp_path, ["{py} {run} {study} {figdir} {ws}"])
    res = refresh_study_figures(ws, "s", dry_run=True)
    assert res["skipped"] is None
    assert len(res["ran"]) == 1 and res["failed"] == []
    c = res["ran"][0]
    assert c.startswith(sys.executable)  # {py} -> invoking interpreter
    assert "parquet-runs/r1" in c
    assert " s " in c
    assert "reports/figures/s" in c


def test_runs_command_and_writes_figure(tmp_path):
    ws = _ws(tmp_path, ["mkdir -p {figdir} && printf ok > {figdir}/fig.html"])
    res = refresh_study_figures(ws, "s")
    assert res["failed"] == [] and len(res["ran"]) == 1
    assert (ws / "reports" / "figures" / "s" / "fig.html").read_text() == "ok"


def test_skips_when_no_figure_refresh(tmp_path):
    ws = tmp_path / "ws"
    (ws / "studies" / "s").mkdir(parents=True)
    (ws / "workspace.yaml").write_text("schema_version: 2\nname: w\n")
    (ws / "studies" / "s" / "study.yaml").write_text("name: s\n")
    res = refresh_study_figures(ws, "s")
    assert "no figure_refresh" in res["skipped"]
    assert res["ran"] == [] and res["failed"] == []


def test_skips_when_no_runs(tmp_path):
    ws = _ws(tmp_path, ["echo x"], with_run=False)
    res = refresh_study_figures(ws, "s")
    assert "no parquet-runs" in res["skipped"]


def test_records_command_failure(tmp_path):
    ws = _ws(tmp_path, ["false"])  # exits non-zero
    res = refresh_study_figures(ws, "s")
    assert len(res["failed"]) == 1 and res["ran"] == []


def test_latest_run_dir_picks_newest(tmp_path):
    ws = _ws(tmp_path, ["echo x"])
    import os, time
    older = ws / "studies" / "s" / "parquet-runs" / "r1"
    newer = ws / "studies" / "s" / "parquet-runs" / "r2"
    newer.mkdir()
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    assert latest_run_dir(ws, "s").name == "r2"
