"""SP5 — the "decisions needed" scan (Active Investigation Framework, Guide layer).

A PURE, deterministic aggregator. It makes NO new judgment: it GATHERS + RANKS
the divergences/gaps SP1–SP4 already compute into one per-investigation ranked
list — the "what needs my decision" entry point a navigator should LEAD with.

The six signals (all reuse — none reimplemented):

  1. Uncovered acceptance criterion  — ``linkage_index.ac_gating_matrix(..)["gaps"]``  (high)
  2. Verdict divergence              — persisted ``pipeline_gate.gate_evaluator.diverges_from_authored``
                                        + per-test ``computed_outcomes[t]["reconcile"]=="divergent"`` (high)
  3. Open expert feedback           — ``feedback_actions.study_feedback_actions``    (medium)
  4. Phantom / not-in-structure observable — ``readout_validation.validate_readouts`` (high, OPT-IN)
  5. Param drift                    — ``param_enforcement.check_enforced_params``     (high)
  6. Stale finding                  — greenfield ``_stale_findings`` classifier       (low)

Isolation invariant (the SP4b lesson): the scan is build-free and cheap by
DEFAULT — signals 1,2,3,5,6 read YAML only. Signal 4 (phantom observable) needs
a composite build, so it is opt-in behind an INJECTED ``observables_for_ref``;
with no ``observables_for_ref`` the scan omits signal 4 entirely.

Best-effort PER SIGNAL: one raising source must never sink the scan (mirrors
``linkage_index``'s per-study tolerance). The output is EPHEMERAL — never written
back to YAML. AI-free: deterministic aggregation only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .workspace_paths import WorkspacePaths
from . import linkage_index


# ---------------------------------------------------------------------------
# Item shape + ranking
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Finding statuses that mark a finding as already terminal/accepted — these are
# NOT decisions-needed even with no seeded_study.
_TERMINAL_FINDING_STATUSES = {
    "accepted", "resolved", "closed", "seeded", "confirms", "done",
}


def _item(kind: str, severity: str, study: str | None, ref: str,
          title: str, detail: str, action_hint: str) -> dict:
    return {
        "kind": kind,
        "severity": severity,
        "study": study,
        "ref": ref,
        "title": title,
        "detail": detail,
        "action_hint": action_hint,
    }


# ---------------------------------------------------------------------------
# Signal 6: stale-finding classifier (greenfield)
# ---------------------------------------------------------------------------

def _stale_findings(spec: dict) -> list[dict]:
    """Return the findings in ``spec`` that are stale.

    A finding is stale when:
      * ``next_action`` absent/empty AND no ``seeded_study``, OR
      * ``next_action`` present but no ``seeded_study``.

    i.e. it carries no ``seeded_study`` link — the "what next" signal was never
    followed through. A finding whose ``status`` marks it terminal/accepted (see
    ``_TERMINAL_FINDING_STATUSES``) is excluded.
    """
    out: list[dict] = []
    for f in (spec.get("findings") or []):
        if not isinstance(f, dict):
            continue
        status = str(f.get("status") or "").strip().lower()
        if status in _TERMINAL_FINDING_STATUSES:
            continue
        seeded = f.get("seeded_study")
        has_seeded = isinstance(seeded, str) and seeded.strip() != ""
        if not has_seeded:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Per-signal collectors (each best-effort, called inside its own try/except)
# ---------------------------------------------------------------------------

def _uncovered_ac_items(ws_root: Path, inv_slug: str) -> list[dict]:
    matrix = linkage_index.ac_gating_matrix(ws_root, inv_slug)
    items: list[dict] = []
    for gap in (matrix.get("gaps") or []):
        behavior = gap.get("behavior") or ""
        items.append(_item(
            "uncovered_ac", "high", None, behavior,
            f"Acceptance criterion '{behavior}' has no study link",
            "No study: link covers this criterion — it cannot be gated.",
            "link or author a study",
        ))
    return items


def _verdict_divergence_items(slug: str, spec: dict) -> list[dict]:
    items: list[dict] = []
    pg = spec.get("pipeline_gate")
    ge = pg.get("gate_evaluator") if isinstance(pg, dict) else None
    if isinstance(ge, dict) and ge.get("diverges_from_authored"):
        items.append(_item(
            "verdict_divergence", "high", slug, slug,
            f"Study '{slug}' computed verdict diverges from the authored gate",
            "pipeline_gate.gate_evaluator.diverges_from_authored is set.",
            "reconcile verdict",
        ))
    for run in (spec.get("runs") or []):
        if not isinstance(run, dict):
            continue
        co = run.get("computed_outcomes")
        if not isinstance(co, dict):
            continue
        for test, entry in co.items():
            if isinstance(entry, dict) and entry.get("reconcile") == "divergent":
                items.append(_item(
                    "verdict_divergence", "high", slug, str(test),
                    f"Test '{test}' computed outcome diverges from the authored outcome",
                    f"run '{run.get('name')}': computed_outcomes['{test}'].reconcile == 'divergent'.",
                    "reconcile verdict",
                ))
    return items


def _open_feedback_items(ws_root: Path, slug: str) -> list[dict]:
    from .feedback_actions import study_feedback_actions

    res = study_feedback_actions(ws_root, slug)
    items: list[dict] = []
    for it in (res.get("items") or []):
        if it.get("status") != "open":
            continue
        items.append(_item(
            "open_feedback", "medium", slug, str(it.get("item_id") or ""),
            f"Unaddressed expert feedback on '{slug}'",
            it.get("text") or "",
            "apply or dismiss feedback",
        ))
    return items


def _param_drift_items(slug: str, spec: dict) -> list[dict]:
    from .param_enforcement import check_enforced_params, load_enforced_params

    declared = load_enforced_params(spec)
    if not declared:
        return []
    items: list[dict] = []
    for run in (spec.get("runs") or []):
        if not isinstance(run, dict):
            continue
        applied = run.get("params")
        if not isinstance(applied, dict):
            # Can't assemble applied params for this run — skip it (best-effort).
            continue
        for v in check_enforced_params(declared, applied):
            items.append(_item(
                "param_drift", "high", slug, v.param,
                f"Enforced param '{v.param}' not honored by run '{run.get('name')}'",
                v.describe(),
                "re-run / update enforcement",
            ))
    return items


def _stale_finding_items(slug: str, spec: dict) -> list[dict]:
    items: list[dict] = []
    for f in _stale_findings(spec):
        fid = str(f.get("id") or "")
        na = f.get("next_action")
        if isinstance(na, str) and na.strip():
            detail = f"next_action set ('{na.strip()}') but no seeded_study."
        else:
            detail = "no next_action and no seeded_study."
        items.append(_item(
            "stale_finding", "low", slug, fid,
            f"Finding '{fid}' has no follow-through",
            detail,
            "draft next_action / seed",
        ))
    return items


def _phantom_observable_items(
    slug: str, spec: dict, observables_for_ref: Callable[[str], Any],
) -> list[dict]:
    from .readout_validation import validate_readouts

    items: list[dict] = []
    for ref in linkage_index._composites_of_study(spec):
        try:
            available = observables_for_ref(ref)
        except Exception:  # noqa: BLE001 — a build that raises skips this ref
            continue
        if not isinstance(available, dict):
            continue
        try:
            results = validate_readouts(spec, available=available)
        except Exception:  # noqa: BLE001
            continue
        for r in results:
            if r.get("status") == "not_in_structure":
                items.append(_item(
                    "phantom_observable", "high", slug, str(r.get("name") or ""),
                    f"Readout '{r.get('name')}' is not in the composite structure",
                    r.get("detail") or "",
                    "fix the readout",
                ))
    return items


# ---------------------------------------------------------------------------
# The aggregator
# ---------------------------------------------------------------------------

def _member_studies(wp: WorkspacePaths, inv_spec: dict) -> list[tuple[str, dict]]:
    """Resolve the investigation's member studies (slug, spec), filtered to its
    ``studies:`` list. Best-effort — unparseable studies are silently skipped."""
    members = inv_spec.get("studies")
    member_set = (
        {m for m in members if isinstance(m, str)} if isinstance(members, list)
        else None
    )
    out: list[tuple[str, dict]] = []
    for slug, _sdir, spec in linkage_index._iter_studies(wp):
        if member_set is None or slug in member_set:
            out.append((slug, spec))
    return out


def scan_investigation(
    ws_root: Path | str,
    inv_slug: str,
    *,
    observables_for_ref: Callable[[str], Any] | None = None,
) -> dict:
    """Aggregate SP1–SP4 signals for one investigation into a ranked list.

    Args:
        ws_root: workspace root.
        inv_slug: the investigation slug (``investigations/<slug>/investigation.yaml``).
        observables_for_ref: OPT-IN. A ``ref -> {"leaves", "catalogs"}`` callable
            (the dashboard's cached composite-build adapter). When provided, the
            phantom-observable signal (4) runs; otherwise it is omitted and the
            scan is fully build-free.

    Returns:
        ``{"investigation": slug, "items": [...], "summary": {...}}`` where each
        item is the normalized ``{kind, severity, study, ref, title, detail,
        action_hint}`` dict, sorted by severity (high→medium→low) then kind then
        ref. PURE — reads YAML only, writes nothing.
    """
    ws_root = Path(ws_root)
    wp = WorkspacePaths.load(ws_root)
    inv_spec = linkage_index._load(
        wp.dir("investigations") / inv_slug / "investigation.yaml"
    ) or {}

    items: list[dict] = []

    # Signal 1 — uncovered acceptance criteria (investigation-level).
    try:
        items.extend(_uncovered_ac_items(ws_root, inv_slug))
    except Exception:  # noqa: BLE001
        pass

    # Per member study: signals 2,3,5,6 (+4 when opted in). Each in its own
    # try/except so one failing source never sinks the whole scan.
    for slug, spec in _member_studies(wp, inv_spec):
        try:
            items.extend(_verdict_divergence_items(slug, spec))
        except Exception:  # noqa: BLE001
            pass
        try:
            items.extend(_open_feedback_items(ws_root, slug))
        except Exception:  # noqa: BLE001
            pass
        try:
            items.extend(_param_drift_items(slug, spec))
        except Exception:  # noqa: BLE001
            pass
        try:
            items.extend(_stale_finding_items(slug, spec))
        except Exception:  # noqa: BLE001
            pass
        if observables_for_ref is not None:
            try:
                items.extend(
                    _phantom_observable_items(slug, spec, observables_for_ref)
                )
            except Exception:  # noqa: BLE001
                pass

    items.sort(key=lambda i: (
        _SEVERITY_RANK.get(i["severity"], 99), i["kind"], i["ref"]
    ))

    return {
        "investigation": inv_slug,
        "items": items,
        "summary": _summary(items),
    }


def _summary(items: list[dict]) -> dict:
    by_severity = {"high": 0, "medium": 0, "low": 0}
    by_kind: dict[str, int] = {}
    for it in items:
        sev = it["severity"]
        if sev in by_severity:
            by_severity[sev] += 1
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {
        "by_severity": by_severity,
        "by_kind": by_kind,
        "total": len(items),
    }
