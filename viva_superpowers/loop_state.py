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
STATES = ("AUTHOR", "AUDIT", "SELECT", "SPIKE", "LOCK", "BUILD", "RUN", "EVALUATE",
          "DECIDE", "NAVIGATE", "DONE", "GIVE_UP")
# SELECT: the model-sourcing decision (reuse an existing module / compose several /
# build-new) is recorded on the state as `sourcing` and graded by
# `module_sourcing.build_sourcing_report` before the tests are locked. It adds no
# immutability invariant — sourcing is graded, not frozen.
# SPIKE: a feasibility probe run between SELECT and LOCK — a cheap run through the
# ACTUAL simulator demonstrating the mechanism vocabulary can express the phenomenon
# (directionally) BEFORE any numeric threshold is frozen. Recorded via `record_spike`
# on the `spike` field; a lock reached while the spike marked the phenomenon
# non-expressible is an I0 violation. Cheap insurance against locking a contract the
# engine cannot satisfy (the two most expensive errors observed were exactly this).

# Ledger note kinds — the SDD-style ledger (commits, rulings, deferred findings)
# folds into the ONE state as typed `log` rows, so an investigation has a single
# source of truth instead of a state file + a separate ledger + a trajectory.
NOTE_KINDS = ("commit", "ruling", "deferred", "note")

# The five typed NAVIGATE actions. A model-build iteration records which kind of
# action it took, so the history is a legible scientific record rather than
# "iteration N: changed stuff". MODIFY (a structural edit) carries the strongest
# obligation: it must be justified by a diagnosis (see `validate`, I6).
ACTIONS = ("TUNE", "SELECT", "MODIFY", "MEASURE", "GIVE_UP")


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
        "spike": None,
        "history": [],
        "log": [],
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


def record_spike(state: dict, *, expressible: bool, artifact: dict | None = None,
                 note: str = "") -> dict:
    """Record the feasibility spike and move to the SPIKE state.

    ``expressible`` is the probe's verdict: did a cheap run through the ACTUAL
    simulator show the chosen mechanism vocabulary can produce the phenomenon,
    at least directionally? ``artifact`` is the evidence (e.g. ``{n_steps, trend,
    plot_path}``). Locking a contract while ``expressible`` is False is an I0
    violation (see :func:`validate`) — the spike exists precisely to stop the loop
    from freezing numeric thresholds against a target the engine cannot express."""
    state = dict(state)
    state["spike"] = {"expressible": bool(expressible),
                      "artifact": dict(artifact or {}), "note": note}
    state["state"] = "SPIKE"
    return state


def advance(state: dict, to_state: str, **fields) -> dict:
    if to_state not in STATES:
        raise ValueError(f"unknown loop state {to_state!r}")
    state = dict(state)
    state["state"] = to_state
    state.update(fields)
    return state


def record_iteration(state: dict, *, edit: str, target: str,
                     margin_deltas: dict, gate: str, tests: list | None = None,
                     action: str | None = None, diagnosis: dict | None = None) -> dict:
    """Append one iteration to the loop history.

    ``tests`` (optional) is the per-test verdict snapshot for this iteration —
    a list of ``{"name", "verdict", "margin"}`` — which lets a renderer draw a
    per-test signed-margin matrix (rows=tests, columns=iterations) instead of
    only the aggregate ``gate``. Omitted for back-compat; when absent the record
    simply carries no ``tests`` key.

    ``action`` (optional) is one of :data:`ACTIONS` — the typed kind of step this
    iteration took (TUNE / SELECT / MODIFY / MEASURE / GIVE_UP), so the history is
    a legible scientific record. A ``MODIFY`` (structural edit) should carry a
    ``diagnosis`` (``{"hypotheses": [...>=2...], "discriminating_measure": ...}``);
    :func:`validate` flags a MODIFY without one (I6). Both are omitted for
    back-compat; a record with no ``action`` is a legacy iteration and is exempt.
    """
    if action is not None and action not in ACTIONS:
        raise ValueError(f"unknown loop action {action!r}; expected one of {ACTIONS}")
    state = dict(state)
    state["iteration"] = int(state.get("iteration", 0)) + 1
    budget = dict(state.get("budget") or {})
    budget["spent"] = int(budget.get("spent", 0)) + 1
    state["budget"] = budget
    record = {
        "iteration": state["iteration"], "edit": edit, "target": target,
        "margin_deltas": margin_deltas or {}, "gate": gate,
    }
    if action is not None:
        record["action"] = action
    if diagnosis is not None:
        record["diagnosis"] = diagnosis
    if tests:
        record["tests"] = [
            {"name": t.get("name"), "verdict": t.get("verdict"), "margin": t.get("margin")}
            for t in tests
        ]
    state["history"] = list(state.get("history") or []) + [record]
    return state


