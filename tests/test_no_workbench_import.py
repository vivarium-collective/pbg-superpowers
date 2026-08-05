"""Phase 3 lock-in (plugin side): no viva_superpowers module may import the
vivarium_workbench package.

This is the invariant the whole rewire-first re-architecture protects. The
plugin's core (study_audit and its closure) is imported by v2ecoli / sms-ecoli
and exercised by their CI ``study_audit --gate`` step, which runs with
``--no-install-package vivarium-workbench``. If any plugin module imported the
workbench, that gate would break — and, more broadly, the dependency direction
must stay one-way (workbench → plugin), or the Phase-0 import cycle returns.

Compute that needs the workbench belongs IN the workbench
(vivarium_workbench/lib/), reached via its HTTP API or a ``vwb`` CLI verb from a
skill — never by the plugin importing back into it.
"""
from __future__ import annotations

import ast
import pathlib


def _modules_importing_workbench() -> dict[str, list[int]]:
    """Map each viva_superpowers file -> line numbers importing vivarium_workbench."""
    root = pathlib.Path(__file__).resolve().parents[1] / "viva_superpowers"
    offenders: dict[str, list[int]] = {}
    for f in root.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        lines: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "vivarium_workbench"
                or node.module.startswith("vivarium_workbench.")
            ):
                lines.append(node.lineno)
            elif isinstance(node, ast.Import):
                if any(a.name == "vivarium_workbench" or a.name.startswith("vivarium_workbench.")
                       for a in node.names):
                    lines.append(node.lineno)
        if lines:
            offenders[str(f.relative_to(root.parent))] = sorted(lines)
    return offenders


def test_plugin_never_imports_the_workbench():
    offenders = _modules_importing_workbench()
    assert not offenders, (
        "viva_superpowers modules import vivarium_workbench (breaks the audit-gate "
        "invariant + reintroduces the plugin→workbench cycle):\n"
        + "\n".join(f"  - {f}: lines {lines}" for f, lines in offenders.items())
        + "\n\nMove the compute into the workbench and reach it via the API / a vwb verb."
    )
