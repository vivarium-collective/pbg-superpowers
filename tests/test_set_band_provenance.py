"""TDD tests for set_band_provenance (spine stage 3b, Task 1).

Tests are written BEFORE the implementation (TDD red phase).
set_band_provenance lives in pbg_superpowers.band_provenance.

Covers:
  - Basic set on behavior_tests[]
  - Sets calibration_anchor when provided
  - Comment preservation (comments on other entries survive byte-identical)
  - Other entries/keys entirely untouched
  - Idempotency: second identical call returns False (no write)
  - Non-existent test name → returns False, never fabricates an entry
  - Merge into an existing cites list (dedup, preserve order)
  - Works for tests[] section too (not just behavior_tests[])
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Inline YAML fixtures (no real workspace needed)
# ---------------------------------------------------------------------------

_STUDY_YAML = """\
# Study header comment — must survive round-trip
name: my-study
status: draft

# Behavior tests section
behavior_tests:
  # Pre-entry comment on frac-test
  - name: frac-test
    pass_if:
      op: in_range
      low: 0.2
      high: 0.5
  - name: mass-doubling  # inline comment on mass-doubling entry
    pass_if:
      op: periodic_doubling
      tolerance: 0.15

tests:
  - name: total-dnaa
    pass_if:
      op: generation_average_in_range
      low: 300
      high: 800
"""

_STUDY_WITH_CITES = """\
name: has-cites-study
behavior_tests:
  - name: frac-test
    cites:
      - existing-ref
    pass_if:
      op: in_range
      low: 0.2
      high: 0.5
  - name: other-test
    cites:
      - other-only
    pass_if:
      op: in_range
      low: 0.1
      high: 0.9
"""

_STUDY_TESTS_ONLY = """\
name: tests-section-study
tests:
  - name: v4-total-dnaa
    pass_if:
      op: generation_average_in_range
      low: 300
      high: 800
"""


def _make_study_dir(tmp_path: Path, content: str) -> Path:
    """Write content to tmp_path/study.yaml and return the study dir."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "study.yaml").write_text(content)
    return tmp_path


# ---------------------------------------------------------------------------
# Task 1 TDD tests — all should FAIL before implementation
# ---------------------------------------------------------------------------


def test_import():
    """set_band_provenance is importable from band_provenance."""
    from pbg_superpowers.band_provenance import set_band_provenance  # noqa: F401


def test_sets_cites_on_behavior_test(tmp_path):
    """Basic: sets cites on a behavior_test entry; returns True."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    result = set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])

    assert result is True, "expected True (write occurred)"
    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    assert bt["frac-test"].get("cites") == ["boesen2024"], (
        f"cites not set; got {bt['frac-test']}"
    )


def test_sets_calibration_anchor(tmp_path):
    """calibration_anchor is written when provided."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    anchor = {"literature_target": 0.35, "cites": ["boesen2024"]}
    set_band_provenance(study_dir, "frac-test", cites=["boesen2024"],
                        calibration_anchor=anchor)

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    saved_anchor = bt["frac-test"].get("calibration_anchor")
    assert saved_anchor == anchor, f"calibration_anchor not saved; got {saved_anchor}"


def test_other_entries_untouched(tmp_path):
    """After writing frac-test cites, mass-doubling entry is byte-identical."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}

    # mass-doubling must be untouched
    assert bt["mass-doubling"]["pass_if"]["op"] == "periodic_doubling"
    assert bt["mass-doubling"]["pass_if"]["tolerance"] == 0.15
    assert "cites" not in bt["mass-doubling"], "mass-doubling must not gain a cites key"


def test_comment_preservation(tmp_path):
    """Comments on untouched entries survive the ruamel round-trip."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])

    written = (study_dir / "study.yaml").read_text()
    # Top-level header comment
    assert "Study header comment" in written, "top-level comment was stripped"
    # Inline comment on mass-doubling
    assert "inline comment on mass-doubling" in written, (
        "inline comment on mass-doubling was stripped"
    )


def test_idempotent_second_call_returns_false(tmp_path):
    """Second identical call returns False (no write)."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    first = set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])
    assert first is True

    mtime_after_first = (study_dir / "study.yaml").stat().st_mtime

    second = set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])
    assert second is False, "second identical call must return False (idempotent)"

    mtime_after_second = (study_dir / "study.yaml").stat().st_mtime
    assert mtime_after_first == mtime_after_second, (
        "study.yaml was written on a no-op call (not idempotent)"
    )


def test_nonexistent_name_returns_false(tmp_path):
    """A non-existent test name returns False; no entry is fabricated."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    original_text = (study_dir / "study.yaml").read_text()

    result = set_band_provenance(study_dir, "no-such-test", cites=["boesen2024"])

    assert result is False, "non-existent name must return False"
    # File must be completely unchanged
    assert (study_dir / "study.yaml").read_text() == original_text, (
        "study.yaml was modified for a non-existent test name — fabrication!"
    )


