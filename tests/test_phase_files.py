"""Tests for phase_files: create_initial_plan, write_phase_file, parse_plan_status."""
from pathlib import Path

import pytest

from pbg_superpowers.phase_files import (
    create_initial_plan, write_phase_file, parse_plan_status,
)
from pbg_superpowers.phase_md import parse_phase_md


def test_create_initial_plan_writes_files(tmp_path):
    phases_dir = tmp_path / "phases"
    create_initial_plan(
        phases_dir,
        model_name="ecoli-rep",
        phases=[
            {"n": 1, "name": "DnaA accumulation", "objective": "Steady-state pool"},
            {"n": 2, "name": "Initiation trigger",
             "objective": "Threshold-fire of oriC", "prereq_phases": [1]},
        ],
    )
    assert (phases_dir / "plan.md").exists()
    p1 = (phases_dir / "phase-1.md").read_text()
    assert "phase: 1" in p1
    assert "DnaA accumulation" in p1
    assert "status: planned" in p1
    # plan.md has both rows
    plan = (phases_dir / "plan.md").read_text()
    assert "DnaA accumulation" in plan
    assert "Initiation trigger" in plan
    # phase-2.md captures prereq_phases
    p2 = (phases_dir / "phase-2.md").read_text()
    fm2, _ = parse_phase_md(p2)
    assert fm2["prereq_phases"] == [1]


def test_parse_plan_status_reads_fixture(fixtures_dir):
    fm = parse_plan_status(fixtures_dir / "phases" / "phase-1-planned.md")
    assert fm["status"] == "planned"
    fm2 = parse_plan_status(fixtures_dir / "phases" / "phase-2-in_progress.md")
    assert fm2["status"] == "in_progress"
    assert fm2["prereq_phases"] == [1]
    fm3 = parse_plan_status(fixtures_dir / "phases" / "phase-3-gate_pending.md")
    assert fm3["status"] == "gate_pending"
    assert fm3["acceptance_tests"][0]["status"] == "failing"
    assert fm3["parameters_added"][0]["name"] == "fork_speed"
