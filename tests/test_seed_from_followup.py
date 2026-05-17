"""Pass 10B tests for ``/pbg-study seed-from-followup --from-finding`` helper.

The skill is prose-driven (Claude follows the steps in SKILL.md and shells
out to this Python module for the deterministic bits). These tests pin
the heuristic:

  - ``build_child_seed_from_finding`` derives ``purpose`` / ``key_assumptions``
    / ``seeded_from`` from a finding entry.
  - ``build_parent_proposal_patch`` flips proposal status to ``seeded`` and
    records ``seeded_study`` + ``linked_finding``.
  - The convenience ``apply_from_finding`` loads a real parent yaml,
    rejects a missing finding id, and produces a ChildSeed mergeable
    into a fresh child template.
  - The CLI smoke (``python -m pbg_superpowers.seed_from_followup``)
    prints a non-empty preview and exits 0 on the happy path; exits 2
    when the finding doesn't exist.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from pbg_superpowers import seed_from_followup as sff


# ---------------------------------------------------------------------------
# Fixture: a parent study with one finding + one proposal
# ---------------------------------------------------------------------------


def _make_parent_study(tmp_path: Path) -> Path:
    sd = tmp_path / "studies" / "dnaa-01"
    sd.mkdir(parents=True)
    spec = {
        "name": "dnaa-01",
        "baseline": [{"name": "b1", "composite": "pkg.composites.x"}],
        "findings": [
            {
                "id": "F-03",
                "kind": "biological",
                "status": "contradicts",
                "statement": (
                    "v2ecoli underestimates the DnaA-ATP fraction at "
                    "initiation by ~5x."
                ),
                "evidence": {
                    "from_test": "dnaA-atp-fraction",
                    "smoking_gun": (
                        "DnaA-ATP / DnaA-total stays at 0.05 across all "
                        "timepoints; literature reports 0.20-0.30."
                    ),
                },
                "explanation": (
                    "The current DnaA model treats ATP/ADP cycling as "
                    "instantaneous; in reality ATP-loading is gated by "
                    "DARS-mediated reactivation."
                ),
                "next_action": (
                    "Calibrate the DARS reactivation rate to match the "
                    "literature ATP fraction in range 0.20-0.30."
                ),
            },
            {  # second finding with no next_action / no smoking_gun
                "id": "F-04",
                "kind": "computational",
                "status": "novel",
                "statement": "Listener emits NaN when n_dnaA drops below 5.",
            },
        ],
        "followup_proposals": [
            {
                "id": "calibrate-dars",
                "title": "Calibrate DARS reactivation rate",
                "motivation": (
                    "F-03 shows we badly underestimate DnaA-ATP fraction."
                ),
                "status": "proposed",
            }
        ],
    }
    (sd / "study.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    return sd / "study.yaml"


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------


def test_build_child_seed_from_finding_populates_all_three_blocks(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    seed = sff.build_child_seed_from_finding(
        parent, "dnaa-01", "calibrate-dars", "F-03",
    )
    # purpose.mechanism comes from explanation verbatim
    assert "DARS-mediated reactivation" in seed.purpose["mechanism"]
    # purpose.question is derived from next_action ("Calibrate..." → "How do we calibrate...?")
    assert seed.purpose["question"].endswith("?")
    assert "calibrate" in seed.purpose["question"].lower()
    # purpose.expected_outcome trips on the "to match"/"in range" cue
    assert "0.20" in seed.purpose["expected_outcome"]
    # key_assumptions picks up the smoking_gun string
    assert len(seed.key_assumptions) == 1
    assert "DnaA-ATP" in seed.key_assumptions[0]
    # seeded_from has all three sub-fields
    assert seed.seeded_from == {
        "study": "dnaa-01",
        "proposal_id": "calibrate-dars",
        "finding": "F-03",
    }


def test_build_child_seed_handles_finding_without_optional_fields(tmp_path):
    """F-04 has no explanation, no next_action, no smoking_gun. The seed
    should still produce a usable purpose.question (falling back to the
    statement) and an empty key_assumptions list."""
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    seed = sff.build_child_seed_from_finding(
        parent, "dnaa-01", "calibrate-dars", "F-04",
    )
    assert seed.purpose["question"].startswith("Investigate")
    assert "mechanism" not in seed.purpose
    assert "expected_outcome" not in seed.purpose
    assert seed.key_assumptions == []
    assert seed.seeded_from["finding"] == "F-04"


def test_build_child_seed_raises_on_unknown_finding(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    with pytest.raises(ValueError, match="F-99"):
        sff.build_child_seed_from_finding(
            parent, "dnaa-01", "calibrate-dars", "F-99",
        )


def test_build_parent_proposal_patch_flips_status_and_adds_linked_finding():
    proposal = {
        "id": "calibrate-dars",
        "title": "x",
        "motivation": "y",
        "status": "proposed",
    }
    patched = sff.build_parent_proposal_patch(
        proposal, new_slug="dnaa-02-dars-calibration", finding_id="F-03",
    )
    assert patched["status"] == "seeded"
    assert patched["seeded_study"] == "dnaa-02-dars-calibration"
    assert patched["linked_finding"] == "F-03"
    # Original is untouched.
    assert proposal["status"] == "proposed"


def test_build_parent_proposal_patch_preserves_existing_linked_finding():
    """If the proposal already pointed at the finding, don't overwrite."""
    proposal = {
        "id": "calibrate-dars",
        "status": "proposed",
        "linked_finding": "F-03",
    }
    patched = sff.build_parent_proposal_patch(
        proposal, new_slug="dnaa-02", finding_id="F-03",
    )
    assert patched["linked_finding"] == "F-03"


