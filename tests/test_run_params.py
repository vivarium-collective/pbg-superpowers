"""Tests for pbg_superpowers.run_params — per-run parameter provenance capture,
ruamel-preserving write into runs[].provenance.params, and table-ready render."""
from __future__ import annotations

from pathlib import Path

import pytest

from pbg_superpowers import run_params as rp


# ---------------------------------------------------------------------------
# fakes — exercise units handling without a hard pint/unum dependency
# ---------------------------------------------------------------------------

class _UnumLike:
    """Duck-types unum.Unum: .asNumber() + .strUnit()."""
    def __init__(self, num, unit):
        self._num, self._unit = num, unit

    def asNumber(self):
        return self._num

    def strUnit(self):
        return self._unit


class _PintLike:
    """Duck-types pint.Quantity: .magnitude + .units."""
    def __init__(self, magnitude, units):
        self.magnitude, self.units = magnitude, units


# ---------------------------------------------------------------------------
# capture_run_params
# ---------------------------------------------------------------------------

def test_capture_normalizes_scalars_units_and_source():
    captured = rp.capture_run_params(
        {
            "v": _UnumLike(1.2e-3, "1/min"),     # unum-like quantity
            "kd_atp": _PintLike(45.0, "nM"),     # pint-like quantity
            "hydrolysis_rate": 0.5,              # plain float, unit via units map
            "model": "v2ecoli",                  # string passthrough
            "use_cache": True,                   # bool stays bool
        },
        overrides=["v", "kd_atp"],
        units={"hydrolysis_rate": "1/s"},
    )

    assert captured["v"] == {"value": 1.2e-3, "units": "1/min", "source": "override"}
    assert captured["kd_atp"] == {"value": 45.0, "units": "nM", "source": "override"}
    assert captured["hydrolysis_rate"] == {
        "value": 0.5, "units": "1/s", "source": "resolved"}
    # no units -> "units" key omitted; string/bool preserved
    assert captured["model"] == {"value": "v2ecoli", "source": "resolved"}
    assert captured["use_cache"] == {"value": True, "source": "resolved"}
    assert captured["use_cache"]["value"] is True  # not coerced to 1


def test_capture_is_json_yaml_safe_and_sorted():
    import json
    captured = rp.capture_run_params({
        "z_nested": {"a": _UnumLike(2.0, "mM"), "b": [1, 2]},
        "a_first": 3,
    })
    # iteration order is deterministic (sorted by name)
    assert list(captured) == ["a_first", "z_nested"]
    # nested quantity flattened to "<mag> <unit>"; whole thing round-trips JSON
    assert captured["z_nested"]["value"] == {"a": "2.0 mM", "b": [1, 2]}
    json.dumps(captured)  # must not raise


def test_capture_include_exclude_filters():
    captured = rp.capture_run_params(
        {"keep": 1, "drop_ex": 2, "drop_inc": 3},
        include=["keep", "drop_ex"],
        exclude=["drop_ex"],
    )
    assert set(captured) == {"keep"}


def test_capture_empty():
    assert rp.capture_run_params(None) == {}
    assert rp.capture_run_params({}) == {}


# ---------------------------------------------------------------------------
# write_run_params — ruamel round-trip preserving comments / prose / siblings
# ---------------------------------------------------------------------------

_STUDY_TEXT = """\
name: demo-study
# top-level comment that must survive the write
objective: |
  Multi-line prose objective.
  Second line of prose.
runs:
# comment attached to the first run
- name: run-a
  status: completed
  params:
    seed: 7
  summary: first run, authored prose stays put
- name: run-b
  status: completed
  outcomes:
    some-test:
      result: PASS
enforced_params:
  v: 0.0012
"""


def _write_study(tmp_path: Path) -> Path:
    d = tmp_path / "studies" / "demo"
    d.mkdir(parents=True)
    (d / "study.yaml").write_text(_STUDY_TEXT, encoding="utf-8")
    return d


