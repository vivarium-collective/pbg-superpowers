"""Pass 10B helper for ``/pbg-study seed-from-followup --from-finding <id>``.

The bulk of ``seed-from-followup`` is prose-driven (the Claude host
follows the steps in ``skills/pbg-study/SKILL.md``) — there is no
dashboard API and no full Python implementation. What *can* be made
deterministic and testable is the **finding-to-child pre-population**:
given a parent study and a finding id, derive the child's ``purpose``
block, ``key_assumptions``, ``seeded_from`` stamp, plus a starter
``pipeline_gate``, ``behavior_tests`` carryover, and a ``model_change``
hint, and produce the updated parent proposal entry. This module
exposes those primitives so the prose flow + a CLI smoke test can
share one implementation.

Public surface:

  - :func:`build_child_seed_from_finding` — pure function: given the
    parent study dict, a proposal id, and a finding id, returns a
    ``ChildSeed`` with the new study's ``purpose`` + ``key_assumptions``
    + ``seeded_from`` + ``pipeline_gate`` + ``behavior_tests`` +
    ``model_change`` ready to merge into the child template.
  - :func:`build_parent_proposal_patch` — pure function: returns the
    updated proposal-entry dict (status flipped to ``seeded``,
    ``seeded_study`` set, ``linked_finding`` added if absent).
  - :func:`apply_from_finding` — convenience wrapper that loads the
    parent yaml, builds both diffs, and returns them; the actual
    file writes still live in the prose flow (mirrors the
    propose-followup pattern).

Findings-to-child heuristic (also documented in SKILL.md so the
prose flow stays in sync):

  - ``purpose.question`` ← derived from the finding's ``next_action``
    (e.g. "Investigate why X" / "Calibrate Y to match Z"). Falls back
    to "Investigate <finding.statement first-sentence>?" if absent.
  - ``purpose.mechanism`` ← finding's ``explanation`` verbatim (when
    set; else empty string).
  - ``purpose.expected_outcome`` ← derived from ``next_action`` if it
    implies a target (heuristic: keywords like "to match", "within",
    "in range"); else empty string.
  - ``key_assumptions[0]`` ← ``evidence.smoking_gun`` (if present and
    a plain string).
  - ``seeded_from.finding`` ← the supplied finding id.
  - ``seeded_from.evidence`` ← copy of the parent finding's
    ``evidence`` block, so the child's lineage is self-contained
    without the reader having to flip back to the parent.
  - ``pipeline_gate.proceed_condition`` ← finding's ``next_action``
    verbatim, as a starting point for what unblocks downstream work.
  - ``behavior_tests`` ← the parent's behavior_test referenced by
    ``finding.evidence.from_test`` (the test that produced this
    finding — exactly what the follow-up must make pass), reclassified
    as ``primary``.
  - ``model_change`` ← ``{notes: "TBD — see purpose.mechanism for
    the hypothesized mechanism."}`` when the finding has an
    ``explanation`` to anchor on; absent otherwise.

The host Claude can edit any of these before writing — this just
seeds the draft.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbg_superpowers.text_utils import first_sentence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ChildSeed:
    """Fields to merge into the newly-created child study.yaml."""

    purpose: dict = field(default_factory=dict)
    key_assumptions: list[str] = field(default_factory=list)
    seeded_from: dict = field(default_factory=dict)
    pipeline_gate: dict = field(default_factory=dict)
    behavior_tests: list[dict] = field(default_factory=list)
    model_change: dict = field(default_factory=dict)

    def merge_into(self, child: dict) -> dict:
        """Apply the seed onto a partially-constructed child study dict.

        Non-destructive merge:
          - ``purpose`` — existing keys win (the prose flow's earlier
            propose-followup seed has already populated parts of it).
          - ``key_assumptions`` — append, dedup.
          - ``seeded_from`` — merged key-by-key (new ``finding`` /
            ``evidence`` keys add; existing ``study`` / ``proposal_id``
            preserved).
          - ``pipeline_gate`` — existing keys win at the key level.
          - ``behavior_tests`` — append, dedup by ``name``.
          - ``model_change`` — existing keys win at the key level.
        """
        out = dict(child)
        # Purpose: existing wins.
        existing_purpose = dict(out.get("purpose") or {})
        for k, v in self.purpose.items():
            if v and not existing_purpose.get(k):
                existing_purpose[k] = v
        if existing_purpose:
            out["purpose"] = existing_purpose
        # key_assumptions: append, dedup preserving order.
        existing_ka = list(out.get("key_assumptions") or [])
        for a in self.key_assumptions:
            if a and a not in existing_ka:
                existing_ka.append(a)
        if existing_ka:
            out["key_assumptions"] = existing_ka
        # seeded_from: merge key-by-key.
        existing_sf = dict(out.get("seeded_from") or {})
        for k, v in self.seeded_from.items():
            if v:
                existing_sf[k] = v
        if existing_sf:
            out["seeded_from"] = existing_sf
        # pipeline_gate: existing keys win.
        existing_pg = dict(out.get("pipeline_gate") or {})
        for k, v in self.pipeline_gate.items():
            if v and not existing_pg.get(k):
                existing_pg[k] = v
        if existing_pg:
            out["pipeline_gate"] = existing_pg
        # behavior_tests: append, dedup by name.
        existing_bt = list(out.get("behavior_tests") or [])
        existing_names = {
            t.get("name") for t in existing_bt
            if isinstance(t, dict) and t.get("name")
        }
        for t in self.behavior_tests:
            name = t.get("name") if isinstance(t, dict) else None
            if name and name in existing_names:
                continue
            existing_bt.append(t)
            if name:
                existing_names.add(name)
        if existing_bt:
            out["behavior_tests"] = existing_bt
        # model_change: existing keys win. Only an object-shape model_change
        # is mergeable; if the child already has a string-shape model_change
        # (terse summary), leave it alone — caller can promote manually.
        existing_mc = out.get("model_change")
        if isinstance(existing_mc, dict) or existing_mc is None:
            merged_mc = dict(existing_mc or {})
            for k, v in self.model_change.items():
                if v and not merged_mc.get(k):
                    merged_mc[k] = v
            if merged_mc:
                out["model_change"] = merged_mc
        return out


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def find_finding(study: dict, finding_id: str) -> dict | None:
    """Return the finding entry with ``id == finding_id``, or None."""
    for f in (study.get("findings") or []):
        if isinstance(f, dict) and f.get("id") == finding_id:
            return f
    return None


def find_proposal(study: dict, proposal_id: str) -> dict | None:
    """Return the followup_proposals entry with ``id == proposal_id``, or None."""
    for p in (study.get("followup_proposals") or []):
        if isinstance(p, dict) and p.get("id") == proposal_id:
            return p
    return None


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------


_TARGET_HINT_RE = re.compile(
    r"(to match|within|in range|to ([0-9]+|the literature)|equal to|"
    r"at most|at least|below|above)",
    re.IGNORECASE,
)


def _first_sentence(text: str) -> str:
    return first_sentence(text)


def _derive_question(next_action: str | None, statement: str) -> str:
    """Turn an imperative next_action into a question, or fall back to statement."""
    if next_action:
        action = next_action.strip().rstrip(".")
        # Imperative-mood next_actions become questions of the form
        # "Why does <statement-implication>?" / "How do we <action>?".
        # Keep this conservative — the prose flow lets the user edit anyway.
        lower = action.lower()
        if lower.startswith(("investigate", "calibrate", "fix", "tune", "explore", "diagnose")):
            return f"How do we {action[0].lower()}{action[1:]}?"
        if lower.startswith(("seed", "follow up", "run")):
            return f"What does {action.lower()} reveal?"
        return f"{action}?"
    s = _first_sentence(statement)
    if not s:
        return ""
    s = s.rstrip(".!?")
    return f"Investigate {s.lower()}?"


def _derive_expected_outcome(next_action: str | None) -> str:
    """If next_action implies a target (keywords like 'to match', 'within'),
    use the trailing clause as the expected_outcome; else empty."""
    if not next_action:
        return ""
    m = _TARGET_HINT_RE.search(next_action)
    if not m:
        return ""
    return next_action[m.start():].strip().rstrip(".")


def _smoking_gun_assumption(finding: dict) -> str | None:
    """Pull evidence.smoking_gun out as a key_assumption string if present."""
    ev = finding.get("evidence") or {}
    sg = ev.get("smoking_gun") if isinstance(ev, dict) else None
    if isinstance(sg, str) and sg.strip():
        return sg.strip()
    return None


def _evidence_block(finding: dict) -> dict | None:
    """Return a deep-ish copy of finding.evidence (dict) for seeded_from.

    Returns None if evidence is missing or not a dict — we don't propagate
    non-dict evidence into seeded_from.evidence because it would shadow the
    field's expected shape downstream.
    """
    ev = finding.get("evidence")
    if not isinstance(ev, dict) or not ev:
        return None
    # Shallow copy is fine; values are scalars/lists/strings in the
    # findings schema.
    return dict(ev)


def _evidence_test_names(finding: dict) -> list[str]:
    """Tests referenced by the finding's evidence.

    Looks at ``evidence.from_test`` (string) and ``evidence.from_tests``
    (list) — the latter is rare but accepted. Returns names in
    declaration order, dedup'd.
    """
    ev = finding.get("evidence")
    if not isinstance(ev, dict):
        return []
    out: list[str] = []

    def _add(x):
        if isinstance(x, str) and x.strip() and x.strip() not in out:
            out.append(x.strip())

    _add(ev.get("from_test"))
    for x in (ev.get("from_tests") or []):
        _add(x)
    return out


def _find_parent_behavior_test(parent_study: dict, name: str) -> dict | None:
    """Look up a behavior_test by name in the parent study."""
    for t in (parent_study.get("behavior_tests") or []):
        if isinstance(t, dict) and t.get("name") == name:
            return t
    return None


def _carryover_behavior_test(parent_test: dict) -> dict:
    """Build the child's behavior_test entry from a parent test.

    The parent test is the one that produced the finding — it's the
    test the follow-up exists to make pass. We copy its shape but
    reclassify as ``primary`` for the new study (the child's reason
    for existing).
    """
    keep = ("name", "description", "measure", "pass_if", "units",
            "requires_simulation", "blocked_by_requirements",
            "calibration_anchor", "cites")
    out: dict = {}
    for k in keep:
        if k in parent_test:
            v = parent_test[k]
            if isinstance(v, dict):
                out[k] = dict(v)
            elif isinstance(v, list):
                out[k] = list(v)
            else:
                out[k] = v
    out["classification"] = "primary"
    return out


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_child_seed_from_finding(
    parent_study: dict,
    parent_slug: str,
    proposal_id: str,
    finding_id: str,
) -> ChildSeed:
    """Pre-populate child study fields from a parent finding.

    Raises ``ValueError`` if the finding id isn't in
    ``parent_study.findings``. Heuristic mapping is documented in this
    module's docstring.
    """
    finding = find_finding(parent_study, finding_id)
    if finding is None:
        avail = [
            (f.get("id") or "<no-id>")
            for f in (parent_study.get("findings") or [])
            if isinstance(f, dict)
        ]
        raise ValueError(
            f"finding {finding_id!r} not in parent {parent_slug!r}.findings "
            f"(available: {sorted(avail)})"
        )
    statement = finding.get("statement", "") or ""
    next_action = finding.get("next_action")
    explanation = finding.get("explanation", "") or ""

    purpose = {
        "question": _derive_question(next_action, statement),
        "mechanism": explanation.strip(),
        "expected_outcome": _derive_expected_outcome(next_action),
    }
    # Drop empty values so the merge doesn't blank out existing purpose keys.
    purpose = {k: v for k, v in purpose.items() if v}

    key_assumptions: list[str] = []
    sg = _smoking_gun_assumption(finding)
    if sg:
        key_assumptions.append(sg)

    seeded_from: dict = {
        "study": parent_slug,
        "proposal_id": proposal_id,
        "finding": finding_id,
    }
    ev_block = _evidence_block(finding)
    if ev_block is not None:
        seeded_from["evidence"] = ev_block

    pipeline_gate: dict = {}
    if isinstance(next_action, str) and next_action.strip():
        pipeline_gate["proceed_condition"] = next_action.strip()

    # Carry over the parent behavior_tests referenced by this finding —
    # they're the ones the follow-up must make pass.
    behavior_tests: list[dict] = []
    for test_name in _evidence_test_names(finding):
        parent_test = _find_parent_behavior_test(parent_study, test_name)
        if parent_test is not None:
            behavior_tests.append(_carryover_behavior_test(parent_test))

    model_change: dict = {}
    if explanation.strip():
        model_change["notes"] = (
            "TBD — see purpose.mechanism for the hypothesized mechanism."
        )

    return ChildSeed(
        purpose=purpose,
        key_assumptions=key_assumptions,
        seeded_from=seeded_from,
        pipeline_gate=pipeline_gate,
        behavior_tests=behavior_tests,
        model_change=model_change,
    )


def build_parent_proposal_patch(
    proposal: dict,
    new_slug: str,
    finding_id: str | None,
) -> dict:
    """Return an updated copy of ``proposal`` with status=seeded.

    Sets ``status: seeded`` and ``seeded_study: <new_slug>``. When
    ``finding_id`` is provided and the proposal doesn't already
    reference it, also adds ``linked_finding: <finding_id>``.
    """
    out = dict(proposal)
    out["status"] = "seeded"
    out["seeded_study"] = new_slug
    if finding_id and out.get("linked_finding") != finding_id:
        out["linked_finding"] = finding_id
    return out


# ---------------------------------------------------------------------------
# Convenience entry — used by the SKILL prose flow + the CLI smoke test
# ---------------------------------------------------------------------------


@dataclass
class FromFindingPlan:
    """Both diffs ready for the prose flow's confirm + write step."""

    child_seed: ChildSeed
    updated_proposal: dict
    finding: dict           # the source finding (for the preview)
    proposal: dict          # the original proposal (for diffing)


