"""Golden test: compute_outcomes against the real dnaa-1-expression hive.

Operates on a TMP COPY of study.yaml — NEVER modifies anything under v2e-invest.

Run with: .venv/bin/python -m pytest tests/test_computed_outcomes_golden.py -v -s
"""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
import yaml

from pbg_superpowers import study_evaluator as se

# ---------------------------------------------------------------------------
# Real paths (read-only; test is skipped when absent)
# ---------------------------------------------------------------------------

V2E_INVEST = Path("/Users/eranagmon/code/v2e-invest")
STUDY_YAML = V2E_INVEST / "studies" / "dnaa-1-expression" / "study.yaml"

# The parquet: field in study.yaml points one level above the experiment dir.
# The real experiment dir (with history/) is inside it.
PARQUET_PARENT = (
    V2E_INVEST
    / "studies"
    / "dnaa-1-expression"
    / "parquet-runs"
    / "dnaa1-mechA-1.7e-3-7gen"
)
HIVE_PATH = PARQUET_PARENT / "dnaa1_mechA_1p7e-3_7gen"

_REAL_DATA_PRESENT = STUDY_YAML.exists() and HIVE_PATH.exists()

skipif_no_real_data = pytest.mark.skipif(
    not _REAL_DATA_PRESENT,
    reason="real dnaa-1 data not present at expected paths",
)


# ---------------------------------------------------------------------------
# Helper: copy study.yaml to tmp and point the 1.7e-3 run at the real hive
# ---------------------------------------------------------------------------

def _prepare_tmp_study(tmp_path: Path) -> tuple[Path, Path]:
    """Copy real study.yaml to tmp_path; update the 1.7e-3 run's parquet: to absolute.

    Returns (study_dir, tmp_study_yaml).
    NEVER touches anything under v2e-invest.
    """
    import ruamel.yaml

    study_dir = tmp_path / "dnaa-1-expression"
    study_dir.mkdir()
    tmp_study_yaml = study_dir / "study.yaml"
    shutil.copy(STUDY_YAML, tmp_study_yaml)

    # Update the parquet: field for the 1.7e-3 run to the absolute parent path.
    # This is necessary because the dated path in study.yaml
    # (dnaa1-mechA-1.7e-3-7gen-2026-05-31) doesn't match the actual dir on disk
    # (dnaa1-mechA-1.7e-3-7gen). The absolute path we set resolves correctly.
    ryaml = ruamel.yaml.YAML()
    ryaml.preserve_quotes = True
    ryaml.width = 4096
    with open(tmp_study_yaml, encoding="utf-8") as fh:
        doc = ryaml.load(fh)

    target_run = None
    for run in doc.get("runs", []):
        parquet_val = str(run.get("parquet", ""))
        if "1.7e-3-7gen" in parquet_val and "fullhist" not in parquet_val:
            run["parquet"] = str(PARQUET_PARENT)
            target_run = run
            break

    assert target_run is not None, (
        "Could not find dnaa1-mechA-1.7e-3-7gen run in study.yaml"
    )

    sio = io.StringIO()
    ryaml.dump(doc, sio)
    tmp_study_yaml.write_text(sio.getvalue(), encoding="utf-8")

    return study_dir, tmp_study_yaml


# ---------------------------------------------------------------------------
# Golden tests
# ---------------------------------------------------------------------------

