"""The hard visualization gate: a study that DECLARES completion must show
≥1 visualization on a rendered surface, or the linter errors (blocking).

Counterpart to the warning-level ``missing_visualizations`` (which applies while
a study is still in design). Uses the direct ``_LintContext`` call style of the
``viz_stale`` tests — ``WorkspacePaths.load`` tolerates a missing workspace.yaml
and falls back to flat ``studies/<slug>/`` under the tmp root.
"""
from __future__ import annotations

from viva_superpowers.report_linter import (
    _LintContext,
    _check_status_claims_done_no_visualizations,
)

CHECK = "status_claims_done_no_visualizations"


def _findings(ws_root, slug, spec):
    ctx = _LintContext(ws_root=ws_root, slug=slug, spec=spec)
    _check_status_claims_done_no_visualizations(ctx)
    return [f for f in ctx.findings if f.check == CHECK]


def test_completed_study_without_viz_is_a_blocking_error(tmp_path):
    found = _findings(tmp_path, "s1", {"status": "completed", "visualizations": []})
    assert len(found) == 1
    f = found[0]
    assert f.level == "error"
    assert f.field_path == "visualizations"
    assert "declares completion" in f.message


def test_gate_passed_and_evaluated_also_trigger(tmp_path):
    assert _findings(tmp_path, "s1", {"gate_status": "passed"})
    assert _findings(tmp_path, "s2", {"evaluation_status": "evaluated"})


def test_completed_study_with_declared_visualization_is_silent(tmp_path):
    spec = {"status": "completed",
            "visualizations": [{"name": "ladder", "address": "local:RecruitmentLadder"}]}
    assert _findings(tmp_path, "s1", spec) == []


def test_completed_study_with_embed_visualization_is_silent(tmp_path):
    spec = {"gate_status": "passed",
            "embed_visualizations": [{"name": "x", "html_path": "viz/x.html"}]}
    assert _findings(tmp_path, "s1", spec) == []


def test_completed_study_with_on_disk_chart_is_silent(tmp_path):
    sd = tmp_path / "studies" / "s1" / "viz"
    sd.mkdir(parents=True)
    (sd / "mechanism-ladder.html").write_text("<div>chart</div>", encoding="utf-8")
    assert _findings(tmp_path, "s1", {"status": "completed"}) == []


def test_in_progress_study_without_viz_does_not_error(tmp_path):
    # Still in design → the warning-level missing_visualizations applies, but the
    # hard gate must NOT fire (it only binds studies that claim completion).
    assert _findings(tmp_path, "s1", {"status": "in-progress", "visualizations": []}) == []


def test_workspace_pseudo_slug_is_skipped(tmp_path):
    assert _findings(tmp_path, "<workspace>", {"status": "completed"}) == []
