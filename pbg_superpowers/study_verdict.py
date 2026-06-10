"""Roll per-test outcomes → a study verdict → write the coded gate_evaluator slot.

Spine stage #2 (coded gate/verdict/acceptance roll-up).

The verdict rule is the single canonical source replacing the three inline
``tests-passed`` re-implementations. The ``passed`` predicate EXACTLY matches
``vivarium_dashboard.server._condition_satisfied`` ``tests-passed`` branch:
    counts["fail"] == 0 and counts["pass"] > 0

Public API
----------
roll_up_verdict(spec) -> dict
    Pure function: canonical per-test outcomes → {result, blocked_by, evaluated_by}.

write_gate_evaluator(study_dir) -> bool
    Ruamel round-trip write of pipeline_gate.gate_evaluator (parallel coded slot).
    Never touches gate_status / report.verdict / any authored field.
    Returns True when the file was changed, False on a no-op (idempotent).
"""
from __future__ import annotations

from pathlib import Path

from .study_outcomes import canonical_outcomes
from .study_status import _TEST_FAIL, _TEST_PASS, _TEST_SKIP, _study_tests


# ---------------------------------------------------------------------------
# Verdict vocabulary — the result values this module emits
# ---------------------------------------------------------------------------
_RESULT_PASSED = "passed"
_RESULT_FAILED = "failed"
_RESULT_NEEDS_CALIBRATION = "needs_calibration"
_RESULT_BLOCKED = "blocked"
_RESULT_NOT_STARTED = "not_started"

# Map authored gate_status values → the same result vocabulary so divergence
# can be detected by simple equality.
_GATE_STATUS_MAP: dict[str, str] = {
    "passed": _RESULT_PASSED,
    "failed": _RESULT_FAILED,
    "failed_evaluation": _RESULT_FAILED,
    "blocked": _RESULT_BLOCKED,
    "needs_calibration": _RESULT_NEEDS_CALIBRATION,
}


# ---------------------------------------------------------------------------
# Task 1: roll_up_verdict
# ---------------------------------------------------------------------------

def roll_up_verdict(spec: dict) -> dict:
    """Compute the study verdict from the canonical run's per-test outcomes.

    Parameters
    ----------
    spec : dict
        The study spec (e.g. from study_io.load_yaml_mapping). Must carry at
        least one of ``behavior_tests`` / ``tests`` / ``expected_behavior`` and
        optionally ``runs``.

    Returns
    -------
    dict with keys:
        result       : str  — one of the _RESULT_* constants above
        blocked_by   : list[str]  — test names that are FAIL or still pending
        evaluated_by : str  — always "code"
    """
    tests = _study_tests(spec)
    outcomes = canonical_outcomes(spec)

    has_any_run = bool((spec.get("runs") or []))

    pass_names: list[str] = []
    fail_names: list[str] = []
    skip_names: list[str] = []
    pending_names: list[str] = []

    for t in tests:
        name = t.get("name") or ""
        out = outcomes.get(name)
        res = out.get("result") if isinstance(out, dict) else out
        r = str(res or "").strip().lower()
        if r in _TEST_PASS:
            pass_names.append(name)
        elif r in _TEST_FAIL:
            fail_names.append(name)
        elif r in _TEST_SKIP:
            skip_names.append(name)
        else:
            pending_names.append(name)

    # Verdict rule — canonical; must mirror server._condition_satisfied exactly.
    # Priority: FAIL > PARTIAL/SKIP (needs_calibration) > PASSED > no-run.
    # Note: the gate condition for DAG unblocking is "fail==0 and pass>0"
    # (server._condition_satisfied, tests-passed). The displayed verdict adds a
    # finer bucket: "needs_calibration" when any partial/skip outcomes exist
    # alongside passes, so calibration work is visibly outstanding.
    if fail_names:
        result = _RESULT_FAILED
        blocked_by = fail_names + pending_names
    elif skip_names and not fail_names:
        # Any PARTIAL/SKIP outcome, no failures → needs calibration
        result = _RESULT_NEEDS_CALIBRATION
        blocked_by = []
    elif pass_names and not fail_names:
        # passed: fail==0 and pass>0 — EXACTLY the server.py gate predicate
        result = _RESULT_PASSED
        blocked_by = []
    elif not has_any_run or not tests:
        result = _RESULT_NOT_STARTED
        blocked_by = list(t.get("name", "") for t in tests)
    else:
        # Has runs but all tests are pending (no recorded outcomes)
        result = _RESULT_BLOCKED
        blocked_by = pending_names

    return {
        "result": result,
        "blocked_by": blocked_by,
        "evaluated_by": "code",
    }


