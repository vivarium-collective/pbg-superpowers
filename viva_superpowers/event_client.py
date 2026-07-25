"""Agentic-spine event reactor (RFC-0002 Phase A).

Tails workspace/.pbg/events.jsonl from a persisted cursor and dispatches typed
events to handlers. At-least-once: handlers must be idempotent on event_id.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from investigation_contracts import read_log


class EventClient:
    def __init__(self, ws_root, consumer: str):
        self.ws_root = Path(ws_root)
        self.consumer = consumer
        self._handlers: dict[str, list] = {}

    @property
    def _log(self) -> Path:
        return self.ws_root / ".pbg" / "events.jsonl"

    @property
    def _cursor_file(self) -> Path:
        return self.ws_root / ".pbg" / f"event_cursor.{self.consumer}"

    def _cursor(self):
        return self._cursor_file.read_text().strip() if self._cursor_file.is_file() else None

    def _set_cursor(self, event_id: str):
        self._cursor_file.parent.mkdir(parents=True, exist_ok=True)
        self._cursor_file.write_text(event_id, encoding="utf-8")

    def on(self, event_type: str, handler):
        self._handlers.setdefault(event_type, []).append(handler)
        return self

    def poll_once(self) -> int:
        types = list(self._handlers) or None
        n = 0
        for ev in read_log(self._log, self._cursor(), types):
            for h in self._handlers.get(ev.get("type"), []):
                h(ev)
            self._set_cursor(ev["event_id"])   # advance after handling (at-least-once)
            n += 1
        return n

    def run(self, poll_interval: float = 1.0):
        while True:
            self.poll_once()
            time.sleep(poll_interval)


def on_finding_created(ws_root, envelope: dict) -> Path:
    """Reaction handler: write a structured 'finding observed' record.

    Idempotent — keyed by event_id (overwrite-stable)."""
    ws_root = Path(ws_root)
    rdir = ws_root / ".pbg" / "reactions"
    rdir.mkdir(parents=True, exist_ok=True)
    payload = envelope.get("payload", {})
    record = {
        "observed_event": envelope["event_id"],
        "event_type": envelope["type"],
        "finding_id": payload.get("finding_id"),
        "study": payload.get("study"),
        "noted_at": envelope.get("occurred_at"),
        "next_action": "stub: agentic spine would propose the next study here",
    }
    out = rdir / f"{envelope['event_id']}.yaml"
    out.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return out
