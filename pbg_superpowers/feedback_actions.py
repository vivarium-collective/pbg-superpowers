"""Feedback → action: the closed half of the reflexive loop (SP3b).

The existing :mod:`feedback_import` / :mod:`feedback_tracking` modules import
and display expert feedback but dead-end at a free-text status string —
nothing turns a feedback item into a tracked, applied change. This module adds
the missing half, starting with the read side:

- :func:`feedback_item_id` — a stable id for one annotation entry (section +
  ts + author), so an action can be keyed back to the exact feedback it
  addresses.
- :func:`study_feedback_actions` — a PURE aggregator (mirrors
  :func:`feedback_tracking.study_feedback_tracked`) that reads the feedback
  files, matches ``study-<slug>`` annotations, and joins each with a NEW
  ``actions:`` block (parallel to ``responses:``) keyed by ``item_id``,
  deriving status ``open`` / ``applied`` / ``dismissed``.

The apply primitives (the write side) land in the next task.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from pbg_superpowers.feedback_import import _feedback_files
from pbg_superpowers.workspace_paths import WorkspacePaths

# Action status sets ──────────────────────────────────────────────────────────

_APPLIED_STATUSES = {"applied", "done", "resolved"}
_DISMISSED_STATUSES = {"dismissed", "wontfix", "rejected"}


# ── stable item id ────────────────────────────────────────────────────────────


def feedback_item_id(section: str, ts: str, author: str) -> str:
    """A stable, content-derived id for one annotation entry.

    Derived from ``section`` + ``ts`` + ``author`` (the natural key of an
    annotation entry) so an ``actions[item_id]`` block can point back at the
    exact feedback it addresses. Deterministic across processes (sha1 hex,
    truncated) — no randomness, no clock.
    """
    h = hashlib.sha1(
        "\x00".join((section or "", ts or "", author or "")).encode("utf-8")
    )
    return "fb-" + h.hexdigest()[:16]


def _derive_action_status(action: dict | None) -> str:
    """Map an ``actions[item_id]`` entry to ``open`` / ``applied`` / ``dismissed``."""
    if not action or not isinstance(action, dict):
        return "open"
    raw = str(action.get("status") or "").lower().strip()
    if raw in _APPLIED_STATUSES:
        return "applied"
    if raw in _DISMISSED_STATUSES:
        return "dismissed"
    return "open"


# ── pure aggregator ───────────────────────────────────────────────────────────


def study_feedback_actions(
    workspace: Path | str,
    study_slug: str,
) -> dict[str, Any]:
    """Aggregate all feedback for *study_slug*, joined with its tracked actions.

    Mirrors :func:`feedback_tracking.study_feedback_tracked`: scans every
    ``investigations/<inv>/`` for feedback files (via ``_feedback_files``),
    matches sections by the ``study-<slug>`` prefix, and for each annotation
    entry joins the NEW ``actions:`` block (keyed by ``feedback_item_id``).

    Returns ``{"items": [...], "summary": {open, applied, dismissed, total}}``.
    Each item::

        {
            "item_id":   str,
            "section":   str,
            "ts":        str,
            "author":    str,
            "text":      str,
            "report_id": str | None,
            "action":    dict | None,   # the actions[item_id] entry, if any
            "status":    "open" | "applied" | "dismissed",
        }

    PURE read — no writes. Items are newest-first; malformed files are skipped.
    """
    prefix = "study-" + study_slug

    inv_root = WorkspacePaths.load(workspace).investigations
    if not inv_root.is_dir():
        return _empty_result()

    items: list[dict] = []

    for inv_dir in sorted(inv_root.iterdir()):
        if not inv_dir.is_dir():
            continue
        for path in _feedback_files(inv_dir):
            try:
                data = yaml.safe_load(path.read_text())
            except (yaml.YAMLError, OSError):
                continue
            if not isinstance(data, dict):
                continue

            meta = data.get("meta") or {}
            report_id = meta.get("report_id") if isinstance(meta, dict) else None

            annotations = data.get("annotations") or {}
            if not isinstance(annotations, dict):
                continue

            actions = data.get("actions") or {}
            if not isinstance(actions, dict):
                actions = {}

            for section_id, entries in annotations.items():
                if section_id != prefix and not section_id.startswith(prefix + "-"):
                    continue
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    ts = entry.get("ts") or ""
                    author = entry.get("author") or ""
                    item_id = feedback_item_id(section_id, ts, author)
                    action = actions.get(item_id)
                    if not isinstance(action, dict):
                        action = None
                    items.append({
                        "item_id": item_id,
                        "section": section_id,
                        "ts": ts,
                        "author": author,
                        "text": entry.get("text") or "",
                        "report_id": report_id,
                        "action": action,
                        "status": _derive_action_status(action),
                    })

    items.sort(key=lambda i: i.get("ts") or "", reverse=True)
    return {"items": items, "summary": _summarize(items)}


def _empty_result() -> dict:
    return {
        "items": [],
        "summary": {"open": 0, "applied": 0, "dismissed": 0, "total": 0},
    }


def _summarize(items: list[dict]) -> dict:
    open_c = sum(1 for i in items if i["status"] == "open")
    applied_c = sum(1 for i in items if i["status"] == "applied")
    dismissed_c = sum(1 for i in items if i["status"] == "dismissed")
    return {
        "open": open_c,
        "applied": applied_c,
        "dismissed": dismissed_c,
        "total": len(items),
    }
