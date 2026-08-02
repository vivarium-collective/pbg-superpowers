"""Guard: the /viva-cite-bands skill wires in the investigation-references pool.

If this regresses (the skill stops referencing the deterministic gap surface or
the sanctioned write path), the investigation references → band citations loop
silently breaks. Keep the wiring named in SKILL.md.
"""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "viva-cite-bands" / "SKILL.md"


def test_skill_mentions_citation_gaps_surface():
    text = SKILL.read_text(encoding="utf-8")
    assert "investigation_citation_gaps" in text
    assert "viva-citation-gaps" in text


def test_skill_mentions_set_band_provenance_apply():
    text = SKILL.read_text(encoding="utf-8")
    assert "set_band_provenance" in text
