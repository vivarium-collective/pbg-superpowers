"""Tests for the consolidated shared helpers (Theme 3 streamlining):
``study_io``, ``text_utils``, and ``paths.find_workspace_root``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pbg_superpowers import study_io
from pbg_superpowers.paths import find_workspace_root
from pbg_superpowers.text_utils import first_sentence


# --- study_io ---------------------------------------------------------------

def test_load_yaml_blank_file_is_empty_dict(tmp_path: Path):
    p = tmp_path / "x.yaml"
    p.write_text("")
    assert study_io.load_yaml(p) == {}


def test_load_yaml_is_lenient_about_non_mapping(tmp_path: Path):
    p = tmp_path / "x.yaml"
    p.write_text("- a\n- b\n")
    assert study_io.load_yaml(p) == ["a", "b"]  # no guard, returns the list


def test_load_yaml_mapping_rejects_non_mapping(tmp_path: Path):
    p = tmp_path / "x.yaml"
    p.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="not a mapping"):
        study_io.load_yaml_mapping(p)


def test_dump_yaml_round_trips_and_preserves_order_and_unicode(tmp_path: Path):
    data = {"z": 1, "a": "café", "nested": {"k": [1, 2, 3]}}
    text = study_io.dump_yaml(data)
    # insertion order kept (z before a), unicode not escaped
    assert text.index("z:") < text.index("a:")
    assert "café" in text
    # round-trips back to the same structure
    p = tmp_path / "rt.yaml"
    p.write_text(text)
    assert study_io.load_yaml_mapping(p) == data


def test_save_yaml_atomic_writes_and_leaves_no_tmp(tmp_path: Path):
    p = tmp_path / "study.yaml"
    study_io.save_yaml_atomic(p, {"name": "demo", "n": 2})
    assert study_io.load_yaml(p) == {"name": "demo", "n": 2}
    assert not (tmp_path / "study.yaml.tmp").exists()


def test_atomic_write_overwrites(tmp_path: Path):
    p = tmp_path / "f.txt"
    p.write_text("old")
    study_io.atomic_write(p, "new")
    assert p.read_text() == "new"
    assert not (tmp_path / "f.txt.tmp").exists()


# --- text_utils.first_sentence ----------------------------------------------

def test_first_sentence_splits_on_terminator():
    assert first_sentence("Hello world. More text.") == "Hello world."


def test_first_sentence_collapses_whitespace():
    assert first_sentence("  a\n  b   c ") == "a b c"


def test_first_sentence_empty():
    assert first_sentence("") == ""


def test_first_sentence_no_truncation_by_default():
    long = "x" * 500  # no terminator
    assert first_sentence(long) == long


def test_first_sentence_truncates_when_max_chars_given():
    long = "x" * 500
    out = first_sentence(long, max_chars=10)
    assert len(out) == 10 and out.endswith("…")


# --- paths.find_workspace_root ----------------------------------------------

def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "studies" / "s").mkdir(parents=True)
    (ws / "workspace.yaml").write_text("name: t\n")
    return ws


def test_find_workspace_root_walks_up(tmp_path: Path):
    ws = _ws(tmp_path)
    assert find_workspace_root(ws / "studies" / "s") == ws


def test_find_workspace_root_raises_by_default(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        find_workspace_root(tmp_path / "empty")


def test_find_workspace_root_missing_ok_returns_none(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    assert find_workspace_root(tmp_path / "empty", missing_ok=True) is None
