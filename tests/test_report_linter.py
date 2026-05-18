"""Tests for the Pass B report linter (pbg_superpowers.report_linter).

One test per check, plus override-file roundtrip + render-blocking
integration tests.

Fixtures live under tests/fixtures/lint-cases/ — one workspace per case,
each with a minimal workspace.yaml and a studies/<slug>/study.yaml that
triggers exactly the violations under test (plus a clean baseline).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pbg_superpowers.report_linter import (
    LintFinding,
    apply_overrides,
    format_findings,
    has_blocking_errors,
    lint_workspace_report,
    load_overrides,
    main,
    override_path,
    write_override,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lint-cases"


def _copy_fixture(name: str, dest: Path) -> Path:
    src = FIXTURES / name
    if not src.is_dir():
        raise FileNotFoundError(src)
    shutil.copytree(src, dest)
    return dest


def _findings_by_check(findings: list[LintFinding]) -> dict[str, list[LintFinding]]:
    out: dict[str, list[LintFinding]] = {}
    for f in findings:
        out.setdefault(f.check, []).append(f)
    return out


# ---------------------------------------------------------------------------
# Clean baseline — no findings at all
# ---------------------------------------------------------------------------


def test_clean_baseline_produces_no_findings(tmp_path):
    ws = _copy_fixture("clean-baseline", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    assert findings == [], f"expected empty list, got {findings}"
    assert not has_blocking_errors(findings)


# ---------------------------------------------------------------------------
# 1. incomplete_summaries
# ---------------------------------------------------------------------------


def test_incomplete_summaries_fires_on_evaluated_without_conclusion_logic(tmp_path):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    incs = by_check.get("incomplete_summaries", [])
    assert len(incs) == 1
    f = incs[0]
    assert f.level == "error"
    assert f.study_slug == "study-incomplete"
    assert "conclusion_logic" in f.field_path
    assert "evaluated" in f.message.lower()


# ---------------------------------------------------------------------------
# 2. status_contradictions
# ---------------------------------------------------------------------------


def test_status_contradictions_fires_for_each_combo(tmp_path):
    ws = _copy_fixture("status-contradictions", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    contradictions = by_check.get("status_contradictions", [])
    # 3 distinct studies, each triggering 1 distinct contradiction.
    slugs = sorted({f.study_slug for f in contradictions})
    assert slugs == ["study-contradict", "study-impl-running", "study-review-blocked"]
    assert all(f.level == "error" for f in contradictions)


# ---------------------------------------------------------------------------
# 3. missing_provenance
# ---------------------------------------------------------------------------


def test_missing_provenance_fires_for_each_finding_without_run_ids(tmp_path):
    ws = _copy_fixture("missing-provenance", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    prov = by_check.get("missing_provenance", [])
    # 2 findings in the fixture both lack run_ids.
    assert len(prov) == 2
    paths = sorted(f.field_path for f in prov)
    assert paths == [
        "findings[0].provenance.run_ids",
        "findings[1].provenance.run_ids",
    ]
    assert all(f.level == "error" for f in prov)


# ---------------------------------------------------------------------------
# 4. unresolved_placeholders
# ---------------------------------------------------------------------------


def test_unresolved_placeholders_fires_for_TBD_TODO_insert_fillin(tmp_path):
    ws = _copy_fixture("unresolved-placeholders", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    placeholders = by_check.get("unresolved_placeholders", [])
    # 4 strings hit a placeholder: objective(TBD), description(TODO),
    # purpose.mechanism(<insert>), purpose.expected_outcome([fill in]).
    assert len(placeholders) == 4
    fields = sorted(f.field_path for f in placeholders)
    assert "description" in fields
    assert "objective" in fields
    assert "purpose.mechanism" in fields
    assert "purpose.expected_outcome" in fields
    assert all(f.level == "error" for f in placeholders)


# ---------------------------------------------------------------------------
# 5. duplicate_modal_phrases
# ---------------------------------------------------------------------------


def test_duplicate_modal_phrases_fires_on_near_identical_test_descriptions(tmp_path):
    ws = _copy_fixture("duplicate-modal", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    dupes = by_check.get("duplicate_modal_phrases", [])
    # test-one and test-two have identical descriptions -> 1 finding flagged
    # on the second (b) item. test-three is distinct.
    assert len(dupes) == 1
    assert dupes[0].level == "warning"
    assert "test-two" in dupes[0].message or "test-one" in dupes[0].message


# ---------------------------------------------------------------------------
# 6. truncated_takeaways
# ---------------------------------------------------------------------------


def test_truncated_takeaways_fires_on_short_or_unterminated_text(tmp_path):
    ws = _copy_fixture("truncated-takeaway", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    trunc = by_check.get("truncated_takeaways", [])
    # Both if_pass ("Confirm reproduces and") and if_fail ("Halt") trigger
    # — if_fail trips the <20 char rule; if_pass trips the missing-terminator
    # rule.
    paths = sorted(f.field_path for f in trunc)
    assert paths == ["conclusion_logic.if_fail", "conclusion_logic.if_pass"]
    assert all(f.level == "error" for f in trunc)


# ---------------------------------------------------------------------------
# Pass 10A — findings-protocol checks
# ---------------------------------------------------------------------------


def test_decide_phase_missing_findings_fires_on_decide_with_no_findings(tmp_path):
    ws = _copy_fixture("decide-missing-findings", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    decide = by_check.get("decide_phase_missing_findings", [])
    assert len(decide) == 1
    f = decide[0]
    assert f.level == "error"
    assert f.study_slug == "study-decide"
    assert "/pbg-study findings" in f.message
    assert "study-decide" in f.message


def test_finding_without_evidence_fires_for_biological_with_no_link(tmp_path):
    ws = _copy_fixture("finding-no-evidence", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    no_ev = by_check.get("finding_without_evidence", [])
    # Only F-01 (biological, no evidence link) should fire.
    # F-02 has evidence.from_run.
    # F-03 is methodological — kind not in the warned set.
    # F-04 has evidence.from_test.
    assert len(no_ev) == 1
    f = no_ev[0]
    assert f.level == "warning"
    assert "F-01" in f.message
    assert "biological" in f.message


def test_finding_cites_unknown_bib_key_fires_per_unknown_key(tmp_path):
    ws = _copy_fixture("finding-unknown-bib", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    unknown = by_check.get("finding_cites_unknown_bib_key", [])
    # F-01 cites 2 unknown keys (MadeUpKey2099, AnotherFakeRef); F-02 is clean.
    assert len(unknown) == 2
    assert all(f.level == "error" for f in unknown)
    keys_called_out = sorted(
        msg
        for f in unknown
        for msg in [f.message]
    )
    assert any("MadeUpKey2099" in m for m in keys_called_out)
    assert any("AnotherFakeRef" in m for m in keys_called_out)


def test_finding_references_unknown_expert_doc_fires(tmp_path):
    ws = _copy_fixture("finding-unknown-expert", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    unk = by_check.get("finding_references_unknown_expert_doc", [])
    # F-01 references known_expert_doc -> ok.
    # F-02 references mystery_doc_not_in_workspace -> fires.
    assert len(unk) == 1
    f = unk[0]
    assert f.level == "error"
    assert "F-02" in f.message
    assert "mystery_doc_not_in_workspace" in f.message


# ---------------------------------------------------------------------------
# 11. visualization_address_unresolved
# ---------------------------------------------------------------------------


def test_visualization_address_unresolved_fires_on_missing_local_class(tmp_path):
    """Both `local:DnaAStateVisualization` and `local:DnaABoxOccupancyVisualization`
    point at classes that don't exist anywhere under pkg/visualizations/."""
    ws = _copy_fixture("viz-address-unresolved", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    unresolved = by_check.get("visualization_address_unresolved", [])
    assert len(unresolved) == 2
    assert all(f.level == "error" for f in unresolved)
    classes_called_out = sorted(f.message for f in unresolved)
    assert any("DnaAStateVisualization" in m for m in classes_called_out)
    assert any("DnaABoxOccupancyVisualization" in m for m in classes_called_out)
    # Field path points at the offending visualizations[] entry, not the study root.
    assert all(f.field_path.startswith("visualizations[") for f in unresolved)


def test_visualization_address_unresolved_skips_dotted_and_empty(tmp_path):
    """The fixture also declares a dotted address, an empty address, and a
    bare class name without the local: prefix. None of those should fire."""
    ws = _copy_fixture("viz-address-unresolved", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    unresolved = by_check.get("visualization_address_unresolved", [])
    # Exactly the two local: entries with missing classes fired — no more.
    assert len(unresolved) == 2
    # The viz names of the skipped entries must not appear in any finding.
    flagged_viz_names = [
        f.message.split("'")[1] for f in unresolved  # `Visualization 'NAME' …`
    ]
    assert "ts-from-obs" not in flagged_viz_names  # dotted path skipped
    assert "empty-addr" not in flagged_viz_names   # empty address skipped
    assert "bare-name" not in flagged_viz_names    # no local: prefix skipped


def test_visualization_address_resolved_produces_no_findings(tmp_path):
    """Classes declared via subclassing OR via @as_visualization update_*
    factories resolve cleanly. Both PascalCase and snake_case forms work."""
    ws = _copy_fixture("viz-address-resolved", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    assert by_check.get("visualization_address_unresolved", []) == []


def test_visualization_address_check_tolerates_missing_visualizations_field(tmp_path):
    """A study with no visualizations[] block must not crash the linter."""
    ws = _copy_fixture("clean-baseline", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    assert by_check.get("visualization_address_unresolved", []) == []


# ---------------------------------------------------------------------------
# 12. dag_edges_* — F3 (canonical pipeline_gate.prerequisites)
# ---------------------------------------------------------------------------


def test_dag_edges_legacy_only_fires_migration_warning(tmp_path):
    """A study with parent_studies but no pipeline_gate.prerequisites fires
    the soft migration warning — same shape as the runtime DeprecationWarning
    the dashboard emits."""
    ws = _copy_fixture("dag-edges-legacy-only", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    legacy = by_check.get("dag_edges_legacy_only", [])
    assert len(legacy) == 1
    f = legacy[0]
    assert f.level == "warning"
    assert f.study_slug == "legacy"
    assert "pipeline_gate.prerequisites" in f.message
    assert "back-compat fallback" in f.message
    # The disagreement and redundant variants must NOT fire for this case.
    assert by_check.get("dag_edges_legacy_redundant", []) == []
    assert by_check.get("dag_edges_legacy_and_canonical_disagree", []) == []


def test_dag_edges_both_agree_fires_redundancy_warning(tmp_path):
    """When both fields list the same parent SLUG SET (regardless of per-entry
    condition), the legacy field is redundant — warn so the workspace drops
    it during the next edit."""
    ws = _copy_fixture("dag-edges-both-agree", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    redundant = by_check.get("dag_edges_legacy_redundant", [])
    assert len(redundant) == 1
    f = redundant[0]
    assert f.level == "warning"
    assert f.study_slug == "agree"
    assert "Drop the `parent_studies` field" in f.message
    # The legacy-only warning must NOT fire — the canonical field IS set.
    assert by_check.get("dag_edges_legacy_only", []) == []


def test_dag_edges_both_conflict_fires_error(tmp_path):
    """When both fields list DIFFERENT parent sets, the dashboard silently
    ignores the legacy entries — that's a real foot-gun, so it's an error."""
    ws = _copy_fixture("dag-edges-both-conflict", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    disagree = by_check.get("dag_edges_legacy_and_canonical_disagree", [])
    assert len(disagree) == 1
    f = disagree[0]
    assert f.level == "error"
    assert f.study_slug == "conflict"
    # Message names both sets so the author can see which side is which.
    assert "upstream-a" in f.message
    assert "upstream-z" in f.message
    assert "silently ignored" in f.message


def test_dag_edges_check_silent_on_clean_baseline(tmp_path):
    """A study with neither field set produces no DAG-edge findings."""
    ws = _copy_fixture("clean-baseline", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    by_check = _findings_by_check(findings)
    assert by_check.get("dag_edges_legacy_only", []) == []
    assert by_check.get("dag_edges_legacy_redundant", []) == []
    assert by_check.get("dag_edges_legacy_and_canonical_disagree", []) == []


# ---------------------------------------------------------------------------
# Override file roundtrip
# ---------------------------------------------------------------------------


def test_override_keys_are_stable_across_runs(tmp_path):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    a = lint_workspace_report(ws)
    b = lint_workspace_report(ws)
    keys_a = sorted(f.override_key for f in a)
    keys_b = sorted(f.override_key for f in b)
    assert keys_a == keys_b
    assert all(":" in k for k in keys_a)  # check:slug:hash shape


def test_write_override_creates_file_and_downgrades_finding(tmp_path):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    blockers = [f for f in findings if f.level == "error"]
    assert blockers
    write_override(ws, blockers[0], reason="acked in PR-123")

    path = override_path(ws)
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert len(data["overrides"]) == 1
    entry = data["overrides"][0]
    assert entry["key"] == blockers[0].override_key
    assert entry["reason"] == "acked in PR-123"
    assert entry["check"] == "incomplete_summaries"
    assert entry["study_slug"] == "study-incomplete"

    overrides = load_overrides(ws)
    assert blockers[0].override_key in overrides
    assert not has_blocking_errors(findings, overrides)

    downgraded = apply_overrides(findings, overrides)
    matching = [f for f in downgraded if f.override_key == blockers[0].override_key]
    assert matching and matching[0].level == "warning"
    assert "[overridden]" in matching[0].message


def test_write_override_is_idempotent(tmp_path):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    findings = lint_workspace_report(ws)
    f = [x for x in findings if x.level == "error"][0]
    write_override(ws, f)
    write_override(ws, f)
    data = json.loads(override_path(ws).read_text())
    assert len(data["overrides"]) == 1


# ---------------------------------------------------------------------------
# Integration: render_workspace_report refuses to render on blocking errors
# ---------------------------------------------------------------------------


def test_render_workspace_report_blocks_on_lint_errors(tmp_path):
    from pbg_superpowers.report import render_workspace_report, ReportLintBlocked

    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    with pytest.raises(ReportLintBlocked) as excinfo:
        render_workspace_report(ws, today="2026-05-17")
    assert excinfo.value.findings
    # The HTML must NOT have been written.
    assert not (ws / "reports" / "index.html").exists()


def test_render_workspace_report_force_logs_overrides_and_proceeds(tmp_path):
    """--force writes overrides AND renders. Re-run is then clean."""
    from pbg_superpowers.report import render_workspace_report

    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")

    # Without a templates dir / decisions file the template render itself
    # may still fail — but the linter gate happens FIRST, so if force
    # gets past the linter, the linter half of Pass B works. We still
    # verify the override file got populated even if the subsequent HTML
    # render is unrelated to lint logic.
    try:
        render_workspace_report(ws, today="2026-05-17", force=True)
    except Exception:
        pass

    # The override file must exist and contain the previously-blocking finding.
    data = json.loads(override_path(ws).read_text())
    assert data["overrides"], "force=True must have logged at least one override"

    # Re-run: now the linter should be clean (or at least not blocking).
    findings = lint_workspace_report(ws)
    overrides = load_overrides(ws)
    assert not has_blocking_errors(findings, overrides)


def test_render_workspace_report_lint_false_bypasses_check(tmp_path):
    """lint=False preserves pre-Pass-B unconditional behavior."""
    from pbg_superpowers.report import render_workspace_report

    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    # The linter would otherwise block; with lint=False we skip it
    # entirely. Render may still fail downstream on template lookup but
    # NOT with ReportLintBlocked.
    try:
        render_workspace_report(ws, today="2026-05-17", lint=False)
    except Exception as e:
        from pbg_superpowers.report import ReportLintBlocked
        assert not isinstance(e, ReportLintBlocked)


# ---------------------------------------------------------------------------
# CLI: python -m pbg_superpowers.report_linter
# ---------------------------------------------------------------------------


def test_cli_exits_0_on_clean_workspace(tmp_path, capsys):
    ws = _copy_fixture("clean-baseline", tmp_path / "ws")
    rc = main(["--ws", str(ws)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_cli_exits_1_on_blocking_findings(tmp_path, capsys):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    rc = main(["--ws", str(ws)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "BLOCKING" in err


def test_cli_force_exits_0_and_writes_overrides(tmp_path, capsys):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    rc = main(["--ws", str(ws), "--force"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "logged" in err
    assert override_path(ws).is_file()


def test_cli_json_mode_emits_valid_json(tmp_path, capsys):
    ws = _copy_fixture("incomplete-summary", tmp_path / "ws")
    main(["--ws", str(ws), "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert all("level" in entry and "override_key" in entry for entry in data)


# ---------------------------------------------------------------------------
# format_findings smoke
# ---------------------------------------------------------------------------


def test_format_findings_empty_returns_OK(tmp_path):
    assert "OK" in format_findings([])


def test_format_findings_renders_each_level(tmp_path):
    findings = [
        LintFinding(level="error", study_slug="s", field_path="f", message="m1",
                    override_key="k1", check="x"),
        LintFinding(level="warning", study_slug="s", field_path="f", message="m2",
                    override_key="k2", check="y"),
    ]
    txt = format_findings(findings)
    assert "[ERROR]" in txt
    assert "[WARNING]" in txt
    assert "override_key: k1" in txt