def apply_from_finding(
    parent_yaml: Path,
    proposal_id: str,
    finding_id: str,
    new_slug: str,
) -> FromFindingPlan:
    """Load parent study.yaml + build both diffs. Does NOT write."""
    parent_yaml = Path(parent_yaml)
    if not parent_yaml.is_file():
        raise FileNotFoundError(parent_yaml)
    parent_study = yaml.safe_load(parent_yaml.read_text()) or {}
    parent_slug = parent_study.get("name") or parent_yaml.parent.name

    finding = find_finding(parent_study, finding_id)
    if finding is None:
        raise ValueError(
            f"finding {finding_id!r} not in parent {parent_slug!r}.findings"
        )
    proposal = find_proposal(parent_study, proposal_id)
    if proposal is None:
        raise ValueError(
            f"proposal {proposal_id!r} not in parent {parent_slug!r}.followup_proposals"
        )

    seed = build_child_seed_from_finding(
        parent_study, parent_slug, proposal_id, finding_id,
    )
    updated = build_parent_proposal_patch(proposal, new_slug, finding_id)
    return FromFindingPlan(
        child_seed=seed,
        updated_proposal=updated,
        finding=finding,
        proposal=proposal,
    )


# ---------------------------------------------------------------------------
# CLI entry: python -m pbg_superpowers.seed_from_followup <parent-yaml>
#   <proposal-id> <finding-id> [--new-slug S]
#
# Prints a YAML-shaped preview of both diffs. Used by the SKILL prose flow
# to surface the proposed changes before the host Claude commits the write.
# Never writes anything itself — that's the prose flow's job.
# ---------------------------------------------------------------------------


