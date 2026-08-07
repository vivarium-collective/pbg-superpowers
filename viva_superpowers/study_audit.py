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
import contextlib
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

    def hard_failures(self, allowlist=None) -> list:
        """Hard-tier failures as ``(slug, CheckResult)``.

        When ``allowlist`` (a set of ``"slug:check-name"`` keys) is given,
        failures whose key is listed are EXCLUDED — they are known-accepted
        debt tracked elsewhere. The gate fails only on what remains.
        """
        allow = allowlist or set()
        out = []
        for audit in list(self.studies) + list(self.investigations):
            for c in audit.checks:
                if c.tier == HARD and c.status == FAIL:
                    if f"{audit.slug}:{c.name}" in allow:
                        continue
                    out.append((audit.slug, c))
        return out

    def hard_failure_keys(self) -> set:
        """All hard-failure ``"slug:check-name"`` keys (ignoring any allowlist)."""
        keys = set()
        for audit in list(self.studies) + list(self.investigations):
            for c in audit.checks:
                if c.tier == HARD and c.status == FAIL:
                    keys.add(f"{audit.slug}:{c.name}")
        return keys

    def stale_allowlist_entries(self, allowlist) -> set:
        """Allowlist keys that no longer match any hard failure.

        These are the ratchet signal: an entry parked as known-debt whose
        study has since been fixed must be REMOVED from the allowlist, so the
        gate flags it (the allowlist may only shrink, never silently rot).
        """
        return set(allowlist or set()) - self.hard_failure_keys()

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

def _default_registry(extra_packages=None) -> tuple[set[str], dict]:
    """Best-effort (known_composites, generator_params) from installed generators.

    ``known_composites`` is the set of registered generator names/ids;
    ``generator_params`` maps each name to the set of its declared parameter
    keys. Wrapped in try/except so a discovery failure yields empty defaults
    rather than crashing the audit (tests inject fakes and never hit this).
    """
    try:
        gens = _discover_generators(extra_packages=extra_packages)
    except Exception:  # noqa: BLE001 — discovery is best-effort
        return set(), {}
    known = set(gens.keys())
    params = {sid: set((getattr(entry, "parameters", None) or {}).keys())
              for sid, entry in gens.items()}
    return known, params


def _discover_generators(extra_packages=None):
    """Thin, monkeypatchable indirection over the real generator discovery.

    Imported lazily so ``study_audit`` never hard-depends on process-bigraph at
    import time, and so unit tests can patch this symbol without importing
    ``composite_generator`` (whose import can fail in a minimal test venv)."""
    from viva_superpowers.composite_generator import discover_generators

    return discover_generators(extra_packages=extra_packages)


def _workspace_packages(wp: WorkspacePaths) -> list[str]:
    """Best-effort import names for the workspace's own composite generators.

    The workspace Python package (e.g. ``pbg_v2ecoli`` / ``v2ecoli``) registers
    its ``@composite_generator`` decorators only when imported, so include it and
    its ``.composites`` subpackage in the discovery import set."""
    out: list[str] = []
    try:
        pkg = wp.package
        name = pkg.name
        # Migration window: wp.package now computes the canonical viva_<slug>,
        # but a not-yet-migrated workspace may still ship pbg_<slug>/ on disk.
        # Prefer the directory that actually exists so discovery imports the
        # real package (an explicit package_path override is left untouched).
        if name.startswith("viva_") and not pkg.is_dir():
            legacy = wp.root / ("pbg_" + name[len("viva_"):])
            if legacy.is_dir():
                name = legacy.name
        if name:
            out.append(name)
            out.append(f"{name}.composites")
    except Exception:  # noqa: BLE001
        pass
    return out


