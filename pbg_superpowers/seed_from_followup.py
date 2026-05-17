"""Pass 10B helper for ``/pbg-study seed-from-followup --from-finding <id>``.

The bulk of ``seed-from-followup`` is prose-driven (the Claude host
follows the steps in ``skills/pbg-study/SKILL.md``) — there is no
dashboard API and no full Python implementation. What *can* be made
deterministic and testable is the **finding-to-child-purpose
pre-population**: given a parent study and a finding id, derive the
child's ``purpose`` block, ``key_assumptions``, and ``seeded_from``
stamp, and produce the updated parent proposal entry. This module
exposes those primitives so the prose flow + a CLI smoke test can
share one implementation.

Public surface:

  - :func:`build_child_seed_from_finding` — pure function: given the
    parent study dict, a proposal id, and a finding id, returns a
    ``ChildSeed`` with the new study's ``purpose`` + ``key_assumptions``
    + ``seeded_from`` ready to merge into the child template.
  - :func:`build_parent_proposal_patch` — pure function: returns the
    updated proposal-entry dict (status flipped to ``seeded``,
    ``seeded_study`` set, ``linked_finding`` added if absent).
  - :func:`apply_from_finding` — convenience wrapper that loads the
    parent yaml, builds both diffs, and returns them; the actual
    file writes still live in the prose flow (mirrors the
    propose-followup pattern).

Findings-to-purpose heuristic (also documented in SKILL.md so the
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


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ChildSeed:
    """Fields to merge into the newly-created child study.yaml."""

    purpose: dict = field(default_factory=dict)
    key_assumptions: list[str] = field(default_factory=list)
    seeded_from: dict = field(default_factory=dict)

    def merge_into(self, child: dict) -> dict:
        """Apply the seed onto a partially-constructed child study dict.

        Non-destructive merge for ``purpose`` (existing keys win — the prose
        flow's earlier propose-followup seed has already populated parts of
        it) and ``key_assumptions`` (append, dedup). ``seeded_from`` is
        merged key-by-key (the new ``finding`` key adds; existing
        ``study`` / ``proposal_id`` are preserved).
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
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", text.strip())
    m = re.search(r"(?<=[.!?])\s", flat)
    return (flat[: m.start() + 1] if m else flat).rstrip()


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

    seeded_from = {
        "study": parent_slug,
        "proposal_id": proposal_id,
        "finding": finding_id,
    }
    return ChildSeed(
        purpose=purpose,
        key_assumptions=key_assumptions,
        seeded_from=seeded_from,
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
    out("# Child seed (merge into the new study.yaml):")
    out(yaml.safe_dump(
        {
            "purpose": plan.child_seed.purpose,
            "key_assumptions": plan.child_seed.key_assumptions,
            "seeded_from": plan.child_seed.seeded_from,
        },
        sort_keys=False,
    ))
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