def _print_preview(plan: FromFindingPlan, new_slug: str, out=print) -> None:
    cs = plan.child_seed
    seed_dict: dict = {
        "purpose": cs.purpose,
        "key_assumptions": cs.key_assumptions,
        "seeded_from": cs.seeded_from,
    }
    if cs.pipeline_gate:
        seed_dict["pipeline_gate"] = cs.pipeline_gate
    if cs.behavior_tests:
        seed_dict["behavior_tests"] = cs.behavior_tests
    if cs.model_change:
        seed_dict["model_change"] = cs.model_change
    out("# Child seed (merge into the new study.yaml):")
    out(yaml.safe_dump(seed_dict, sort_keys=False))
    out(f"# Updated parent proposal ({plan.proposal.get('id')}):")
    out(yaml.safe_dump([plan.updated_proposal], sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m pbg_superpowers.seed_from_followup",
        description=(
            "Pass 10B helper. Pre-compute the child-seed + parent-proposal "
            "patch for `/pbg-study seed-from-followup --from-finding`. "
            "Read-only: prints the proposed diffs; does not write."
        ),
    )
    p.add_argument("parent_yaml", help="path to studies/<parent-slug>/study.yaml")
    p.add_argument("proposal_id")
    p.add_argument("finding_id")
    p.add_argument("--new-slug", default=None,
                   help="slug for the new child study (default: proposal id)")
    args = p.parse_args(argv)

    new_slug = args.new_slug or args.proposal_id
    try:
        plan = apply_from_finding(
            Path(args.parent_yaml), args.proposal_id, args.finding_id, new_slug,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    _print_preview(plan, new_slug)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
