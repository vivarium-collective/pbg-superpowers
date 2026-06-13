"""Compositional ablation over a composite's requires/provides graph.

A skeptical reviewer's question about an emergent behavior is "which *part*
actually causes it?". Answering it means systematically removing/attenuating one
process at a time and asking whether a declared behavior breaks. This module is
the generic engine for that — a compositional analogue of a gene-knockout
screen.

It is pure and model-agnostic: the model supplies two callables (``build_fn`` to
assemble a composite with an optional perturbation node, ``evaluate_fn`` to
reduce a built composite to a ``{measure: value}`` dict) plus ``behavior_tests``
(predicates over those measures). The engine enumerates the ablations from the
static composite document, runs each, and classifies the process's causal role.

The enumeration walks the same requires/provides reasoning as
``pbg_autopoiesis.meter`` (``operational_closure`` / ``interface_of``) — here
applied over a composite_state *dict* rather than live process instances: each
``_type == "process"`` entry's ``outputs`` wiring names the stores that process
*provides*, and those are the stores worth ablating. Perturbation nodes are
built with :func:`pbg_superpowers.intervention.intervention_node`, so any
Intervention ``mode`` (``knockout``/``scale``/``decouple``/``invert``/…) is a
valid ablation mode.

Storage shape (the model writes the suite output into ``study.yaml``)::

    ablations:
      - {process, target, mode, behavior_test, baseline_result,
         ablated_result, role, causally_necessary}
"""
from __future__ import annotations

from typing import Any, Callable

from .intervention import intervention_node


__all__ = ["generate_ablations", "classify_ablation", "run_ablation_suite"]


# ---------------------------------------------------------------------------
# Enumeration over the requires/provides graph
# ---------------------------------------------------------------------------

def _provided_store_paths(proc_node: dict) -> list[list]:
    """The store paths a process *provides* — the values of its ``outputs``
    wiring, normalized to ``list`` paths. Mirrors meter's ``provides`` walk
    (a process provides what its outputs are wired to)."""
    outputs = proc_node.get("outputs") or {}
    paths: list[list] = []
    if not isinstance(outputs, dict):
        return paths
    for store in outputs.values():
        if isinstance(store, str):
            paths.append([store])
        elif isinstance(store, (list, tuple)):
            paths.append(list(store))
    return paths


def generate_ablations(
    composite_state: dict,
    *,
    modes: tuple[str, ...] = ("knockout", "scale"),
    scale_value: float = 0.5,
) -> list[dict]:
    """Enumerate single-process ablations from a static composite document.

    Walks ``composite_state`` for ``_type == "process"`` entries; for each, reads
    its ``outputs`` wiring (the stores it provides) and, for every provided store
    × every mode in ``modes``, emits an ablation descriptor::

        {"process": <name>, "target": <store_path:list>, "mode": <m>,
         "value": <0.0 for knockout / scale_value for scale / scale_value otherwise>,
         "node": intervention_node(store_path, mode=m, value=...)}

    ``value`` is ``0.0`` for ``knockout`` and ``scale_value`` for every other
    mode (``scale``/``decouple``/``invert`` ignore or reinterpret it harmlessly).
    Pure; reads the doc only.
    """
    ablations: list[dict] = []
    if not isinstance(composite_state, dict):
        return ablations
    for name, node in composite_state.items():
        if not (isinstance(node, dict) and node.get("_type") == "process"):
            continue
        for store_path in _provided_store_paths(node):
            for mode in modes:
                value = 0.0 if mode == "knockout" else scale_value
                ablations.append({
                    "process": name,
                    "target": list(store_path),
                    "mode": mode,
                    "value": value,
                    "node": intervention_node(list(store_path), mode=mode, value=value),
                })
    return ablations


# ---------------------------------------------------------------------------
# Classification of a process's causal role
# ---------------------------------------------------------------------------

def _split_gap(results: dict) -> tuple[dict, int]:
    """Separate the test booleans from the optional ``_closure_gap`` integer."""
    tests = {k: v for k, v in results.items() if k != "_closure_gap"}
    gap = results.get("_closure_gap", 0) or 0
    try:
        gap = int(gap)
    except (TypeError, ValueError):
        gap = 0
    return tests, gap


