from pathlib import Path
from pbg_superpowers.refresh_viz import refresh_study_viz
from pbg_superpowers.viz_freshness import read_meta, stamp_meta

def _study(tmp):
    d = tmp / "studies" / "s1"; (d / "charts").mkdir(parents=True); return d

def test_refresh_runs_command_and_stamps(tmp_path):
    d = _study(tmp_path)
    spec = {"visualizations": [{
        "name": "v", "chart": "charts/c.svg",
        "render": "python -c \"open('charts/c.svg','w').write('<svg/>')\"",
    }]}
    latest = {"run_id": "r9", "completed_at": 1.0, "generation_id": None,
              "emitter_path": "out/r9"}
    results = refresh_study_viz(d, spec, latest)
    assert (d / "charts" / "c.svg").is_file()
    assert read_meta(d / "charts" / "c.svg")["source_run_id"] == "r9"
    assert results[0]["status"] == "rendered"

def test_refresh_failing_command_keeps_old_meta(tmp_path):
    d = _study(tmp_path)
    (d / "charts" / "c.svg").write_text("OLD")
    stamp_meta(d / "charts" / "c.svg", source_run_id="rOLD",
               generation_id=None, rendered_at=1.0, command="x")
    spec = {"visualizations": [{"name": "v", "chart": "charts/c.svg",
                                "render": "python -c \"import sys; sys.exit(3)\""}]}
    results = refresh_study_viz(d, spec, {"run_id": "rNEW", "completed_at": 2.0})
    assert results[0]["status"] == "error"
    assert read_meta(d / "charts" / "c.svg")["source_run_id"] == "rOLD"  # unchanged

def test_refresh_reports_entries_without_command(tmp_path):
    d = _study(tmp_path)
    spec = {"visualizations": [{"name": "v", "chart": "charts/c.svg"}]}  # no render
    results = refresh_study_viz(d, spec, {"run_id": "r", "completed_at": 1.0})
    assert results[0]["status"] == "needs_manual_refresh"

def test_refresh_no_visualizations(tmp_path):
    d = _study(tmp_path)
    assert refresh_study_viz(d, {}, {"run_id": "r"}) == []


def test_refresh_pinned_stamps_source_run(tmp_path):
    d = _study(tmp_path)
    spec = {"visualizations": [{
        "name": "v", "chart": "charts/c.svg", "source_run": "PINNED",
        "render": "python -c \"open('charts/c.svg','w').write('<svg/>')\""}]}
    refresh_study_viz(d, spec, {"run_id": "LATEST", "completed_at": 1.0})
    assert read_meta(d / "charts" / "c.svg")["source_run_id"] == "PINNED"
