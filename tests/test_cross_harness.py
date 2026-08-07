"""Cross-harness delivery guard.

The Claude gateway (`skills/viva-orient/SKILL.md`, auto-injected by
`hooks/session-start`) and the harness-neutral gateway (`AGENTS.md`, read by Codex
/ Cursor / others) must not drift apart, and `AGENTS.md` must actually be
harness-neutral. See docs/cross-harness.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
ORIENT = ROOT / "skills" / "viva-orient" / "SKILL.md"
CODEX_TOOLS = ROOT / "references" / "codex-tools.md"

_VIVA_CMD = re.compile(r"/viva-[a-z][a-z0-9-]*")

# The 7 skills whose bodies assume subagent dispatch — codex-tools.md must give
# each an inline fallback (kept in sync with the grep in the PR scope).
_DISPATCH_SKILLS = {
    "viva-expert", "viva-report", "viva-investigation", "viva-study",
    "viva-harden-investigation", "viva-navigate", "viva-orient",
}


def test_agents_and_codex_refs_exist():
    assert AGENTS.is_file(), "AGENTS.md gateway is missing"
    assert CODEX_TOOLS.is_file(), "references/codex-tools.md is missing"


def test_rule_is_present_in_both_gateways():
    rule = "even a 1% chance"
    assert rule in ORIENT.read_text(), "viva-orient lost the 1%-chance Rule"
    assert rule in AGENTS.read_text(), (
        "AGENTS.md must carry the same 1%-chance Rule as viva-orient"
    )


def test_routing_coverage_no_drift():
    """Every /viva-* command viva-orient routes to must also appear in AGENTS.md.

    Adding a route to viva-orient without mirroring it into AGENTS.md fails here.
    """
    orient_cmds = set(_VIVA_CMD.findall(ORIENT.read_text()))
    agents_cmds = set(_VIVA_CMD.findall(AGENTS.read_text()))
    missing = orient_cmds - agents_cmds
    assert not missing, (
        f"AGENTS.md is missing /viva-* commands present in viva-orient: "
        f"{sorted(missing)} — mirror the routing table / skill map."
    )


def test_agents_is_harness_neutral():
    text = AGENTS.read_text()
    # Affirmative: it must tell the reader to open the SKILL.md file (no Skill tool).
    assert "SKILL.md" in text and "open" in text.lower(), (
        "AGENTS.md must instruct opening skills/<name>/SKILL.md (no Claude Skill tool)"
    )
    # It must point at the idiom map.
    assert "codex-tools.md" in text


def test_codex_tools_covers_dispatch_skills():
    text = CODEX_TOOLS.read_text()
    missing = {s for s in _DISPATCH_SKILLS if s not in text}
    assert not missing, (
        f"references/codex-tools.md must give an inline fallback for the "
        f"dispatch-using skills; missing: {sorted(missing)}"
    )