def record_note(state: dict, *, kind: str, text: str, refs: list | None = None) -> dict:
    """Append a typed ledger row to the ONE state — the SDD ledger (commits, rulings,
    deferred findings) lives here rather than in a separate file. ``kind`` is one of
    :data:`NOTE_KINDS`; the row is stamped with the current iteration so the log
    interleaves with ``history`` on a render."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"unknown note kind {kind!r}; expected one of {NOTE_KINDS}")
    state = dict(state)
    row = {"kind": kind, "text": text, "refs": list(refs or []),
           "at_iteration": int(state.get("iteration", 0))}
    state["log"] = list(state.get("log") or []) + [row]
    return state


def to_trajectory(state: dict) -> dict:
    """Render the ``model_build_trajectory/v2`` view FROM the state — so the trajectory
    is a derived projection, not a separately-captured artifact. The state owns
    question / audit / spike / lock / iterations / result / log; a driver may augment
    the render with driver-only extras (a `draft` spec, `timeseries`) it holds, but it
    never needs to persist a second copy of what the state already records."""
    prereg = state.get("prereg_record") or {}
    return {
        "schema": "model_build_trajectory/v2",
        "study": state.get("study"),
        "question": state.get("question"),
        "audit": state.get("audit"),
        "spike": state.get("spike"),
        "lock": {
            "tests_hash": state.get("locked_tests_hash"),
            "locked_at_iteration": prereg.get("locked_at_iteration"),
            "reopen_count": int(state.get("reopen_count", 0)),
            "prior_hashes": list(prereg.get("prior_hashes") or []),
        },
        "iterations": list(state.get("history") or []),
        "result": {
            "state": state.get("state"),
            "last_verdict": state.get("last_verdict"),
            "budget": state.get("budget"),
        },
        "log": list(state.get("log") or []),
    }


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
    # I0 — feasibility: never lock a contract against a phenomenon the simulator
    # cannot express. A spike marked non-expressible while the tests are locked is
    # the failure the SPIKE stage exists to prevent. Absence of a spike is NOT a
    # violation (back-compat with pre-SPIKE loop files); only an explicit
    # non-expressible verdict under a lock is.
    spike = state.get("spike")
    if locked and isinstance(spike, dict) and spike.get("expressible") is False:
        out.append("I0: contract locked while the feasibility spike marked the "
                   "phenomenon non-expressible by the simulator")
    # I6 — diagnosis before structural change: a MODIFY (structural model edit) must
    # be justified by a diagnosis with >=2 competing hypotheses AND the MEASURE that
    # discriminates them. A failed margin should trigger diagnosis, not a reflexive
    # edit. Only enforced on iterations that declare action=="MODIFY"; legacy
    # iterations (no action) and other actions (TUNE/SELECT/MEASURE) are exempt.
    for h in (state.get("history") or []):
        if h.get("action") != "MODIFY":
            continue
        diag = h.get("diagnosis") or {}
        hyps = diag.get("hypotheses") or []
        if len(hyps) < 2 or not diag.get("discriminating_measure"):
            out.append(
                f"I6: MODIFY at iteration {h.get('iteration')} without a diagnosis "
                "(>=2 competing hypotheses + a discriminating MEASURE)")
    return out
