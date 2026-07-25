"""Tests for the compositional ablation engine (viva_superpowers.ablation)."""
import pytest

from viva_superpowers.ablation import (
    generate_ablations, classify_ablation, run_ablation_suite,
)


# A synthetic 2-process composite document. Each process provides one store via
# its outputs wiring; a non-process store entry must be ignored.
SYNTH_STATE = {
    "producer": {
        "_type": "process",
        "address": "local:Producer",
        "outputs": {"out": ["substrate"]},
        "inputs": {"feed": ["nutrient"]},
    },
    "consumer": {
        "_type": "process",
        "address": "local:Consumer",
        "outputs": {"out": ["biomass"]},
        "inputs": {"in": ["substrate"]},
    },
    "substrate": 0.0,            # plain store — not a process, must be skipped
    "biomass": {"_type": "float"},
}


def test_generate_ablations_enumerates_process_provided_stores():
    abls = generate_ablations(SYNTH_STATE)
    # 2 processes × 1 provided store × 2 default modes (knockout, scale) = 4
    assert len(abls) == 4
    procs = {a["process"] for a in abls}
    assert procs == {"producer", "consumer"}
    targets = {tuple(a["target"]) for a in abls}
    assert targets == {("substrate",), ("biomass",)}


def test_generate_ablations_values_and_node_shape():
    abls = generate_ablations(SYNTH_STATE, modes=("knockout", "scale"), scale_value=0.25)
    by_mode = {(a["process"], a["mode"]): a for a in abls}
    ko = by_mode[("producer", "knockout")]
    assert ko["value"] == 0.0
    assert ko["node"]["_type"] == "process"
    assert ko["node"]["config"]["mode"] == "knockout"
    assert ko["node"]["outputs"]["target"] == ["substrate"]
    sc = by_mode[("producer", "scale")]
    assert sc["value"] == pytest.approx(0.25)
    assert sc["node"]["config"]["value"] == pytest.approx(0.25)


def test_generate_ablations_custom_modes_includes_decouple_invert():
    abls = generate_ablations(SYNTH_STATE, modes=("decouple", "invert"))
    modes = {a["mode"] for a in abls}
    assert modes == {"decouple", "invert"}
    assert len(abls) == 4


def test_generate_ablations_ignores_non_process_and_bad_input():
    assert generate_ablations({}) == []
    assert generate_ablations({"x": 1.0}) == []
    assert generate_ablations("not a dict") == []  # type: ignore[arg-type]


def test_classify_necessary_on_test_flip():
    cls = classify_ablation({"grows": True}, {"grows": False})
    assert cls == {"role": "necessary", "causally_necessary": True}


def test_classify_necessary_on_closure_gap_opening():
    cls = classify_ablation(
        {"grows": True, "_closure_gap": 0},
        {"grows": True, "_closure_gap": 2},
    )
    assert cls["role"] == "necessary"
    assert cls["causally_necessary"] is True


def test_classify_redundant_when_identical():
    cls = classify_ablation({"grows": True}, {"grows": True})
    assert cls == {"role": "redundant", "causally_necessary": False}


def test_classify_modulatory_when_measure_moves_but_no_flip():
    # A non-test measure changed (closure gap shrank, or a FAIL->PASS) but no
    # PASS->FAIL flip and the gap did not open.
    cls = classify_ablation(
        {"grows": True, "_closure_gap": 2},
        {"grows": True, "_closure_gap": 1},
    )
    assert cls == {"role": "modulatory", "causally_necessary": False}


def test_run_ablation_suite_toy_model():
    # Toy model: each process contributes additively to a "yield" measure.
    # build_fn(None) = full system; an ablation node knocking 'substrate' kills
    # the producer's contribution; knocking 'biomass' is harmless here.
    contributions = {"substrate": 5.0, "biomass": 0.0}

    def build_fn(node):
        if node is None:
            return {"ablated_store": None}
        # The intervention node targets a store path; record which store is hit.
        return {"ablated_store": tuple(node["outputs"]["target"])}

    def evaluate_fn(comp):
        ablated = comp["ablated_store"]
        total = sum(
            v for store, v in contributions.items()
            if ablated != (store,)
        )
        return {"yield": total}

    behavior_tests = {"produces_yield": lambda m: m["yield"] >= 3.0}

    records = run_ablation_suite(SYNTH_STATE, build_fn, evaluate_fn, behavior_tests)
    assert len(records) == 4  # 2 processes × 2 modes

    by = {(r["process"], r["mode"]): r for r in records}
    # Knocking the producer's provided store (substrate) drops yield 5->0: FAIL.
    prod_ko = by[("producer", "knockout")]
    assert prod_ko["behavior_test"] == "produces_yield"
    assert prod_ko["baseline_result"] is True
    assert prod_ko["ablated_result"] is False
    assert prod_ko["role"] == "necessary"
    assert prod_ko["causally_necessary"] is True
    # Knocking the consumer's provided store (biomass) does nothing: redundant.
    cons_ko = by[("consumer", "knockout")]
    assert cons_ko["role"] == "redundant"
    assert cons_ko["causally_necessary"] is False
