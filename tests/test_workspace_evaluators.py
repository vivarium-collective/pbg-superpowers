import sys
import textwrap
from pathlib import Path

import pytest

from pbg_superpowers import study_evaluator as se


def _make_fixture_ws(tmp_path: Path, kind: str = "toy_kind") -> Path:
    """A throwaway workspace whose pbg_<name>.evaluators registers one evaluator."""
    ws = tmp_path / "ws"
    pkg = ws / "pbg_toyws"
    pkg.mkdir(parents=True)
    (ws / "workspace.yaml").write_text("name: toyws\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "evaluators.py").write_text(textwrap.dedent(f"""
        def _toy(test, reader, ws_root):
            return {{"result": "PASS", "evaluated_by": "toy",
                    "detail": "from " + str(ws_root)}}
        def register_evaluators(registry):
            registry["{kind}"] = _toy
    """), encoding="utf-8")
    return ws


def test_loader_finds_and_calls_hook(tmp_path):
    ws = _make_fixture_ws(tmp_path)
    se.clear_workspace_evaluator_cache()
    reg = se.load_workspace_evaluators(ws)
    assert "toy_kind" in reg
    out = reg["toy_kind"]({}, None, ws)
    assert out["evaluated_by"] == "toy"


def test_loader_absent_hook_returns_empty(tmp_path):
    ws = tmp_path / "bare"
    ws.mkdir()
    (ws / "workspace.yaml").write_text("name: bare\n", encoding="utf-8")
    se.clear_workspace_evaluator_cache()
    assert se.load_workspace_evaluators(ws) == {}


def test_loader_broken_hook_degrades(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    pkg = ws / "pbg_brokenws"
    pkg.mkdir(parents=True)
    (ws / "workspace.yaml").write_text("name: brokenws\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "evaluators.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    se.clear_workspace_evaluator_cache()
    assert se.load_workspace_evaluators(ws) == {}  # never raises


def test_evaluate_test_dispatches_to_registered_evaluator(tmp_path):
    ws = _make_fixture_ws(tmp_path, kind="toy_kind")
    se.clear_workspace_evaluator_cache()
    test = {"name": "t", "measure": {"kind": "toy_kind"}, "pass_if": {"op": "x"}}
    out = se.evaluate_test(test, reader=None, ws_root=ws)
    assert out["evaluated_by"] == "toy"


def test_evaluate_test_unknown_kind_no_ws_still_agent():
    test = {"name": "t", "measure": {"kind": "nope"}, "pass_if": {"op": "x"}}
    out = se.evaluate_test(test, reader=None, ws_root=None)
    assert out["evaluated_by"] == "agent"
