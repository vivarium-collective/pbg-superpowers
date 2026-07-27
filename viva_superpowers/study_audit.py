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

    # Every study slug known anywhere in the workspace (flat + nested), used to
    # resolve inputs[].from producer edges.
    known_slugs = {d.name for d in wp.iter_study_dirs()}

    # Workspace-level L0: no study.yaml may live under investigations/. Emitted
    # once (only when a nested study exists, i.e. the fail case).
    nested = _nested_study_files(wp)
    if nested:
        wa = StudyAudit(slug=ws_root.name or "<workspace>", checks=[])
        rels = ", ".join(sorted(str(p.relative_to(ws_root)) for p in nested))
        wa.checks.append(CheckResult(
            "L0", "no-nested-study", FAIL, HARD,
            f"study.yaml found under investigations/: {rels}"))
        report.studies.append(wa)

    # Enumerate top-level studies/<slug>/study.yaml only. Nested studies under
    # investigations/ are a structural violation caught by `no-nested-study`.
    studies_dir = wp.studies
    if studies_dir.is_dir():
        for sdir in sorted(p for p in studies_dir.iterdir() if p.is_dir()):
            if (sdir / "study.yaml").is_file():
                audit = StudyAudit(slug=sdir.name, checks=[])
                _audit_study(audit, sdir, wp, known_slugs,
                             known_composites, generator_params)
                report.studies.append(audit)

    inv_dir = wp.investigations
    if inv_dir.is_dir():
        for idir in sorted(p for p in inv_dir.iterdir() if p.is_dir()):
            if (idir / "investigation.yaml").is_file():
                audit = StudyAudit(slug=idir.name, checks=[])
                _audit_investigation(audit, idir, wp, known_slugs)
                report.investigations.append(audit)

    return report


# ---------------------------------------------------------------------------
# Per-study checks
# ---------------------------------------------------------------------------

def _nested_study_files(wp: WorkspacePaths) -> list:
    inv_dir = wp.investigations
    if not inv_dir.is_dir():
        return []
    return sorted(inv_dir.glob("**/study.yaml"))


def _iter_models(spec: dict):
    """Yield (label, model_dict) for the baseline + each variant, canonical form."""
    conditions = spec.get("conditions")
    if not isinstance(conditions, dict):
        return
    baseline = conditions.get("baseline")
    if isinstance(baseline, dict):
        yield ("baseline", baseline)
    for v in (conditions.get("variants") or []):
        if isinstance(v, dict):
            yield (v.get("name", "variant"), v)


def _composite_resolvable(name: str, known_composites: set, wp: WorkspacePaths) -> bool:
    if not name:
        return False
    if name in known_composites:
        return True
    if any(name == s or name.endswith("." + s) or name.endswith(s)
           for s in _RESOLVABLE_SUFFIXES):
        return True
    # file-discovered *.composite.yaml whose stem matches the composite name
    comp_dir = wp.composites
    if comp_dir.is_dir():
        tail = name.rsplit(".", 1)[-1]
        for pat in ("*.composite.yaml", "*.composite.yml", "*.composite.json"):
            for f in comp_dir.glob(pat):
                stem = f.name
                for suffix in (".composite.yaml", ".composite.yml", ".composite.json"):
                    if stem.endswith(suffix):
                        stem = stem[: -len(suffix)]
                        break
                if stem in (name, tail):
                    return True
    return False


