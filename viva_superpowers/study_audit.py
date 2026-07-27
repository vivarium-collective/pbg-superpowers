"""L0-L5 study-reproducibility audit.

A self-contained, workbench-free evaluator of a workspace against the L0-L5
reproducibility contract. Returns a structured, JSON-serializable
:class:`AuditReport` and provides a CLI with a ``--gate`` mode (non-zero exit on
any HARD-tier failure) for CI.

This module MUST NOT import ``vivarium_workbench``: it ships in the package
v2ecoli CI imports, so a workbench dependency here would invert the dependency
graph and break that CI. It reuses only ``viva_superpowers`` internals + stdlib.

Tiers (design doc §3):
  * L0 Structure + L1 Resolvability + L5 graph-validity (acyclic / no-dangling)
    are ``tier="hard"``.
  * L2 Executability, L3 Outputs, L4 Evidence, L5 topological-executable are
    ``tier="soft"`` (warn / ratchet).

``--gate`` exits non-zero iff any ``status=="fail"`` check with ``tier=="hard"``
exists. Every check is best-effort and total: a malformed study.yaml becomes a
single L0 ``fail`` CheckResult, never a traceback that aborts the audit.
"""
from __future__ import annotations

import argparse
import copy
import graphlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from viva_superpowers import study_io
from viva_superpowers.study_canonicalize import canonicalize_models
from viva_superpowers.workspace_paths import WorkspacePaths

HARD = "hard"
SOFT = "soft"
PASS = "pass"
WARN = "warn"
FAIL = "fail"

# Composite names that resolve without a registered generator: file-discovered
# specs (their study.yaml `composite` matches a `*.composite.yaml` stem) and the
# millard2017 metabolism spec. Mirrors the #393 resolvability skip list.
_RESOLVABLE_SUFFIXES = ("millard2017_metabolism",)


@dataclass(frozen=True)
class CheckResult:
    level: str        # "L0".."L5"
    name: str         # short slug, e.g. "no-nested-study", "composite-resolves"
    status: str       # "pass" | "warn" | "fail"
    tier: str         # "hard" | "soft"
    detail: str = ""  # human reason; "" when pass

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class StudyAudit:
    slug: str
    checks: list = field(default_factory=list)

    def worst(self) -> str:
        statuses = {c.status for c in self.checks}
        if FAIL in statuses:
            return FAIL
        if WARN in statuses:
            return WARN
        return PASS

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "worst": self.worst(),
            "checks": [c.as_dict() for c in self.checks],
        }


@dataclass
class AuditReport:
    studies: list = field(default_factory=list)
    investigations: list = field(default_factory=list)

    def hard_failures(self) -> list:
        out = []
        for audit in list(self.studies) + list(self.investigations):
            for c in audit.checks:
                if c.tier == HARD and c.status == FAIL:
                    out.append((audit.slug, c))
        return out

    def as_dict(self) -> dict:
        return {
            "studies": [a.as_dict() for a in self.studies],
            "investigations": [a.as_dict() for a in self.investigations],
            "summary": {
                "n_studies": len(self.studies),
                "n_investigations": len(self.investigations),
                "hard_failures": len(self.hard_failures()),
            },
        }


# ---------------------------------------------------------------------------
# Registry-backed defaults (injectable for testability)
# ---------------------------------------------------------------------------

def _default_registry() -> tuple[set[str], dict]:
    """Best-effort (known_composites, generator_params) from installed generators.

    ``known_composites`` is the set of registered generator names/ids;
    ``generator_params`` maps each name to the set of its declared parameter
    keys. Wrapped in try/except so a discovery failure yields empty defaults
    rather than crashing the audit (tests inject fakes and never hit this).
    """
    try:
        from viva_superpowers.composite_generator import discover_generators

        gens = discover_generators()
    except Exception:  # noqa: BLE001 — discovery is best-effort
        return set(), {}
    known = set(gens.keys())
    params = {sid: set((entry.parameters or {}).keys()) for sid, entry in gens.items()}
    return known, params


def audit_workspace(
    ws_root,
    *,
    known_composites: set | None = None,
    generator_params: dict | None = None,
) -> AuditReport:
    """Audit the workspace at ``ws_root`` against the L0-L5 contract.

    ``known_composites`` / ``generator_params`` default to the installed
    generator registry (``discover_generators``); tests inject fakes so no real
    workspace package is required.
    """
    if known_composites is None or generator_params is None:
        default_known, default_params = _default_registry()
        if known_composites is None:
            known_composites = default_known
        if generator_params is None:
            generator_params = default_params

    ws_root = Path(ws_root)
    wp = WorkspacePaths.load(ws_root)

    report = AuditReport(studies=[], investigations=[])

    # Enumerate top-level studies/<slug>/study.yaml only. Nested studies under
    # investigations/ are a structural violation caught by `no-nested-study`.
    studies_dir = wp.studies
    if studies_dir.is_dir():
        for sdir in sorted(p for p in studies_dir.iterdir() if p.is_dir()):
            if (sdir / "study.yaml").is_file():
                report.studies.append(StudyAudit(slug=sdir.name, checks=[]))

    inv_dir = wp.investigations
    if inv_dir.is_dir():
        for idir in sorted(p for p in inv_dir.iterdir() if p.is_dir()):
            if (idir / "investigation.yaml").is_file():
                report.investigations.append(StudyAudit(slug=idir.name, checks=[]))

    return report


def main(argv=None) -> int:  # pragma: no cover — implemented in Task 4
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
