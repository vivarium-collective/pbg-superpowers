"""Tests for Task 4: sync wiring + CLI.

Covers:
- study_outcomes.sync includes gate_evaluator in summary
- viva-roll-up CLI via main()
"""
from __future__ import annotations

from pathlib import Path

import pytest

from viva_superpowers import study_io, run_registry
from viva_superpowers import study_outcomes as so


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _study_dir(tmp_path: Path, spec: dict) -> Path:
    d = tmp_path / "studies" / "s1"
    d.mkdir(parents=True)
    study_io.save_yaml_atomic(d / "study.yaml", spec)
    return d


# ---------------------------------------------------------------------------
# sync wiring: summary["gate"]
# ---------------------------------------------------------------------------

class TestSyncGateWiring:
    def test_sync_includes_gate_key(self, tmp_path: Path):
        d = _study_dir(tmp_path, {
            "name": "s1",
            "behavior_tests": [{"name": "t1"}],
            "runs": [],
        })
        summary = so.sync(d)
        assert "gate" in summary

    def test_sync_gate_has_changed_field(self, tmp_path: Path):
        d = _study_dir(tmp_path, {
            "name": "s1",
            "behavior_tests": [{"name": "t1"}],
            "runs": [],
        })
        summary = so.sync(d)
        assert "changed" in summary["gate"] or "error" in summary["gate"]

    def test_sync_gate_idempotent_second_call_not_changed(self, tmp_path: Path):
        d = _study_dir(tmp_path, {
            "name": "s1",
            "behavior_tests": [{"name": "t1"}],
            "runs": [],
        })
        first = so.sync(d)
        assert first["gate"].get("changed") is True  # first time: changed
        second = so.sync(d)
        assert second["gate"].get("changed") is False  # second time: no-op

    def test_sync_writes_gate_evaluator_into_study_yaml(self, tmp_path: Path):
        d = _study_dir(tmp_path, {
            "name": "s1",
            "behavior_tests": [{"name": "t1"}],
            "runs": [{"name": "r1", "status": "completed",
                      "outcomes": {"t1": {"result": "PASS"}}}],
        })
        so.sync(d)
        spec = study_io.load_yaml_mapping(d / "study.yaml")
        ge = spec.get("pipeline_gate", {}).get("gate_evaluator", {})
        assert ge.get("result") == "passed"
        assert ge.get("evaluated_by") == "code"

    def test_sync_gate_does_not_block_on_error(self, tmp_path: Path):
        """If gate_evaluator fails, sync still returns without raising."""
        d = tmp_path / "bad-study"
        d.mkdir()
        # Write a study.yaml that will cause write_gate_evaluator to error
        # (no behavior_tests key — it should still not crash sync)
        study_io.save_yaml_atomic(d / "study.yaml", {"name": "bad"})
        # Should not raise
        summary = so.sync(d)
        assert "gate" in summary


# ---------------------------------------------------------------------------
# CLI: viva-roll-up main()
# ---------------------------------------------------------------------------

class TestRollUpCLI:
    def test_cli_study_creates_gate_evaluator(self, tmp_path: Path):
        ws = tmp_path / "ws"
        sd = ws / "studies" / "my-study"
        sd.mkdir(parents=True)
        (ws / "workspace.yaml").write_text("name: ws\n")
        study_io.save_yaml_atomic(sd / "study.yaml", {
            "name": "my-study",
            "behavior_tests": [{"name": "t1"}],
            "runs": [{"name": "r1", "status": "completed",
                      "outcomes": {"t1": {"result": "PASS"}}}],
        })
        from viva_superpowers.roll_up import main
        rc = main(["--workspace", str(ws), "--study", "my-study"])
        assert rc == 0
        spec = study_io.load_yaml_mapping(sd / "study.yaml")
        assert spec["pipeline_gate"]["gate_evaluator"]["result"] == "passed"

    def test_cli_all_processes_all_studies(self, tmp_path: Path):
        ws = tmp_path / "ws"
        for slug in ("s1", "s2"):
            sd = ws / "studies" / slug
            sd.mkdir(parents=True)
            study_io.save_yaml_atomic(sd / "study.yaml", {
                "name": slug,
                "behavior_tests": [{"name": "t1"}],
                "runs": [],
            })
        (ws / "workspace.yaml").write_text("name: ws\n")
        from viva_superpowers.roll_up import main
        rc = main(["--workspace", str(ws), "--all"])
        assert rc == 0
        for slug in ("s1", "s2"):
            spec = study_io.load_yaml_mapping(ws / "studies" / slug / "study.yaml")
            assert "gate_evaluator" in spec.get("pipeline_gate", {})

    def test_cli_investigation_writes_acceptance(self, tmp_path: Path):
        ws = tmp_path / "ws"
        sd = ws / "studies" / "s1"
        sd.mkdir(parents=True)
        inv_dir = ws / "investigations" / "my-inv"
        inv_dir.mkdir(parents=True)
        (ws / "workspace.yaml").write_text("name: ws\n")
        study_io.save_yaml_atomic(sd / "study.yaml", {
            "name": "s1",
            "behavior_tests": [{"name": "beh-a"}],
            "runs": [{"name": "r1", "status": "completed",
                      "outcomes": {"beh-a": {"result": "PASS"}}}],
        })
        study_io.save_yaml_atomic(inv_dir / "investigation.yaml", {
            "name": "my-inv",
            "acceptance_criteria": [{"study": "s1", "behavior": "beh-a"}],
        })
        from viva_superpowers.roll_up import main
        rc = main(["--workspace", str(ws), "--investigation", "my-inv"])
        assert rc == 0
        spec = study_io.load_yaml_mapping(inv_dir / "investigation.yaml")
        assert spec["executive"]["computed_verdict_status"] == "passing"
