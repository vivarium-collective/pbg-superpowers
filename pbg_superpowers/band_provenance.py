"""Helper for identifying band-bearing study entries that lack structured provenance.

``bands_missing_provenance(spec)`` is the primary entry-point for stage 3b's
agent skill and the report renderer — it surfaces every acceptance band that
carries no machine-linked ``cites`` bib_key, so 3b can prompt the author to
fill them in.

Covered entry kinds:
- ``behavior_tests[]`` — detect via numeric ``pass_if.low``/``high``/``threshold``
  or ``calibration_anchor.literature_target``
- ``tests[]`` — same detection (the v4 per-test array shape)
- ``readouts[]`` — detect via a prose band notation ``[N, M]`` in ``notes``
  (deterministic regex, no AI)

A test/readout is "band-bearing AND missing cites" when:
1. It carries a quantitative acceptance criterion (band or literature_target), AND
2. It has no ``cites: [...]`` field (or the list is empty).
"""
from __future__ import annotations

import re
from typing import Any

# Regex for prose band notation in readout notes: "[0.2, 0.5]" or "[300, 800]".
_PROSE_BAND_RE = re.compile(r"\[(\d+\.?\d*),\s*(\d+\.?\d*)\]")


def _band_from_pass_if(pass_if: Any) -> dict | None:
    """Extract a structured band dict from a pass_if block.

    Returns ``{"low": N, "high": M}`` / ``{"threshold": T}`` when the block
    carries numeric bounds; ``None`` when no band is detectable.
    """
    if not isinstance(pass_if, dict):
        return None
    band: dict = {}
    if isinstance(pass_if.get("low"), (int, float)):
        band["low"] = pass_if["low"]
    if isinstance(pass_if.get("high"), (int, float)):
        band["high"] = pass_if["high"]
    if isinstance(pass_if.get("threshold"), (int, float)):
        band["threshold"] = pass_if["threshold"]
    return band if band else None


def _has_cites(entry: dict) -> bool:
    """True iff the entry carries at least one cite key."""
    cites = entry.get("cites")
    return bool(cites) and isinstance(cites, list)


def bands_missing_provenance(spec: dict) -> list[dict]:
    """Return a list of ``{name, kind, band, field_path}`` dicts.

    Each dict describes a band-bearing entry (behavior_test, test, or readout)
    that has no ``cites`` field — i.e. its acceptance band has no machine-linked
    source in ``references/papers.bib``.

    Parameters
    ----------
    spec:
        Parsed study.yaml dict.

    Returns
    -------
    list[dict]
        Each entry has:
        - ``name`` (str): test/readout name.
        - ``kind`` (str): ``"behavior_test"``, ``"test"``, or ``"readout"``.
        - ``band`` (dict): numeric bounds extracted from ``pass_if`` or prose
          (e.g. ``{"low": 0.2, "high": 0.5}``).
        - ``field_path`` (str): stable YAML path (e.g. ``"behavior_tests[0]"``).
    """
    if not isinstance(spec, dict):
        return []

    result: list[dict] = []

    # --- behavior_tests[] and tests[] ----------------------------------------
    section_kinds = [
        ("behavior_tests", "behavior_test"),
        ("tests", "test"),
    ]
    for section, kind in section_kinds:
        items = spec.get(section) or []
        if not isinstance(items, list):
            continue
        for idx, test in enumerate(items):
            if not isinstance(test, dict):
                continue

            # 1. Detect the band.
            band = _band_from_pass_if(test.get("pass_if"))

            # 2. Also treat calibration_anchor.literature_target as a band indicator.
            if not band:
                anch = test.get("calibration_anchor") or {}
                if isinstance(anch, dict) and anch.get("literature_target") is not None:
                    band = {"literature_target": anch["literature_target"]}

            if not band:
                continue  # not a band test — skip

            # 3. Check cites.
            if _has_cites(test):
                continue  # has at least one cite — not missing provenance

            result.append({
                "name": test.get("name", f"<index-{idx}>"),
                "kind": kind,
                "band": band,
                "field_path": f"{section}[{idx}]",
            })

    # --- readouts[] ----------------------------------------------------------
    readouts = spec.get("readouts") or []
    if isinstance(readouts, list):
        for idx, ro in enumerate(readouts):
            if not isinstance(ro, dict):
                continue

            # Detect a prose band notation in the readout's notes string.
            notes = ro.get("notes") or ""
            if not isinstance(notes, str):
                notes = str(notes)
            m = _PROSE_BAND_RE.search(notes)
            if not m:
                continue  # no prose band detected — skip

            band = {"low": float(m.group(1)), "high": float(m.group(2))}

            # Check cites.
            if _has_cites(ro):
                continue  # already cited

            result.append({
                "name": ro.get("name", f"<index-{idx}>"),
                "kind": "readout",
                "band": band,
                "field_path": f"readouts[{idx}]",
            })

    return result
