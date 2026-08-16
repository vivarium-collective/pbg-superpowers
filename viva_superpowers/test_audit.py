"""Deterministic test-sufficiency checks for /viva-audit-tests.

Adds the sufficiency dimensions rigor.py doesn't cover — discrimination
(trivially-wide bands), redundancy (tests on the same observable), objective
coverage (mechanisms with no test), and a discriminating control. Pure; the
skill supplies the AI reasoning (null-model plausibility, mechanism semantics)
and assembles the graded report. See the loop spec §5.
"""
from __future__ import annotations

import re

from viva_superpowers import rigor
from viva_superpowers.test_contract import TestBuilder, check, value
from viva_superpowers import band_provenance


def _tests(spec: dict) -> list:
    return [t for t in (spec.get("behavior_tests") or spec.get("expected_behavior") or [])
            if isinstance(t, dict)]


def _measure_path(t: dict) -> str:
    m = t.get("measure") or {}
    return str(m.get("path") or m.get("field") or m.get("formula") or "").strip()


def band_too_wide(spec: dict, *, frac: float = 0.5) -> list:
    """Numeric-band tests whose half-width exceeds `frac` of the band midpoint's
    magnitude — a band so wide a wrong model likely also passes."""
    out = []
    for t in rigor._numeric_band_tests(spec):
        pi = t.get("pass_if") or {}
        lo, hi = pi.get("low"), pi.get("high")
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
            continue
        mid = (lo + hi) / 2.0
        half = (hi - lo) / 2.0
        ref = abs(mid) if mid != 0 else 1.0
        if half > frac * ref:
            out.append({"name": t.get("name"), "half_width": half, "midpoint": mid})
    return out


def redundant_paths(spec: dict) -> list:
    """Groups of ≥2 tests keyed on the same measure path (a suite that looks
    broad but tests one observable)."""
    by_path: dict = {}
    for t in _tests(spec):
        p = _measure_path(t)
        if p:
            by_path.setdefault(p, []).append(str(t.get("name") or ""))
    return [{"path": p, "tests": names} for p, names in by_path.items() if len(names) > 1]


def objective_mechanisms(spec: dict) -> list:
    """Mechanism tags named in the question / purpose.mechanism / study_card —
    snake_case tokens the tests should cover. Best-effort tokenization."""
    blobs = [str(spec.get("question") or ""),
             str((spec.get("purpose") or {}).get("mechanism") or ""),
             str((spec.get("study_card") or {}).get("mechanism") or "")]
    mechs = set()
    for b in blobs:
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", b):
            if "_" in tok or tok[:1].islower() and any(c.isupper() for c in tok[1:]):
                mechs.add(tok)
    return sorted(mechs)


def uncovered_mechanisms(spec: dict) -> list:
    """Mechanisms with no PRIMARY test measuring or citing them (a deterministic
    scaffold — the skill closes the semantic gap for near-misses)."""
    tests = [t for t in _tests(spec) if str(t.get("classification", "")) == "primary"]
    haystack = " ".join(_measure_path(t) + " " + " ".join(map(str, t.get("cites") or []))
                        for t in tests).lower()
    return [m for m in objective_mechanisms(spec) if m.lower() not in haystack]


def has_discriminating_control(spec: dict) -> bool:
    """A test that acts as a negative control — the correct model should FAIL it
    if the mechanism were absent (`control: negative` or a diagnostic classification)."""
    for t in _tests(spec):
        if str(t.get("control", "")).lower() == "negative":
            return True
        if str(t.get("classification", "")) == "diagnostic":
            return True
    return False


def _axis(id, label, ok: bool, severity, detail):
    # A boolean sufficiency dimension → a predicate-style axis: within_tol when ok,
    # else mismatch (hard) / drift (soft), carrying a human detail.
    verdict = "within_tol" if ok else ("mismatch" if severity == "hard" else "drift")
    return check(id, label, None, value(1.0, op=">="), severity=severity,
                 verdict=verdict, detail=detail)


def build_audit_report(spec: dict) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    wide = band_too_wide(spec)
    uncovered = uncovered_mechanisms(spec)
    dupes = redundant_paths(spec)
    missing_prov = band_provenance.bands_missing_provenance(spec)
    tb = TestBuilder(model_ref=str(spec.get("name") or ""))
    tb.add("sufficiency", _axis(
        "discrimination", "Discrimination (bands not trivially wide)",
        not wide, "hard", {"wide_bands": wide}))
    tb.add("sufficiency", _axis(
        "objective_coverage", "Objective coverage (mechanisms tested)",
        not uncovered, "hard", {"uncovered_mechanisms": uncovered}))
    tb.add("sufficiency", _axis(
        "redundancy", "Independence (tests on distinct observables)",
        not dupes, "soft", {"shared_paths": dupes}))
    tb.add("sufficiency", _axis(
        "discriminating_control", "Discriminating control present",
        has_discriminating_control(spec), "soft", {}))
    tb.add("provenance", _axis(
        "band_provenance", "Bands carry citation/provenance",
        not missing_prov, "soft", {"missing": missing_prov}))
    return tb.build()


def audit_gate(report: dict) -> str:
    hard_mismatch = soft_issue = False
    for g in (report.get("groups") or {}).values():
        for ax in g.get("axes") or []:
            v, sev = ax.get("verdict"), ax.get("severity", "hard")
            if v == "mismatch" and sev == "hard":
                hard_mismatch = True
            elif v in ("mismatch", "drift"):
                soft_issue = True
    return "fail" if hard_mismatch else ("warn" if soft_issue else "pass")
