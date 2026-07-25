"""Tests for viva_superpowers.package_audit."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import textwrap
import urllib.error

import pytest

from viva_superpowers.package_audit import audit_repo, _has_dep, _check_pypi, render_report


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


# ---------------------------------------------------------------------------
# _check_pypi tests (network calls mocked)
# ---------------------------------------------------------------------------

def _make_urlopen_ctx(data: bytes):
    """Build a mock context-manager response for urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_check_pypi_published():
    import json
    payload = json.dumps({"info": {"version": "1.2.3"}}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_ctx(payload)):
        status, detail = _check_pypi("pbg-foo")
    assert status == "PASS"
    assert "1.2.3" in detail
    assert "pbg-foo" in detail


def test_check_pypi_not_found():
    err = urllib.error.HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None)
    with patch("urllib.request.urlopen", side_effect=err):
        status, detail = _check_pypi("pbg-notreal")
    assert status == "WARN"
    assert "NOT published on PyPI" in detail


def test_check_pypi_server_error():
    err = urllib.error.HTTPError(url="", code=503, msg="Service Unavailable", hdrs=None, fp=None)
    with patch("urllib.request.urlopen", side_effect=err):
        status, detail = _check_pypi("pbg-foo")
    assert status == "WARN"
    assert "503" in detail


def test_check_pypi_offline():
    """Network timeout / connection error should produce WARN, not crash."""
    with patch("urllib.request.urlopen", side_effect=OSError("Network unreachable")):
        status, detail = _check_pypi("pbg-foo")
    assert status == "WARN"
    assert "PyPI check failed" in detail


def test_audit_includes_pypi_check(tmp_path):
    """audit_repo() should include a 'published on PyPI' check when [project].name is set."""
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [project]
        name = "pbg-testpkg"
        version = "0.1.0"
        requires-python = ">=3.10"
        dependencies = ["bigraph-schema>=0.0.60", "process-bigraph>=0.0.66"]
    """))
    import json
    payload = json.dumps({"info": {"version": "0.1.0"}}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_ctx(payload)):
        report = audit_repo(tmp_path, run_install=False)
    names = [c.name for c in report.checks]
    assert "published on PyPI" in names
    pypi_check = next(c for c in report.checks if c.name == "published on PyPI")
    assert pypi_check.status == "PASS"


def test_audit_pypi_check_not_published(tmp_path):
    """WARN (not FAIL) when the package is absent from PyPI."""
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [project]
        name = "pbg-notpublished"
        version = "0.1.0"
        requires-python = ">=3.10"
        dependencies = ["bigraph-schema>=0.0.60", "process-bigraph>=0.0.66"]
    """))
    err = urllib.error.HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None)
    with patch("urllib.request.urlopen", side_effect=err):
        report = audit_repo(tmp_path, run_install=False)
    pypi_check = next((c for c in report.checks if c.name == "published on PyPI"), None)
    assert pypi_check is not None
    assert pypi_check.status == "WARN"
    # A WARN on the PyPI check must NOT be counted as a FAIL
    fails = [c for c in report.checks if c.status == "FAIL"]
    assert not fails, f"unexpected FAILs: {fails}"