def audit_workspace(
    ws_root,
    *,
    known_composites: set | None = None,
    generator_params: dict | None = None,
    extra_packages: list | None = None,
) -> AuditReport:
    """Audit the workspace at ``ws_root`` against the L0-L5 contract.

    ``known_composites`` / ``generator_params`` default to the installed
    generator registry (``discover_generators``); tests inject fakes so no real
    workspace package is required. ``extra_packages`` are additional package
    names to import so their ``@composite_generator`` decorators fire before the
    registry is read (a workspace's own composites live in its package, not in an
    installed top-level dist). The workspace's own package + ``.composites`` are
    added automatically (best-effort).
    """
    # Resolve up-front: WorkspacePaths.load resolves internally, so
    # _nested_study_files returns absolute paths — relative_to needs an absolute
    # base or it raises ValueError when ws_root is ".".
    ws_root = Path(ws_root).resolve()
    wp = WorkspacePaths.load(ws_root)

    if known_composites is None or generator_params is None:
        # Best-effort: make the workspace importable and include its own
        # composites package so workspace-local composites resolve.
        extra = list(extra_packages or [])
        try:
            for p in (str(ws_root), str(ws_root.parent)):
                if p not in sys.path:
                    sys.path.insert(0, p)
            extra += _workspace_packages(wp)
        except Exception:  # noqa: BLE001 — best-effort
            pass
        default_known, default_params = _default_registry(extra_packages=extra)
        if known_composites is None:
            known_composites = default_known
        if generator_params is None:
            generator_params = default_params

    report = AuditReport(studies=[], investigations=[])

    # Every study slug known anywhere in the workspace (flat + nested), used to
    # resolve inputs[].from producer edges.
    known_slugs = {d.name for d in wp.iter_study_dirs()}

    # Workspace-level L0: no study.yaml may live under investigations/. Emitted
    # once (only when a nested study exists, i.e. the fail case). NOTE: nested
    # investigations/**/study.yaml is a DELIBERATE L0 violation — the
    # reproducibility contract mandates the flat studies/ layout with
    # investigations referencing members via `members:` (Phase 1 migrated
    # v2ecoli to it). This intentionally diverges from
    # WorkspacePaths.iter_study_dirs' general nested-study support; do not
    # "fix" it to accept nested studies.
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
                # Safety net: totality is guaranteed even for unforeseen shapes.
                try:
                    _audit_study(audit, sdir, wp, known_slugs,
                                 known_composites, generator_params)
                except Exception as exc:  # noqa: BLE001
                    audit.checks.append(CheckResult(
                        "L0", "audit-error", FAIL, HARD, f"audit crashed: {exc}"))
                report.studies.append(audit)

    inv_dir = wp.investigations
    if inv_dir.is_dir():
        for idir in sorted(p for p in inv_dir.iterdir() if p.is_dir()):
            if (idir / "investigation.yaml").is_file():
                audit = StudyAudit(slug=idir.name, checks=[])
                try:
                    _audit_investigation(audit, idir, wp, known_slugs)
                except Exception as exc:  # noqa: BLE001
                    audit.checks.append(CheckResult(
                        "L0", "audit-error", FAIL, HARD, f"audit crashed: {exc}"))
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
    variants = conditions.get("variants")
    for v in (variants if isinstance(variants, list) else []):
        if isinstance(v, dict):
            yield (v.get("name", "variant"), v)


def _composite_alias_set(known_composites: set) -> set:
    """Expand registry ids into the forms a study.yaml may reference.

    A registered generator id is ``<dotted_module>.<name>``. In a workspace whose
    composite modules are named after the composite (v2ecoli style), the id
    duplicates its tail — ``v2ecoli.composites.parca.parca`` — while studies
    reference the collapsed module form ``v2ecoli.composites.parca`` or the bare
    name ``parca``. Expand every known id into: the full id, its bare last
    segment, and (only when the tail is duplicated) the collapsed module form."""
    out: set = set()
    for k in known_composites:
        if not isinstance(k, str):
            continue
        out.add(k)
        if "." in k:
            module, _, last = k.rpartition(".")
            out.add(last)  # bare composite name
            if module.rpartition(".")[2] == last:  # duplicated tail -> collapse
                out.add(module)
    return out