def _audit_study(audit, sdir, wp, known_slugs, known_composites, generator_params):
    """Append L0/L1 (and later L2/L3/L4) checks for one study. Total: any error
    becomes a single L0 fail rather than a traceback."""
    try:
        spec = study_io.load_yaml(sdir / "study.yaml")
        if not isinstance(spec, dict):
            raise ValueError("top-level YAML is not a mapping")
    except Exception as exc:  # noqa: BLE001
        audit.checks.append(CheckResult(
            "L0", "readable", FAIL, HARD, f"unreadable study.yaml: {exc}"))
        return

    # --- L0 slug-matches-dir ------------------------------------------------
    declared = spec.get("name") or spec.get("slug")
    if declared is not None and str(declared) != sdir.name:
        audit.checks.append(CheckResult(
            "L0", "slug-matches-dir", FAIL, HARD,
            f"study.yaml name/slug {declared!r} != dir {sdir.name!r}"))
    else:
        audit.checks.append(CheckResult("L0", "slug-matches-dir", PASS, HARD))

    # --- L0 canonical-model-schema -----------------------------------------
    _check_model_schema(audit, spec)

    # --- L1 composite-resolves ---------------------------------------------
    unresolved = []
    for label, model in _iter_models(spec):
        comp = model.get("composite") if isinstance(model, dict) else None
        if not _composite_resolvable(comp, known_composites, wp):
            unresolved.append(f"{label}:{comp!r}")
    if unresolved:
        audit.checks.append(CheckResult(
            "L1", "composite-resolves", FAIL, HARD,
            "unresolved composite(s): " + ", ".join(unresolved)))
    else:
        audit.checks.append(CheckResult("L1", "composite-resolves", PASS, HARD))

    # --- L1 params-are-generator-accepted ----------------------------------
    bad_params = []
    for label, model in _iter_models(spec):
        comp = model.get("composite") if isinstance(model, dict) else None
        # skip when the composite is unresolved (already caught) or we have no
        # declared parameter set for it.
        if comp not in generator_params:
            continue
        allowed = set(generator_params.get(comp) or set()) | {"n_steps"}
        params = model.get("params") if isinstance(model, dict) else None
        if isinstance(params, dict):
            extra = set(params.keys()) - allowed
            if extra:
                bad_params.append(f"{label}: {sorted(extra)} not in {sorted(allowed)}")
    if bad_params:
        audit.checks.append(CheckResult(
            "L1", "params-are-generator-accepted", FAIL, HARD,
            "; ".join(bad_params)))
    else:
        audit.checks.append(CheckResult(
            "L1", "params-are-generator-accepted", PASS, HARD))

    # --- L1 inputs-from-resolves -------------------------------------------
    dangling = _dangling_inputs(spec, known_slugs)
    if dangling:
        audit.checks.append(CheckResult(
            "L1", "inputs-from-resolves", FAIL, HARD,
            "dangling inputs[].from: " + ", ".join(sorted(dangling))))
    else:
        audit.checks.append(CheckResult("L1", "inputs-from-resolves", PASS, HARD))


def _dangling_inputs(spec: dict, known_slugs: set) -> set:
    out = set()
    for e in (spec.get("inputs") or []):
        if isinstance(e, dict):
            frm = e.get("from")
            if frm and str(frm) not in known_slugs:
                out.add(str(frm))
    return out


def _check_model_schema(audit, spec: dict) -> None:
    """L0 canonical-model-schema: conditions.baseline has a composite and every
    variant is a mapping with a composite; canonicalization is a no-op."""
    try:
        probe = copy.deepcopy(spec)
        report = canonicalize_models(probe)
    except Exception as exc:  # noqa: BLE001
        audit.checks.append(CheckResult(
            "L0", "canonical-model-schema", FAIL, HARD,
            f"canonicalization error: {exc}"))
        return

    # A non-no-op structural change (top-level baseline/variants that needed
    # moving, or a case requiring a human) means the on-disk form isn't canonical.
    bad_flags = {"multi_baseline_needs_human", "both_dropped_toplevel",
                 "both_dropped_toplevel_variants"}
    flags = set(report.get("flags") or [])
    if report.get("inherited_composites") or (flags & bad_flags) \
            or ("baseline" in spec) or ("variants" in spec):
        audit.checks.append(CheckResult(
            "L0", "canonical-model-schema", FAIL, HARD,
            f"non-canonical model schema (flags={sorted(flags)})"))
        return

    conditions = probe.get("conditions")
    baseline = conditions.get("baseline") if isinstance(conditions, dict) else None
    if not isinstance(baseline, dict) or not baseline.get("composite"):
        audit.checks.append(CheckResult(
            "L0", "canonical-model-schema", FAIL, HARD,
            "conditions.baseline with a composite is required"))
        return
    for v in (conditions.get("variants") or []):
        if not isinstance(v, dict) or not v.get("composite"):
            audit.checks.append(CheckResult(
                "L0", "canonical-model-schema", FAIL, HARD,
                "every variant must be a mapping with a composite"))
            return
    audit.checks.append(CheckResult("L0", "canonical-model-schema", PASS, HARD))


# ---------------------------------------------------------------------------
# Per-investigation checks
# ---------------------------------------------------------------------------

def _audit_investigation(audit, idir, wp, known_slugs):
    try:
        spec = study_io.load_yaml(idir / "investigation.yaml")
    except Exception as exc:  # noqa: BLE001
        audit.checks.append(CheckResult(
            "L0", "investigation-members-only", FAIL, HARD,
            f"unreadable investigation.yaml: {exc}"))
        return

    # --- L0 investigation-members-only -------------------------------------
    if not isinstance(spec, dict):
        audit.checks.append(CheckResult(
            "L0", "investigation-members-only", FAIL, HARD,
            "top-level YAML is not a mapping"))
    elif "studies" in spec and "members" not in spec:
        audit.checks.append(CheckResult(
            "L0", "investigation-members-only", WARN, HARD,
            "carries legacy `studies:` key; rename to `members:`"))
    else:
        audit.checks.append(CheckResult("L0", "investigation-members-only", PASS, HARD))


def main(argv=None) -> int:  # pragma: no cover — implemented in Task 4
    raise NotImplementedError


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
