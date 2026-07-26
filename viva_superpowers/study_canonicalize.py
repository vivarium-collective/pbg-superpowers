"""Canonicalize a study's model declaration into the conditions.{baseline,variants}
form. Pure, in-place, comment-preserving-safe (moves value nodes, never reserializes)."""
from __future__ import annotations


def _as_single_baseline(entry):
    """Return a {name?, composite, params} mapping from a top-level baseline list entry."""
    return entry


def canonicalize_models(spec) -> dict:
    report = {"changed": False, "style": "canonical", "flags": [], "inherited_composites": []}
    top_baseline = spec.get("baseline")
    conditions = spec.get("conditions")

    # --- classify + move top-level baseline/variants into conditions (Style B / both) ---
    if isinstance(top_baseline, list):
        if len(top_baseline) > 1:
            report["flags"].append("multi_baseline_needs_human")
            return report  # leave untouched
        report["style"] = "both" if isinstance(conditions, dict) and conditions.get("baseline") else "B"
        if conditions is None or not isinstance(conditions, dict):
            spec["conditions"] = {}
            conditions = spec["conditions"]
        if conditions.get("baseline") and conditions["baseline"].get("composite"):
            report["flags"].append("both_dropped_toplevel")   # conditions wins
        elif top_baseline:
            conditions["baseline"] = top_baseline[0]           # move node (keeps its comments)
        # move a top-level variants list in, if present and conditions lacks one
        top_variants = spec.get("variants")
        if isinstance(top_variants, list) and not conditions.get("variants"):
            conditions["variants"] = top_variants
        for k in ("baseline", "variants"):
            if k in spec:
                del spec[k]
        report["changed"] = True

    conditions = spec.get("conditions")
    if not isinstance(conditions, dict) or not conditions.get("baseline"):
        return report  # nothing canonical to normalize (e.g. parca / non-model study)

    base_composite = conditions["baseline"].get("composite")

    # --- normalize variants: inherit composite, rename parameter_overrides -> params ---
    for v in (conditions.get("variants") or []):
        if not isinstance(v, dict):
            continue
        if "parameter_overrides" in v and "params" not in v:
            v["params"] = v.pop("parameter_overrides"); report["changed"] = True
        if not v.get("composite") and base_composite:
            v["composite"] = base_composite
            report["inherited_composites"].append(v.get("name", "?")); report["changed"] = True

    # --- ensure model_settings key exists (kept separate) ---
    if "model_settings" not in conditions:
        conditions["model_settings"] = []; report["changed"] = True

    return report
