"""Golden test: evaluate_study against the real dnaa-1-expression run.

The real data paths are only available on the developer's machine, so the
test is skipped when the paths are absent.  When present, it:
  1. Runs evaluate_study against the real hive.
  2. Asserts no exceptions.
  3. Asserts every outcome has the correct shape.
  4. Confirms all study tests are agent-bucketed with reasons (the paths are
     either vector observables, non-run-data kinds, or unsupported windows —
     all correct B2 routing, documented in the plan).
  5. Runs synthetic tests using clean scalar observables to confirm the
     code-evaluation path produces concrete, biologically-sane verdicts.

Run with:
    .venv/bin/python -m pytest tests/test_study_evaluator_golden.py -v -s
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import polars as pl
import pytest
import yaml

pytest.importorskip("pbg_emitters")

from pbg_superpowers import study_evaluator as se

# ---------------------------------------------------------------------------
# Paths to real data (read-only — never modified)
# ---------------------------------------------------------------------------

STUDY_YAML = Path("/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/study.yaml")
HIVE_PATH = Path(
    "/Users/eranagmon/code/v2e-invest/studies/dnaa-1-expression/parquet-runs"
    "/dnaa1-mechA-1.7e-3-7gen/dnaa1_mechA_1p7e-3_7gen"
)

_REAL_DATA_PRESENT = STUDY_YAML.exists() and HIVE_PATH.exists()

skipif_no_real_data = pytest.mark.skipif(
    not _REAL_DATA_PRESENT,
    reason="real dnaa-1 data not present at expected paths",
)


# ---------------------------------------------------------------------------
# Real-observable code-evaluation tests — build minimal test specs and
# evaluate them against the REAL dnaa-1 hive data (never written to study.yaml).
# The specs are hand-crafted but the data is 100 % from the real parquet run.
# ---------------------------------------------------------------------------

# Real-observable test 1: oriC count in [1,2] per generation (biological sanity check).
# At a healthy cell cycle oriC oscillates 1↔2; the per-gen mean must be in [1,2].
REAL_ORIC_RANGE_CHECK = {
    "name": "_real_oric_range_check",
    "measure": {
        "kind": "range_check_per_generation",
        "path": "listeners.replication_data.number_of_oric",
        "window": "every_generation",
    },
    "pass_if": {"op": "in_range_every_generation", "low": 1.0, "high": 2.0},
}

# Real-observable test 2: cell_mass across the whole lineage.
# Real E. coli cell_mass (full-lineage mean) must land in the biological band
# [550, 700] fg — this confirms REAL hive data is being read, not injected values.
REAL_CELL_MASS_RANGE = {
    "name": "_real_cell_mass_in_band",
    "measure": {
        "kind": "generation_average",
        "path": "listeners.mass.cell_mass",
        "window": "full_lineage_from_gen_0",
    },
    "pass_if": {"op": "range", "low": 100.0, "high": 5000.0},
}

# Real-observable test 3: cv_below on oriC from generation 1 (should be very low CV
# since truncated data keeps oriC=1 throughout each gen in the 1.7e-3 run).
REAL_ORIC_CV = {
    "name": "_real_oric_cv",
    "measure": {
        "kind": "range_check_per_generation",
        "path": "listeners.replication_data.number_of_oric",
        "window": "full_lineage_from_gen_0",
    },
    "pass_if": {"op": "cv_below", "cv_threshold": 0.5},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_verdict_table(outcomes: dict[str, dict]) -> None:
    """Print a human-readable per-test verdict table."""
    sep = "-" * 80
    print(f"\n{sep}")
    print(f"{'TEST NAME':<50}  {'EVALUATED_BY':<12}  RESULT/REASON")
    print(sep)
    for name, out in outcomes.items():
        by = out.get("evaluated_by", "?")
        if by == "code":
            result = out.get("result", "?")
            measured = out.get("measured_value", "?")
            detail = out.get("detail", "")
            print(f"{name:<50}  {by:<12}  {result}  measured={measured!r}")
            if detail:
                print(f"  {'':50}  {'':12}  detail: {detail}")
        else:
            reason = out.get("reason", "?")
            print(f"{name:<50}  {by:<12}  {reason}")
    print(sep)


def _is_valid_outcome_shape(out: dict) -> bool:
    """Return True if *out* matches one of the three valid outcome shapes."""
    by = out.get("evaluated_by")
    if by == "code":
        return all(k in out for k in ("result", "measured_value", "operator", "detail"))
    if by == "agent":
        return "reason" in out
    if by == "needs_rerun":
        return "reason" in out
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@skipif_no_real_data
def test_golden_no_exceptions():
    """evaluate_study must not raise for any test in the real dnaa-1 study."""
    from pbg_emitters import RunReader

    spec = yaml.safe_load(STUDY_YAML.read_text())
    reader = RunReader.open(str(HIVE_PATH))

    outcomes = se.evaluate_study(spec, reader)
    assert isinstance(outcomes, dict)
    assert len(outcomes) > 0


@skipif_no_real_data
def test_golden_all_outcomes_have_valid_shape():
    """Every outcome must match one of the three valid shapes."""
    from pbg_emitters import RunReader

    spec = yaml.safe_load(STUDY_YAML.read_text())
    reader = RunReader.open(str(HIVE_PATH))

    outcomes = se.evaluate_study(spec, reader)
    for name, out in outcomes.items():
        assert _is_valid_outcome_shape(out), (
            f"Test {name!r} has invalid outcome shape: {out}"
        )


@skipif_no_real_data
def test_golden_study_tests_all_agent_bucketed(capsys):
    """All dnaa-1 study tests must be agent-bucketed (correct B2 routing).

    The dnaa-1 tests use:
      - vector observables (listeners.monomer_counts, listeners.rna_counts.mRNA_counts,
        listeners.rnap_data.rna_init_event_per_cistron) — not resolvable as scalars
      - 'derived' kind tests that reference vector observables — now in RUN_DATA_KINDS,
        so they pass the kind gate and hit the vector-observable bucket instead
      - an unsupported window ('per_minute_full_lineage')

    All are correct B2 agent-bucket reasons; bulk resolution and structured
    aggregation are follow-on work (B3+).
    """
    from pbg_emitters import RunReader

    spec = yaml.safe_load(STUDY_YAML.read_text())
    reader = RunReader.open(str(HIVE_PATH))

    outcomes = se.evaluate_study(spec, reader)
    _print_verdict_table(outcomes)

    # Every study test should be agent-bucketed with a reason
    for name, out in outcomes.items():
        assert out["evaluated_by"] == "agent", (
            f"Test {name!r} unexpectedly got evaluated_by={out['evaluated_by']!r}. "
            f"Full outcome: {out}"
        )
        assert "reason" in out and out["reason"], (
            f"Test {name!r} is agent-bucketed but has no reason: {out}"
        )
        # CRITICAL: no fabricated PASS/FAIL
        assert "result" not in out, (
            f"Test {name!r} has a 'result' key in an agent outcome — "
            f"this would be a fabricated verdict! outcome={out}"
        )

    # Spot-check expected reasons for each known test
    # Test 1: monomer_counts is a vector observable
    if "dnaa-monomer-count-in-band-300-800-across-generations" in outcomes:
        reason = outcomes["dnaa-monomer-count-in-band-300-800-across-generations"]["reason"]
        assert "not resolvable" in reason.lower() or "non-run-data" in reason.lower(), (
            f"Unexpected reason for test 1: {reason!r}"
        )

    # Test 2: kind='derived' is now in RUN_DATA_KINDS so it passes the kind gate,
    # but the formula references listeners.monomer_counts (a vector) → vector-observable bucket.
    if "dnaa-concentration-stable-across-generations" in outcomes:
        reason = outcomes["dnaa-concentration-stable-across-generations"]["reason"]
        assert (
            "not resolvable" in reason.lower()
            or "non-run-data" in reason.lower()
            or "kind" in reason.lower()
        ), f"Unexpected reason for test 2: {reason!r}"

    # Test 4: unsupported window 'per_minute_full_lineage'
    if "dnaa-mrna-init-rate-near-biological-rate" in outcomes:
        reason = outcomes["dnaa-mrna-init-rate-near-biological-rate"]["reason"]
        assert "unsupported window" in reason.lower() or "window" in reason.lower(), (
            f"Unexpected reason for test 4: {reason!r}"
        )


@skipif_no_real_data
def test_golden_real_scalar_observables_code_evaluated(capsys):
    """Real-observable code-evaluation: scalar paths from the real dnaa-1 hive.

    This test reads REAL scalar series (listeners.mass.cell_mass and
    listeners.replication_data.number_of_oric) from the real parquet run at
    HIVE_PATH.  It validates that the code-evaluation path works end-to-end
    against real run data and produces biologically sane, unmistakably non-injected
    results.  The tight cell_mass band [550, 700] fg proves real data is flowing.
    """
    from pbg_emitters import RunReader

    reader = RunReader.open(str(HIVE_PATH))

    real_tests = [
        REAL_ORIC_RANGE_CHECK,
        REAL_CELL_MASS_RANGE,
        REAL_ORIC_CV,
    ]
    spec = {"tests": real_tests}
    outcomes = se.evaluate_study(spec, reader)

    print("\n=== Real-observable code-evaluation verdicts ===")
    _print_verdict_table(outcomes)

    # All tests must be code-evaluated (not agent-bucketed)
    for test in real_tests:
        name = test["name"]
        out = outcomes[name]
        assert out["evaluated_by"] == "code", (
            f"Real-observable test {name!r} unexpectedly agent-bucketed: {out}"
        )
        assert out["result"] in ("PASS", "FAIL", "PARTIAL"), (
            f"Real-observable test {name!r} has invalid result: {out['result']!r}"
        )
        assert "measured_value" in out
        assert "operator" in out

    # Biological sanity: oriC mean per gen must be in [1, 2]
    oric_out = outcomes[REAL_ORIC_RANGE_CHECK["name"]]
    assert oric_out["result"] == "PASS", (
        f"oriC range check failed — unexpected for a healthy cell cycle. "
        f"Measured per-gen means: {oric_out.get('measured_value')}"
    )
    # The measured_value is a dict of gen → mean_value
    assert isinstance(oric_out["measured_value"], dict)
    for gen, mean_val in oric_out["measured_value"].items():
        assert 1.0 <= mean_val <= 2.0, (
            f"oriC mean for gen {gen} is {mean_val:.3f} — outside [1, 2]"
        )

    # Cell mass: tight real-data sanity band [550, 700] fg.
    # Synthetic/injected data could trivially satisfy a wide band; this narrow
    # range is only reachable with actual E. coli simulation output from the hive.
    mass_out = outcomes[REAL_CELL_MASS_RANGE["name"]]
    assert mass_out["result"] == "PASS", (
        f"Cell mass range check failed — mean={mass_out.get('measured_value'):.1f} fg"
    )
    cell_mass_mean = float(mass_out["measured_value"])
    assert 550.0 <= cell_mass_mean <= 700.0, (
        f"cell_mass mean {cell_mass_mean:.1f} fg is outside the real-data sanity "
        f"band [550, 700] fg — this suggests non-real data is flowing."
    )


@skipif_no_real_data
def test_golden_never_fabricates_verdict(capsys):
    """No agent-bucketed test may carry a 'result' key.

    This is the most important invariant: the evaluator must NEVER fabricate
    a PASS/FAIL for a test it cannot actually compute.
    """
    from pbg_emitters import RunReader

    spec = yaml.safe_load(STUDY_YAML.read_text())
    reader = RunReader.open(str(HIVE_PATH))

    outcomes = se.evaluate_study(spec, reader)

    for name, out in outcomes.items():
        by = out.get("evaluated_by")
        if by in ("agent", "needs_rerun"):
            assert "result" not in out, (
                f"NEVER-GUESS VIOLATION: test {name!r} is {by!r} but has "
                f"'result'={out.get('result')!r} — this is a fabricated verdict!"
            )


@skipif_no_real_data
def test_golden_full_combined_run(capsys):
    """Combined run: study tests + synthetic tests, printed as one verdict table.

    This is the human-readable integration check.  Run with -s to see output.
    """
    from pbg_emitters import RunReader

    spec = yaml.safe_load(STUDY_YAML.read_text())
    reader = RunReader.open(str(HIVE_PATH))

    # Merge synthetic tests into a copy of the spec
    all_tests = list(spec.get("tests", []))
    all_tests.extend([REAL_ORIC_RANGE_CHECK, REAL_CELL_MASS_RANGE, REAL_ORIC_CV])
    combined_spec = dict(spec)
    combined_spec["tests"] = all_tests

    outcomes = se.evaluate_study(combined_spec, reader)

    print(f"\n{'=' * 80}")
    print(f"dnaa-1-expression golden evaluation  —  {len(outcomes)} tests total")
    print(
        f"  Hive: {HIVE_PATH.name} (NOTE: truncated-emit ~43s/gen; "
        f"scalar observables only in B2)"
    )
    print(f"{'=' * 80}")
    _print_verdict_table(outcomes)

    # Summary counts
    code_pass = sum(1 for o in outcomes.values()
                    if o.get("evaluated_by") == "code" and o.get("result") == "PASS")
    code_fail = sum(1 for o in outcomes.values()
                    if o.get("evaluated_by") == "code" and o.get("result") == "FAIL")
    agent_count = sum(1 for o in outcomes.values() if o.get("evaluated_by") == "agent")
    rerun_count = sum(1 for o in outcomes.values() if o.get("evaluated_by") == "needs_rerun")

    print(f"\nSummary: code PASS={code_pass}  code FAIL={code_fail}  "
          f"agent={agent_count}  needs_rerun={rerun_count}")

    assert all(_is_valid_outcome_shape(o) for o in outcomes.values()), (
        "Some outcomes have invalid shapes"
    )
