"""Tests for pbg_superpowers.chart_store — run-tagged charts + auto-prune."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbg_superpowers import chart_store, viz_freshness


def _study(tmp_path: Path, runs: list[dict],
           visualizations: list[dict] | None = None) -> Path:
    """Build a tmp study dir with a charts/ subdir and a study.yaml."""
    sd = tmp_path / "studies" / "s1"
    (sd / "charts").mkdir(parents=True)
    spec: dict = {"runs": runs}
    if visualizations is not None:
        spec["visualizations"] = visualizations
    import yaml
    (sd / "study.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    return sd


def _write_chart(sd: Path, name: str, text: str = "<svg/>") -> Path:
    p = sd / "charts" / name
    p.write_text(text, encoding="utf-8")
    return p


def test_tag_and_load_manifest_roundtrip(tmp_path):
    sd = _study(tmp_path, [{"name": "runB", "canonical": True}])
    c = _write_chart(sd, "a.svg")
    chart_store.tag_chart(c, "runB")
    manifest = chart_store.load_manifest(sd / "charts")
    assert manifest["a.svg"]["run_id"] == "runB"
    assert "created" in manifest["a.svg"]
    assert chart_store.chart_run_id(sd / "charts", "a.svg") == "runB"


def test_canonical_run_id_honours_flag(tmp_path):
    sd = _study(tmp_path, [{"name": "runA"}, {"name": "runB", "canonical": True}])
    assert chart_store.canonical_run_id(sd) == "runB"


def test_prune_dry_run_lists_only_superseded(tmp_path):
    sd = _study(tmp_path, [{"name": "runA"}, {"name": "runB", "canonical": True}])
    chart_store.tag_chart(_write_chart(sd, "old.svg"), "runA")     # superseded
    chart_store.tag_chart(_write_chart(sd, "new.svg"), "runB")     # canonical
    _write_chart(sd, "legacy.svg")                                  # untagged

    res = chart_store.prune(sd, dry_run=True)
    assert res["dry_run"] is True
    assert res["canonical_run"] == "runB"
    assert res["superseded"] == ["charts/old.svg"]
    assert res["untagged"] == ["charts/legacy.svg"]
    assert res["deleted"] == []
    # dry-run touches nothing on disk
    assert (sd / "charts" / "old.svg").is_file()
    assert (sd / "charts" / "legacy.svg").is_file()


def test_untagged_charts_are_never_selected(tmp_path):
    sd = _study(tmp_path, [{"name": "runB", "canonical": True}])
    _write_chart(sd, "legacy_a.svg")
    _write_chart(sd, "legacy_b.png")
    res = chart_store.prune(sd, dry_run=False)  # even when deleting
    assert res["superseded"] == []
    assert res["deleted"] == []
    assert set(res["untagged"]) == {"charts/legacy_a.svg", "charts/legacy_b.png"}
    assert (sd / "charts" / "legacy_a.svg").is_file()
    assert (sd / "charts" / "legacy_b.png").is_file()


def test_prune_delete_removes_superseded_and_siblings(tmp_path):
    sd = _study(tmp_path, [{"name": "runA"}, {"name": "runB", "canonical": True}])
    old = _write_chart(sd, "old.svg")
    chart_store.tag_chart(old, "runA")
    # display + provenance sidecars that should go with it
    (sd / "charts" / "old.meta.json").write_text(json.dumps({"title": "Old"}))
    viz_freshness.stamp_meta(old, source_run_id="runA", generation_id=None,
                             rendered_at=1.0, command="cmd")
    new = _write_chart(sd, "new.svg")
    chart_store.tag_chart(new, "runB")
    legacy = _write_chart(sd, "legacy.svg")

    res = chart_store.prune(sd, dry_run=False)
    assert res["superseded"] == ["charts/old.svg"]
    assert "charts/old.svg" in res["deleted"]
    # chart + both sidecars gone
    assert not old.is_file()
    assert not (sd / "charts" / "old.meta.json").is_file()
    assert not (sd / "charts" / "old.svg.meta.json").is_file()
    # canonical + untagged survive
    assert new.is_file()
    assert legacy.is_file()
    # manifest entry for the deleted chart is removed
    assert "old.svg" not in chart_store.load_manifest(sd / "charts")


def test_pinned_source_run_is_protected(tmp_path):
    # runA is non-canonical but a visualizations entry pins source_run: runA.
    sd = _study(
        tmp_path,
        [{"name": "runA"}, {"name": "runB", "canonical": True}],
        visualizations=[{"name": "pinned", "chart": "charts/old.svg",
                         "source_run": "runA"}],
    )
    chart_store.tag_chart(_write_chart(sd, "old.svg"), "runA")
    chart_store.tag_chart(_write_chart(sd, "new.svg"), "runB")
    res = chart_store.prune(sd, dry_run=False)
    assert res["superseded"] == []
    assert res["referenced_runs"] == ["runA"]
    assert (sd / "charts" / "old.svg").is_file()


def test_prune_skips_when_no_canonical_run(tmp_path):
    sd = _study(tmp_path, [])  # no runs → no canonical
    chart_store.tag_chart(_write_chart(sd, "a.svg"), "runX")
    res = chart_store.prune(sd, dry_run=False)
    assert res["canonical_run"] is None
    assert res["skipped"]
    assert res["superseded"] == []
    assert res["deleted"] == []
    assert (sd / "charts" / "a.svg").is_file()


def test_meta_json_fallback_resolves_run(tmp_path):
    # No manifest entry, but viz_freshness meta carries source_run_id.
    sd = _study(tmp_path, [{"name": "runB", "canonical": True}])
    old = _write_chart(sd, "stamped.svg")
    viz_freshness.stamp_meta(old, source_run_id="runA", generation_id=None,
                             rendered_at=1.0, command="cmd")
    assert chart_store.chart_run_id(sd / "charts", "stamped.svg") == "runA"
    res = chart_store.prune(sd, dry_run=True)
    assert res["superseded"] == ["charts/stamped.svg"]


def test_superseded_chart_names_helper(tmp_path):
    sd = _study(tmp_path, [{"name": "runA"}, {"name": "runB", "canonical": True}])
    chart_store.tag_chart(_write_chart(sd, "old.svg"), "runA")
    chart_store.tag_chart(_write_chart(sd, "new.svg"), "runB")
    assert chart_store.superseded_chart_names(sd) == {"old.svg"}
