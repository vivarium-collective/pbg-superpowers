"""Golden test (Task 4): dnaa bulk-expression verdict computes by code.

Evaluates the REAL dnaa-2 ATP-fraction expression against the REAL dnaa-1
parquet hive.  Proves that bulk-id token resolution via RunReader.select
flips the agent→code verdict on real hive data.

Skipped when the real data paths are absent (developer-only gate).
NEVER modifies anything under v2e-invest — read-only.

Run with: .venv/bin/python -m pytest tests/test_study_evaluator_readouts_golden.py -v -s
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pbg_emitters")

from viva_superpowers import study_evaluator as se

# ---------------------------------------------------------------------------
# Paths to real data (read-only — never modified)
# ---------------------------------------------------------------------------

HIVE_PATH = Path(
    "/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/parquet-runs"
    "/dnaa1-mechA-1.7e-3-7gen/dnaa1_mechA_1p7e-3_7gen"
)

_REAL_DATA_PRESENT = HIVE_PATH.exists()

skipif_no_real_data = pytest.mark.skipif(
    not _REAL_DATA_PRESENT,
    reason="real dnaa-1 hive not present at expected path",
)

# ---------------------------------------------------------------------------
# The real dnaa-2 ATP-fraction test (sourced from dnaa-2 study.yaml tests: block)
# ---------------------------------------------------------------------------

DNAA2_ATP_FRACTION_TEST = {
    "name": "dnaa-atp-fraction-in-band-0.2-0.5",
    "measure": {
        "kind": "generation_average",
        "path": "MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])",
        # No explicit window → defaults to "full_lineage_from_gen_0"
    },
    "pass_if": {
        # Real op from dnaa-2 study.yaml: checks all per-gen averages in [low, high]
        "op": "generation_average_in_range",
        "low": 0.2,
        "high": 0.5,
    },
}


# ---------------------------------------------------------------------------
# Golden tests
# ---------------------------------------------------------------------------

@skipif_no_real_data
def test_golden_dnaa_atp_fraction_evaluated_by_code(capsys):
    """THE PAYOFF: dnaa-2 ATP-fraction verdict computes by CODE on real hive data.

    Before Task 1, MONOMER0-160[c]/PD03831[c]/MONOMER0-4565[c] tokens would fail
    reader.series() → ObservableNotFound → agent bucket.

    After Task 1, the bulk-id fallback calls reader.select(bulk_id) for each token
    → the fraction series is computed → evaluate_test returns evaluated_by='code'
    with a numeric measured_value (the per-gen average ATP fractions).
    """
    from pbg_emitters import RunReader

    reader = RunReader.open(str(HIVE_PATH))
    outcome = se.evaluate_test(DNAA2_ATP_FRACTION_TEST, reader)

    print(f"\n=== DnaA ATP-fraction golden result ===")
    print(f"evaluated_by : {outcome.get('evaluated_by')}")
    print(f"result       : {outcome.get('result', 'n/a')}")
    print(f"measured_value: {outcome.get('measured_value')}")
    print(f"detail       : {outcome.get('detail', '')}")
    if "reason" in outcome:
        print(f"reason       : {outcome['reason']}")

    # THE KEY ASSERTION: agent→code flip
    assert outcome["evaluated_by"] == "code", (
        f"Expected evaluated_by='code' (the agent→code flip), "
        f"got {outcome['evaluated_by']!r}. "
        f"reason={outcome.get('reason')!r}"
    )

    # Must have a concrete result and measured_value
    assert outcome.get("result") in ("PASS", "FAIL"), (
        f"Expected PASS or FAIL, got result={outcome.get('result')!r}"
    )
    assert "measured_value" in outcome

    # measured_value is a dict of gen → per-gen average fraction
    mv = outcome["measured_value"]
    assert isinstance(mv, dict), f"Expected dict measured_value, got {type(mv).__name__}"
    assert len(mv) > 0, "measured_value dict is empty"

    # Each per-gen average fraction must be in [0, 1] (it's a molecule fraction)
    for gen, frac in mv.items():
        assert 0.0 <= frac <= 1.0, (
            f"Per-gen fraction for gen {gen} is {frac:.4f} — outside [0, 1]. "
            f"This would indicate a data or expression evaluation error."
        )

    print(f"\nPer-generation DnaA-ATP fractions:")
    for gen in sorted(mv.keys()):
        print(f"  gen {gen}: {mv[gen]:.4f}")
    print(f"\nProof: agent→code flip confirmed. evaluated_by='code'.")


@skipif_no_real_data
def test_golden_dnaa_atp_fraction_measured_value_plausible():
    """The computed DnaA-ATP fraction is plausible for a real WCM run.

    This checks that the fraction is not trivially 0 or 1 (which would indicate
    a bug), and that real data is flowing (not injected constants).
    """
    from pbg_emitters import RunReader

    reader = RunReader.open(str(HIVE_PATH))
    outcome = se.evaluate_test(DNAA2_ATP_FRACTION_TEST, reader)

    assert outcome["evaluated_by"] == "code"
    mv = outcome["measured_value"]

    # At least some per-gen fractions must be non-trivial (not 0 or 1 exactly)
    non_trivial = [v for v in mv.values() if 0.01 < v < 0.99]
    assert len(non_trivial) > 0, (
        f"All per-gen fractions are trivial (0 or 1): {mv}. "
        f"This suggests a data or expression error."
    )


@skipif_no_real_data
def test_golden_never_guess_preserved_with_absent_bulk_id():
    """Never-guess still holds: an absent bulk ID → agent bucket (not a fabricated verdict).

    This confirms that the fallback only helps for present IDs — absent ones still route
    to the agent bucket, never fabricating a PASS.
    """
    from pbg_emitters import RunReader

    reader = RunReader.open(str(HIVE_PATH))
    test = {
        "name": "absent-bulk-test",
        "measure": {
            "kind": "generation_average",
            "path": "COMPLETELY_NONEXISTENT_MOLECULE[c]",
        },
        "pass_if": {"op": "in_range", "low": 0.0, "high": 1.0},
    }
    outcome = se.evaluate_test(test, reader)
    assert outcome["evaluated_by"] == "agent", (
        f"Absent bulk ID must route to agent, got: {outcome}"
    )
    assert "result" not in outcome, (
        f"NEVER-GUESS VIOLATION: absent bulk ID has 'result' key: {outcome}"
    )
    assert "reason" in outcome


@skipif_no_real_data
def test_golden_full_dnaa_bulk_expression_pipeline(capsys):
    """Combined pipeline: ATP fraction + total DnaA, both via bulk-id resolution."""
    from pbg_emitters import RunReader

    reader = RunReader.open(str(HIVE_PATH))

    tests = [
        DNAA2_ATP_FRACTION_TEST,
        {
            "name": "total-dnaa-in-band-300-800",
            "measure": {
                "kind": "generation_average",
                "path": "PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c]",
            },
            "pass_if": {
                "op": "generation_average_in_range",
                "low": 0.0,
                "high": 100000.0,  # wide band — just proves code evaluation
            },
        },
    ]

    outcomes = se.evaluate_study({"tests": tests}, reader)

    print(f"\n=== Full bulk-expression pipeline ===")
    for name, out in outcomes.items():
        print(f"  {name}: evaluated_by={out.get('evaluated_by')} "
              f"result={out.get('result', 'n/a')}")

    # Both must be code-evaluated
    for test in tests:
        name = test["name"]
        out = outcomes[name]
        assert out["evaluated_by"] == "code", (
            f"Test {name!r} expected code, got: {out}"
        )
        assert out.get("result") in ("PASS", "FAIL")