def _composite_resolvable(name: str, known_composites: set, wp: WorkspacePaths) -> bool:
    if not name:
        return False
    if name in _composite_alias_set(known_composites):
        return True
    if any(name == s or name.endswith("." + s) for s in _RESOLVABLE_SUFFIXES):
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

    # The L1 model checks reason over the CANONICALIZED model: a variant that
    # omits `composite` legitimately inherits the baseline's, so resolvability /
    # param validation must see the effective (post-canonicalization) model, not
    # the raw one.
    try:
        canon = copy.deepcopy(spec)
        canonicalize_models(canon)
    except Exception:  # noqa: BLE001
        canon = spec

    # --- L1 composite-resolves ---------------------------------------------
    unresolved = []
    for label, model in _iter_models(canon):
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
    for label, model in _iter_models(canon):
        comp = model.get("composite") if isinstance(model, dict) else None
        # Skip when the composite is unresolved (already caught) or we have no
        # declared parameter set for it. NOTE: file-discovered *.composite.yaml
        # composites resolve (composite-resolves passes) but have no
        # generator_params entry, so their params are intentionally NOT validated
        # here — an accepted coverage gap.
        if comp not in generator_params:
            continue
        allowed = set(generator_params.get(comp) or set()) | {"n_steps"}
        # Read both the canonical `params` and the legacy `parameter_overrides`
        # key (canonicalize_models only renames it for variants, never baseline),
        # so a legacy key can't smuggle unknown params past validation.
        declared: set = set()
        for key in ("params", "parameter_overrides"):
            block = model.get(key) if isinstance(model, dict) else None
            if isinstance(block, dict):
                declared |= set(block.keys())
        extra = declared - allowed
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

    # --- L2 node-keyable (soft) --------------------------------------------
    # Content-addressable iff the composite resolves AND every inputs[].from
    # producer resolves — then an artifact_id could be formed. Reuse L1 results.
    composite_ok = _status_of(audit, "composite-resolves") == PASS
    inputs_ok = _status_of(audit, "inputs-from-resolves") == PASS
    if composite_ok and inputs_ok:
        audit.checks.append(CheckResult("L2", "node-keyable", PASS, SOFT))
    else:
        reason = []
        if not composite_ok:
            reason.append("composite unresolved")
        if not inputs_ok:
            reason.append("input producer unresolved")
        audit.checks.append(CheckResult(
            "L2", "node-keyable", WARN, SOFT,
            "not content-addressable: " + ", ".join(reason)))

    # --- L3 outputs-present (soft) -----------------------------------------
    _check_outputs_present(audit, sdir, spec)

    # --- L4 report-card-verdict (soft) -------------------------------------
    _check_report_card_verdict(audit, sdir)


def _status_of(audit, name) -> str | None:
    for c in audit.checks:
        if c.name == name:
            return c.status
    return None


def _declares_outputs(spec: dict) -> bool:
    for key in ("visualizations", "report_cards", "observables"):
        val = spec.get(key)
        if isinstance(val, (list, dict)) and len(val) > 0:
            return True
    return False


def _report_card_dir(sdir: Path) -> Path:
    return sdir / "viz" / "report_card"


def _check_outputs_present(audit, sdir: Path, spec: dict) -> None:
    if not _declares_outputs(spec):
        audit.checks.append(CheckResult("L3", "outputs-present", PASS, SOFT))
        return
    viz = sdir / "viz"
    html = list(viz.glob("**/*.html")) if viz.is_dir() else []
    rc = _report_card_dir(sdir)
    cards = list(rc.glob("*.html")) if rc.is_dir() else []
    if html or cards:
        audit.checks.append(CheckResult("L3", "outputs-present", PASS, SOFT))
    else:
        audit.checks.append(CheckResult(
            "L3", "outputs-present", WARN, SOFT,
            "declares observables/report cards but viz/ has no rendered output"))


def _check_report_card_verdict(audit, sdir: Path) -> None:
    rc = _report_card_dir(sdir)
    cards = sorted(rc.glob("*.html")) if rc.is_dir() else []
    if not cards:
        audit.checks.append(CheckResult("L4", "report-card-verdict", PASS, SOFT))
        return
    missing = []
    for card in cards:
        verdict = card.with_name(card.name[: -len(".html")] + ".verdict.json")
        ok = False
        if verdict.is_file():
            try:
                data = json.loads(verdict.read_text(encoding="utf-8"))
                ok = isinstance(data, dict) and bool(data.get("overall"))
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            missing.append(card.name)
    if missing:
        audit.checks.append(CheckResult(
            "L4", "report-card-verdict", WARN, SOFT,
            "cards without a computed verdict: " + ", ".join(missing)))
    else:
        audit.checks.append(CheckResult("L4", "report-card-verdict", PASS, SOFT))


