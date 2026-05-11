#!/usr/bin/env python3
"""Audit all pbg-* repos listed in pbg-template's catalog for PyPI readiness.

Reads ../pbg-template/scripts/_catalog/modules.json (sibling repo), shallow-
clones each entry, runs audit_repo(run_install=False), and writes a Markdown
report to docs/audits/pbg-pypi-audit-<date>.md.

Usage:
    python scripts/audit-pbg-catalog.py [--no-clone]   # --no-clone skips git clone (dev/test)
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Locate pbg-superpowers root (script lives in scripts/).
SUPERPOWERS_ROOT = Path(__file__).resolve().parent.parent

# Locate pbg-template catalog (sibling repo).
CATALOG_PATH = SUPERPOWERS_ROOT.parent / "pbg-template" / "scripts" / "_catalog" / "modules.json"

# Audit output directory.
AUDITS_DIR = SUPERPOWERS_ROOT / "docs" / "audits"

# Ensure the local package is importable.
sys.path.insert(0, str(SUPERPOWERS_ROOT))
from pbg_superpowers.package_audit import audit_repo, AuditReport  # noqa: E402


def _clone_repo(url: str, dest: Path, timeout: int = 120) -> bool:
    """Shallow-clone *url* to *dest*. Returns True on success."""
    r = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return r.returncode == 0


def _summary_row(name: str, report: AuditReport) -> dict[str, str]:
    """Collapse a report into a single-row dict for the summary table."""
    status_map = {c.name: c.status for c in report.checks}

    def cell(key: str) -> str:
        s = status_map.get(key, "N/A")
        return s

    # Process/Step check carries a count in the detail.
    proc_check = next((c for c in report.checks if c.name == "Process/Step subclasses"), None)
    proc_cell = "N/A"
    if proc_check:
        if proc_check.status == "PASS":
            # Extract count from detail like "found 3: FooProcess (Process), ..."
            detail = proc_check.detail
            n = detail.split(" ")[1] if detail.startswith("found") else "?"
            proc_cell = f"PASS ({n})"
        else:
            proc_cell = proc_check.status

    # PyPI check detail for inline summary.
    pypi_check = next((c for c in report.checks if c.name == "published on PyPI"), None)
    pypi_cell = "N/A"
    if pypi_check:
        if pypi_check.status == "PASS":
            # "published on PyPI as pbg-foo (latest: 0.3.2)"
            pypi_cell = f"PASS — {pypi_check.detail}"
        else:
            pypi_cell = f"WARN — {pypi_check.detail}"

    return {
        "name": name,
        "pyproject": cell("pyproject.toml"),
        "bigraph_schema": cell("bigraph-schema dep"),
        "process_bigraph": cell("process-bigraph dep"),
        "requires_python": cell("requires-python"),
        "subclasses": proc_cell,
        "pypi": pypi_cell,
    }


def _per_repo_section(name: str, report: AuditReport) -> str:
    """Render a per-repo markdown section."""
    lines = [f"### {name}", ""]
    counts: dict[str, int] = {}
    for c in report.checks:
        counts[c.status] = counts.get(c.status, 0) + 1
        detail = f" — {c.detail}" if c.detail else ""
        lines.append(f"- **{c.name}**: `{c.status}`{detail}")
    lines.append("")
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    lines.append(f"*Summary: {summary}*")
    if report.fixes:
        lines.append("")
        lines.append("Recommended fixes:")
        for fix in report.fixes:
            lines.append(f"- {fix}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-clone", action="store_true",
                        help="Skip git clone; only run against already-cloned repos in a tmp dir")
    args = parser.parse_args()

    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog not found at {CATALOG_PATH}", file=sys.stderr)
        print("Make sure pbg-template is checked out as a sibling of pbg-superpowers.", file=sys.stderr)
        return 2

    modules = json.loads(CATALOG_PATH.read_text())
    print(f"Loaded {len(modules)} catalog entries from {CATALOG_PATH}")

    today = datetime.date.today().isoformat()
    rows: list[dict[str, str]] = []
    per_repo_sections: list[str] = []

    tmp_root = Path(tempfile.mkdtemp(prefix="pbg-pypi-audit-"))
    print(f"Working directory: {tmp_root}")

    try:
        for entry in modules:
            name = entry["name"]
            source = entry.get("source", "")
            dest = tmp_root / name

            print(f"\n--- {name} ---")
            if not args.no_clone:
                print(f"  Cloning {source} ...")
                ok = _clone_repo(source, dest)
                if not ok:
                    print(f"  WARNING: clone failed; skipping {name}")
                    # Produce a placeholder row.
                    rows.append({
                        "name": name,
                        "pyproject": "FAIL (clone failed)",
                        "bigraph_schema": "N/A",
                        "process_bigraph": "N/A",
                        "requires_python": "N/A",
                        "subclasses": "N/A",
                        "pypi": "N/A",
                    })
                    per_repo_sections.append(
                        f"### {name}\n\n- clone failed from {source}\n\n"
                    )
                    continue

            if not dest.exists():
                print(f"  SKIP: {dest} does not exist (use --no-clone only when repos are pre-cloned)")
                continue

            report = audit_repo(dest, run_install=False)
            rows.append(_summary_row(name, report))
            per_repo_sections.append(_per_repo_section(name, report))

            # Print a quick status line.
            pass_count = sum(1 for c in report.checks if c.status == "PASS")
            warn_count = sum(1 for c in report.checks if c.status == "WARN")
            fail_count = sum(1 for c in report.checks if c.status == "FAIL")
            print(f"  PASS={pass_count} WARN={warn_count} FAIL={fail_count}")

    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    # Build markdown report.
    header_cols = [
        "Repo", "pyproject", "bigraph-schema", "process-bigraph",
        "requires-python", "Process subclasses", "Published on PyPI",
    ]
    row_keys = [
        "name", "pyproject", "bigraph_schema", "process_bigraph",
        "requires_python", "subclasses", "pypi",
    ]

    table_lines = [
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join("---" for _ in header_cols) + " |",
    ]
    for row in rows:
        table_lines.append("| " + " | ".join(row.get(k, "N/A") for k in row_keys) + " |")

    report_md = "\n".join([
        f"# pbg-* PyPI publication audit ({today})",
        "",
        "Generated by `scripts/audit-pbg-catalog.py`. Run periodically to track",
        "progress toward full PyPI publication of the catalog.",
        "",
        f"Catalog: `{CATALOG_PATH}`",
        f"Entries audited: {len(rows)}",
        "",
        "## Summary",
        "",
        *table_lines,
        "",
        "## Per-repo findings",
        "",
        *per_repo_sections,
    ])

    AUDITS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDITS_DIR / f"pbg-pypi-audit-{today}.md"
    out_path.write_text(report_md)
    print(f"\nReport written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
