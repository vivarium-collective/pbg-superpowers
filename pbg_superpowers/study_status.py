"""Derive a study's status from execution state (don't trust hand-set fields).

v2ecoli round-2 integration friction #2 (2026-05-22): a report shipped
``status: planning-with-baseline-confirmed`` and a "for expert review prior to
execution" tagline *after all 8 studies had executed with verdicts*. The
expert and the user caught it — no check did. The authored status string had
drifted from reality.

The robust fix is **derive-on-read**: compute the observably-derivable status
axes from execution state (runs.db + recorded verdicts) instead of trusting a
hand-maintained field that can't keep up. This module is the shared core both
the dashboard (live render) and the report (export) call, so a study's status
reflects what actually ran — by construction, it can't go stale.

Multi-axis status vocabulary (Pass A): design / implementation / simulation /
evaluation / gate / expert_review. Of these:

- ``simulation_status`` and ``evaluation_status`` are **observable** — fully
  derivable from runs + verdicts. This module derives them.
- ``design_status`` / ``implementation_status`` / ``expert_review_status`` are
  **authored intent** (was it designed? is the code written? did an expert
  sign off?) — not derivable from a run, so they pass through unchanged.
- ``gate_status`` mixes authored prerequisites with test outcomes; deriving it
  needs the test pass/fail signal and is left for a follow-up.

``status_disagreements`` reports where a *stored* axis contradicts its derived
value, so the report can surface "stored: planning / actual: ran" the way the
param-enforcement banner surfaces declared-vs-applied drift.
"""
from __future__ import annotations

from typing import Any


# runs_meta.status vocabulary → our coarse buckets. "ran" is the v2/legacy
# completed marker; "complete"/"completed" are the canonical ones.
_RUN_COMPLETE = {"complete", "completed", "ran", "done"}
_RUN_RUNNING = {"running"}
# failed / orphaned count as "attempted" but not a clean completion.


def derive_simulation_status(runs: list[dict] | None) -> str:
    """``ran`` if any run completed, ``running`` if one is in progress, else
    ``not_run``. Derived purely from runs.db rows."""
    has_complete = False
    has_running = False
    for r in runs or []:
        st = str((r or {}).get("status") or "").strip().lower()
        if st in _RUN_COMPLETE:
            has_complete = True
        elif st in _RUN_RUNNING:
            has_running = True
    if has_complete:
        return "ran"
    if has_running:
        return "running"
    return "not_run"


def _has_recorded_verdicts(spec: dict) -> bool:
    """True if the study carries evaluation output (verdicts / findings)."""
    for key in ("conclusion_verdicts", "findings"):
        v = spec.get(key)
        if isinstance(v, (list, dict)) and len(v) > 0:
            return True
    return False


def derive_evaluation_status(spec: dict, runs: list[dict] | None,
                             *, has_verdicts: bool | None = None) -> str:
    """``evaluated`` only when a run completed AND verdicts/findings exist;
    otherwise ``not_evaluated``. You can't evaluate what hasn't run."""
    if derive_simulation_status(runs) != "ran":
        return "not_evaluated"
    if has_verdicts is None:
        has_verdicts = _has_recorded_verdicts(spec)
    return "evaluated" if has_verdicts else "not_evaluated"


# Which axes this module derives, and the function that derives each.
_DERIVABLE_AXES = ("simulation_status", "evaluation_status")


def derive_status(spec: dict, runs: list[dict] | None,
                  *, has_verdicts: bool | None = None) -> dict[str, dict]:
    """Return ``{axis: {"value": str, "source": str}}`` for the derivable axes.

    Only the observable axes (simulation, evaluation) are returned — authored
    axes aren't derivable and are left to the spec. ``source`` is a short
    human string for the report ("3 completed run(s)").
    """
    runs = runs or []
    n_complete = sum(
        1 for r in runs
        if str((r or {}).get("status") or "").strip().lower() in _RUN_COMPLETE
    )
    sim = derive_simulation_status(runs)
    evalst = derive_evaluation_status(spec, runs, has_verdicts=has_verdicts)
    sim_source = (
        f"{n_complete} completed run(s)" if n_complete
        else ("a run in progress" if sim == "running" else "no runs in runs.db")
    )
    eval_source = (
        "completed run + recorded verdicts" if evalst == "evaluated"
        else ("no verdicts recorded yet" if sim == "ran" else "nothing run to evaluate")
    )
    return {
        "simulation_status": {"value": sim, "source": sim_source},
        "evaluation_status": {"value": evalst, "source": eval_source},
    }


# Axis value ordering, least→most advanced. Disagreements are only flagged
# when the DERIVED value outranks the stored one — i.e. execution has moved
# past what the stored status claims (the round-2 #2 case: a "planning" /
# "not_run" status on a study that has actually run). The reverse (stored
# claims more than the evidence shows) is NOT flagged: runs.db can simply be
# absent from a given checkout, so a stored ``ran`` with no local db is
# ambiguous, not proof of drift.
_AXIS_RANK = {
    "simulation_status": {"not_run": 0, "running": 1, "ran": 2},
    "evaluation_status": {"not_evaluated": 0, "evaluated": 1},
}


def status_disagreements(spec: dict, runs: list[dict] | None,
                         *, has_verdicts: bool | None = None) -> list[dict]:
    """Where a stored axis (or legacy ``status``) lags BEHIND execution state.

    Returns ``[{axis, stored, derived, message}]`` — empty when everything
    agrees, the stored value is absent, or the stored value merely claims
    *more* than the local runs.db shows (ambiguous: the db may not be in this
    checkout). Only flags when the derived value outranks the stored one — the
    "planning status after the study already ran" drift (round-2 #2).
    """
    derived = derive_status(spec, runs, has_verdicts=has_verdicts)
    out: list[dict] = []
    for axis, info in derived.items():
        stored = spec.get(axis)
        if not stored or stored == info["value"]:
            continue
        ranks = _AXIS_RANK.get(axis, {})
        if ranks.get(info["value"], -1) <= ranks.get(stored, 99):
            continue  # derived not more advanced than stored → not flagged
        out.append({
            "axis": axis,
            "stored": stored,
            "derived": info["value"],
            "message": (
                f"{axis}: stored {stored!r} but execution state implies "
                f"{info['value']!r} ({info['source']})"
            ),
        })
    # Legacy free-form `status`: only flag the unambiguous planning-vs-ran case.
    legacy = str(spec.get("status") or "").strip().lower()
    sim = derived["simulation_status"]["value"]
    if legacy and ("planning" in legacy or legacy == "planned") and sim == "ran":
        out.append({
            "axis": "status",
            "stored": spec.get("status"),
            "derived": "ran",
            "message": (
                f"status: headline {spec.get('status')!r} still says planning, "
                f"but the study has completed runs ({derived['simulation_status']['source']})"
            ),
        })
    return out