def _dangling_inputs(spec: dict, known_slugs: set) -> set:
    out = set()
    inputs = spec.get("inputs")
    for e in (inputs if isinstance(inputs, list) else []):
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

    # A genuinely non-canonical on-disk form: top-level baseline/variants that
    # needed moving into conditions, or a case flagged for a human. NOTE:
    # composite inheritance (a variant omitting `composite`) and the
    # model_settings auto-add are accepted no-op-ish normalizations — they do
    # NOT make a study non-canonical, so `inherited_composites` is deliberately
    # not a failure trigger here.
    bad_flags = {"multi_baseline_needs_human", "both_dropped_toplevel",
                 "both_dropped_toplevel_variants"}
    flags = set(report.get("flags") or [])
    if (flags & bad_flags) or ("baseline" in spec) or ("variants" in spec):
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
        return
    if "studies" in spec and "members" not in spec:
        audit.checks.append(CheckResult(
            "L0", "investigation-members-only", WARN, HARD,
            "carries legacy `studies:` key; rename to `members:`"))
    else:
        audit.checks.append(CheckResult("L0", "investigation-members-only", PASS, HARD))

    # --- L5 ordering over the members inputs[].from DAG --------------------
    _audit_investigation_dag(audit, spec, wp, known_slugs)


def _member_slugs(spec: dict) -> list[str]:
    """Normalize members entries: bare slugs or {study|slug|name: ...} dicts.
    Falls back to the legacy `studies:` key."""
    entries = spec.get("members")
    if not isinstance(entries, list):
        entries = spec.get("studies") or []
    if not isinstance(entries, list):
        return []
    out = []
    for e in entries:
        if isinstance(e, str):
            out.append(e)
        elif isinstance(e, dict):
            slug = e.get("study") or e.get("slug") or e.get("name")
            if slug:
                out.append(str(slug))
    return out


def _study_inputs_from(wp: WorkspacePaths, slug: str) -> list[str]:
    """The inputs[].from producer slugs declared by study ``slug`` (best-effort)."""
    try:
        sdir = wp.study_dir(slug)
        spec = study_io.load_yaml(sdir / "study.yaml")
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(spec, dict):
        return []
    out = []
    inputs = spec.get("inputs")
    for e in (inputs if isinstance(inputs, list) else []):
        if isinstance(e, dict) and e.get("from"):
            out.append(str(e["from"]))
    return out


def _build_dag_graph(spec: dict, wp: WorkspacePaths) -> dict[str, set]:
    """Consumer -> {producer slugs} edges over an investigation's `members`
    (via each member's `inputs[].from`). Shared graph-construction for both
    the L5 audit (:func:`_audit_investigation_dag`) and the public rerun-order
    helper (:func:`investigation_execution_order`) so the DAG is built
    exactly once, the same way, in both places."""
    members = _member_slugs(spec)
    graph: dict[str, set] = {}
    for m in members:
        graph.setdefault(m, set())
        for producer in _study_inputs_from(wp, m):
            graph.setdefault(producer, set())
            graph[m].add(producer)
    return graph


def investigation_execution_order(wp: WorkspacePaths, inv_spec: dict) -> list[str]:
    """Topological execution order of an investigation's member studies over
    the `inputs.from` DAG (producers before consumers).

    Reuses the same graph-building `_audit_investigation_dag` does
    (`_member_slugs` + `_study_inputs_from`) plus `graphlib`'s toposort.
    Best-effort: a cycle (`graphlib.CycleError`) degrades to the declared
    member order rather than raising — a caller like an investigation rerun
    must never fail a batch just because the DAG is malformed.

    The returned list is restricted to `inv_spec`'s own members: a member's
    `inputs[].from` may name a producer that is itself not a member (an
    external/upstream study, or a dangling reference) — that producer still
    shapes the ordering among members but is never itself returned, so a
    caller iterating this list only ever launches actual members.
    """
    members = _member_slugs(inv_spec)
    graph = _build_dag_graph(inv_spec, wp)
    try:
        full_order = list(graphlib.TopologicalSorter(graph).static_order())
    except graphlib.CycleError:
        return list(members)
    member_set = set(members)
    return [slug for slug in full_order if slug in member_set]


