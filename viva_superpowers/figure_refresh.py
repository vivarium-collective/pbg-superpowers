"""Re-render a study's figures from its canonical run — the generic auto-refresh
that closes the recurring "verdict updated but plots stale" gap (see the
v2ecoli dnaa-replication friction log, 2026-06-01).

A study declares HOW to refresh its figures in ``study.yaml``::

    figure_refresh:
      - "python scripts/render_dnaa2_sixpanel.py --run {run} --seed 0 --step 3 --format both"

Placeholders substituted before each command runs (cwd = workspace root):

  {run}    — the canonical (latest-by-mtime) ``studies/<slug>/parquet-runs/<id>`` dir
  {study}  — the study slug
  {figdir} — ``reports/figures/<slug>``
  {ws}     — the workspace root
  {py}     — the invoking interpreter (``sys.executable``) — use ``{py} scripts/foo.py``
             instead of bare ``python`` so the render gets the venv's deps

This keeps figure RENDERING workspace-specific (the commands are the study's own
bespoke renderers — many read parquet directly and have no ``inputs_map`` for
the generic ``render_study_visualizations`` path) while the WHEN — re-render
from the run that just finished — is owned by the framework. Run-completion
paths (workflow drivers, ``/pbg-study run-*``) should call
``refresh_study_figures`` so figures track runs by construction; the
``figure_stale_vs_run`` linter then has nothing to flag.

Standalone::

    python -m viva_superpowers.figure_refresh <slug> [<slug> ...] [--dry-run]

Security note: commands run via the shell. They are the study's OWN declared
config inside the repo (no external input), which is the same trust level as the
bespoke render scripts they invoke.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from . import chart_store

_CHART_SUFFIXES = (".png", ".svg", ".html", ".pdf")


def _chart_mtimes(figdir: Path) -> dict[Path, float]:
    """Snapshot {chart_file: mtime} under figdir (empty if it doesn't exist)."""
    out: dict[Path, float] = {}
    if figdir.is_dir():
        for p in figdir.iterdir():
            if p.is_file() and p.suffix.lower() in _CHART_SUFFIXES:
                out[p] = p.stat().st_mtime
    return out


def find_workspace_root(start: Path | None = None) -> Path:
    """Nearest ancestor (inclusive) containing ``workspace.yaml``; else ``start``."""
    p = (start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / "workspace.yaml").is_file():
            return d
    return p


def latest_run_dir(ws_root: Path, slug: str) -> Path | None:
    """Most-recent ``studies/<slug>/parquet-runs/<id>/`` by mtime, or None."""
    root = Path(ws_root) / "studies" / slug / "parquet-runs"
    if not root.is_dir():
        return None
    runs = [p for p in root.iterdir() if p.is_dir()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def study_figure_refresh_commands(ws_root: Path, slug: str) -> list[str]:
    """The ``figure_refresh:`` command-template list from a study's yaml."""
    y = Path(ws_root) / "studies" / slug / "study.yaml"
    if not y.is_file():
        return []
    try:
        spec = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    cmds = spec.get("figure_refresh") or []
    return [c for c in cmds if isinstance(c, str) and c.strip()]


def refresh_study_figures(ws_root: Path, slug: str,
                          run_dir: Path | str | None = None,
                          *, dry_run: bool = False) -> dict:
    """Run a study's ``figure_refresh`` commands with placeholders substituted.

    Returns ``{slug, run, ran: [...], failed: [...], skipped: reason|None}``.
    Never raises on a command failure — collects them in ``failed`` (the caller
    decides whether a viz-refresh failure should matter; a run must not fail
    because a plot didn't render).
    """
    ws_root = Path(ws_root)
    cmds = study_figure_refresh_commands(ws_root, slug)
    if not cmds:
        return {"slug": slug, "run": None, "ran": [], "failed": [],
                "skipped": "no figure_refresh declared in study.yaml"}
    run = Path(run_dir) if run_dir else latest_run_dir(ws_root, slug)
    if run is None:
        return {"slug": slug, "run": None, "ran": [], "failed": [],
                "skipped": "no parquet-runs to render from"}
    subs = {
        "run": str(run),
        "study": slug,
        "figdir": str(ws_root / "reports" / "figures" / slug),
        "ws": str(ws_root),
        # The interpreter that invoked us — almost always the workspace venv's
        # python (the driver / `python -m viva_superpowers.figure_refresh` runs
        # under it). Studies should write "{py} scripts/foo.py", NOT bare
        # "python ...", so the render gets the venv's deps instead of whatever
        # `python` PATH happens to resolve to (a recurring v2ecoli footgun).
        "py": sys.executable,
    }
    figdir = ws_root / "reports" / "figures" / slug
    before = {} if dry_run else _chart_mtimes(figdir)
    ran: list[str] = []
    failed: list[str] = []
    for raw in cmds:
        try:
            cmd = raw.format(**subs)
        except (KeyError, IndexError) as e:
            failed.append(raw)
            sys.stderr.write(f"figure_refresh[{slug}] bad placeholder in {raw!r}: {e}\n")
            continue
        if dry_run:
            ran.append(cmd)
            continue
        r = subprocess.run(cmd, shell=True, cwd=str(ws_root),
                           capture_output=True, text=True)
        if r.returncode == 0:
            ran.append(cmd)
        else:
            failed.append(cmd)
            sys.stderr.write(
                f"figure_refresh[{slug}] FAILED ({r.returncode}): {cmd}\n"
                f"{(r.stderr or '')[-800:]}\n")
    if not dry_run and ran:
        # Tag the chart files this run actually (re-)wrote so a later canonical
        # run can prune the superseded ones (chart_store; best-effort, never
        # blocks a refresh). Only newly-written/changed files are tagged.
        try:
            after = _chart_mtimes(figdir)
            produced = [p for p, m in after.items()
                        if p not in before or m > before[p]]
            if produced:
                chart_store.tag_charts(figdir, run.name, produced)
        except Exception:
            pass
    return {"slug": slug, "run": str(run), "ran": ran, "failed": failed,
            "skipped": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-render studies' figures from their canonical run "
                    "(reads each study.yaml's figure_refresh: commands).")
    ap.add_argument("slugs", nargs="+", help="study slug(s)")
    ap.add_argument("--ws", default=None, help="workspace root (default: auto-detect)")
    ap.add_argument("--run", default=None,
                    help="override canonical run dir (only meaningful for one slug)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print substituted commands without running them")
    a = ap.parse_args(argv)
    ws = Path(a.ws) if a.ws else find_workspace_root()
    rc = 0
    for slug in a.slugs:
        res = refresh_study_figures(ws, slug, run_dir=a.run, dry_run=a.dry_run)
        if res["skipped"]:
            print(f"  {slug}: skipped — {res['skipped']}")
        else:
            print(f"  {slug}: ran {len(res['ran'])}, failed {len(res['failed'])} "
                  f"(run {res['run']})")
            for c in res["ran"]:
                print(f"      {'[dry-run] ' if a.dry_run else ''}{c}")
        if res["failed"]:
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
