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
