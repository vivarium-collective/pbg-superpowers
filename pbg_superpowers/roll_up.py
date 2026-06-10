"""CLI: pbg-roll-up — write coded verdicts (gate_evaluator + investigation acceptance).

Usage
-----
# Roll up gate evaluator for one study:
pbg-roll-up --study <slug> [--workspace .]

# Roll up gate evaluators for all studies:
pbg-roll-up --all [--workspace .]

# Roll up investigation acceptance for one investigation:
pbg-roll-up --investigation <slug> [--workspace .]

# Roll up all (all studies + all investigations):
pbg-roll-up --all --investigations [--workspace .]
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write coded gate verdicts and investigation acceptance slots."
    )
    ap.add_argument("--workspace", default=".", metavar="DIR",
                    help="Workspace root (default: current dir)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--study", metavar="SLUG",
                     help="Roll up gate evaluator for a single study")
    grp.add_argument("--all", action="store_true",
                     help="Roll up gate evaluators for every study in the workspace")
    grp.add_argument("--investigation", metavar="SLUG",
                     help="Roll up acceptance for a single investigation")
    ap.add_argument("--investigations", action="store_true",
                    help="Also roll up acceptance for all investigations (with --all)")
    args = ap.parse_args(argv)

    from .workspace_paths import WorkspacePaths

    ws = Path(args.workspace)
    paths = WorkspacePaths.load(ws)

    if args.study:
        _roll_study(paths.studies / args.study)
    elif args.all:
        total_changed = total_err = 0
        for d in paths.iter_study_dirs():
            changed, err = _roll_study(d, quiet=False)
            total_changed += changed
            total_err += err
        print(f"TOTAL changed={total_changed} errors={total_err}")
        if args.investigations:
            _roll_all_investigations(paths, ws)
    elif args.investigation:
        inv_dir = paths.investigations / args.investigation
        _roll_investigation(inv_dir, ws)

    return 0


def _roll_study(study_dir: Path, quiet: bool = False) -> tuple[int, int]:
    """Write gate_evaluator for one study. Returns (changed, error) counts."""
    from .study_verdict import write_gate_evaluator

    try:
        changed = write_gate_evaluator(study_dir)
        status = "changed" if changed else "no-op"
        print(f"{study_dir.name}: gate_evaluator {status}")
        return (1 if changed else 0, 0)
    except Exception as exc:  # noqa: BLE001
        print(f"{study_dir.name}: ERROR — {exc}")
        return (0, 1)


def _roll_investigation(inv_dir: Path, workspace: Path) -> None:
    from .investigation_status import write_investigation_acceptance

    try:
        changed = write_investigation_acceptance(inv_dir, workspace)
        status = "changed" if changed else "no-op"
        print(f"{inv_dir.name}: computed_acceptance {status}")
    except Exception as exc:  # noqa: BLE001
        print(f"{inv_dir.name}: ERROR — {exc}")


def _roll_all_investigations(paths, workspace: Path) -> None:
    from .investigation_status import write_investigation_acceptance

    inv_root = paths.investigations
    if not inv_root.is_dir():
        return
    total_changed = total_err = 0
    for inv in sorted(p for p in inv_root.iterdir() if p.is_dir()):
        if not (inv / "investigation.yaml").exists():
            continue
        try:
            changed = write_investigation_acceptance(inv, workspace)
            status = "changed" if changed else "no-op"
            print(f"{inv.name}: computed_acceptance {status}")
            if changed:
                total_changed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{inv.name}: ERROR — {exc}")
            total_err += 1
    print(f"Investigations: changed={total_changed} errors={total_err}")


if __name__ == "__main__":
    raise SystemExit(main())
