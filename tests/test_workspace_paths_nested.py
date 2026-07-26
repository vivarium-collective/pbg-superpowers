"""Top-level-only study resolution (investigation-centric structure, Phase 1).

Studies are resolved ONLY from the canonical top-level ``studies/`` directory.
A study that exists solely under a nested ``investigations/*/studies/`` path is
intentionally NOT resolvable (single canonical location, no shadow copies)."""
from pathlib import Path

import pytest

from viva_superpowers.workspace_paths import WorkspacePaths


def _ws(tmp, nested: bool):
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    if nested:
        d = tmp / "investigations" / "inv-a" / "studies" / "s1"
    else:
        d = tmp / "studies" / "s1"
    d.mkdir(parents=True)
    (d / "study.yaml").write_text(
        ("investigation: inv-a\n" if nested else "") + "name: s1\n", encoding="utf-8")
    return WorkspacePaths.load(tmp)


def test_study_dir_nested_not_resolved(tmp_path):
    wp = _ws(tmp_path, nested=True)
    with pytest.raises(FileNotFoundError):
        wp.study_dir("s1")


def test_study_dir_flat_backcompat(tmp_path):
    wp = _ws(tmp_path, nested=False)
    assert wp.study_dir("s1") == tmp_path / "studies" / "s1"


def test_iter_study_dirs_ignores_nested_only(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert [p.name for p in wp.iter_study_dirs()] == []


def test_study_owner_nested_only_is_none(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert wp.study_owner("s1") is None


def test_study_owner_flat_is_none(tmp_path):
    wp = _ws(tmp_path, nested=False)
    assert wp.study_owner("s1") is None


def test_paths_cli_study_dir_nested_only_not_found(tmp_path, capsys):
    # CLI --study resolution delegates to WorkspacePaths.study_dir, which raises
    # FileNotFoundError uncaught (no try/except in _main) — this propagates as a
    # non-zero process exit when run as a script.
    _ws(tmp_path, nested=True)
    from viva_superpowers.paths import _main
    with pytest.raises(FileNotFoundError):
        _main(["--study", "s1", "--workspace", str(tmp_path)])


def test_inputs_dir_nested(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert wp.inputs_dir("inv-a") == tmp_path / "investigations" / "inv-a" / "inputs"
