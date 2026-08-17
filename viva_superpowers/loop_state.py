"""Persisted protocol state for the agentic model-building loop.

`.pbg/loop/<study>.json` (schema model_build_loop/v1) is the loop's audit trail
AND the seam that lets a supervised in-session run become an autonomous dispatched
run — any executor reads/advances the same file. Pure: stdlib + viva_superpowers
intra-imports only (AI-free; no process_bigraph / workbench). See
docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md §3-§4.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from viva_superpowers import paths, study_io

SCHEMA = "model_build_loop/v1"
STATES = ("AUTHOR", "AUDIT", "SELECT", "LOCK", "BUILD", "RUN", "EVALUATE",
          "DECIDE", "NAVIGATE", "DONE", "GIVE_UP")
# SELECT: the model-sourcing decision (reuse an existing module / compose several /
# build-new) is recorded on the state as `sourcing` and graded by
# `module_sourcing.build_sourcing_report` before the tests are locked. It adds no
# immutability invariant — sourcing is graded, not frozen.


def loop_path(ws_root, study: str) -> Path:
    return paths.workspace_dir("pbg", root=ws_root) / "loop" / f"{study}.json"


def create(ws_root, study: str, question: str, *, max_iterations: int = 12) -> dict:
    return {
        "schema": SCHEMA,
        "study": study,
        "question": question,
        "state": "AUTHOR",
        "iteration": 0,
        "budget": {"max_iterations": int(max_iterations), "spent": 0},
        "audit": None,
        "locked_tests_hash": None,
        "prereg_record": {"locked_at_iteration": None, "prior_hashes": []},
        "reopen_count": 0,
        "last_verdict": None,
        "history": [],
    }


def save(ws_root, study: str, state: dict) -> Path:
    p = loop_path(ws_root, study)
    p.parent.mkdir(parents=True, exist_ok=True)
    study_io.atomic_write(p, json.dumps(state, indent=1, sort_keys=False) + "\n")
    return p


def load(ws_root, study: str) -> "dict | None":
    p = loop_path(ws_root, study)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def tests_hash(tests: list) -> str:
    """Content hash of the behavior_tests set, stable to ordering (the set is
    what's locked, not its order). Canonicalized via sorted-keys JSON."""
    canon = sorted(json.dumps(t, sort_keys=True) for t in (tests or []))
    return "sha256:" + hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()


def lock_tests(state: dict, tests: list) -> dict:
    """Pre-register (freeze) the Test set. A RE-lock (an existing locked hash that
    differs — i.e. the loop re-opened → re-audited → re-locked a changed Test set)
    records the anti-gaming trail: the prior hash is retained in
    ``prereg_record.prior_hashes`` and ``reopen_count`` is bumped. So every
    change to a locked Test set is visible post-hoc — you cannot weaken a Test to
    pass without it showing up as a recorded reopen (spec §7)."""
    state = dict(state)
    new_hash = tests_hash(tests)
    prev = state.get("locked_tests_hash")
    prereg = dict(state.get("prereg_record") or {})
    prereg["prior_hashes"] = list(prereg.get("prior_hashes") or [])
    if prev and prev != new_hash:
        prereg["prior_hashes"].append(prev)
        state["reopen_count"] = int(state.get("reopen_count", 0)) + 1
    prereg["locked_at_iteration"] = state.get("iteration", 0)
    state["locked_tests_hash"] = new_hash
    state["prereg_record"] = prereg
    state["state"] = "LOCK"
    return state


def advance(state: dict, to_state: str, **fields) -> dict:
    if to_state not in STATES:
        raise ValueError(f"unknown loop state {to_state!r}")
    state = dict(state)
    state["state"] = to_state
    state.update(fields)
    return state


def record_iteration(state: dict, *, edit: str, target: str,
                     margin_deltas: dict, gate: str, tests: list | None = None) -> dict:
    """Append one iteration to the loop history.

    ``tests`` (optional) is the per-test verdict snapshot for this iteration —
    a list of ``{"name", "verdict", "margin"}`` — which lets a renderer draw a
    per-test signed-margin matrix (rows=tests, columns=iterations) instead of
    only the aggregate ``gate``. Omitted for back-compat; when absent the record
    simply carries no ``tests`` key.
    """
    state = dict(state)
    state["iteration"] = int(state.get("iteration", 0)) + 1
    budget = dict(state.get("budget") or {})
    budget["spent"] = int(budget.get("spent", 0)) + 1
    state["budget"] = budget
    record = {
        "iteration": state["iteration"], "edit": edit, "target": target,
        "margin_deltas": margin_deltas or {}, "gate": gate,
    }
    if tests:
        record["tests"] = [
            {"name": t.get("name"), "verdict": t.get("verdict"), "margin": t.get("margin")}
            for t in tests
        ]
    state["history"] = list(state.get("history") or []) + [record]
    return state


def validate(state: dict, current_tests: list, *, is_reopen: bool = False) -> list:
    """Invariant violations (empty = clean). I1: after LOCK the tests are frozen
    (a change is only legal on a reopen). I4: no `passed` roll-up the gate rejects."""
    out = []
    locked = state.get("locked_tests_hash")
    if locked and not is_reopen and tests_hash(current_tests) != locked:
        out.append("I1: locked behavior_tests changed outside a re-open→AUDIT round")
    # I1b — reopen-trail integrity: reopen_count must equal the number of retained
    # prior hashes. A change to a locked Test set is only legitimate through a
    # re-lock (lock_tests records both together); a mismatch means the trail was
    # tampered with (or a weakening was slipped in without a recorded reopen).
    prereg = state.get("prereg_record") or {}
    n_prior = len(prereg.get("prior_hashes") or [])
    if int(state.get("reopen_count", 0)) != n_prior:
        out.append("I1b: reopen_count does not match the retained prior-hash trail")
    lv = state.get("last_verdict") or {}
    if str(lv.get("roll_up")) == "passed" and str(lv.get("gate")) == "fail":
        out.append("I4: roll_up 'passed' contradicts a failing severity gate")
    return out