def test_write_roundtrips_without_clobbering(tmp_path):
    import yaml
    study_dir = _write_study(tmp_path)
    captured = rp.capture_run_params(
        {"v": _UnumLike(0.0012, "1/min"), "kd": 45},
        overrides=["v"],
    )
    assert rp.write_run_params(
        study_dir, "run-b", captured, captured_at="2026-06-22",
        source="dashboard-runner") is True

    text = (study_dir / "study.yaml").read_text(encoding="utf-8")
    # comments + prose preserved
    assert "# top-level comment that must survive the write" in text
    assert "# comment attached to the first run" in text
    assert "Second line of prose." in text
    assert "first run, authored prose stays put" in text

    spec = yaml.safe_load(text)
    runs = {r["name"]: r for r in spec["runs"]}
    # sibling run untouched
    assert runs["run-a"]["params"] == {"seed": 7}
    assert "provenance" not in runs["run-a"]
    # target run got provenance.params (NOT runs[].params, which study_outcomes owns)
    prov = runs["run-b"]["provenance"]
    assert prov["params"]["v"] == {"value": 0.0012, "units": "1/min", "source": "override"}
    assert prov["params"]["kd"] == {"value": 45, "source": "resolved"}
    assert prov["params_captured_at"] == "2026-06-22"
    assert prov["params_source"] == "dashboard-runner"
    # untouched enforced_params declaration still present
    assert spec["enforced_params"] == {"v": 0.0012}


def test_write_accepts_yaml_path_and_is_idempotent(tmp_path):
    import yaml
    study_dir = _write_study(tmp_path)
    study_yaml = study_dir / "study.yaml"
    captured = rp.capture_run_params({"kd": 45})
    rp.write_run_params(study_yaml, "run-b", captured, captured_at="2026-06-22")
    first = study_yaml.read_text(encoding="utf-8")
    # re-capture/re-write identical params -> stable content
    rp.write_run_params(study_yaml, "run-b", captured, captured_at="2026-06-22")
    second = study_yaml.read_text(encoding="utf-8")
    assert first == second
    spec = yaml.safe_load(second)
    runs = {r["name"]: r for r in spec["runs"]}
    assert runs["run-b"]["provenance"]["params"]["kd"]["value"] == 45


def test_write_unknown_run_raises(tmp_path):
    study_dir = _write_study(tmp_path)
    with pytest.raises(LookupError):
        rp.write_run_params(study_dir, "no-such-run", {"x": {"value": 1}})


# ---------------------------------------------------------------------------
# render_run_params_rows / table
# ---------------------------------------------------------------------------

def test_render_rows_from_captured_with_enforced_flag():
    captured = rp.capture_run_params(
        {"v": _UnumLike(0.0012, "1/min"), "kd": 45, "model": "v2ecoli"},
        overrides=["v"],
    )
    rows = rp.render_run_params_rows(captured, enforced=["v"])
    assert rows == [
        {"param": "kd", "value": 45, "units": None, "source": "resolved", "enforced": False},
        {"param": "model", "value": "v2ecoli", "units": None, "source": "resolved", "enforced": False},
        {"param": "v", "value": 0.0012, "units": "1/min", "source": "override", "enforced": True},
    ]


def test_render_rows_from_run_record():
    run = {
        "name": "run-b",
        "params": {"seed": 7},  # mechanical sparse field — must be ignored
        "provenance": {"params": {"v": {"value": 0.0012, "units": "1/min", "source": "override"}}},
    }
    rows = rp.render_run_params_rows(run)
    assert len(rows) == 1
    assert rows[0]["param"] == "v" and rows[0]["units"] == "1/min"


def test_render_rows_empty():
    assert rp.render_run_params_rows({}) == []
    assert rp.render_run_params_rows({"name": "r", "status": "completed"}) == []


def test_render_table_html():
    captured = rp.capture_run_params({"v": _UnumLike(0.0012, "1/min")}, overrides=["v"])
    html = rp.render_run_params_table_html(captured, enforced=["v"], caption="Run params")
    assert "<table" in html and "</table>" in html
    assert "<caption>Run params</caption>" in html
    assert "0.0012" in html and "1/min" in html
    assert "✓" in html  # enforced check mark
    assert rp.render_run_params_table_html({}) == ""
