"""Failure-mode tests covering the testable in-process portions of spec §13.

Many of the §13 error modes are runtime-only (gh CLI, network, dashboard server,
submodule pointer divergence) and are exercised by the SKILL.md walkthroughs at
runtime, not by L1 tests. The cases below are the ones with pure-Python entry
points: schema corruption, frontmatter malformations, gate evaluation gaps."""
import pytest

from pbg_superpowers.workspace_yaml import (
    load_workspace, save_workspace, WorkspaceValidationError,
)
from pbg_superpowers.phase_md import parse_phase_md, PhaseValidationError
from pbg_superpowers.phase_gate import evaluate_gate


def test_save_refuses_malformed_workspace_yaml(tmp_path):
    """Per spec §13: 'workspace.yaml malformed' → refuse to mutate; preserve invalid file."""
    p = tmp_path / "workspace.yaml"
    with pytest.raises(WorkspaceValidationError):
        save_workspace(p, {"schema_version": "BAD"})
    assert not p.exists(), "save must NOT write the file when validation fails"


def test_load_rejects_truncated_workspace_yaml(tmp_path):
    """A YAML parse error or schema mismatch must surface — not silently load partial state."""
    p = tmp_path / "workspace.yaml"
    p.write_text("schema_version: 1\nname:\nbroken_token::")  # invalid YAML
    with pytest.raises(Exception):
        load_workspace(p)


def test_phase_md_rejects_no_frontmatter():
    """Per spec §13 (phase frontmatter integrity): refuse to parse a file with no frontmatter."""
    with pytest.raises(PhaseValidationError):
        parse_phase_md("just body, no frontmatter")


def test_phase_md_rejects_unclosed_frontmatter():
    """A frontmatter block without a closing --- is invalid."""
    text = "---\nphase: 1\nname: x\n"  # never closes
    with pytest.raises(PhaseValidationError):
        parse_phase_md(text)


def test_phase_gate_pending_means_not_passed():
    """Per spec §13: 'Phase Gate fails' — pending tests block the gate."""
    fm = {"acceptance_tests": [{"id": "phase-1.t1", "desc": "x", "status": "pending"}]}
    res = evaluate_gate(fm)
    assert res.passed is False
    assert "pending" in res.reason.lower()


def test_phase_gate_no_tests_means_not_passed():
    """An empty acceptance_tests list is not a free pass — fail loudly."""
    res = evaluate_gate({"acceptance_tests": []})
    assert res.passed is False
    assert "no acceptance tests" in res.reason.lower()


def test_phase_gate_failing_blocks_promotion():
    """Per spec §13: any acceptance failure blocks the gate (status: gate_pending in production)."""
    fm = {"acceptance_tests": [
        {"id": "phase-1.t1", "desc": "a", "status": "passing"},
        {"id": "phase-1.t2", "desc": "b", "status": "failing"},
    ]}
    res = evaluate_gate(fm)
    assert res.passed is False
    assert "failing" in res.reason.lower()