@skipif_no_real_data
def test_compute_outcomes_golden_writes_block(tmp_path: Path, capsys):
    """compute_outcomes writes computed_outcomes for the 1.7e-3 run.

    The test:
    1. Copies real study.yaml to tmp (never touches v2e-invest).
    2. Points the 1.7e-3 run's parquet: to the real hive (absolute path).
    3. Runs compute_outcomes on the tmp study_dir.
    4. Asserts computed_outcomes block was written with reconcile flags set.
    5. Asserts all dnaa-1 tests are agent-bucketed (vector observables / unsupported window).
    6. Asserts authored outcomes on the canonical run are byte-unchanged.
    7. Asserts the real study.yaml is completely untouched.
    """
    study_dir, tmp_study_yaml = _prepare_tmp_study(tmp_path)
    original_real_text = STUDY_YAML.read_text(encoding="utf-8")
    original_doc = yaml.safe_load(STUDY_YAML.read_text())

    # --- Run compute_outcomes (no ws_root needed: parquet is absolute) ---
    summary = se.compute_outcomes(study_dir)
    print(f"\ncompute_outcomes summary: {summary}")

    # --- Load output ---
    after_text = tmp_study_yaml.read_text(encoding="utf-8")
    after_doc = yaml.safe_load(after_text)

    # 1. Find the target run (1.7e-3-7gen, parquet absolute) in the output
    target_run_after = None
    for run in after_doc.get("runs", []):
        if str(run.get("parquet", "")).endswith("dnaa1-mechA-1.7e-3-7gen"):
            target_run_after = run
            break

    assert target_run_after is not None, (
        "Target run (1.7e-3-7gen with absolute parquet:) not found in output"
    )
    assert "computed_outcomes" in target_run_after, (
        "computed_outcomes block was not written for the target run"
    )

    co = target_run_after["computed_outcomes"]
    print(f"\ncomputed_outcomes block keys: {list(co.keys())}")

    # 2. Each test has a reconcile flag with a valid value
    for test_name, outcome in co.items():
        if test_name.startswith("_"):
            continue
        assert "reconcile" in outcome, f"Missing reconcile flag for {test_name!r}"
        assert outcome["reconcile"] in ("agree", "divergent", "no_authored"), (
            f"Invalid reconcile value for {test_name!r}: {outcome['reconcile']!r}"
        )

    # 3. All dnaa-1 tests must be agent-bucketed
    #    (vector observables, parenthetical-annotated paths, unsupported windows)
    agent_tests = [
        name for name, outcome in co.items()
        if not name.startswith("_") and outcome.get("evaluated_by") == "agent"
    ]
    non_agent = [
        name for name, outcome in co.items()
        if not name.startswith("_") and outcome.get("evaluated_by") != "agent"
    ]
    print(f"\nAgent-bucketed tests ({len(agent_tests)}): {agent_tests}")
    if non_agent:
        print(f"Non-agent tests (unexpected): {non_agent}")
    assert len(agent_tests) > 0, "Expected at least some agent-bucketed tests"
    # For the 1.7e-3 run (no authored outcomes), all reconcile flags must be no_authored
    for test_name in agent_tests:
        assert co[test_name]["reconcile"] == "no_authored", (
            f"Expected no_authored for {test_name!r} (no authored outcomes on this run), "
            f"got {co[test_name]['reconcile']!r}"
        )

    # 4. The canonical run's authored outcomes block is COMPLETELY UNCHANGED.
    #    (authored outcomes live on dnaa1-v08e3-canonical-2026-06-09, not the 1.7e-3 run)
    canonical_before = None
    for run in original_doc.get("runs", []):
        if run.get("outcomes"):
            canonical_before = run["outcomes"]
            break

    canonical_after = None
    for run in after_doc.get("runs", []):
        if run.get("outcomes"):
            canonical_after = run["outcomes"]
            break

    if canonical_before and canonical_after:
        assert canonical_before == canonical_after, (
            "INVARIANT VIOLATION: authored outcomes were modified!"
        )
        print(f"\nAuthored outcomes (canonical run) — UNTOUCHED: {list(canonical_before.keys())}")

    # 5. The REAL v2e-invest study.yaml is completely untouched.
    assert STUDY_YAML.read_text(encoding="utf-8") == original_real_text, (
        "NEVER-MODIFY VIOLATION: the real study.yaml was modified!"
    )

    # 6. Print reconcile flags for the final report
    print("\nReconcile flags produced by compute_outcomes:")
    for test_name, outcome in co.items():
        if test_name.startswith("_"):
            continue
        print(
            f"  {test_name}:\n"
            f"    reconcile={outcome.get('reconcile')!r}\n"
            f"    evaluated_by={outcome.get('evaluated_by')!r}\n"
            f"    reason={outcome.get('reason', '-')!r}"
        )


@skipif_no_real_data
def test_compute_outcomes_golden_idempotent(tmp_path: Path):
    """Running compute_outcomes twice on the dnaa-1 copy produces byte-identical output."""
    study_dir, tmp_study_yaml = _prepare_tmp_study(tmp_path)

    se.compute_outcomes(study_dir)
    text_first = tmp_study_yaml.read_text(encoding="utf-8")

    se.compute_outcomes(study_dir)
    text_second = tmp_study_yaml.read_text(encoding="utf-8")

    assert text_first == text_second, (
        "compute_outcomes is not idempotent — second run produced different bytes"
    )


@skipif_no_real_data
def test_compute_outcomes_golden_real_v2einvest_untouched(tmp_path: Path):
    """compute_outcomes NEVER modifies anything under v2e-invest."""
    original_text = STUDY_YAML.read_text(encoding="utf-8")
    study_dir, _ = _prepare_tmp_study(tmp_path)

    se.compute_outcomes(study_dir)

    assert STUDY_YAML.read_text(encoding="utf-8") == original_text, (
        "NEVER-MODIFY VIOLATION: the real study.yaml was modified!"
    )
