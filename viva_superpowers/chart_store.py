"""Run-tagged chart store + auto-prune of superseded-run charts.

The recurring #1 expert friction (see ``v2e-invest`` docs/conventions/
expert-feedback-friction-analysis.md): a study's report renders EVERY chart
file in its ``charts/`` dir (the dashboard's
``study_charts.discover_static_study_charts`` globs ``*.svg|png|gif``
unconditionally), so when a new canonical run lands the OLD run's charts keep
showing and the expert has to ask, again, "why do you still have the old
visualizations… this section is stale".

There was no record of *which run produced which chart*. This module adds one:
a sidecar manifest ``<charts_dir>/.chart-runs.json`` mapping each chart
basename to ``{run_id, created}``. With that record we can identify charts whose
producing run has been *superseded* by the study's canonical run and prune them.

Design principles
-----------------
* **Deterministic, pure-Python, no AI, no network.** The dashboard and the
  framework run-completion / report paths call these directly.
* **Tag on write.** Whatever renders a chart (``figure_refresh``,
  ``refresh_viz``, the dashboard run path) records the producing run id.
* **Prune is opt-in and safe.** ``prune`` defaults to ``dry_run=True`` — it only
  *lists* superseded files; deleting requires an explicit ``dry_run=False``.
* **Untagged legacy charts are never deleted.** A chart with no resolvable
  producing run is reported as ``untagged`` (so a human can decide), never
  pruned. This is the load-bearing safety guarantee.
* **Explicitly-pinned charts are kept.** A chart whose run id is the canonical
  run, or is pinned by a current ``visualizations:``/``embed_visualizations:``
  ``source_run`` entry, is protected.

Tag resolution falls back to the ``viz_freshness`` ``<chart>.meta.json``
sidecar's ``source_run_id`` when the manifest has no entry for a chart, so
charts already stamped by the existing render path are covered without an
explicit re-tag.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import study_io, study_outcomes, run_registry, viz_freshness

# Sidecar manifest filename, written inside the study's charts/ dir.
MANIFEST_NAME = ".chart-runs.json"

# Chart media families discovered/pruned (mirrors study_charts discovery).
CHART_EXTS = (".svg", ".png", ".gif")

# Keys that may carry a run's identity across the various runs[] shapes in the
# wild (study_outcomes/run_registry write `name`/`run_id`; colonies-style
# studies use `simulation`).
_RUN_ID_KEYS = ("run_id", "name", "simulation", "experiment_id", "id")


# ---------------------------------------------------------------------------
# Manifest IO
# ---------------------------------------------------------------------------

def manifest_path(charts_dir: Path | str) -> Path:
    """Path to the run-tag manifest inside ``charts_dir``."""
    return Path(charts_dir) / MANIFEST_NAME


def load_manifest(charts_dir: Path | str) -> dict:
    """Load ``{basename: {run_id, created}}``; tolerant ({} on any error)."""
    p = manifest_path(charts_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_manifest(charts_dir: Path | str, manifest: dict) -> None:
    """Atomically overwrite the manifest (reuses study_io.atomic_write)."""
    charts_dir = Path(charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)
    study_io.atomic_write(
        manifest_path(charts_dir),
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

def tag_chart(chart_path: Path | str, run_id: str,
              *, charts_dir: Path | str | None = None,
              created: str | None = None) -> None:
    """Record that ``run_id`` produced ``chart_path``.

    Keyed by the chart's *basename* (filenames are unique within a charts dir).
    ``charts_dir`` defaults to the chart's parent. ``created`` defaults to an
    ISO-8601 UTC timestamp. Idempotent: re-tagging overwrites the entry (the
    common case when a refresh re-renders the same basename from a new run).
    """
    chart_path = Path(chart_path)
    cdir = Path(charts_dir) if charts_dir is not None else chart_path.parent
    manifest = load_manifest(cdir)
    manifest[chart_path.name] = {
        "run_id": str(run_id),
        "created": created or _now_iso(),
    }
    _write_manifest(cdir, manifest)


def tag_charts(charts_dir: Path | str, run_id: str,
               chart_paths, *, created: str | None = None) -> None:
    """Tag many charts with one ``run_id`` in a single manifest write."""
    cdir = Path(charts_dir)
    manifest = load_manifest(cdir)
    stamp = created or _now_iso()
    for cp in chart_paths:
        manifest[Path(cp).name] = {"run_id": str(run_id), "created": stamp}
    _write_manifest(cdir, manifest)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Run-id resolution
# ---------------------------------------------------------------------------

def _run_id_of(run: dict | None) -> str | None:
    if not isinstance(run, dict):
        return None
    for k in _RUN_ID_KEYS:
        v = run.get(k)
        if v:
            return str(v)
    return None


def canonical_run_id(study_dir: Path | str) -> str | None:
    """Resolve the study's canonical run id.

    Primary: ``study_outcomes.canonical_run`` over ``study.yaml``'s ``runs:``
    (honours an explicit ``canonical: true``, else newest completed). Falls back
    to the latest row in ``runs.db`` via ``run_registry.latest_run``. Returns
    ``None`` when no run can be resolved (in which case prune is a no-op — we
    can't know what's superseded)."""
    study_dir = Path(study_dir)
    study_yaml = study_dir / "study.yaml"
    if study_yaml.is_file():
        try:
            spec = study_io.load_yaml(study_yaml)
        except Exception:  # noqa: BLE001 — malformed yaml → fall through to db
            spec = {}
        rid = _run_id_of(study_outcomes.canonical_run(spec))
        if rid:
            return rid
    latest = run_registry.latest_run(study_dir / "runs.db")
    return (latest or {}).get("run_id")


def referenced_run_ids(study_dir: Path | str) -> set[str]:
    """Run ids explicitly pinned by current visualization entries.

    A ``visualizations:`` / ``embed_visualizations:`` entry may carry
    ``source_run: <id>`` to anchor its chart to a specific (possibly
    non-canonical) run. Those runs' charts are intentional and must be kept."""
    study_dir = Path(study_dir)
    study_yaml = study_dir / "study.yaml"
    out: set[str] = set()
    if not study_yaml.is_file():
        return out
    try:
        spec = study_io.load_yaml(study_yaml)
    except Exception:  # noqa: BLE001
        return out
    for block in ("visualizations", "embed_visualizations"):
        for entry in (spec.get(block) or []):
            if isinstance(entry, dict) and entry.get("source_run"):
                out.add(str(entry["source_run"]))
    return out


