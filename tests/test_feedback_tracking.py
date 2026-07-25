"""TDD tests for viva_superpowers.feedback_tracking.study_feedback_tracked.

Stage 3c: tracked, status-bearing index per study.
Status derivation: addressed if responses[section].status in {done, addressed, resolved};
dismissed if in {dismissed, wontfix}; else open.
"""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


# ── Minimal workspace fixture ─────────────────────────────────────────────────


@pytest.fixture
def ws(tmp_path) -> Path:
    """Workspace with a workspace.yaml so WorkspacePaths.load() works."""
    (tmp_path / "workspace.yaml").write_text("name: test-ws\n")
    (tmp_path / "investigations").mkdir()
    return tmp_path


# ── Basic cases ───────────────────────────────────────────────────────────────


def test_empty_when_no_investigations(ws):
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    result = study_feedback_tracked(ws, "foo")
    assert result == {"items": [], "summary": {"open": 0, "addressed": 0, "dismissed": 0, "total": 0}}


def test_open_items_when_no_responses(ws):
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1", "report_id": "rpt-1"},
            "annotations": {
                "study-foo": [
                    {"ts": "2026-01-01T10:00:00Z", "author": "Alice", "text": "Needs more data"},
                ],
                "study-foo-charts": [
                    {"ts": "2026-01-01T09:00:00Z", "author": "Bob", "text": "Zoom in please"},
                ],
                "study-bar": [
                    {"ts": "2026-01-01T08:00:00Z", "author": "Alice", "text": "Wrong study — excluded"},
                ],
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    items = result["items"]
    # study-bar excluded; study-foo and study-foo-charts included
    assert len(items) == 2
    sections = {i["section"] for i in items}
    assert sections == {"study-foo", "study-foo-charts"}
    # All open (no responses)
    assert all(i["status"] == "open" for i in items)
    # Newest-first: study-foo (10:00) then study-foo-charts (09:00)
    assert items[0]["section"] == "study-foo"
    assert items[1]["section"] == "study-foo-charts"
    summary = result["summary"]
    assert summary["open"] == 2
    assert summary["addressed"] == 0
    assert summary["dismissed"] == 0
    assert summary["total"] == 2


def test_addressed_when_response_status_done(ws):
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1", "report_id": "rpt-x"},
            "annotations": {
                "study-foo-charts": [
                    {"ts": "2026-01-02T10:00:00Z", "author": "Alice", "text": "Fix the plot"},
                ],
            },
            "responses": {
                "study-foo-charts": {
                    "status": "done",
                    "by": "claude",
                    "at": "2026-01-03",
                    "response": "Fixed the plot by adding zoom.",
                },
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    items = result["items"]
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "addressed"
    assert item["response"] == "Fixed the plot by adding zoom."
    assert item["responded_by"] == "claude"
    assert item["responded_at"] == "2026-01-03"
    assert item["report_id"] == "rpt-x"
    assert result["summary"]["addressed"] == 1
    assert result["summary"]["open"] == 0


def test_addressed_aliases(ws):
    """'addressed' and 'resolved' also map to addressed status."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    for status_val in ("addressed", "resolved"):
        ws2 = ws / f"ws_{status_val}"
        ws2.mkdir()
        (ws2 / "workspace.yaml").write_text("name: test\n")
        (ws2 / "investigations").mkdir()
        _write(
            ws2 / "investigations" / "inv1" / "feedback" / "r1.yaml",
            {
                "meta": {"investigation": "inv1"},
                "annotations": {"study-foo": [{"ts": "2026-01-01T10:00:00Z", "author": "A", "text": "t"}]},
                "responses": {"study-foo": {"status": status_val}},
            },
        )
        result = study_feedback_tracked(ws2, "foo")
        assert result["items"][0]["status"] == "addressed", f"failed for {status_val}"


def test_dismissed_status(ws):
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    for status_val in ("dismissed", "wontfix"):
        ws2 = ws / f"ws_{status_val}"
        ws2.mkdir()
        (ws2 / "workspace.yaml").write_text("name: test\n")
        (ws2 / "investigations").mkdir()
        _write(
            ws2 / "investigations" / "inv1" / "feedback" / "r1.yaml",
            {
                "meta": {"investigation": "inv1"},
                "annotations": {"study-foo": [{"ts": "2026-01-01T10:00:00Z", "author": "A", "text": "t"}]},
                "responses": {"study-foo": {"status": status_val}},
            },
        )
        result = study_feedback_tracked(ws2, "foo")
        assert result["items"][0]["status"] == "dismissed", f"failed for {status_val}"
    assert result["summary"]["dismissed"] == 1


def test_multiple_annotations_per_section_share_section_status(ws):
    """Multiple annotations under the same section all get the same status."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1"},
            "annotations": {
                "study-foo-charts": [
                    {"ts": "2026-01-02T10:00:00Z", "author": "Alice", "text": "First comment"},
                    {"ts": "2026-01-01T10:00:00Z", "author": "Bob", "text": "Second comment"},
                ],
            },
            "responses": {
                "study-foo-charts": {
                    "status": "done",
                    "by": "claude",
                    "at": "2026-01-03",
                    "response": "Both comments addressed.",
                },
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    items = result["items"]
    assert len(items) == 2
    assert all(i["status"] == "addressed" for i in items)
    # Newest-first
    assert items[0]["ts"] == "2026-01-02T10:00:00Z"
    assert items[1]["ts"] == "2026-01-01T10:00:00Z"
    assert result["summary"] == {"open": 0, "addressed": 2, "dismissed": 0, "total": 2}


def test_mixed_statuses(ws):
    """open, addressed, and dismissed items across sections."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback-2026-01" / "feedback.yaml",
        {
            "meta": {"investigation": "inv1", "report_id": "rpt-mix"},
            "annotations": {
                "study-foo": [{"ts": "2026-01-05T10:00:00Z", "author": "A", "text": "open question"}],
                "study-foo-charts": [{"ts": "2026-01-04T10:00:00Z", "author": "B", "text": "done zoom"}],
                "study-foo-embeds": [{"ts": "2026-01-03T10:00:00Z", "author": "C", "text": "wontfix embed"}],
                "study-bar": [{"ts": "2026-01-01T00:00:00Z", "author": "D", "text": "excluded"}],
            },
            "responses": {
                "study-foo-charts": {"status": "done", "by": "claude", "at": "2026-01-05", "response": "Zoomed."},
                "study-foo-embeds": {"status": "wontfix"},
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    items = result["items"]
    assert len(items) == 3
    by_section = {i["section"]: i for i in items}
    assert by_section["study-foo"]["status"] == "open"
    assert by_section["study-foo-charts"]["status"] == "addressed"
    assert by_section["study-foo-embeds"]["status"] == "dismissed"
    summary = result["summary"]
    assert summary == {"open": 1, "addressed": 1, "dismissed": 1, "total": 3}


def test_across_multiple_investigations(ws):
    """Feedback from different investigations for the same study is merged."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv-a" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv-a"},
            "annotations": {
                "study-foo": [{"ts": "2026-01-01T10:00:00Z", "author": "A", "text": "from inv-a"}],
            },
        },
    )
    _write(
        ws / "investigations" / "inv-b" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv-b"},
            "annotations": {
                "study-foo-charts": [{"ts": "2026-01-02T10:00:00Z", "author": "B", "text": "from inv-b"}],
            },
            "responses": {
                "study-foo-charts": {"status": "done", "by": "claude", "at": "2026-01-03", "response": "OK"},
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    assert len(result["items"]) == 2
    assert result["summary"]["open"] == 1
    assert result["summary"]["addressed"] == 1


def test_tolerates_malformed_files(ws):
    """Malformed files are skipped gracefully."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    bad_path = ws / "investigations" / "inv1" / "feedback" / "bad.yaml"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("not: valid: yaml: [{")
    # Also a valid file alongside it
    _write(
        ws / "investigations" / "inv1" / "feedback" / "good.yaml",
        {
            "meta": {"investigation": "inv1"},
            "annotations": {
                "study-foo": [{"ts": "2026-01-01T10:00:00Z", "author": "A", "text": "ok"}],
            },
        },
    )
    result = study_feedback_tracked(ws, "foo")
    assert len(result["items"]) == 1
    assert result["items"][0]["text"] == "ok"


def test_item_carries_report_id(ws):
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1", "report_id": "rpt-999"},
            "annotations": {
                "study-foo": [{"ts": "2026-01-01T10:00:00Z", "author": "A", "text": "hi"}],
            },
        },
    )
    items = study_feedback_tracked(ws, "foo")["items"]
    assert items[0]["report_id"] == "rpt-999"


def test_items_newest_first_across_sections(ws):
    """Global sort is newest-first regardless of section."""
    from viva_superpowers.feedback_tracking import study_feedback_tracked
    _write(
        ws / "investigations" / "inv1" / "feedback" / "r1.yaml",
        {
            "meta": {"investigation": "inv1"},
            "annotations": {
                "study-foo-a": [{"ts": "2026-01-03T10:00:00Z", "author": "A", "text": "newest"}],
                "study-foo-b": [{"ts": "2026-01-01T10:00:00Z", "author": "B", "text": "oldest"}],
                "study-foo-c": [{"ts": "2026-01-02T10:00:00Z", "author": "C", "text": "middle"}],
            },
        },
    )
    items = study_feedback_tracked(ws, "foo")["items"]
    texts = [i["text"] for i in items]
    assert texts == ["newest", "middle", "oldest"]


# ── Golden test: real v2e-invest workspace ────────────────────────────────────

REAL_WS = Path("/Users/eranagmon/code/v2e-invest")


@pytest.mark.skipif(not REAL_WS.is_dir(), reason="v2e-invest workspace not present")
def test_golden_dnaa_3_box_binding_has_addressed_items():
    """dnaa-3-box-binding has at least one addressed item (status: done in real feedback).

    The real feedback at investigations/dnaa-replication/feedback-2026-06-06-1544/feedback.yaml
    has responses: {study-dnaa-3-box-binding-charts: {status: done}}.
    """
    from viva_superpowers.feedback_tracking import study_feedback_tracked

    result = study_feedback_tracked(REAL_WS, "dnaa-3-box-binding")
    items = result["items"]
    summary = result["summary"]

    # Must have items
    assert len(items) > 0, "Expected feedback items for dnaa-3-box-binding"

    # Must have at least one addressed item (the real feedback has status: done)
    assert summary["addressed"] > 0, (
        f"Expected addressed > 0; got summary={summary}"
    )

    # Addressed items that have a response field must have non-empty text
    addressed = [i for i in items if i["status"] == "addressed"]
    assert len(addressed) > 0, "Expected at least one addressed item"
    addressed_with_response = [i for i in addressed if "response" in i]
    assert len(addressed_with_response) > 0, (
        "At least one addressed item must carry a 'response' field "
        "(the real feedback has a detailed response text)"
    )
    assert all(i["response"] for i in addressed_with_response), (
        "Addressed items with a 'response' key must have non-empty text"
    )

    # All items have required fields
    required = {"section", "ts", "author", "text", "status", "report_id"}
    for item in items:
        missing = required - set(item.keys())
        assert not missing, f"Item missing fields {missing}: {item}"

    # Summary arithmetic checks out
    assert summary["total"] == summary["open"] + summary["addressed"] + summary["dismissed"]

    # Log what we found for the final report
    print(
        f"\nGolden result for dnaa-3-box-binding: "
        f"open={summary['open']} addressed={summary['addressed']} "
        f"dismissed={summary['dismissed']} total={summary['total']}"
    )