def test_merges_existing_cites_dedup(tmp_path):
    """Merges new keys into an existing cites list; existing keys stay; dedup."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_WITH_CITES)
    result = set_band_provenance(
        study_dir, "frac-test", cites=["existing-ref", "new-ref"]
    )
    assert result is True

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    cites = bt["frac-test"]["cites"]
    # existing-ref kept, new-ref added, no duplicates
    assert "existing-ref" in cites
    assert "new-ref" in cites
    assert cites.count("existing-ref") == 1, "existing-ref duplicated"


def test_merge_does_not_clobber_other_entries_cites(tmp_path):
    """other-test's cites list is untouched when we write to frac-test."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_WITH_CITES)
    set_band_provenance(study_dir, "frac-test", cites=["new-ref"])

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    assert bt["other-test"]["cites"] == ["other-only"], (
        "other-test's cites were modified when they should be untouched"
    )


def test_works_for_tests_section(tmp_path):
    """set_band_provenance also finds entries in tests[] (not just behavior_tests[])."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_TESTS_ONLY)
    result = set_band_provenance(study_dir, "v4-total-dnaa", cites=["ref2024"])

    assert result is True
    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    tests = {t["name"]: t for t in updated.get("tests", [])}
    assert tests["v4-total-dnaa"].get("cites") == ["ref2024"]


def test_behavior_tests_searched_before_tests(tmp_path):
    """When both sections have an entry with the same name, behavior_tests wins."""
    from pbg_superpowers.band_provenance import set_band_provenance

    ambiguous = """\
name: ambiguous-study
behavior_tests:
  - name: shared-name
    pass_if:
      low: 0.1
      high: 0.9
tests:
  - name: shared-name
    pass_if:
      low: 300
      high: 800
"""
    study_dir = _make_study_dir(tmp_path, ambiguous)
    set_band_provenance(study_dir, "shared-name", cites=["ref2024"])

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    ts = {t["name"]: t for t in updated.get("tests", [])}
    # behavior_tests entry gets cites
    assert bt["shared-name"].get("cites") == ["ref2024"]
    # tests entry does NOT get cites
    assert "cites" not in ts["shared-name"], (
        "tests[] entry got cites even though behavior_tests[] matched first"
    )


def test_frac_test_keys_preserved(tmp_path):
    """The targeted entry retains its existing keys (name, pass_if, etc.)."""
    from pbg_superpowers.band_provenance import set_band_provenance

    study_dir = _make_study_dir(tmp_path, _STUDY_YAML)
    set_band_provenance(study_dir, "frac-test", cites=["boesen2024"])

    updated = yaml.safe_load((study_dir / "study.yaml").read_text())
    bt = {t["name"]: t for t in updated.get("behavior_tests", [])}
    entry = bt["frac-test"]
    assert entry["name"] == "frac-test"
    assert entry["pass_if"]["low"] == 0.2
    assert entry["pass_if"]["high"] == 0.5


# ---------------------------------------------------------------------------
# Task 3 smoke tests (added after SKILL.md exists)
# ---------------------------------------------------------------------------


def test_skill_file_exists():
    """skills/pbg-cite-bands/SKILL.md exists."""
    skill = Path(__file__).resolve().parents[1] / "skills" / "pbg-cite-bands" / "SKILL.md"
    assert skill.is_file(), f"SKILL.md not found at {skill}"


def test_skill_frontmatter_valid():
    """SKILL.md has required front-matter fields and expected values."""
    import yaml as _yaml
    skill = Path(__file__).resolve().parents[1] / "skills" / "pbg-cite-bands" / "SKILL.md"
    text = skill.read_text()
    assert text.startswith("---\n"), "SKILL.md must start with YAML front-matter"
    end = text.find("\n---\n", 4)
    assert end != -1, "SKILL.md front-matter not closed"
    fm = _yaml.safe_load(text[4:end]) or {}
    assert fm.get("name") == "pbg-cite-bands"
    assert fm.get("user-invocable") is True
    assert "description" in fm
    assert "allowed-tools" in fm


def test_skill_references_helpers():
    """SKILL.md body references the three key helpers by exact Python name."""
    skill = Path(__file__).resolve().parents[1] / "skills" / "pbg-cite-bands" / "SKILL.md"
    body = skill.read_text()
    assert "bands_missing_provenance" in body, "skill must reference bands_missing_provenance"
    assert "search_expert_docs" in body, "skill must reference search_expert_docs"
    assert "set_band_provenance" in body, "skill must reference set_band_provenance"


def test_skill_references_proposed_inputs_guardrail():
    """SKILL.md documents the proposed_inputs / never-fabricate guardrail."""
    skill = Path(__file__).resolve().parents[1] / "skills" / "pbg-cite-bands" / "SKILL.md"
    body = skill.read_text()
    assert "proposed_inputs" in body, "skill must mention proposed_inputs fallback"


def test_helpers_importable():
    """All helpers referenced by the skill are importable."""
    from pbg_superpowers.band_provenance import bands_missing_provenance  # noqa: F401
    from pbg_superpowers.band_provenance import set_band_provenance  # noqa: F401
    from pbg_superpowers.expert_search import search_expert_docs  # noqa: F401