def chart_run_id(charts_dir: Path | str, basename: str) -> str | None:
    """The run id that produced chart ``basename``, or ``None`` if untagged.

    Manifest first; falls back to the ``viz_freshness`` ``<chart>.meta.json``
    sidecar's ``source_run_id`` so already-stamped charts are covered."""
    cdir = Path(charts_dir)
    entry = load_manifest(cdir).get(basename)
    if isinstance(entry, dict) and entry.get("run_id"):
        return str(entry["run_id"])
    meta = viz_freshness.read_meta(cdir / basename)
    if isinstance(meta, dict) and meta.get("source_run_id"):
        return str(meta["source_run_id"])
    return None


# ---------------------------------------------------------------------------
# Classification + prune
# ---------------------------------------------------------------------------

def _chart_files(charts_dir: Path) -> list[Path]:
    if not charts_dir.is_dir():
        return []
    return sorted(
        p for p in charts_dir.iterdir()
        if p.is_file() and p.suffix.lower() in CHART_EXTS
    )


def classify_charts(study_dir: Path | str) -> dict:
    """Bucket a study's chart files by their producing run.

    Returns a dict::

        {
          "charts_dir":     "<abs path>",
          "canonical_run":  "<id>" | None,
          "referenced_runs": ["<id>", ...],
          "canonical":   ["charts/<name>", ...],  # produced by the canonical run
          "referenced":  [...],                    # pinned by a visualizations entry
          "superseded":  [...],                    # tagged to a non-canonical, unpinned run
          "untagged":    [...],                    # no resolvable run — NEVER pruned
        }

    Relpaths are ``charts/<name>`` to match the dashboard's chart records.
    When the canonical run can't be resolved, nothing is marked ``superseded``
    (we can't know what's stale): a pinned chart still lands in ``referenced``,
    and every other chart — tagged or not — is reported under ``untagged`` so a
    human decides. Pruning is then a no-op (see :func:`prune`)."""
    study_dir = Path(study_dir)
    charts_dir = study_dir / "charts"
    canon = canonical_run_id(study_dir)
    refs = referenced_run_ids(study_dir)

    res = {
        "charts_dir": str(charts_dir),
        "canonical_run": canon,
        "referenced_runs": sorted(refs),
        "canonical": [],
        "referenced": [],
        "superseded": [],
        "untagged": [],
    }
    for f in _chart_files(charts_dir):
        rel = f"charts/{f.name}"
        rid = chart_run_id(charts_dir, f.name)
        if rid is None:
            res["untagged"].append(rel)
        elif canon is not None and rid == canon:
            res["canonical"].append(rel)
        elif rid in refs:
            res["referenced"].append(rel)
        elif canon is None:
            # Tagged, but we can't resolve a canonical run to compare against —
            # do NOT call it superseded. Treat conservatively as keep/untagged.
            res["untagged"].append(rel)
        else:
            res["superseded"].append(rel)
    return res


