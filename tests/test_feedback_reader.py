"""Tests for the imported-feedback reader (Thread B.1)."""
import yaml

from pbg_superpowers.feedback_import import (
    load_investigation_feedback, feedback_for_study,
)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def test_empty_when_no_feedback(tmp_path):
    (tmp_path / "investigations" / "inv").mkdir(parents=True)
    assert load_investigation_feedback(tmp_path, "inv") == {}


def test_reads_canonical_feedback_dir(tmp_path):
    inv = tmp_path / "investigations" / "dnaa"
    _write(inv / "feedback" / "2026-05-21T00-03-28Z.yaml", {
        "meta": {"investigation": "dnaa", "report_id": "rpt-1"},
        "annotations": {
            "study-dnaa-00-parameter-foundation-embeds": [
                {"author": "Haochen", "text": "longer time please",
                 "ts": "2026-05-21T00:03:28Z"},
            ],
        },
    })
    fb = load_investigation_feedback(tmp_path, "dnaa")
    section = fb["study-dnaa-00-parameter-foundation-embeds"]
    assert len(section) == 1
    assert section[0]["author"] == "Haochen"
    assert section[0]["report_id"] == "rpt-1"


def test_reads_dated_round_folder(tmp_path):
    """The dnaa investigation keeps rounds as feedback-<date>/feedback.yaml."""
    inv = tmp_path / "investigations" / "dnaa"
    _write(inv / "feedback-2026-05-21" / "feedback.yaml", {
        "meta": {"investigation": "dnaa", "report_id": "rpt-2"},
        "annotations": {
            "study-dnaa-02-atp-hydrolysis-embeds": [
                {"author": "Haochen", "text": "RIDA premature",
                 "ts": "2026-05-21T02:13:30Z"},
            ],
        },
    })
    fb = load_investigation_feedback(tmp_path, "dnaa")
    assert "study-dnaa-02-atp-hydrolysis-embeds" in fb


def test_merges_multiple_files_newest_first(tmp_path):
    inv = tmp_path / "investigations" / "dnaa"
    sect = "study-dnaa-01-expression-dynamics-charts"
    _write(inv / "feedback" / "a.yaml", {
        "meta": {"investigation": "dnaa", "report_id": "old"},
        "annotations": {sect: [
            {"author": "H", "text": "earlier", "ts": "2026-05-20T10:00:00Z"}]},
    })
    _write(inv / "feedback" / "b.yaml", {
        "meta": {"investigation": "dnaa", "report_id": "new"},
        "annotations": {sect: [
            {"author": "H", "text": "later", "ts": "2026-05-21T10:00:00Z"}]},
    })
    fb = load_investigation_feedback(tmp_path, "dnaa")
    texts = [e["text"] for e in fb[sect]]
    assert texts == ["later", "earlier"]  # newest-first


def test_feedback_for_study_matches_prefix_and_suffixes(tmp_path):
    fb = {
        "study-dnaa-00-parameter-foundation-embeds": [
            {"author": "H", "text": "a", "ts": "2026-05-21T00:00:00Z"}],
        "study-dnaa-00-parameter-foundation-charts": [
            {"author": "H", "text": "b", "ts": "2026-05-21T01:00:00Z"}],
        "study-dnaa-01-expression-dynamics-embeds": [
            {"author": "H", "text": "other", "ts": "2026-05-21T02:00:00Z"}],
        "references": [
            {"author": "H", "text": "refs", "ts": "2026-05-21T03:00:00Z"}],
    }
    out = feedback_for_study(fb, "dnaa-00-parameter-foundation")
    texts = [e["text"] for e in out]
    # Only dnaa-00 sections, newest-first; dnaa-01 + references excluded.
    assert texts == ["b", "a"]
    assert all(e["section"].startswith("study-dnaa-00-parameter-foundation") for e in out)


def test_feedback_for_study_no_match(tmp_path):
    fb = {"study-other-embeds": [{"author": "H", "text": "x", "ts": "t"}]}
    assert feedback_for_study(fb, "dnaa-00") == []


def test_malformed_entries_skipped(tmp_path):
    inv = tmp_path / "investigations" / "dnaa"
    _write(inv / "feedback" / "bad.yaml", {
        "meta": {"investigation": "dnaa"},
        "annotations": {
            "study-dnaa-00-x": ["not-a-dict", {"author": "H", "text": "ok", "ts": "t"}],
            "study-dnaa-00-y": "not-a-list",
        },
    })
    fb = load_investigation_feedback(tmp_path, "dnaa")
    assert [e["text"] for e in fb["study-dnaa-00-x"]] == ["ok"]
    assert "study-dnaa-00-y" not in fb