def test_build_parent_proposal_patch_without_finding_skips_link():
    """If --from-finding wasn't passed (finding_id=None), no linked_finding key."""
    proposal = {"id": "x", "status": "proposed"}
    patched = sff.build_parent_proposal_patch(
        proposal, new_slug="child", finding_id=None,
    )
    assert "linked_finding" not in patched
    assert patched["status"] == "seeded"


# ---------------------------------------------------------------------------
# ChildSeed.merge_into — non-destructive merge onto a partial child
# ---------------------------------------------------------------------------


def test_child_seed_merge_into_preserves_existing_purpose_fields(tmp_path):
    """If propose-followup already populated child.purpose.question,
    --from-finding's seed must NOT clobber it."""
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    seed = sff.build_child_seed_from_finding(
        parent, "dnaa-01", "calibrate-dars", "F-03",
    )
    child = {
        "name": "dnaa-02-dars-calibration",
        "purpose": {"question": "Pre-existing question from proposal seed."},
    }
    merged = seed.merge_into(child)
    # existing question wins
    assert merged["purpose"]["question"] == "Pre-existing question from proposal seed."
    # but mechanism + expected_outcome get added
    assert merged["purpose"]["mechanism"]
    assert merged["purpose"]["expected_outcome"]
    # seeded_from + key_assumptions added
    assert merged["seeded_from"]["finding"] == "F-03"
    assert merged["key_assumptions"]


def test_child_seed_merge_into_dedups_key_assumptions(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    seed = sff.build_child_seed_from_finding(
        parent, "dnaa-01", "calibrate-dars", "F-03",
    )
    existing_ka = list(seed.key_assumptions)  # same string already present
    child = {"key_assumptions": existing_ka}
    merged = seed.merge_into(child)
    assert merged["key_assumptions"] == existing_ka


def test_child_seed_merge_into_merges_seeded_from_with_existing(tmp_path):
    """If the propose-followup step already wrote {study, proposal_id},
    the --from-finding helper adds `finding:` without nuking the rest."""
    parent_yaml = _make_parent_study(tmp_path)
    parent = yaml.safe_load(parent_yaml.read_text())
    seed = sff.build_child_seed_from_finding(
        parent, "dnaa-01", "calibrate-dars", "F-03",
    )
    child = {"seeded_from": {"study": "dnaa-01", "proposal_id": "calibrate-dars"}}
    merged = seed.merge_into(child)
    assert merged["seeded_from"] == {
        "study": "dnaa-01",
        "proposal_id": "calibrate-dars",
        "finding": "F-03",
    }


# ---------------------------------------------------------------------------
# apply_from_finding — convenience wrapper
# ---------------------------------------------------------------------------


def test_apply_from_finding_end_to_end(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    plan = sff.apply_from_finding(
        parent_yaml,
        proposal_id="calibrate-dars",
        finding_id="F-03",
        new_slug="dnaa-02-dars-calibration",
    )
    assert plan.child_seed.seeded_from["finding"] == "F-03"
    assert plan.updated_proposal["status"] == "seeded"
    assert plan.updated_proposal["linked_finding"] == "F-03"
    assert plan.finding["id"] == "F-03"
    # The original proposal is untouched
    assert plan.proposal["status"] == "proposed"


def test_apply_from_finding_rejects_unknown_proposal(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    with pytest.raises(ValueError, match="bogus"):
        sff.apply_from_finding(
            parent_yaml, "bogus", "F-03", "child",
        )


def test_apply_from_finding_rejects_missing_parent(tmp_path):
    with pytest.raises(FileNotFoundError):
        sff.apply_from_finding(
            tmp_path / "nonexistent.yaml", "p", "F-01", "child",
        )


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_happy_path_exits_zero_and_prints_diffs(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    cp = subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.seed_from_followup",
         str(parent_yaml), "calibrate-dars", "F-03",
         "--new-slug", "dnaa-02-dars-calibration"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    assert "Child seed" in cp.stdout
    assert "F-03" in cp.stdout
    assert "calibrate-dars" in cp.stdout
    assert "dnaa-02-dars-calibration" in cp.stdout


def test_cli_unknown_finding_exits_2(tmp_path):
    parent_yaml = _make_parent_study(tmp_path)
    cp = subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.seed_from_followup",
         str(parent_yaml), "calibrate-dars", "F-99"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2
    assert "F-99" in cp.stderr
