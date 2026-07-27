"""Tests for the L0-L5 study-reproducibility audit (viva_superpowers.study_audit)."""
import json

from viva_superpowers.study_audit import (
    CheckResult,
    StudyAudit,
    AuditReport,
    audit_workspace,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _ws(tmp_path, name="t"):
    (tmp_path / "workspace.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    (tmp_path / "studies").mkdir(exist_ok=True)
    return tmp_path


def _study(tmp_path, slug, text):
    d = tmp_path / "studies" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "study.yaml").write_text(text, encoding="utf-8")
    return d


def _find(audit, name):
    return next((c for c in audit.checks if c.name == name), None)


def _all_checks(report):
    out = []
    for a in list(report.studies) + list(report.investigations):
        out.extend(a.checks)
    return out


def _find_any(report, name):
    return next((c for c in _all_checks(report) if c.name == name), None)


# ---------------------------------------------------------------------------
# Task 1 — data model + enumeration + empty report
# ---------------------------------------------------------------------------

def test_empty_workspace_returns_empty_report(tmp_path):
    _ws(tmp_path)
    report = audit_workspace(tmp_path)
    assert report.studies == []
    assert report.investigations == []
    assert report.hard_failures() == []
    d = report.as_dict()
    assert d["studies"] == []
    assert d["investigations"] == []
    # fully JSON-serializable
    assert json.loads(json.dumps(d)) == d


def test_worst_semantics():
    a = StudyAudit(slug="s", checks=[])
    assert a.worst() == "pass"
    a.checks.append(CheckResult("L0", "x", "pass", "hard"))
    assert a.worst() == "pass"
    a.checks.append(CheckResult("L2", "y", "warn", "soft"))
    assert a.worst() == "warn"
    a.checks.append(CheckResult("L0", "z", "fail", "hard"))
    assert a.worst() == "fail"


def test_enumeration_produces_one_studyaudit_per_study(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1", "name: s1\n")
    _study(tmp_path, "s2", "name: s2\n")
    report = audit_workspace(tmp_path)
    slugs = {a.slug for a in report.studies}
    assert {"s1", "s2"} <= slugs
