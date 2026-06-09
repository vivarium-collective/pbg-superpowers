"""The package __version__ must match pyproject [project].version.

scaffold._plugin_version() stamps __version__ into every new workspace, so a
drift between the two silently mislabels scaffolded workspaces.
"""
import tomllib

import pbg_superpowers


def test_version_matches_pyproject(plugin_root):
    pyproject = plugin_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    assert pbg_superpowers.__version__ == data["project"]["version"]