def _audit_investigation_dag(audit, spec, wp, known_slugs):
    members = _member_slugs(spec)
    graph = _build_dag_graph(spec, wp)
    # Dangling: any producer named by a member's inputs[].from that isn't a
    # known study slug in this workspace.
    dangling = set()
    for m in members:
        for producer in graph.get(m, ()):
            if producer not in known_slugs:
                dangling.add(producer)

    # --- no-dangling-edges (hard) ------------------------------------------
    if dangling:
        audit.checks.append(CheckResult(
            "L5", "no-dangling-edges", FAIL, HARD,
            "member inputs[].from name non-existent studies: "
            + ", ".join(sorted(dangling))))
    else:
        audit.checks.append(CheckResult("L5", "no-dangling-edges", PASS, HARD))

    # --- dag-acyclic (hard) + topological-executable (soft) ----------------
    try:
        ts = graphlib.TopologicalSorter(graph)
        order = list(ts.static_order())
        audit.checks.append(CheckResult("L5", "dag-acyclic", PASS, HARD))
        audit.checks.append(CheckResult(
            "L5", "topological-executable", PASS, SOFT,
            "order: " + " -> ".join(order)))
    except graphlib.CycleError as exc:
        audit.checks.append(CheckResult(
            "L5", "dag-acyclic", FAIL, HARD, f"cycle in inputs[].from DAG: {exc.args}"))
        audit.checks.append(CheckResult(
            "L5", "topological-executable", WARN, SOFT,
            "execution order not derivable (DAG invalid)"))


_GLYPH = {PASS: "✓", WARN: "⚠", FAIL: "✗"}  # ✓ ⚠ ✗


def render_report(report: AuditReport) -> str:
    """Human-readable table: per audit, one line per check, then a summary."""
    lines: list[str] = []
    sections = [("STUDY", report.studies), ("INVESTIGATION", report.investigations)]
    for kind, audits in sections:
        for audit in audits:
            lines.append(f"{kind} {audit.slug}  [{audit.worst()}]")
            for c in audit.checks:
                glyph = _GLYPH.get(c.status, "?")
                row = f"  {glyph} {c.level} {c.name} ({c.tier})"
                if c.detail:
                    row += f" — {c.detail}"
                lines.append(row)
    hard = report.hard_failures()
    lines.append("")
    lines.append(
        f"summary: {len(report.studies)} studies, "
        f"{len(report.investigations)} investigations, "
        f"{len(hard)} hard failure(s)"
    )
    return "\n".join(lines)


def load_allowlist(path) -> set:
    """Parse a known-accepted-failures file into a set of ``"slug:check"`` keys.

    One key per line; ``#`` starts a comment; blank lines ignored. A missing
    file is an empty allowlist (not an error) so `--gate` degrades safely.
    """
    p = Path(path)
    if not p.is_file():
        return set()
    entries = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="viva-study-audit")
    ap.add_argument("--workspace", default=".", help="workspace root (default: .)")
    ap.add_argument("--json", action="store_true",
                    help="emit the report as JSON instead of a table")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if any hard-tier check fails (for CI)")
    ap.add_argument("--package", action="append", dest="package", default=None,
                    metavar="PKG",
                    help="extra package to import for composite discovery "
                         "(repeatable), e.g. --package v2ecoli.composites")
    ap.add_argument("--allowlist", default=None, metavar="FILE",
                    help="file of known-accepted 'slug:check' hard failures "
                         "(one per line, # comments). --gate ignores these but "
                         "STILL FAILS on any stale entry that no longer occurs "
                         "(the allowlist may only shrink — a ratchet).")
    args = ap.parse_args(argv)

    if args.json:
        # Package-import side effects print to stdout during discovery; keep the
        # real stdout pristine so the emitted JSON always parses. Redirect that
        # noise to stderr while the report is built.
        with contextlib.redirect_stdout(sys.stderr):
            report = audit_workspace(args.workspace, extra_packages=args.package)
        print(json.dumps(report.as_dict()))
    else:
        report = audit_workspace(args.workspace, extra_packages=args.package)
        print(render_report(report))

    if not args.gate:
        return 0

    allow = load_allowlist(args.allowlist) if args.allowlist else set()
    new_fails = report.hard_failures(allowlist=allow)
    stale = report.stale_allowlist_entries(allow)
    if allow:
        known = len(allow) - len(stale)
        print(f"[gate] allowlist: {known} known-accepted failure(s) suppressed",
              file=sys.stderr)
    for slug, c in new_fails:
        print(f"[gate] FAIL {slug}:{c.name} — {c.detail}", file=sys.stderr)
    for key in sorted(stale):
        print(f"[gate] STALE allowlist entry '{key}' no longer fails — "
              f"remove it from the allowlist (ratchet)", file=sys.stderr)
    return 1 if (new_fails or stale) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
