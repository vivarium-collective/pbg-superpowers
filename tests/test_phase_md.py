import pytest
from pbg_superpowers.phase_md import (
    parse_phase_md, render_phase_md, PhaseValidationError,
)


SAMPLE = """---
phase: 1
name: DnaA accumulation
status: planned
prereq_phases: []
gate_passed: false
acceptance_tests: []
---

## Phase 1: DnaA accumulation

### Objective
Reach steady-state DnaA pool.
"""


def test_parse_returns_frontmatter_and_body():
    fm, body = parse_phase_md(SAMPLE)
    assert fm["phase"] == 1
    assert fm["name"] == "DnaA accumulation"
    assert "## Phase 1" in body


def test_render_roundtrip():
    fm, body = parse_phase_md(SAMPLE)
    rendered = render_phase_md(fm, body)
    fm2, body2 = parse_phase_md(rendered)
    assert fm == fm2
    assert body.strip() == body2.strip()


def test_parse_rejects_missing_frontmatter():
    with pytest.raises(PhaseValidationError):
        parse_phase_md("just body, no frontmatter")


def test_parse_validates_against_schema():
    bad = """---
phase: 1
name: X
status: NOPE
prereq_phases: []
gate_passed: false
acceptance_tests: []
---
"""
    with pytest.raises(PhaseValidationError):
        parse_phase_md(bad)


def test_parse_handles_no_trailing_newline():
    """File without trailing newline after closing --- must still parse."""
    text = SAMPLE.rstrip("\n")
    fm, body = parse_phase_md(text)
    assert fm["phase"] == 1


def test_parse_handles_crlf_line_endings():
    """Windows CRLF line endings should be normalized."""
    text = SAMPLE.replace("\n", "\r\n")
    fm, body = parse_phase_md(text)
    assert fm["phase"] == 1
