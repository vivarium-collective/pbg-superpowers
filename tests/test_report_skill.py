"""Guard test for the /viva-report skill (Phase 2.1d rewire).

Asserts the SKILL.md is a THIN client of the workbench dashboard API
(GET /api/report-lint, POST /api/study-readout-migrate, POST /api/render)
rather than importing/invoking viva_superpowers compute in-process. The
prior attempt at this rewire reimplemented compute (including override-log
logic) in the skill; the workbench endpoints were then enhanced to do that
server-side, so this guard also blocks any client-side override-key /
override-log reimplementation creeping back in.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parents[1] / "skills" / "viva-report" / "SKILL.md"


@pytest.fixture
def skill_text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert _SKILL.is_file(), "skills/viva-report/SKILL.md must exist"


def test_references_report_lint_backend(skill_text):
    assert "GET /api/report-lint" in skill_text or "/api/report-lint" in skill_text
    assert "curl" in skill_text


def test_references_readout_migrate_backend(skill_text):
    assert "/api/study-readout-migrate" in skill_text


def test_references_render_backend(skill_text):
    assert "/api/render" in skill_text
    # today/force body fields (byte-stable CI render + forced-render w/
    # server-side override logging) must be documented as POST body fields,
    # not reimplemented client-side.
    assert '"today"' in skill_text
    assert '"force"' in skill_text or "'force'" in skill_text


def test_no_inline_plugin_compute(skill_text):
    """2.1d rewire: zero in-process viva_superpowers consumer sites for the
    3 rewired ops (report_linter, readout_migration, report render).

    A SKILL.md is a program — `from viva_superpowers.X import Y` and
    `python -m viva_superpowers.X` (beyond the untouched bootstrap/deferred
    call sites) are hard-blocker consumer sites, not prose.
    """
    assert "python -m viva_superpowers.report_linter" not in skill_text
    assert "from viva_superpowers.readout_migration" not in skill_text
    assert "from viva_superpowers.report import" not in skill_text
    assert "from viva_superpowers.report import render_workspace_report" not in skill_text
    assert "render_workspace_report(" not in skill_text
    assert "from vivarium_workbench.lib.report import" not in skill_text


def test_no_client_side_override_reimplementation(skill_text):
    """The whole point of the 2.1d endpoint enhancement: override-key
    derivation / override-log writing must live server-side only. If the
    skill starts hashing/deriving override keys or writing
    report-lint-overrides.json itself, the endpoints were bypassed.
    """
    assert "hashlib" not in skill_text
    assert "write_override(" not in skill_text
    assert "load_overrides(" not in skill_text
    assert "apply_overrides(" not in skill_text
    assert "_override_key(" not in skill_text


def test_server_preflight_documented(skill_text):
    # viva-catalog's exact preflight idiom: workspace.yaml walk-up +
    # .pbg/server/server-info, erroring (not silently falling back) when
    # the dashboard server is not running.
    assert "workspace.yaml" in skill_text
    assert ".pbg/server/server-info" in skill_text
    assert "/viva-workbench start" in skill_text


def test_bootstrap_call_sites_untouched(skill_text):
    # paths --env stays OUT of scope for the report rewire (bootstrap/deferred).
    assert "python -m viva_superpowers.paths --env" in skill_text
    # Phase 2.1j rewired the dashboard-restart site to the vwb CLI (the plugin's
    # server manager viva_superpowers.workbench was deleted).
    assert "vwb server-restart" in skill_text
    assert "python -m viva_superpowers.workbench" not in skill_text
