"""TDD tests for pbg_superpowers.feedback_actions (SP3b — feedback → action).

The feedback loop dead-ends today at a free-text status string. SP3b adds a
deterministic ``actions:`` surface (parallel to ``responses:``) keyed by a
stable ``feedback_item_id`` and apply primitives that turn an open feedback
item into a tracked, applied action.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


@pytest.fixture
def ws(tmp_path) -> Path:
    """Workspace with a workspace.yaml so WorkspacePaths.load() works."""
    (tmp_path / "workspace.yaml").write_text("name: test-ws\n")
    (tmp_path / "investigations").mkdir()
    (tmp_path / "studies").mkdir()
    return tmp_path


# ── feedback_item_id ──────────────────────────────────────────────────────────


def test_feedback_item_id_stable():
    from pbg_superpowers.feedback_actions import feedback_item_id

    a = feedback_item_id("study-s1", "2026-06-10T00:00", "alice")
    assert a == feedback_item_id("study-s1", "2026-06-10T00:00", "alice")  # stable
    assert a != feedback_item_id("study-s1", "2026-06-10T00:00", "bob")    # author
    assert a != feedback_item_id("study-s1", "2026-06-11T00:00", "alice")  # ts
    assert a != feedback_item_id("study-s2", "2026-06-10T00:00", "alice")  # section
    assert isinstance(a, str) and a


# ── study_feedback_actions (pure aggregator) ──────────────────────────────────


def test_actions_empty_when_no_investigations(ws):
    from pbg_superpowers.feedback_actions import study_feedback_actions

    res = study_feedback_actions(ws, "foo")
    assert res == {"items": [], "summary": {"open": 0, "applied": 0, "dismissed": 0, "total": 0}}


def test_open_when_no_action(ws):
    from pbg_superpowers.feedback_actions import study_feedback_actions

    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1", "report_id": "rpt-1"},
            "annotations": {
                "study-foo": [
                    {"ts": "2026-01-01T10:00:00Z", "author": "Alice", "text": "Needs X"},
                ],
                "study-bar": [
                    {"ts": "2026-01-01T08:00:00Z", "author": "Bob", "text": "other study"},
                ],
            },
        },
    )
    res = study_feedback_actions(ws, "foo")
    assert len(res["items"]) == 1
    it = res["items"][0]
    assert it["item_id"]
    assert it["section"] == "study-foo"
    assert it["text"] == "Needs X"
    assert it["status"] == "open"
    assert it.get("action") is None
    assert res["summary"] == {"open": 1, "applied": 0, "dismissed": 0, "total": 1}


def test_actions_join_annotation_and_action(ws):
    from pbg_superpowers.feedback_actions import feedback_item_id, study_feedback_actions

    iid = feedback_item_id("study-foo", "2026-01-01T10:00:00Z", "Alice")
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1"},
            "annotations": {
                "study-foo": [
                    {"ts": "2026-01-01T10:00:00Z", "author": "Alice", "text": "Calibrate"},
                ],
            },
            "actions": {
                iid: {
                    "kind": "next_action",
                    "target_study": "foo",
                    "target_finding": "F-01",
                    "proposed_text": "Calibrate Y to match Z",
                    "status": "open",
                },
            },
        },
    )
    res = study_feedback_actions(ws, "foo")
    it = res["items"][0]
    assert it["item_id"] == iid
    assert it["text"] == "Calibrate"
    assert it["status"] in ("open", "applied", "dismissed")
    assert it["action"]["kind"] in ("next_action", "finding", "design-edit", "study-seed")
    assert it["action"]["proposed_text"] == "Calibrate Y to match Z"
    assert "open" in res["summary"]


def test_actions_status_applied_and_dismissed(ws):
    from pbg_superpowers.feedback_actions import feedback_item_id, study_feedback_actions

    iid_a = feedback_item_id("study-foo", "2026-01-02T10:00:00Z", "A")
    iid_d = feedback_item_id("study-foo", "2026-01-01T10:00:00Z", "D")
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1"},
            "annotations": {
                "study-foo": [
                    {"ts": "2026-01-02T10:00:00Z", "author": "A", "text": "applied one"},
                    {"ts": "2026-01-01T10:00:00Z", "author": "D", "text": "dismissed one"},
                ],
            },
            "actions": {
                iid_a: {"kind": "next_action", "target_study": "foo",
                        "target_finding": "F-01", "proposed_text": "do",
                        "status": "applied", "by": "claude", "at": "2026-01-03"},
                iid_d: {"kind": "design-edit", "target_study": "foo",
                        "proposed_text": "noop", "status": "dismissed"},
            },
        },
    )
    res = study_feedback_actions(ws, "foo")
    by_id = {i["item_id"]: i for i in res["items"]}
    assert by_id[iid_a]["status"] == "applied"
    assert by_id[iid_d]["status"] == "dismissed"
    assert res["summary"] == {"open": 0, "applied": 1, "dismissed": 1, "total": 2}
