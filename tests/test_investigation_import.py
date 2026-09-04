"""Tests for viva_superpowers.investigation_import (selection guard + parsing)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from viva_superpowers.investigation_import import (
    assert_selection_ok,
    check,
    load_selection,
    pinned_rev,
    present_slugs,
)


def _make_ws(tmp_path: Path, workspace_yaml: str, inv_slugs: list[str]) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "workspace.yaml").write_text(textwrap.dedent(workspace_yaml))
    for slug in inv_slugs:
        d = ws / "investigations" / slug
        d.mkdir(parents=True)
        (d / "investigation.yaml").write_text(f"name: {slug}\n")
    return ws


def test_present_slugs_requires_investigation_yaml(tmp_path: Path) -> None:
    ws = _make_ws(tmp_path, "name: t\n", ["alpha", "beta"])
    # a bare dir without investigation.yaml is not counted
    (ws / "investigations" / "stray-dir").mkdir()
    assert present_slugs(ws) == {"alpha", "beta"}


def test_load_selection_plain_list(tmp_path: Path) -> None:
    ws = _make_ws(
        tmp_path,
        """
        name: t
        imported_investigations:
          - alpha
          - beta
        native_investigations:
          - gamma
        """,
        [],
    )
    sel = load_selection(ws)
    assert sel.allow == ["alpha", "beta"]
    assert sel.native == ["gamma"]
    assert sel.source is None


def test_load_selection_source_form(tmp_path: Path) -> None:
    ws = _make_ws(
        tmp_path,
        """
        name: t
        imported_investigations:
          from: v2ecoli
          git: https://github.com/vivarium-collective/v2ecoli.git
          allow:
            - alpha
        """,
        [],
    )
    sel = load_selection(ws)
    assert sel.allow == ["alpha"]
    assert sel.source is not None
    assert sel.source.package == "v2ecoli"
    assert sel.source.subtree == "workspace/investigations"  # default
    assert sel.source.rev_token == "v2ecoli"


def test_check_passes_when_all_declared(tmp_path: Path) -> None:
    ws = _make_ws(
        tmp_path,
        """
        name: t
        imported_investigations: [alpha, beta]
        native_investigations: [gamma]
        """,
        ["alpha", "beta", "gamma"],
    )
    assert check(ws) == []
    assert_selection_ok(ws)  # does not raise


def test_check_flags_undeclared_investigation(tmp_path: Path) -> None:
    # `intruder` is present on disk but in neither list — must fail.
    ws = _make_ws(
        tmp_path,
        """
        name: t
        imported_investigations: [alpha]
        native_investigations: []
        """,
        ["alpha", "intruder"],
    )
    problems = check(ws)
    assert len(problems) == 1
    assert "intruder" in problems[0].message
    with pytest.raises(AssertionError, match="intruder"):
        assert_selection_ok(ws)


def test_check_flags_overlap(tmp_path: Path) -> None:
    ws = _make_ws(
        tmp_path,
        """
        name: t
        imported_investigations: [alpha]
        native_investigations: [alpha]
        """,
        ["alpha"],
    )
    problems = check(ws)
    assert any("BOTH imported and native" in p.message for p in problems)


def test_pinned_rev_from_uv_lock(tmp_path: Path) -> None:
    ws = _make_ws(tmp_path, "name: t\n", [])
    sha = "a" * 40
    (ws / "uv.lock").write_text(
        'source = { git = "https://github.com/vivarium-collective/v2ecoli.git?rev=main#'
        + sha
        + '" }\n'
    )
    assert pinned_rev(ws, "v2ecoli") == sha
    assert pinned_rev(ws, "nonesuch") is None
