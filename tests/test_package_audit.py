"""Tests for pbg_superpowers.package_audit."""
from pathlib import Path
import textwrap

import pytest

from pbg_superpowers.package_audit import audit_repo, _has_dep, render_report


def test_has_dep_matches_with_versions():
    assert _has_dep(["bigraph-schema>=0.0.60", "process-bigraph"], "bigraph-schema")
    assert _has_dep(["bigraph-schema>=0.0.60", "process-bigraph"], "process-bigraph")
    assert not _has_dep(["bigraph-schema>=0.0.60"], "bigraph-viz")
    assert _has_dep(["jsonschema[format-nongpl]>=4.21"], "jsonschema")


def test_has_dep_no_false_positives():
    # "bigraph-schema-extras" should NOT match "bigraph-schema"
    assert not _has_dep(["bigraph-schema-extras"], "bigraph-schema")
    assert _has_dep(["bigraph-schema"], "bigraph-schema")
    assert _has_dep(["bigraph-schema>=0.0.60"], "bigraph-schema")
    assert _has_dep(["bigraph-schema==0.0.60"], "bigraph-schema")


def test_audit_compliant_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"
        [project]
        name = "pbg-foo"
        version = "0.1.0"
        requires-python = ">=3.10"
        dependencies = ["bigraph-schema>=0.0.60", "process-bigraph>=0.0.66"]
    """))
    pkg = tmp_path / "pbg_foo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "processes.py").write_text(textwrap.dedent("""
        from process_bigraph import Process
        class MyProcess(Process):
            pass
    """))
    report = audit_repo(tmp_path, run_install=False)
    fails = [c for c in report.checks if c.status == "FAIL"]
    assert not fails, f"unexpected FAILs: {fails}"


def test_audit_missing_bigraph_schema(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1"\ndependencies = []\n')
    report = audit_repo(tmp_path, run_install=False)
    names = {c.name for c in report.checks if c.status == "FAIL"}
    assert "bigraph-schema dep" in names


def test_audit_no_pyproject(tmp_path):
    report = audit_repo(tmp_path, run_install=False)
    assert report.checks[0].status == "FAIL"
    assert "pyproject.toml" in report.checks[0].name


def test_audit_missing_requires_python(tmp_path):
    """Missing requires-python should produce a WARN, not a FAIL."""
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [project]
        name = "pbg-bar"
        version = "0.1.0"
        dependencies = ["bigraph-schema>=0.0.60", "process-bigraph>=0.0.66"]
    """))
    report = audit_repo(tmp_path, run_install=False)
    statuses = {c.name: c.status for c in report.checks}
    assert statuses.get("requires-python") == "WARN"
    fails = [c for c in report.checks if c.status == "FAIL"]
    assert not fails, f"unexpected FAILs: {fails}"


def test_render_report_includes_fixes(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1"\ndependencies=[]\n')
    report = audit_repo(tmp_path, run_install=False)
    rendered = render_report(report)
    assert "=== Audit:" in rendered
    assert "=== Summary ===" in rendered
    assert "FAIL" in rendered
    # Fixes should appear since bigraph-schema is missing
    assert "bigraph-schema" in rendered
