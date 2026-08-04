"""Guard: the /viva-cite-bands skill wires in the investigation-references pool.

If this regresses (the skill stops referencing the deterministic gap surface or
the sanctioned write path), the investigation references → band citations loop
silently breaks. Keep the wiring named in SKILL.md.

Phase 2.1e (rewire-first): the skill is a thin workbench-API client — it must
call the dashboard endpoints (`/api/citation-gaps`, `/api/band-provenance`,
`/api/expert-search`, `/api/report-lint`) rather than importing
`viva_superpowers.*` compute modules directly.
"""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "viva-cite-bands" / "SKILL.md"


def test_skill_mentions_citation_gaps_surface():
    text = SKILL.read_text(encoding="utf-8")
    assert "/api/citation-gaps" in text


def test_skill_mentions_band_provenance_apply():
    text = SKILL.read_text(encoding="utf-8")
    assert "POST /api/band-provenance" in text or "POST \"$URL/api/band-provenance\"" in text
    assert "/api/band-provenance" in text


def test_skill_has_no_direct_viva_superpowers_compute_imports():
    """The skill must not import band_provenance/citation_gaps/expert_search/
    report_linter/study_io compute modules directly — those calls belong to
    the workbench server backing the API, not this client-side skill."""
    text = SKILL.read_text(encoding="utf-8")
    banned = [
        "viva_superpowers.band_provenance",
        "viva_superpowers.citation_gaps",
        "viva_superpowers.expert_search",
        "viva_superpowers.report_linter",
        "viva_superpowers.study_io",
    ]
    for module in banned:
        assert module not in text, f"skill still imports {module} directly — should call the API instead"