def superseded_chart_names(study_dir: Path | str) -> set[str]:
    """Just the basenames of superseded charts — the set a discovery hook
    (e.g. ``study_charts.discover_static_study_charts``) can skip to hide
    non-canonical charts. Empty set when the canonical run is unresolved or
    every chart is current/untagged."""
    return {Path(rel).name for rel in classify_charts(study_dir)["superseded"]}


def _sibling_paths(chart_file: Path, protected: set[str]) -> list[Path]:
    """Files to remove alongside a superseded ``chart_file``:

    * its ``viz_freshness`` provenance sidecar ``<file>.meta.json``,
    * its ``study_charts`` display sidecar ``<stem>.meta.json``,
    * same-stem chart-media twins (e.g. a ``.svg`` rendered next to a ``.png``)
      — but ONLY when that twin is not itself protected (canonical/referenced).

    ``protected`` is the set of protected basenames.
    """
    stem = chart_file.stem
    cdir = chart_file.parent
    out: list[Path] = []
    # provenance sidecar: <file>.meta.json  (e.g. c.svg.meta.json)
    out.append(chart_file.with_suffix(chart_file.suffix + ".meta.json"))
    # display sidecar: <stem>.meta.json  (e.g. c.meta.json)
    out.append(cdir / f"{stem}.meta.json")
    # same-stem chart-media twins
    for ext in CHART_EXTS:
        twin = cdir / f"{stem}{ext}"
        if twin == chart_file:
            continue
        if twin.name in protected:
            continue
        if twin.is_file():
            out.append(twin)
            # the twin's own provenance sidecar too
            out.append(twin.with_suffix(twin.suffix + ".meta.json"))
    return out


def prune(study_dir: Path | str, *, dry_run: bool = True) -> dict:
    """Identify (and, with ``dry_run=False``, delete) superseded-run charts.

    SAFE BY DEFAULT: ``dry_run=True`` only lists. Untagged charts are never
    selected. Returns::

        {
          "canonical_run":   "<id>" | None,
          "referenced_runs": [...],
          "superseded":      ["charts/<name>", ...],  # selected
          "untagged":        [...],                   # reported, not touched
          "deleted":         [...],                   # files removed (empty if dry_run)
          "dry_run":         True/False,
          "skipped":         "<reason>" | None,       # set when no canonical run
        }
    """
    study_dir = Path(study_dir)
    cls = classify_charts(study_dir)
    superseded = cls["superseded"]
    result = {
        "canonical_run": cls["canonical_run"],
        "referenced_runs": cls["referenced_runs"],
        "superseded": superseded,
        "untagged": cls["untagged"],
        "deleted": [],
        "dry_run": dry_run,
        "skipped": None,
    }
    if cls["canonical_run"] is None:
        result["skipped"] = "no canonical run resolved — nothing pruned"
        return result
    if dry_run or not superseded:
        return result

    charts_dir = Path(cls["charts_dir"])
    protected = {Path(rel).name for rel in (cls["canonical"] + cls["referenced"])}
    manifest = load_manifest(charts_dir)
    deleted: list[str] = []
    manifest_dirty = False

    for rel in superseded:
        chart_file = study_dir / rel
        targets = [chart_file] + _sibling_paths(chart_file, protected)
        for t in targets:
            if t.is_file():
                try:
                    t.unlink()
                except OSError:
                    continue
                # report removed chart-media as study-relative; sidecars as-is
                deleted.append(f"charts/{t.name}")
                if t.name in manifest:
                    del manifest[t.name]
                    manifest_dirty = True

    if manifest_dirty:
        _write_manifest(charts_dir, manifest)
    result["deleted"] = deleted
    return result


def main(argv=None) -> int:
    import argparse
    from .workspace_paths import WorkspacePaths

    ap = argparse.ArgumentParser(
        description="List or prune superseded-run charts in a study.")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--study", required=True, help="study slug")
    ap.add_argument("--delete", action="store_true",
                    help="actually delete (default: dry-run list only)")
    args = ap.parse_args(argv)

    paths = WorkspacePaths.load(Path(args.workspace))
    sd = paths.study_dir(args.study)
    res = prune(sd, dry_run=not args.delete)
    print(f"study: {args.study}  canonical_run={res['canonical_run']}")
    if res["skipped"]:
        print(f"  skipped: {res['skipped']}")
    for rel in res["superseded"]:
        print(f"  {'DELETED' if not res['dry_run'] else 'superseded'}: {rel}")
    for rel in res["untagged"]:
        print(f"  untagged (kept): {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
