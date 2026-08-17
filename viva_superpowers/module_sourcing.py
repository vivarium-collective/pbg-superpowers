"""Deterministic model-SOURCING audit — did the loop reuse / compose / build-new
appropriately?

Extends test-sufficiency (:mod:`viva_superpowers.test_audit`) with the sourcing
decision. Given a task's required capability tokens and a catalog of modules (each
with declared capabilities), it grades whether the chosen sourcing was sound:

- reuse an existing module that already covers the task,
- compose several when the task spans their domains,
- build-new ONLY when no catalogued module (or composition) fits.

Pure stdlib + viva_superpowers; the ``/viva-audit-tests`` skill adds the LLM
near-miss judgment for semantic fit the tokens miss. Reuses the capability
subset-match rule (``requires ⊆ capabilities``, same as
``vivarium_workbench.lib.analysis_tools``). See the model-sourcing spec.
"""
from __future__ import annotations

from viva_superpowers.test_contract import TestBuilder, check, value

_BUILD = {"build-new", "build_new", "build", "new"}


def _caps(catalog: dict, module: str) -> set:
    return set((catalog or {}).get(module) or [])


def match_modules(requires, catalog: dict) -> list:
    """Single catalogued modules whose capabilities cover ``requires`` (⊇)."""
    req = set(requires or [])
    return sorted(m for m in (catalog or {}) if req <= _caps(catalog, m))


def _union(chosen, catalog: dict) -> set:
    have = set()
    for m in (chosen or []):
        have |= _caps(catalog, m)
    return have


def covers(requires, chosen, catalog: dict) -> bool:
    """The UNION of the chosen modules' capabilities covers ``requires`` (composition fit)."""
    return set(requires or []) <= _union(chosen, catalog)


def missing_capabilities(requires, chosen, catalog: dict) -> list:
    return sorted(set(requires or []) - _union(chosen, catalog))


def _axis(axis_id, label, ok: bool, severity, detail):
    verdict = "within_tol" if ok else ("mismatch" if severity == "hard" else "drift")
    return check(axis_id, label, None, value(1.0, op=">="), severity=severity,
                 verdict=verdict, detail=detail)


def build_sourcing_report(spec: dict, catalog: dict) -> dict:
    """Grade the study's ``sourcing`` decision against its ``requires`` + the catalog.

    ``spec`` carries ``requires: [tokens]`` and ``sourcing: {decision, modules,
    rationale}``; ``catalog`` is ``{module_name: [capabilities]}``. Returns a
    ``report_card_verdict/v2`` doc with a ``sourcing`` group (axis IDs stable)."""
    spec = spec if isinstance(spec, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    requires = spec.get("requires") or []
    src = spec.get("sourcing") or {}
    decision = str(src.get("decision") or "").lower()
    chosen = src.get("modules") or []
    is_build = decision in _BUILD

    # A pre-existing single-module fit, and whether the whole catalog *could* cover it.
    single_fits = match_modules(requires, catalog)
    catalog_covers = covers(requires, list(catalog.keys()), catalog)

    # source_fit: for reuse/compose the chosen modules must actually cover the task.
    # build-new has no chosen module to grade (the new module is assumed to cover it;
    # its teeth are `reinvention`/`novelty_justified` below), so it is not-applicable → ok.
    fit = True if is_build else covers(requires, chosen, catalog)
    missing = [] if is_build else missing_capabilities(requires, chosen, catalog)
    reinvented = is_build and (bool(single_fits) or catalog_covers)   # built new though a fit exists
    novelty_ok = (not is_build) or (not single_fits and not catalog_covers)
    surveyed = bool(src.get("rationale") or src.get("candidates"))

    tb = TestBuilder(model_ref=str(spec.get("name") or ""))
    tb.add("sourcing", _axis(
        "source_fit", "Sourcing fit (chosen module(s) cover the required capabilities)",
        fit, "hard", {"missing_capabilities": missing, "chosen": chosen, "requires": list(requires)}))
    tb.add("sourcing", _axis(
        "reinvention", "No reinvention (didn't build new where a module already fits)",
        not reinvented, "hard", {"existing_fits": single_fits, "decision": decision}))
    tb.add("sourcing", _axis(
        "novelty_justified", "Novelty justified (build-new only when nothing fits)",
        novelty_ok, "soft", {"decision": decision, "existing_fits": single_fits}))
    tb.add("sourcing", _axis(
        "survey_recorded", "Catalog surveyed (rationale / candidates recorded)",
        surveyed, "soft", {}))
    return tb.build()


def sourcing_gate(report: dict) -> str:
    """pass / warn / fail — hard mismatch fails, any soft issue warns."""
    hard_mismatch = soft = False
    for g in (report.get("groups") or {}).values():
        for ax in g.get("axes") or []:
            v, sev = ax.get("verdict"), ax.get("severity", "hard")
            if v == "mismatch" and sev == "hard":
                hard_mismatch = True
            elif v in ("mismatch", "drift"):
                soft = True
    return "fail" if hard_mismatch else ("warn" if soft else "pass")
