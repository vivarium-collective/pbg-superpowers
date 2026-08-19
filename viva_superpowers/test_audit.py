"""Deterministic test-sufficiency checks for /viva-tests audit.

Adds the sufficiency dimensions rigor.py doesn't cover — discrimination
(trivially-wide bands), redundancy (tests on the same observable), objective
coverage (mechanisms with no test), and a discriminating control. Pure; the
skill supplies the AI reasoning (null-model plausibility, mechanism semantics)
and assembles the graded report. See the loop spec §5.
"""
from __future__ import annotations

import re

from viva_superpowers.test_contract import TestBuilder, check, value
from viva_superpowers import band_provenance


def _tests(spec: dict) -> list:
    """Every behavior_tests[] / expected_behavior[] / tests[] entry (dicts only).

    Mirrors rigor._study_test_entries's section merge (behavior_tests + tests,
    concatenated — not an ``or`` fallback), plus expected_behavior (the section
    scaffold.py emits by default), so a study authored under any one of these
    sections is visible to every check in this module — band_too_wide included.
    """
    out = []
    for section in ("behavior_tests", "expected_behavior", "tests"):
        for t in (spec or {}).get(section) or []:
            if isinstance(t, dict):
                out.append(t)
    return out


def _measure_path(t: dict) -> str:
    m = t.get("measure") or {}
    return str(m.get("path") or m.get("field") or m.get("formula") or "").strip()


def band_too_wide(spec: dict, *, frac: float = 0.5) -> list:
    """Numeric-band tests whose half-width exceeds `frac` of the band midpoint's
    magnitude — a band so wide a wrong model likely also passes.

    Filters `_tests(spec)` itself (behavior_tests + expected_behavior + tests)
    rather than delegating to `rigor._numeric_band_tests` (which only reads
    behavior_tests + tests) — otherwise a wide band authored under
    `expected_behavior:` (the section `scaffold.py` emits by default) would
    escape this check even though redundant_paths/uncovered_mechanisms/
    has_discriminating_control already see it via `_tests`.
    """
    out = []
    for t in _tests(spec):
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


def one_sided_loose_primary(spec: dict) -> list:
    """PRIMARY tests whose `pass_if` is a one-sided comparator (`<=`/`<`/`>=`/`>`
    with a `value`/`threshold`, no `low`/`high` band) — a bound this audit's
    band-width check can't grade for looseness since it has no stated interval,
    so a trivially-loose one-sided threshold (e.g. `<= 1e12`) would otherwise
    pass `band_too_wide` silently. Flagged as unverifiable tightness."""
    out = []
    for t in _tests(spec):
        if str(t.get("classification", "")) != "primary":
            continue
        pi = t.get("pass_if") or {}
        has_band = isinstance(pi.get("low"), (int, float)) and isinstance(pi.get("high"), (int, float))
        if has_band:
            continue
        op = str(pi.get("op") or "")
        val = pi.get("value") if "value" in pi else pi.get("threshold")
        if op in ("<=", "<", ">=", ">") and isinstance(val, (int, float)):
            out.append({"name": t.get("name"), "op": op, "value": val})
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


def _bands_missing_provenance(spec: dict) -> list:
    """Band-bearing tests with NO provenance source at all. `band_provenance`
    flags bands lacking `cites`; a `pass_if.provenance` is an equally-valid source
    (matching `rigor._test_threshold_sourced`), so a band that carries one is NOT
    missing provenance. Keep only the bands that have neither."""
    by_name = {str(t.get("name")): t for t in _tests(spec)}
    out = []
    for m in band_provenance.bands_missing_provenance(spec):
        t = by_name.get(str(m.get("name"))) or {}
        if not (t.get("pass_if") or {}).get("provenance"):
            out.append(m)
    return out


def has_discriminating_control(spec: dict) -> bool:
    """A test that acts as a negative control — the correct model should FAIL it
    if the mechanism were absent (`control: negative` or a diagnostic classification)."""
    for t in _tests(spec):
        if str(t.get("control", "")).lower() == "negative":
            return True
        if str(t.get("classification", "")) == "diagnostic":
            return True
    return False


