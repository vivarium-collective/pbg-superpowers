"""Benchmark run collectors — turn an already-run study into scored artifacts.

The pure, AI-free half of the study-automation benchmark's run harness (spec §4):
given a study the loop has already driven (its `.pbg/loop/<study>.json` +
`study.yaml`), collect the trial's artifacts and score them via `benchmark_score`.
The *dispatch* half (scaffold a study per item, run `/viva-model-build --autonomous`)
is agent work in the `/viva-benchmark` skill — it calls these collectors after each
loop finishes. Pure: reads workspace files + git-free version capture; no loop, no
LLM, no process_bigraph/workbench import.
"""
from __future__ import annotations

import yaml

from viva_superpowers import benchmark_score, loop_state, paths, test_audit


def collect_trial_artifacts(ws_root, study: str) -> dict:
    """The `artifacts` dict `benchmark_score.build_trial_report` consumes:
    the study's loop_state, the deterministic audit gate over its (locked) Tests,
    and those behavior_tests. Best-effort — a missing study/loop yields empty
    pieces (the scorer then reads it as an incomplete/ungraded trial)."""
    ls = loop_state.load(ws_root, study) or {}
    spec = {}
    try:
        sf = paths.workspace_dir("studies", root=ws_root) / study / "study.yaml"
        if sf.is_file():
            spec = yaml.safe_load(sf.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        spec = {}
    behavior_tests = spec.get("behavior_tests") or spec.get("expected_behavior") or []
    try:
        gate = test_audit.audit_gate(test_audit.build_audit_report(spec))
    except Exception:  # noqa: BLE001
        gate = "fail"
    return {"loop_state": ls, "audit_gate": gate, "behavior_tests": behavior_tests}


def capture_variant(*, skills_label: str = "", rubric_prompt_version: str = "1") -> dict:
    """The framework variant identity recorded in the report (spec §6) so two runs
    are comparable and diff-able. The installed viva_superpowers version pins the
    plugin; `skills_label` is a human tag ("audit-v2"); the rubric prompt version
    pins the LLM-judge half."""
    from viva_superpowers import __version__ as vsp_version
    return {"viva_superpowers_version": vsp_version,
            "skills_label": skills_label,
            "rubric_prompt_version": rubric_prompt_version}


def score_suite(trials: list, *, suite: str = "", variant: dict | None = None,
                ws_root=None) -> dict:
    """Collect + score every trial → a benchmark_report/v1. Each trial is
    ``{"item": <item dict>, "study": <slug>}`` (the loop already ran it in
    ``ws_root``); or ``{"item": ..., "artifacts": <pre-collected dict>}`` to skip
    collection. A trial that errors collecting scores against empty artifacts,
    never aborting the suite."""
    scored = []
    for t in trials:
        item = t.get("item") or {}
        artifacts = t.get("artifacts")
        if artifacts is None:
            try:
                artifacts = collect_trial_artifacts(ws_root, t.get("study"))
            except Exception:  # noqa: BLE001
                artifacts = {"loop_state": {}, "audit_gate": "fail", "behavior_tests": []}
        scored.append({"item": item, "report": benchmark_score.build_trial_report(item, artifacts)})
    return benchmark_score.aggregate(scored, suite=suite, variant=variant or {})
