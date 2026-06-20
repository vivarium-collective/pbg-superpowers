"""Tracked, status-bearing feedback index per study (spine stage 3c).

Reads both ``annotations`` and ``responses`` blocks across all feedback files
in every investigation, matches sections by the ``study-<slug>`` prefix (like
``feedback_for_study``), and derives per-item status:

- ``addressed`` — the section has a ``responses`` entry with ``status`` in
  {done, addressed, resolved}
- ``dismissed`` — the section response ``status`` is in {dismissed, wontfix}
- ``open`` — everything else (no response, or unrecognised status)

The existing ``load_investigation_feedback`` (annotations-only) is unchanged;
this module is purely additive.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pbg_superpowers.feedback_import import _feedback_files
from pbg_superpowers.workspace_paths import WorkspacePaths

# Status sets ─────────────────────────────────────────────────────────────────

_ADDRESSED_STATUSES = {"done", "addressed", "resolved"}
_DISMISSED_STATUSES = {"dismissed", "wontfix"}


def _derive_status(response: dict | None) -> str:
    """Map a section's ``responses`` entry to a string status."""
    if not response or not isinstance(response, dict):
        return "open"
    raw = str(response.get("status") or "").lower().strip()
    if raw in _ADDRESSED_STATUSES:
        return "addressed"
    if raw in _DISMISSED_STATUSES:
        return "dismissed"
    return "open"


def study_feedback_tracked(
    workspace: Path | str,
    study_slug: str,
) -> dict[str, Any]:
    """Aggregate all feedback for *study_slug* with per-item status derivation.

    Scans every ``investigations/<inv>/`` in *workspace* for feedback files
    (via ``_feedback_files``), reads both ``annotations`` and ``responses``
    blocks, and builds a tracked list + summary.

    Parameters
    ----------
    workspace:
        Workspace root (the directory containing ``investigations/``).
    study_slug:
        The study's short slug, e.g. ``"dnaa-3-box-binding"``.  Sections are
        matched by the ``study-<slug>`` prefix, exactly as
        ``feedback_for_study`` does.

    Returns
    -------
    ``{"items": [...], "summary": {open, addressed, dismissed, total}}``

    Each item dict::

        {
            "section":       str,   # full section id, e.g. "study-foo-charts"
            "ts":            str,   # ISO-8601 annotation timestamp
            "author":        str,
            "text":          str,
            "status":        str,   # "open" | "addressed" | "dismissed"
            "report_id":     str | None,
            # Only present when status is "addressed" or "dismissed" with a response:
            "response":      str,
            "responded_by":  str,
            "responded_at":  str,
        }

    Items are sorted newest-first by ``ts``.  Malformed files are skipped
    silently (tolerant, like the existing reader).
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
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                continue
            if not isinstance(data, dict):
                continue

            meta = data.get("meta") or {}
            report_id = meta.get("report_id") if isinstance(meta, dict) else None

            annotations: dict = data.get("annotations") or {}
            if not isinstance(annotations, dict):
                continue

            responses: dict = data.get("responses") or {}
            if not isinstance(responses, dict):
                responses = {}

            for section_id, entries in annotations.items():
                # Match only sections targeting this study
                if section_id != prefix and not section_id.startswith(prefix + "-"):
                    continue
                if not isinstance(entries, list):
                    continue

                # Derive status from this file's responses block for this section
                section_response = responses.get(section_id)
                status = _derive_status(section_response)

                # Build common response fields (only when a response exists)
                resp_fields: dict = {}
                if isinstance(section_response, dict):
                    resp_text = section_response.get("response")
                    if resp_text:
                        resp_fields["response"] = str(resp_text)
                    resp_by = section_response.get("by")
                    if resp_by:
                        resp_fields["responded_by"] = str(resp_by)
                    resp_at = section_response.get("at")
                    if resp_at:
                        resp_fields["responded_at"] = str(resp_at)

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    item: dict = {
                        "section": section_id,
                        "ts": entry.get("ts") or "",
                        "author": entry.get("author") or "",
                        "text": entry.get("text") or "",
                        "status": status,
                        "report_id": report_id,
                    }
                    item.update(resp_fields)
                    items.append(item)

    # Sort newest-first (ISO-8601 timestamps are lexically sortable)
    items.sort(key=lambda i: i.get("ts") or "", reverse=True)

    summary = _summarize(items)
    return {"items": items, "summary": summary}


def _empty_result() -> dict:
    return {
        "items": [],
        "summary": {"open": 0, "addressed": 0, "dismissed": 0, "total": 0},
    }


def _summarize(items: list[dict]) -> dict:
    open_c = sum(1 for i in items if i["status"] == "open")
    addressed_c = sum(1 for i in items if i["status"] == "addressed")
    dismissed_c = sum(1 for i in items if i["status"] == "dismissed")
    return {
        "open": open_c,
        "addressed": addressed_c,
        "dismissed": dismissed_c,
        "total": len(items),
    }