def is_comparison_study(spec: dict) -> bool:
    """A COMPARISON study grades a model against an external REFERENCE (e.g. v2ecoli
    vs vEcoli) rather than building a mechanism to clear absolute bands. Its checks
    are report-card comparisons and the reference standard is the discriminator, so
    the sufficiency axes are computed differently (see build_audit_report). Detected
    by a `comparison:` block, `report_card_refs`, or any `kind: report_card` test."""
    if spec.get("comparison"):
        return True
    if spec.get("report_card_refs"):
        return True
    return any(str(t.get("kind", "")) == "report_card" for t in _tests(spec))


def _card_name(x) -> str:
    # "viz/report_card/statistical.html" -> "statistical"; "statistical" -> "statistical"
    base = str(x or "").rsplit("/", 1)[-1]
    return base[:-5] if base.endswith(".html") else base


def comparison_axes(spec: dict) -> list:
    """The comparison cards this study declares it grades on (`report_cards` list)."""
    return sorted({_card_name(c) for c in (spec.get("report_cards") or []) if c})


def uncovered_comparison_axes(spec: dict) -> list:
    """Declared comparison cards with no test referencing them — the comparison
    analogue of `uncovered_mechanisms`. Covers the compared AXES, not
    question-tokenized mechanism names (which would misread the reference model
    name, e.g. "vEcoli", as an uncovered mechanism)."""
    tested = {_card_name(t.get("card")) for t in _tests(spec)
              if t.get("card") and str(t.get("kind", "")) == "report_card"}
    return [c for c in comparison_axes(spec) if c not in tested]


def has_comparison_reference(spec: dict) -> bool:
    """A comparison study's discriminator is its external reference standard —
    match=pass / diverge=fail is inherent — so a declared reference satisfies the
    discriminating-control requirement. Signalled by `report_card_refs` or a
    `comparison:` block."""
    if spec.get("report_card_refs"):
        return True
    comp = spec.get("comparison")
    return bool(isinstance(comp, dict) and comp)


def _axis(axis_id, label, ok: bool, severity, detail):
    # A boolean sufficiency dimension → a predicate-style axis: within_tol when ok,
    # else mismatch (hard) / drift (soft), carrying a human detail.
    verdict = "within_tol" if ok else ("mismatch" if severity == "hard" else "drift")
    return check(axis_id, label, None, value(1.0, op=">="), severity=severity,
                 verdict=verdict, detail=detail)


def build_audit_report(spec: dict) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    comparison = is_comparison_study(spec)
    wide = band_too_wide(spec)
    loose = one_sided_loose_primary(spec)
    dupes = redundant_paths(spec)
    missing_prov = _bands_missing_provenance(spec)
    # Coverage + the discriminator are computed differently for COMPARISON studies
    # (graded against an external reference) than for model-building studies
    # (mechanism bands + negative controls). The axis IDs stay stable so renderers
    # don't branch; only the label/detail/computation change.
    if comparison:
        uncovered = uncovered_comparison_axes(spec)
        cov_label = "Comparison coverage (each compared card tested)"
        cov_detail = {"uncovered_cards": uncovered}
        control_ok = has_comparison_reference(spec)
        control_label = "Reference standard present (the comparison discriminator)"
    else:
        uncovered = uncovered_mechanisms(spec)
        cov_label = "Objective coverage (mechanisms tested)"
        cov_detail = {"uncovered_mechanisms": uncovered}
        control_ok = has_discriminating_control(spec)
        control_label = "Discriminating control present"
    # Discrimination is 3-state, not the boolean-axis pattern: mismatch (hard)
    # if any band is outright too wide; else drift (soft signal on a hard axis,
    # which audit_gate turns into an overall "warn" — lockable but flagged, not
    # a silent pass) if any primary test has an unverifiable one-sided
    # threshold; else within_tol.
    if wide:
        disc_verdict = "mismatch"
    elif loose:
        disc_verdict = "drift"
    else:
        disc_verdict = "within_tol"
    tb = TestBuilder(model_ref=str(spec.get("name") or ""))
    tb.add("sufficiency", check(
        "discrimination", "Discrimination (bands not trivially wide)", None,
        value(1.0, op=">="), severity="hard", verdict=disc_verdict,
        detail={"wide_bands": wide, "one_sided_loose_primary": loose}))
    tb.add("sufficiency", _axis(
        "objective_coverage", cov_label, not uncovered, "hard", cov_detail))
    tb.add("sufficiency", _axis(
        "redundancy", "Independence (tests on distinct observables)",
        not dupes, "soft", {"shared_paths": dupes}))
    tb.add("sufficiency", _axis(
        "discriminating_control", control_label, control_ok, "soft",
        {"comparison": comparison}))
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