def classify_ablation(baseline: dict, ablated: dict) -> dict:
    """Classify a process's causal role from before/after behavior results.

    ``baseline``/``ablated`` are ``{test_name: bool_pass}`` dicts, optionally
    carrying ``"_closure_gap": int``. Returns
    ``{"role": ..., "causally_necessary": bool}`` where role is:

    - ``necessary`` — any test flips PASS→FAIL, or the operational-closure gap
      *opens* (baseline gap ``0`` → ablated gap ``> 0``). ``causally_necessary``.
    - ``redundant`` — baseline and ablated are identical (nothing moved).
    - ``modulatory`` — some measure changed but no test flipped and the closure
      gap did not open.
    """
    base_tests, base_gap = _split_gap(baseline)
    abl_tests, abl_gap = _split_gap(ablated)

    flipped = any(
        base_tests.get(k) is True and abl_tests.get(k) is False
        for k in base_tests
    )
    gap_opens = base_gap == 0 and abl_gap > 0

    if flipped or gap_opens:
        return {"role": "necessary", "causally_necessary": True}
    if baseline == ablated:
        return {"role": "redundant", "causally_necessary": False}
    return {"role": "modulatory", "causally_necessary": False}


# ---------------------------------------------------------------------------
# The suite runner
# ---------------------------------------------------------------------------

def _apply_tests(measures: Any, behavior_tests: dict) -> dict:
    """Reduce a measures dict to ``{test_name: bool}`` (+ pass through
    ``_closure_gap`` when the measures carry it). Best-effort per test: a
    raising predicate counts as FAIL rather than sinking the suite."""
    results: dict = {}
    for name, fn in behavior_tests.items():
        try:
            results[name] = bool(fn(measures))
        except Exception:  # noqa: BLE001 — a raising predicate is a failed test
            results[name] = False
    if isinstance(measures, dict) and "_closure_gap" in measures:
        results["_closure_gap"] = measures["_closure_gap"]
    return results


def run_ablation_suite(
    base_state: dict,
    build_fn: Callable[[dict | None], Any],
    evaluate_fn: Callable[[Any], dict],
    behavior_tests: dict,
) -> list[dict]:
    """Run the full single-process ablation screen.

    Enumerates ablations from ``base_state`` via :func:`generate_ablations`,
    establishes a baseline (``evaluate_fn(build_fn(None))`` reduced through
    ``behavior_tests``), then for each ablation builds + evaluates the perturbed
    composite and classifies the process's role.

    Args:
        base_state: the composite document to enumerate ablations from.
        build_fn: ``node_or_None -> composite``. Called with ``None`` for the
            baseline and with an ablation's ``node`` for each perturbed run.
        evaluate_fn: ``composite -> {measure: value}``. May include a
            ``"_closure_gap"`` measure to drive the closure-opening rule.
        behavior_tests: ``{name: predicate(measures) -> bool}``.

    Returns:
        A list of records (the ``ablations`` storage shape) ::

            {"process", "target", "mode", "behavior_test", "baseline_result",
             "ablated_result", "role", "causally_necessary"}

        ``behavior_test`` is the first test that flipped PASS→FAIL, or — when
        nothing flipped — the primary (first declared) test.
    """
    primary = next(iter(behavior_tests), None)
    baseline_results = _apply_tests(evaluate_fn(build_fn(None)), behavior_tests)

    records: list[dict] = []
    for ab in generate_ablations(base_state):
        ablated_results = _apply_tests(
            evaluate_fn(build_fn(ab["node"])), behavior_tests
        )
        cls = classify_ablation(baseline_results, ablated_results)

        flipped = [
            k for k in behavior_tests
            if baseline_results.get(k) is True and ablated_results.get(k) is False
        ]
        test = flipped[0] if flipped else primary

        records.append({
            "process": ab["process"],
            "target": ab["target"],
            "mode": ab["mode"],
            "behavior_test": test,
            "baseline_result": baseline_results.get(test) if test is not None else None,
            "ablated_result": ablated_results.get(test) if test is not None else None,
            "role": cls["role"],
            "causally_necessary": cls["causally_necessary"],
        })
    return records
