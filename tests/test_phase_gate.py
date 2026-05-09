"""Tests for phase_gate: generate_test_module + evaluate_gate."""
from pbg_superpowers.phase_gate import (
    generate_test_module, evaluate_gate, GateResult,
)


def test_generate_test_module_emits_one_test_per_acceptance_entry(tmp_path):
    fm = {
        "phase": 1, "name": "x", "status": "in_progress",
        "prereq_phases": [], "gate_passed": False,
        "acceptance_tests": [
            {"id": "phase-1.t1", "desc": "if A then B", "status": "pending"},
            {"id": "phase-1.t2", "desc": "if C then D", "status": "pending"},
        ],
    }
    out = tmp_path / "test_phases.py"
    generate_test_module(fm, out)
    text = out.read_text()
    assert "def test_phase_1_t1" in text
    assert "def test_phase_1_t2" in text
    # Generated tests are failing placeholders so the gate can detect them
    assert "pytest.fail" in text


def test_evaluate_gate_all_pass():
    fm = {"acceptance_tests": [
        {"id": "phase-1.t1", "desc": "x", "status": "passing"},
        {"id": "phase-1.t2", "desc": "y", "status": "passing"},
    ]}
    res = evaluate_gate(fm)
    assert isinstance(res, GateResult)
    assert res.passed is True


def test_evaluate_gate_any_fail():
    fm = {"acceptance_tests": [
        {"id": "phase-1.t1", "desc": "x", "status": "passing"},
        {"id": "phase-1.t2", "desc": "y", "status": "failing"},
    ]}
    assert evaluate_gate(fm).passed is False


def test_evaluate_gate_pending_means_not_yet():
    fm = {"acceptance_tests": [
        {"id": "phase-1.t1", "desc": "x", "status": "pending"},
    ]}
    res = evaluate_gate(fm)
    assert res.passed is False
    assert "pending" in res.reason.lower()


def test_evaluate_gate_no_tests_means_not_passed():
    """Empty acceptance_tests is not a free pass — fail loudly."""
    res = evaluate_gate({"acceptance_tests": []})
    assert res.passed is False
    assert "no acceptance tests" in res.reason.lower()
