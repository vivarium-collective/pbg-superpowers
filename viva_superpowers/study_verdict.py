"""Roll per-test outcomes → a study verdict → write the coded gate_evaluator slot.

Spine stage #2 (coded gate/verdict/acceptance roll-up).

The verdict rule is the single canonical source replacing the three inline
``tests-passed`` re-implementations. The ``passed`` predicate EXACTLY matches
``vivarium_workbench.lib.investigations_index._condition_satisfied`` ``tests-passed`` branch:
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

from .study_outcomes import canonical_outcomes, canonical_run
from .study_status import _study_tests, bucket_tests


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

    # Shared per-test classification (single-sourced in study_status.bucket_tests,
    # also used by count_test_outcomes). The verdict rule below is what makes this
    # the COMPUTED verdict — distinct from study_status.study_clarity_summary,
    # which prefers the AUTHORED gate_status.
    buckets = bucket_tests(tests, outcomes)
    pass_names = buckets["pass"]
    fail_names = buckets["fail"]
    skip_names = buckets["skip"]
    pending_names = buckets["pending"]

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

    # Surface the per-test counts the verdict was derived from, so a consumer
    # can distinguish "4 passed, 1 skipped" from "0 passed, 1 skipped" — both
    # yield needs_calibration by the conservative gate above (skip short-circuits
    # before the pass check, intentionally), but they are very different states
    # for a reader. The result stays the single gate signal; counts carry the
    # progress. Same {total,pass,fail,skip,pending} shape as
    # study_status.count_test_outcomes, from the same bucket_tests source.
    counts = {
        "total": len(tests),
        "pass": len(pass_names),
        "fail": len(fail_names),
        "skip": len(skip_names),
        "pending": len(pending_names),
    }

    return {
        "result": result,
        "blocked_by": blocked_by,
        "counts": counts,
        "evaluated_by": "code",
    }


# ---------------------------------------------------------------------------
# Authored-vs-computed divergence (pure helper, reusable by callers/spines)
# ---------------------------------------------------------------------------

def diverges_from_authored(spec: dict) -> bool:
    """True when the authored ``gate_status`` disagrees with the computed verdict.

    Pure ``spec -> bool``. Maps the authored ``gate_status`` to the result
    vocabulary and compares it to ``roll_up_verdict(spec)['result']``. Returns
    False when there is no recognised authored ``gate_status`` (no comparison
    possible) or when authored and computed agree.

    This is the single canonical divergence rule used by
    :func:`write_gate_evaluator`; it is exposed so other code (e.g. the
    pbg-autopoiesis spine) can compute the same value without a file write.
    """
    spec = spec or {}
    verdict = roll_up_verdict(spec)
    authored_gate = str(spec.get("gate_status") or "").strip().lower()
    authored_mapped = _GATE_STATUS_MAP.get(authored_gate)
    if authored_mapped is None:
        return False
    return authored_mapped != verdict["result"]


# ---------------------------------------------------------------------------
# Pre-registration status (critique #18) — pure spec -> dict
# ---------------------------------------------------------------------------


def _run_start_timestamp(run: dict | None) -> str | None:
    """The canonical run's start time, preferring ``started_at`` then the
    generic ``timestamp`` (which study_outcomes derives from completed/started)."""
    if not isinstance(run, dict):
        return None
    for k in ("started_at", "timestamp"):
        v = run.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def preregistration_status(spec: dict) -> dict:
    """Whether a study's acceptance criteria were PRE-registered (critique #18).

    Pure ``spec -> {preregistered, registered_before_run, criteria_match}``:

    - ``preregistered`` (bool) — a non-empty ``preregistered:`` block exists.
    - ``registered_before_run`` (bool | None) — ``preregistered.registered_at``
      is at or before the canonical run's start time. ``None`` when either
      timestamp is missing (degrade gracefully — author-supplied ``registered_at``
      is often absent).
    - ``criteria_match`` (bool | None) — every name in
      ``preregistered.thresholds`` resolves to a ``behavior_tests[]`` whose
      ``pass_if`` equals the pre-registered threshold. ``None`` when no
      ``thresholds`` were declared.

    Tolerant of a minimal / absent block.
    """
    spec = spec or {}
    prereg = spec.get("preregistered")
    if not isinstance(prereg, dict) or not prereg:
        return {
            "preregistered": False,
            "registered_before_run": None,
            "criteria_match": None,
        }

    out: dict = {
        "preregistered": True,
        "registered_before_run": None,
        "criteria_match": None,
    }

    # registered_before_run — compare the author-supplied registered_at (ISO
    # string) to the canonical run's start. ISO-8601 strings order lexically.
    registered_at = prereg.get("registered_at")
    started = _run_start_timestamp(canonical_run(spec))
    if (isinstance(registered_at, str) and registered_at.strip()
            and isinstance(started, str) and started.strip()):
        out["registered_before_run"] = registered_at.strip() <= started.strip()

    # criteria_match — pre-registered thresholds vs the actual behavior_tests.
    thresholds = prereg.get("thresholds")
    if isinstance(thresholds, dict) and thresholds:
        actual = {
            t.get("name"): t.get("pass_if")
            for t in _study_tests(spec)
            if isinstance(t, dict) and t.get("name")
        }
        match = True
        for name, predeclared in thresholds.items():
            if name not in actual or actual.get(name) != predeclared:
                match = False
                break
        out["criteria_match"] = match

    return out


# ---------------------------------------------------------------------------
# Finding lifecycle floor (critique #25)
# ---------------------------------------------------------------------------

# The maturity ladder a finding climbs (DISTINCT from ``tier``, the claim class,
# and from ``claim_scope``, the claim breadth). The first five are derivable
# from rigor signals; ``retired`` / ``superseded`` are terminal states an author
# sets manually (never auto-derived).
LIFECYCLE_STATES = (
    "observation",
    "candidate-explanation",
    "tested-vs-alternatives",
    "provisional-claim",
    "generalized",
    "retired",
    "superseded",
)
_LIFECYCLE_RANK = {s: i for i, s in enumerate(LIFECYCLE_STATES)}


def lifecycle_floor(finding: dict, spec: dict) -> str:
    """Derive the MINIMUM lifecycle_state a finding has earned (critique #25).

    Pure ``(finding, spec) -> str``. Reuses the rigor signals already computed:

    - ``observation`` — the default floor.
    - ``candidate-explanation`` — the finding is an explanatory claim
      (``tier`` of mechanism/interpretation), not a bare observation.
    - ``tested-vs-alternatives`` — a competing explanation has been EXCLUDED and
      its discriminator names this finding's test (reuses the rigor alternatives
      matcher; degrades to "any excluded alternative in the study").
    - ``provisional-claim`` — the result REPLICATES with cross-seed agreement
      (reuses ``rigor._replication_agreement``).
    - ``generalized`` — a generality / robustness signal is present (critique
      #22; reuses ``rigor._has_generality_signal``).

    Each level's precondition is checked independently and the HIGHEST satisfied
    level is returned (the floor). An authored ``lifecycle_state`` may sit ABOVE
    the floor, but the linter warns when it sits BELOW. ``retired`` /
    ``superseded`` are never returned (they are author-only terminal states).
    """
    finding = finding or {}
    spec = spec or {}
    rank = 0  # observation

    tier = str(finding.get("tier") or "").strip().lower()
    if tier in ("mechanism", "interpretation"):
        rank = max(rank, _LIFECYCLE_RANK["candidate-explanation"])

    # Defensive import of the rigor predicates (rigor imports study_verdict
    # lazily, so a module-level import here would risk a cycle).
    try:
        from . import rigor as _rigor
    except Exception:  # noqa: BLE001
        _rigor = None  # type: ignore

    if _rigor is not None:
        tokens = _rigor._finding_match_tokens(finding)
        excluded = _rigor._excluded_alternatives(spec)
        matched = [a for a in excluded if _rigor._alt_matches(a, tokens)]
        if matched or (excluded and not tokens):
            rank = max(rank, _LIFECYCLE_RANK["tested-vs-alternatives"])

        n_rep, _ = _rigor._replicate_count(spec)
        if n_rep >= 2:
            disagrees, _ = _rigor._replication_agreement(spec, n_rep)
            replicated = (n_rep >= 3) and not disagrees
            if replicated:
                rank = max(rank, _LIFECYCLE_RANK["provisional-claim"])

        # generalized requires the FINDING's OWN generality claim (#22) — NOT a
        # study-level sweep (which would lift every finding in the study) and NOT
        # mere replication (which only earns provisional-claim above). A single
        # declared axis earns provisional-claim; ≥2 axes or an explicit
        # framework-level claim earns generalized. A finding the author marked
        # instance_specific never reaches generalized.
        faxes = _rigor._finding_generality_axes(finding)
        gen = finding.get("generality") if isinstance(finding.get("generality"), dict) else {}
        level = str(gen.get("level") or "").strip().lower()
        if level != "instance_specific" and (len(faxes) >= 2 or level == "framework"):
            rank = max(rank, _LIFECYCLE_RANK["generalized"])
        elif faxes:
            rank = max(rank, _LIFECYCLE_RANK["provisional-claim"])

    return LIFECYCLE_STATES[rank]


def lifecycle_below_floor(finding: dict, spec: dict) -> str | None:
    """If a finding's authored ``lifecycle_state`` sits BELOW its derived floor,
    return the floor; otherwise ``None``.

    Returns ``None`` when no ``lifecycle_state`` is authored, when the authored
    value is unknown (the enum check is a separate concern), or when it is at or
    above the floor.
    """
    finding = finding or {}
    authored = str(finding.get("lifecycle_state") or "").strip().lower()
    if authored not in _LIFECYCLE_RANK:
        return None
    floor = lifecycle_floor(finding, spec)
    if _LIFECYCLE_RANK[authored] < _LIFECYCLE_RANK[floor]:
        return floor
    return None


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

    # Authored gate_status vs computed verdict (single canonical rule).
    diverges = diverges_from_authored(spec)

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

    rt_spec = ryaml.load(study_yaml.read_text(encoding="utf-8"))
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
