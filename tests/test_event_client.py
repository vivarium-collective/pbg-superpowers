import json
from pathlib import Path
from viva_superpowers.event_client import EventClient, on_finding_created


def _event(eid, etype="FindingCreated", study="demo", fid="fX"):
    return {"event_id": eid, "type": etype, "occurred_at": "t", "actor": "agentic",
            "subject": f"finding/{fid}", "transition": {"from": "", "to": "proposed"},
            "provenance": {"actor": "agentic", "agent_id": "p", "timestamp": "t",
                           "source_objects": [], "justification": "j", "tool": "", "commit": ""},
            "payload": {"study": study, "finding_id": fid, "statement": "s"}, "schema_version": 1}


def _seed(ws: Path, events):
    d = ws / ".pbg"; d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_dispatch_and_cursor_advance(tmp_path):
    _seed(tmp_path, [_event("01"), _event("02")])
    seen = []
    c = EventClient(tmp_path, consumer="test")
    c.on("FindingCreated", lambda ev: seen.append(ev["event_id"]))
    assert c.poll_once() == 2
    assert seen == ["01", "02"]
    # cursor persisted → a second poll handles nothing new
    assert c.poll_once() == 0


def test_type_filter(tmp_path):
    _seed(tmp_path, [_event("01", etype="OtherEvent"), _event("02")])
    seen = []
    c = EventClient(tmp_path, consumer="t2")
    c.on("FindingCreated", lambda ev: seen.append(ev["event_id"]))
    c.poll_once()
    assert seen == ["02"]


def test_handler_writes_reaction_record(tmp_path):
    p = on_finding_created(tmp_path, _event("07", fid="fAbc"))
    assert p.is_file()
    import yaml
    rec = yaml.safe_load(p.read_text())
    assert rec["finding_id"] == "fAbc" and rec["study"] == "demo"
