"""Tests for pbg_superpowers.bibtex — the unified workspace bib-key source.

Locks in the correctness fix: study verify and the report linter must resolve
the SAME bib file with the SAME parser (they used to disagree).
"""
from __future__ import annotations

from pathlib import Path

from pbg_superpowers import bibtex
from pbg_superpowers.study_findings import load_bib_keys
from pbg_superpowers.study_verify import _load_bib_keys


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "references").mkdir()
    return tmp_path


def test_parses_keys_with_and_without_trailing_comma(tmp_path: Path):
    ws = _ws(tmp_path)
    (ws / "references" / "papers.bib").write_text(
        "@article{smith2024,\n  title={X},\n}\n@misc{jones_2023}\n"
    )
    assert bibtex.bib_keys(ws) == {"smith2024", "jones_2023"}


def test_missing_file_returns_empty_set_by_default(tmp_path: Path):
    assert bibtex.bib_keys(_ws(tmp_path)) == set()


def test_missing_file_returns_none_with_missing_ok(tmp_path: Path):
    assert bibtex.bib_keys(_ws(tmp_path), missing_ok=True) is None


def test_filename_precedence_prefers_papers_bib(tmp_path: Path):
    ws = _ws(tmp_path)
    (ws / "references" / "papers.bib").write_text("@article{canonical,\n}\n")
    (ws / "references" / "references.bib").write_text("@article{fallback,\n}\n")
    assert bibtex.bib_keys(ws) == {"canonical"}


def test_falls_back_to_references_bib(tmp_path: Path):
    ws = _ws(tmp_path)
    (ws / "references" / "references.bib").write_text("@article{fb,\n}\n")
    assert bibtex.bib_keys(ws) == {"fb"}


def test_verify_and_findings_agree_on_same_file(tmp_path: Path):
    """The regression this fix prevents: verify and lint/findings reading
    different files. Both must now see the same keys from papers.bib."""
    ws = _ws(tmp_path)
    (ws / "references" / "papers.bib").write_text("@article{shared2024,\n}\n")
    findings_keys = load_bib_keys(ws)          # findings + linter path
    verify_keys = _load_bib_keys(ws)           # verify path
    assert findings_keys == {"shared2024"}
    assert verify_keys == {"shared2024"}


def test_verify_soft_skips_when_no_bib_but_findings_returns_empty(tmp_path: Path):
    """Contract difference preserved: verify -> None (soft skip), the
    findings/linter path -> empty set (every cite unknown)."""
    ws = _ws(tmp_path)
    assert _load_bib_keys(ws) is None
    assert load_bib_keys(ws) == set()
