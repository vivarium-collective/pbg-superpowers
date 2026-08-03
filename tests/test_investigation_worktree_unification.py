"""Pass C — Investigation ≡ branch ≡ worktree.

SKILL.md contract tests for the new `/viva-investigation open` subcommand,
and the extended `/viva-investigation new` (branch + commit).
The skills themselves are SKILL.md-driven bash, so the unit-test surface
is the SKILL.md document and the workspace_catalog helpers it shells out
to. End-to-end git interactions are exercised manually (see PR body).
"""
from __future__ import annotations
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text()


# -------------------------------------------------------------- /viva-investigation


def test_pbg_investigation_documents_open_subcommand():
    text = _skill("viva-investigation")
    assert "### `open <slug>" in text, (
        "viva-investigation must document the new `open` subcommand "
        "(creates worktree under .pbg/worktrees/<slug>/ + optional server boot)."
    )


def test_pbg_investigation_frontmatter_lists_open():
    text = _skill("viva-investigation")
    # Argument hint / description should advertise the new subcommand so
    # the catalog surfaces it. We allow either.
    head = text.split("\n---\n", 2)[0]
    assert "open" in head, (
        "viva-investigation frontmatter description must include 'open' "
        "so the consolidated catalog lists it."
    )


def test_pbg_investigation_new_creates_branch_and_commits():
    text = _skill("viva-investigation")
    # The procedure should explicitly create a branch and commit the YAML
    # on it. We assert on the load-bearing operations, not on prose.
    assert "git checkout -b <slug>" in text, (
        "viva-investigation new must check out a new branch named <slug>."
    )
    assert "git commit" in text, (
        "viva-investigation new must commit the new investigation.yaml on "
        "the new branch (so the worktree open step has something to check "
        "out cleanly)."
    )


def test_pbg_investigation_open_uses_standard_worktree_path():
    text = _skill("viva-investigation")
    assert ".pbg/worktrees/<slug>" in text, (
        "viva-investigation open must use the standard worktree location "
        "<workspace>/.pbg/worktrees/<slug>/ so cross-worktree tools (and "
        "the cleanup skill) can find them deterministically."
    )


def test_pbg_investigation_documents_branch_worktree_equivalence():
    text = _skill("viva-investigation")
    assert "Investigation ≡ branch ≡ worktree" in text, (
        "viva-investigation must document the 1:1 slug/branch/worktree "
        "convention up front — that's the load-bearing invariant Pass C."
    )


# Note: the report-mirror server + its `/viva-server` skill were retired; the
# per-worktree dedup + orphan-cleanup of ~/.pbg/servers/*.json is now owned by
# the vivarium-workbench server (which registers via viva_superpowers.
# workspace_catalog) and tested in that repo. See test_workspace_catalog.py for
# the module-level dedup behavior that remains in this package.


# -------------------------------------------------------------- Concept doc


def test_concept_doc_documents_investigation_branch_worktree():
    p = REPO_ROOT / "docs" / "concepts" / "vivarium-workbench-model.md"
    text = p.read_text()
    assert "Investigation ≡ branch ≡ worktree" in text, (
        "Concept doc must document the 1:1 slug/branch/worktree convention."
    )
    assert "/api/investigation-registry" in text, (
        "Concept doc must mention the new cross-worktree registry endpoint."
    )
    assert ".pbg/worktrees/<slug>" in text, (
        "Concept doc must record the standard worktree location."
    )
