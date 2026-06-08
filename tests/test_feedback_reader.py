"""Tests for the imported-feedback reader (Thread B.1) + shared writer (B.2)."""
import pytest
import yaml

from pbg_superpowers.feedback_import import (
    load_investigation_feedback, feedback_for_study,
    write_feedback_payload, FeedbackImportError, apply_offline_actions,
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


# ── Shared writer (B.2): write_feedback_payload ──────────────────────────

def _payload(inv="dnaa", **meta):
    return {
        "meta": {"investigation": inv, "generated_at": "2026-05-21T02:32:39Z", **meta},
        "annotations": {
            "study-dnaa-00-x": [{"author": "H", "text": "longer", "ts": "t"}],
        },
    }


def test_write_feedback_payload_writes_into_feedback_dir(tmp_path):
    (tmp_path / "investigations" / "dnaa").mkdir(parents=True)
    target = write_feedback_payload(tmp_path, _payload())
    assert target.parent == tmp_path / "investigations" / "dnaa" / "feedback"
    data = yaml.safe_load(target.read_text())
    assert data["meta"]["investigation"] == "dnaa"
    assert "study-dnaa-00-x" in data["annotations"]
    # And the reader round-trips it.
    fb = load_investigation_feedback(tmp_path, "dnaa")
    assert fb["study-dnaa-00-x"][0]["text"] == "longer"


def test_write_feedback_payload_never_overwrites(tmp_path):
    (tmp_path / "investigations" / "dnaa").mkdir(parents=True)
    a = write_feedback_payload(tmp_path, _payload())
    b = write_feedback_payload(tmp_path, _payload())  # same generated_at
    assert a != b  # second got a numeric suffix, didn't clobber the first
    assert a.exists() and b.exists()


def test_write_feedback_payload_missing_investigation_dir(tmp_path):
    with pytest.raises(FeedbackImportError, match="does not exist"):
        write_feedback_payload(tmp_path, _payload(inv="nope"))


def test_write_feedback_payload_bad_payload(tmp_path):
    with pytest.raises(FeedbackImportError, match="meta.investigation"):
        write_feedback_payload(tmp_path, {"annotations": {}})


def test_write_feedback_payload_no_create_refuses(tmp_path):
    (tmp_path / "investigations" / "dnaa").mkdir(parents=True)
    with pytest.raises(FeedbackImportError, match="does not exist"):
        write_feedback_payload(tmp_path, _payload(), create=False)


# ── Offline actions: proposed_input_decisions + study_seed_requests ──────

def test_write_payload_preserves_offline_action_keys(tmp_path):
    """The persisted yaml must keep the offline-action keys (faithful copy)."""
    (tmp_path / "investigations" / "dnaa").mkdir(parents=True)
    payload = _payload()
    payload["proposed_input_decisions"] = [
        {"item_id": "ref:smith2020", "decision": "accept", "ts": "t"}]
    payload["study_seed_requests"] = [
        {"title": "follow-up X", "parent": "dnaa-00", "targets": ["dnaA"], "ts": "t"}]
    target = write_feedback_payload(tmp_path, payload)
    data = yaml.safe_load(target.read_text())
    assert data["proposed_input_decisions"][0]["item_id"] == "ref:smith2020"
    assert data["study_seed_requests"][0]["parent"] == "dnaa-00"


def test_apply_offline_actions_noop_when_empty(tmp_path):
    report = apply_offline_actions(tmp_path, {"meta": {"investigation": "dnaa"}})
    assert report == {"decisions": [], "seeds": [], "errors": []}


def test_apply_offline_actions_surfaces_when_dashboard_missing(tmp_path, monkeypatch):
    """If vivarium_dashboard can't be imported, actions are surfaced, not lost."""
    import builtins
    real_import = builtins.__import__

    def _blocked(name, *a, **k):
        if name.startswith("vivarium_dashboard"):
            raise ModuleNotFoundError("blocked for test")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    payload = {
        "meta": {"investigation": "dnaa"},
        "proposed_input_decisions": [{"item_id": "x", "decision": "accept"}],
        "study_seed_requests": [{"title": "y", "parent": "dnaa-00"}],
    }
    report = apply_offline_actions(tmp_path, payload)
    assert len(report["errors"]) == 1
    assert "not importable" in report["errors"][0]
    # Parsed but not dropped.
    assert report["decisions"] and report["seeds"]


def test_apply_offline_actions_applies_decision(tmp_path):
    """End-to-end: an accept decision promotes a kind:reference into inputs.

    Skips when vivarium_dashboard isn't installed in this venv (the apply
    path runs in the dashboard/workspace venv that has it).
    """
    pytest.importorskip("vivarium_dashboard")
    inv = tmp_path / "investigations" / "dnaa"
    inv.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(yaml.safe_dump({
        "name": "dnaa",
        "inputs": {"references": []},
        "proposed_inputs": {"items": [
            {"id": "smith2020", "kind": "reference",
             "citation": "Smith 2020", "status": "pending"}]},
    }, sort_keys=False))
    payload = {
        "meta": {"investigation": "dnaa"},
        "proposed_input_decisions": [
            {"item_id": "smith2020", "decision": "accept", "ts": "t"}],
    }
    report = apply_offline_actions(tmp_path, payload)
    assert report["errors"] == []
    assert report["decisions"][0]["status"] == "accepted"
    # The reference was promoted into inputs.references.
    spec = yaml.safe_load((inv / "investigation.yaml").read_text())
    assert "smith2020" in spec["inputs"]["references"]
    assert spec["proposed_inputs"]["items"][0]["status"] == "accepted"
