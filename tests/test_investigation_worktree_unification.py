"""Pass C — Investigation ≡ branch ≡ worktree.

SKILL.md contract tests for the new `/pbg-investigation open` subcommand,
the extended `/pbg-investigation new` (branch + commit), and the new
`/pbg-server cleanup` subcommand plus its per-worktree dedup behavior.
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


# -------------------------------------------------------------- /pbg-investigation


def test_pbg_investigation_documents_open_subcommand():
    text = _skill("pbg-investigation")
    assert "### `open <slug>" in text, (
        "pbg-investigation must document the new `open` subcommand "
        "(creates worktree under .pbg/worktrees/<slug>/ + optional server boot)."
    )


def test_pbg_investigation_frontmatter_lists_open():
    text = _skill("pbg-investigation")
    # Argument hint / description should advertise the new subcommand so
    # the catalog surfaces it. We allow either.
    head = text.split("\n---\n", 2)[0]
    assert "open" in head, (
        "pbg-investigation frontmatter description must include 'open' "
        "so the consolidated catalog lists it."
    )


def test_pbg_investigation_new_creates_branch_and_commits():
    text = _skill("pbg-investigation")
    # The procedure should explicitly create a branch and commit the YAML
    # on it. We assert on the load-bearing operations, not on prose.
    assert "git checkout -b <slug>" in text, (
        "pbg-investigation new must check out a new branch named <slug>."
    )
    assert "git commit" in text, (
        "pbg-investigation new must commit the new investigation.yaml on "
        "the new branch (so the worktree open step has something to check "
        "out cleanly)."
    )


def test_pbg_investigation_open_uses_standard_worktree_path():
    text = _skill("pbg-investigation")
    assert ".pbg/worktrees/<slug>" in text, (
        "pbg-investigation open must use the standard worktree location "
        "<workspace>/.pbg/worktrees/<slug>/ so cross-worktree tools (and "
        "the cleanup skill) can find them deterministically."
    )


def test_pbg_investigation_documents_branch_worktree_equivalence():
    text = _skill("pbg-investigation")
    assert "Investigation ≡ branch ≡ worktree" in text, (
        "pbg-investigation must document the 1:1 slug/branch/worktree "
        "convention up front — that's the load-bearing invariant Pass C."
    )


# -------------------------------------------------------------- /pbg-server


def test_pbg_server_documents_cleanup_subcommand():
    text = _skill("pbg-server")
    assert "/pbg-server cleanup" in text, (
        "pbg-server must document the cleanup subcommand (removes "
        "orphaned ~/.pbg/servers/*.json records)."
    )
    assert "cleanup-servers" in text, (
        "pbg-server cleanup must shell out to "
        "`python -m pbg_superpowers.workspace_catalog cleanup-servers`."
    )


def test_pbg_server_start_documents_per_worktree_dedup():
    text = _skill("pbg-server")
    assert "duplicates-for-path" in text, (
        "pbg-server start must use the workspace_catalog "
        "duplicates-for-path helper to dedup SAME-path records only."
    )
    # The contract is: kill+restart ONLY records for the SAME worktree
    # path, never records for different worktrees.
    assert "DIFFERENT worktree paths" in text, (
        "pbg-server start must explicitly document that records for "
        "different worktree paths are preserved (parallel agent flow)."
    )


def test_pbg_server_frontmatter_lists_cleanup():
    text = _skill("pbg-server")
    head = text.split("\n---\n", 2)[0]
    assert "cleanup" in head, (
        "pbg-server frontmatter must list cleanup in argument-hint / "
        "description so the consolidated catalog surfaces it."
    )


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
