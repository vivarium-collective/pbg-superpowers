"""Guard test for the /viva-navigate skill (SP4a).

Asserts the SKILL.md documents the seven read-only subcommands and calls the
workbench API (GET /api/linkage-index, GET /api/needs-attention) rather than
importing viva_superpowers compute in-process (2.1b rewire).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-navigate" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file(), "skills/viva-navigate/SKILL.md must exist"


def test_subcommands_documented(skill_text):
    for sub in ("decisions", "ac-gaps", "source", "finding-by-observable", "dag",
                "observable", "composite"):
        assert sub in skill_text, f"subcommand {sub!r} not documented"


def test_references_linkage_backend(skill_text):
    assert "/api/linkage-index" in skill_text
    # Query-param dispatch for each linkage-index-backed subcommand.
    for param in ("investigation=", "source=", "observable=",
                  "observable_registry=", "composite="):
        assert param in skill_text, f"linkage-index param {param!r} not referenced"


def test_references_needs_attention_backend(skill_text):
    # SP5 decisions-needed scan: the navigator LEADS with it.
    assert "/api/needs-attention" in skill_text


def test_read_only_no_ai(skill_text):
    assert "AI-free" in skill_text or "AI judgment" in skill_text
    assert "no writes" in skill_text.lower() or "never writes" in skill_text.lower()


def test_no_inline_plugin_compute(skill_text):
    """2.1b rewire: zero in-process viva_superpowers consumer sites.

    A SKILL.md is a program — `from viva_superpowers.X import Y` and
    `python -m viva_superpowers.X` are hard-blocker consumer sites, not
    prose. This skill must call the workbench API exclusively.
    """
    assert "from viva_superpowers" not in skill_text
    assert "import viva_superpowers" not in skill_text
    assert "-m viva_superpowers" not in skill_text
    assert ".venv/bin/python" not in skill_text


def test_server_preflight_documented(skill_text):
    # viva-catalog's exact preflight idiom: workspace.yaml walk-up +
    # .pbg/server/server-info, erroring (not silently falling back) when
    # the dashboard server is not running.
    assert "workspace.yaml" in skill_text
    assert ".pbg/server/server-info" in skill_text
    assert "/viva-workbench start" in skill_text
