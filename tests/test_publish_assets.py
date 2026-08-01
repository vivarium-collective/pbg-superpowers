"""Tests for viva_superpowers.publish_assets.emit — the read-only-workbench
publish-asset templater (fills the gap that `vivarium-workbench add-dashboard`
is not a real CLI subcommand).
"""

from __future__ import annotations

import os
from pathlib import Path

from viva_superpowers.publish_assets import emit


def test_emit_writes_both_files_at_expected_relative_paths(tmp_path: Path) -> None:
    paths = emit(tmp_path, name="viva-fenics")
    rel = {p.relative_to(tmp_path) for p in paths}
    assert Path("scripts/publish_dashboard.sh") in rel
    assert Path(".github/workflows/publish-dashboard.yml") in rel
    assert (tmp_path / "scripts" / "publish_dashboard.sh").is_file()
    assert (tmp_path / ".github" / "workflows" / "publish-dashboard.yml").is_file()


def test_script_is_executable(tmp_path: Path) -> None:
    emit(tmp_path, name="viva-fenics")
    script = tmp_path / "scripts" / "publish_dashboard.sh"
    assert os.access(script, os.X_OK)


def test_script_contains_publish_invocation_and_default_base_path(tmp_path: Path) -> None:
    emit(tmp_path, name="viva-fenics")
    text = (tmp_path / "scripts" / "publish_dashboard.sh").read_text()
    assert "vivarium-workbench-publish" in text
    assert "/viva-fenics/dashboard" in text
    assert "find " in text and "*.map" in text
    assert ".nojekyll" in text


def test_workflow_contains_gh_pages_publish_steps_and_default_base_path(tmp_path: Path) -> None:
    emit(tmp_path, name="viva-fenics")
    text = (tmp_path / ".github" / "workflows" / "publish-dashboard.yml").read_text()
    assert "gh-pages" in text
    assert "vivarium-workbench" in text
    assert "/viva-fenics/dashboard" in text
    assert "scripts/publish_dashboard.sh" in text


def test_default_base_path_is_slash_name_slash_dashboard(tmp_path: Path) -> None:
    emit(tmp_path, name="foo-bar")
    text = (tmp_path / "scripts" / "publish_dashboard.sh").read_text()
    assert "/foo-bar/dashboard" in text


def test_custom_base_path_and_interactive_url_are_honored(tmp_path: Path) -> None:
    emit(
        tmp_path,
        name="viva-fenics",
        base_path="/custom/path",
        interactive_url="https://github.com/example/example",
    )
    script = (tmp_path / "scripts" / "publish_dashboard.sh").read_text()
    assert "/custom/path" in script
    assert "/viva-fenics/dashboard" not in script
    assert "https://github.com/example/example" in script


def test_emit_creates_parent_dirs(tmp_path: Path) -> None:
    ws = tmp_path / "nested" / "workspace"
    ws.mkdir(parents=True)
    paths = emit(ws, name="viva-fenics")
    for p in paths:
        assert p.is_file()
