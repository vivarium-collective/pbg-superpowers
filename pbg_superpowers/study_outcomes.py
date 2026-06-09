"""Reconcile a study's runs.db into study.yaml and expose the canonical outcome
surface. Mechanical run fields are code-owned; authored outcomes/prose are preserved.
Increment A: record + single-source. (Evaluation of measure/pass_if is Increment B.)"""
from __future__ import annotations

from pathlib import Path

_COMPLETE = {"complete", "completed", "ran", "done"}


def _runs_of(spec_or_runs) -> list[dict]:
    if isinstance(spec_or_runs, list):
        runs = spec_or_runs
    else:
        runs = (spec_or_runs or {}).get("runs") or []
    return [r for r in runs if isinstance(r, dict)]


def canonical_run(spec_or_runs) -> dict | None:
    """The run whose outcomes are authoritative: an explicit `canonical: true`
    (last one wins), else the newest completed run by `timestamp`, else the last
    run, else None."""
    runs = _runs_of(spec_or_runs)
    if not runs:
        return None
    flagged = [r for r in runs if r.get("canonical") is True]
    if flagged:
        return flagged[-1]
    completed = [r for r in runs if str(r.get("status", "")).lower() in _COMPLETE]
    if completed:
        return max(completed, key=lambda r: str(r.get("timestamp", "")))
    return runs[-1]


def canonical_outcomes(spec_or_runs) -> dict:
    """The canonical run's `outcomes` dict (empty if none)."""
    run = canonical_run(spec_or_runs)
    return (run or {}).get("outcomes") or {}
