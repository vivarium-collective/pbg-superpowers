"""Smoke tests for the v0.9 skill consolidation (catalog + expert --lightweight).

The skills themselves are SKILL.md-driven bash (no Python module), so the
unit-test surface is the SKILL.md contract: required sections present, the
v0.8 trio subcommands surfaced under the new merged front door, and the
expert skill documents both heavy and lightweight modes.
"""
from __future__ import annotations
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"


def _read(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text()


# ---------------------------------------------------------------- catalog merge


def test_pbg_catalog_skill_exists():
    assert (SKILLS / "viva-catalog" / "SKILL.md").exists(), (
        "viva-catalog skill dir is the consolidated home for the v0.8 trio "
        "(/pbg-list, /pbg-install, /pbg-uninstall) — it must be present."
    )


@pytest.mark.parametrize("subcmd", ["list", "install", "uninstall"])
def test_pbg_catalog_documents_subcommand(subcmd):
    text = _read("viva-catalog")
    assert subcmd in text, f"viva-catalog SKILL.md must document the '{subcmd}' subcommand"


@pytest.mark.parametrize("endpoint", [
    "/api/workspace-manifest",
    "/api/catalog-install",
    "/api/catalog-uninstall",
])
def test_pbg_catalog_wraps_dashboard_endpoint(endpoint):
    text = _read("viva-catalog")
    assert endpoint in text, (
        f"viva-catalog must wrap {endpoint} to keep parity with the v0.8 skill it replaces"
    )


@pytest.mark.parametrize("removed", ["pbg-list", "pbg-install", "pbg-uninstall"])
def test_v08_trio_skill_dirs_are_gone(removed):
    assert not (SKILLS / removed).exists(), (
        f"{removed} was merged into /viva-catalog in v0.9 and its skill dir must be removed"
    )


# ---------------------------------------------------------- expert lightweight


def test_pbg_expert_documents_lightweight_mode():
    text = _read("viva-expert")
    assert "--lightweight" in text, (
        "viva-expert must document --lightweight (replaces the v0.8 /pbg-wrapper and /pbg-composer)"
    )
    assert "Lightweight Mode" in text or "lightweight mode" in text.lower(), (
        "viva-expert must have a dedicated Lightweight Mode section"
    )


def test_pbg_expert_lightweight_covers_single_and_composite():
    text = _read("viva-expert")
    # Single-tool lightweight form
    assert "single-tool form" in text.lower() or "Lightweight single-tool" in text, (
        "Lightweight Mode must document the single-tool form (replaces /pbg-wrapper)"
    )
    # Composite lightweight form
    assert "composite form" in text.lower() or "Lightweight composite" in text, (
        "Lightweight Mode must document the composite form (replaces /pbg-composer)"
    )


def test_pbg_expert_documents_lightweight_output_layout():
    """Lightweight mode should still write into pbg_<slug>/{processes,composites}/."""
    text = _read("viva-expert")
    assert "pbg_<slug>/processes/" in text, "single-tool lightweight writes processes/<tool>.py"
    assert "pbg_<slug>/composites/" in text, "composite lightweight writes composites/<name>.py"


@pytest.mark.parametrize("removed", ["pbg-wrapper", "pbg-composer"])
def test_v08_wrap_compose_skill_dirs_are_gone(removed):
    assert not (SKILLS / removed).exists(), (
        f"{removed} was folded into /viva-expert --lightweight in v0.9; its skill dir must be removed"
    )


# ---------------------------------------------------------- package -> script


def test_audit_pbg_repo_script_exists():
    script = REPO_ROOT / "scripts" / "audit-pbg-repo.py"
    assert script.exists(), (
        "scripts/audit-pbg-repo.py is the maintainer-facing entry point that replaces the "
        "v0.8 /pbg-package skill"
    )


def test_audit_pbg_repo_script_wraps_package_audit():
    script = REPO_ROOT / "scripts" / "audit-pbg-repo.py"
    text = script.read_text()
    assert "from viva_superpowers.package_audit import main" in text, (
        "audit-pbg-repo.py should reuse viva_superpowers.package_audit — do not duplicate logic"
    )


def test_pbg_package_skill_dir_is_gone():
    assert not (SKILLS / "pbg-package").exists(), (
        "/pbg-package skill was removed in v0.9; the maintainer audit lives at "
        "scripts/audit-pbg-repo.py and the import surface still works via viva_superpowers.package_audit"
    )


# ----------------------------------------------------------- status delegation


def test_pbg_status_delegates_server_section():
    text = _read("viva-status")
    assert "/viva-server status" in text, (
        "viva-status must delegate its server-liveness section to /viva-server status "
        "instead of duplicating the TCP probe"
    )


# ----------------------------------------------- viva-suggest stays for callback


def test_pbg_suggest_remains_for_dashboard_callback():
    """viva-suggest is invoked by the vivarium-workbench 'Suggest' button.

    Removing it would break the dashboard's repo-name/PR-title/PR-body suggest flow,
    so v0.9 keeps the skill registered but flags it as internal-only.
    """
    assert (SKILLS / "viva-suggest" / "SKILL.md").exists(), (
        "viva-suggest must remain installed for the vivarium-workbench Suggest callback"
    )
    text = _read("viva-suggest")
    assert "internal" in text.lower(), (
        "viva-suggest frontmatter/body should flag it as an internal dashboard callback"
    )
