"""Tests for the workspace-layout resolver re-exported by the compat shim.

``viva_superpowers/workspace_paths.py`` is now a thin shim over the shared
``viva-workspace`` package (the former hand-vendored copy is gone). The checks
below pin the re-exported ``LAYOUT_DEFAULTS`` and the canonical ``viva_<slug>``
package naming so the shim keeps exposing the expected public surface.
"""
from viva_superpowers.workspace_paths import (
    WorkspacePaths, LAYOUT_DEFAULTS, package_slug,
)

# The canonical flat layout — must match vivarium-workbench's copy exactly.
# If you change a directory name, change it in BOTH repos.
CANONICAL_LAYOUT_DEFAULTS = {
    "studies": "studies",
    "investigations": "investigations",
    "composites": "composites",
    "references": "references",
    "datasets": "datasets",
    "notes": "notes",
    "experiments": "experiments",
    "reports": "reports",
    "pbg": ".pbg",
    "scripts": "scripts",
    "tests": "tests",
    "docs": "docs",
}


def test_layout_defaults_match_canonical():
    assert LAYOUT_DEFAULTS == CANONICAL_LAYOUT_DEFAULTS


def test_drift_guard_against_vivarium_workbench_if_available():
    try:
        from vivarium_workbench.lib.workspace_paths import (
            LAYOUT_DEFAULTS as DASH_DEFAULTS,
        )
    except ModuleNotFoundError:
        import pytest
        pytest.skip("vivarium_workbench not installed; literal pin checked above")
    assert LAYOUT_DEFAULTS == DASH_DEFAULTS


def test_flat_defaults(tmp_path):
    wp = WorkspacePaths.from_config(tmp_path, {"name": "ws"})
    assert wp.studies == tmp_path / "studies"
    assert wp.pbg / "schemas" == tmp_path / ".pbg" / "schemas"
    assert wp.package == tmp_path / "viva_ws"


def test_layout_overrides(tmp_path):
    wp = WorkspacePaths.from_config(
        tmp_path, {"name": "ws", "layout": {"studies": "workspace/studies"}}
    )
    assert wp.studies == tmp_path / "workspace" / "studies"
    assert wp.investigations == tmp_path / "investigations"  # unspecified -> flat
    assert package_slug("a-b") == "viva_a_b"


def test_workspace_dir_cli(tmp_path, capsys):
    """The paths CLI resolves a dir name honoring layout (skills rely on this)."""
    from viva_superpowers.paths import _main, workspace_dir
    (tmp_path / "workspace.yaml").write_text(
        "name: w\nlayout:\n  investigations: workspace/investigations\n"
    )
    assert workspace_dir("investigations", root=tmp_path) == tmp_path / "workspace" / "investigations"
    assert workspace_dir("studies", root=tmp_path) == tmp_path / "studies"  # default flat
    assert workspace_dir("pbg", root=tmp_path) == tmp_path / ".pbg"

    _main(["investigations", "--workspace", str(tmp_path)])
    assert capsys.readouterr().out.strip() == str(tmp_path / "workspace" / "investigations")

    _main(["--env", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out
    assert f"export INVESTIGATIONS_DIR={tmp_path / 'workspace' / 'investigations'}" in out
    assert f"export STUDIES_DIR={tmp_path / 'studies'}" in out


def test_iter_study_dirs_toplevel_wins_collision(tmp_path):
    from viva_superpowers.workspace_paths import WorkspacePaths
    (tmp_path / "workspace.yaml").write_text("name: t\n")
    top = tmp_path / "studies" / "dup"; top.mkdir(parents=True)
    (top / "study.yaml").write_text("name: dup-TOP\n")
    nested_dup = tmp_path / "investigations" / "inv" / "studies" / "dup"
    nested_dup.mkdir(parents=True); (nested_dup / "study.yaml").write_text("name: dup-NESTED\n")
    nested_only = tmp_path / "investigations" / "inv" / "studies" / "solo"
    nested_only.mkdir(parents=True); (nested_only / "study.yaml").write_text("name: solo\n")
    wp = WorkspacePaths.load(tmp_path)
    dirs = {p.name: str(p) for p in wp.iter_study_dirs()}
    assert "investigations" not in dirs["dup"]      # top-level wins the collision
    assert "investigations" in dirs["solo"]         # nested-only still discovered
    assert set(dirs) == {"dup", "solo"}