# ---------------------------------------------------------------------------
# Task 2: write_gate_evaluator
# ---------------------------------------------------------------------------

def write_gate_evaluator(study_dir) -> bool:
    """Write pipeline_gate.gate_evaluator (coded parallel slot) into study.yaml.

    Uses ruamel round-trip to preserve all comments and formatting. Only the
    ``pipeline_gate.gate_evaluator`` mapping is created/updated — the authored
    ``gate_status``, ``report.verdict``, and all other authored fields are
    NEVER touched.

    ``diverges_from_authored`` is True when the authored ``gate_status`` (mapped
    to the result vocabulary) disagrees with the computed result. False when no
    authored gate_status exists (no comparison possible) or they agree.

    ``evaluated_at`` is intentionally omitted: it is a datetime and is not
    deterministically available in this environment. The caller may inject it
    after the fact if needed.

    Returns True when study.yaml was rewritten, False when the computed
    gate_evaluator is identical to what was already written (idempotent).
    """
    from io import StringIO

    from ruamel.yaml import YAML

    from . import study_io

    study_dir = Path(study_dir)
    study_yaml = study_dir / "study.yaml"

    # Load spec for verdict computation (plain safe-load, no round-trip needed here)
    spec = study_io.load_yaml_mapping(study_yaml)
    verdict = roll_up_verdict(spec)

    # Authored gate_status → mapped result (for divergence check)
    authored_gate = str(spec.get("gate_status") or "").strip().lower()
    authored_mapped = _GATE_STATUS_MAP.get(authored_gate)
    if authored_mapped is None:
        # No recognised authored gate_status → divergence is undefined; default False
        diverges = False
    else:
        diverges = authored_mapped != verdict["result"]

    new_evaluator: dict = {
        "result": verdict["result"],
        "blocked_by": verdict["blocked_by"],
        "evaluated_by": "code",
        "diverges_from_authored": diverges,
    }

    # Round-trip load to preserve comments
    ryaml = YAML()
    ryaml.preserve_quotes = True
    ryaml.width = 4096

    rt_spec = ryaml.load(study_yaml.read_text())
    if rt_spec is None:
        rt_spec = {}

    # Locate or create pipeline_gate
    pg = rt_spec.get("pipeline_gate")
    if not isinstance(pg, dict):
        pg = {}
        rt_spec["pipeline_gate"] = pg

    # Compare existing gate_evaluator to detect no-op
    existing = pg.get("gate_evaluator")
    if isinstance(existing, dict):
        # Compare field by field (ruamel CommentedMap compares equal to plain dict)
        existing_plain = {
            "result": existing.get("result"),
            "blocked_by": list(existing.get("blocked_by") or []),
            "evaluated_by": existing.get("evaluated_by"),
            "diverges_from_authored": existing.get("diverges_from_authored"),
        }
        if existing_plain == new_evaluator:
            return False  # idempotent no-op

    # Write ONLY the gate_evaluator sub-mapping; leave all other fields intact
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    ge = CommentedMap()
    ge["result"] = new_evaluator["result"]
    bl = CommentedSeq(new_evaluator["blocked_by"])
    ge["blocked_by"] = bl
    ge["evaluated_by"] = new_evaluator["evaluated_by"]
    ge["diverges_from_authored"] = new_evaluator["diverges_from_authored"]

    pg["gate_evaluator"] = ge

    buf = StringIO()
    ryaml.dump(rt_spec, buf)
    study_io.atomic_write(study_yaml, buf.getvalue())
    return True
