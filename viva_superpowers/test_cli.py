"""``viva-test`` — run a study's Tests and report pass/fail.

The agent/CI-facing surface over the shipped test contract: it reads the study's
``report.json`` (``test_report/v1`` — the aggregated verdict the flush writes to
``viz/tests/report.json``), applies the severity gate, prints a pytest-style
summary, and exits non-zero when the gate FAILS (a hard mismatch). ``--json``
prints the raw contract for agents/piping.

This deliberately reuses the shipped contract (``build_report`` /
``severity_gate``) rather than a parallel artifact — a *Test* is a check, a
*report card* is the compiled output. When no ``report.json`` exists yet, it
reassembles one from the study's on-disk report cards
(``viz/report_card/<card>.verdict.json``) via ``build_report``.
"""
from __future__ import annotations

import argparse
import json
import sys

_GLYPH = {"within_tol": ".", "drift": "~", "mismatch": "F", "ungraded": "s"}
_SUITE = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def _load_report(ctx, rebuild: bool):
    """The study's test_report/v1 — read report.json, else reassemble from the
    on-disk report-card verdict.json files via build_report."""
    from viva_superpowers.post_sim import build_report, tests_dir
    rp = tests_dir(ctx) / "report.json"
    if rp.is_file() and not rebuild:
        try:
            return json.loads(rp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    cards: dict = {}
    rc_dir = ctx.study_dir / "viz" / "report_card"
    if rc_dir.is_dir():
        for vf in sorted(rc_dir.glob("*.verdict.json")):
            try:
                cards[vf.name[: -len(".verdict.json")]] = json.loads(vf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    if not cards:
        return None
    return build_report(ctx.study_name, None, cards)


def _iter_axes(report: dict):
    for card_name, doc in (report.get("cards") or {}).items():
        for gslug, grp in ((doc or {}).get("groups") or {}).items():
            for ax in grp.get("axes") or []:
                yield card_name, gslug, ax


def _print_summary(report: dict, gate: dict, out) -> None:
    counts = report.get("counts") or {}
    print(f"study: {report.get('study', '?')}", file=out)
    # Per-card glyph line + counts.
    for card_name, doc in (report.get("cards") or {}).items():
        axes = [ax for g in ((doc or {}).get("groups") or {}).values()
                for ax in (g.get("axes") or [])]
        glyphs = "".join(_GLYPH.get(ax.get("verdict", "ungraded"), "s") for ax in axes)
        p = sum(1 for ax in axes if ax.get("verdict") == "within_tol")
        f = sum(1 for ax in axes if ax.get("verdict") == "mismatch")
        d = sum(1 for ax in axes if ax.get("verdict") == "drift")
        bits = [f"{p} passed"]
        if f:
            bits.append(f"{f} failed")
        if d:
            bits.append(f"{d} drift")
        print(f"  {card_name:<20} {glyphs:<20} {', '.join(bits)}  ({len(axes)} total)", file=out)
    # Failing axes in detail (with citation when present).
    for card_name, _g, ax in _iter_axes(report):
        if ax.get("verdict") != "mismatch":
            continue
        meter = ax.get("meter")
        meter_s = f"  {meter}" if meter not in (None, "") else ""
        print(f"    FAIL  {card_name}::{ax.get('id')}{meter_s}", file=out)
        cite = ax.get("citation")
        if cite:
            print(f"          └ {cite}", file=out)
    print("─" * 46, file=out)
    total = int(counts.get("axes") or 0)
    passed = int(counts.get("within_tol") or 0)
    hard = int(counts.get("hard_mismatch") or 0)
    suite = _SUITE.get(gate.get("status"), "?")
    tail = f"  [{hard} hard]" if hard else ""
    print(f"SUITE: {suite}  ({passed}/{total} passed)  gate: {gate.get('status')}{tail}", file=out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="viva-test",
        description="Run a study's Tests and report pass/fail (agent/CI signal).")
    ap.add_argument("study", help="study slug")
    ap.add_argument("--workspace", default=".", help="workspace root (default: cwd)")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="print the raw test_report/v1 (with gate) to stdout")
    ap.add_argument("--rebuild", action="store_true",
                    help="reassemble the report from on-disk report cards")
    ap.add_argument("--quiet", action="store_true", help="suppress the summary")
    args = ap.parse_args(argv)

    from viva_superpowers.paths import workspace_root
    from viva_superpowers.post_sim import StudyContext
    from viva_superpowers.study_verdict import severity_gate

    try:
        ws = workspace_root(args.workspace)
        ctx = StudyContext.load(ws, args.study)
    except Exception as e:  # noqa: BLE001
        print(f"viva-test: cannot load study {args.study!r}: {e}", file=sys.stderr)
        return 2

    report = _load_report(ctx, args.rebuild)
    if not report or not report.get("cards"):
        print(f"viva-test: no test report for {args.study!r} — run the study first "
              f"(the flush writes viz/tests/report.json), or check "
              f"viz/report_card/*.verdict.json", file=sys.stderr)
        return 2

    gate = severity_gate(report)
    report["gate"] = gate
    if args.as_json:
        print(json.dumps(report, indent=1, allow_nan=False))
    elif not args.quiet:
        _print_summary(report, gate, sys.stdout)
    return 1 if gate.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
