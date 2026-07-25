"""Tests for the calibration-sweep engine (viva_superpowers.calibration_sweep).

The injected ``run_fn`` is always a pure, deterministic synthetic function with
a known optimum, so the sweep's decision logic can be asserted exactly without
touching a simulator.
"""
import math

import pytest

from viva_superpowers.calibration_sweep import (
    AcceptanceBand,
    SweepSpec,
    enumerate_grid,
    run_sweep,
    summarize,
)


# ---------------------------------------------------------------------------
# Synthetic run_fns with known optima
# ---------------------------------------------------------------------------

def linear_metric(params, seed):
    """metric = 1000 * v, with a tiny deterministic per-seed jitter.

    For v in {1.0, 1.1, 1.2} the means are 1000, 1100, 1200. A band of
    [1050, 1150] admits only v=1.1. Jitter is seed-deterministic (no RNG) so
    the whole sweep is reproducible."""
    v = params["v"]
    jitter = (seed % 3 - 1) * 0.5   # -0.5, 0.0, +0.5 cycling — mean ~0
    return 1000.0 * v + jitter


def coupled_metric(params, seed):
    """metric depends on two coupled knobs a, b (for the zipped-grid test)."""
    return 100.0 * params["a"] + 10.0 * params["b"]


# ---------------------------------------------------------------------------
# enumerate_grid
# ---------------------------------------------------------------------------

def test_enumerate_grid_cartesian():
    pts = enumerate_grid({"a": [1, 2], "b": [10, 20]}, mode="cartesian")
    assert pts == [
        {"a": 1, "b": 10},
        {"a": 1, "b": 20},
        {"a": 2, "b": 10},
        {"a": 2, "b": 20},
    ]


def test_enumerate_grid_zipped():
    pts = enumerate_grid({"a": [1, 2, 3], "b": [10, 20, 30]}, mode="zipped")
    assert pts == [{"a": 1, "b": 10}, {"a": 2, "b": 20}, {"a": 3, "b": 30}]


def test_enumerate_grid_single_param():
    pts = enumerate_grid({"v": [1.0, 1.1, 1.2]})
    assert pts == [{"v": 1.0}, {"v": 1.1}, {"v": 1.2}]


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------

def test_band_rejects_inverted():
    with pytest.raises(ValueError):
        AcceptanceBand("m", 10.0, 5.0)


def test_spec_rejects_unequal_zipped_lengths():
    with pytest.raises(ValueError):
        SweepSpec(grid={"a": [1, 2], "b": [10]}, seeds=[0],
                  band=AcceptanceBand("m", 0, 1), grid_mode="zipped")


def test_spec_rejects_empty_grid_and_seeds():
    with pytest.raises(ValueError):
        SweepSpec(grid={}, seeds=[0], band=AcceptanceBand("m", 0, 1))
    with pytest.raises(ValueError):
        SweepSpec(grid={"v": [1.0]}, seeds=[], band=AcceptanceBand("m", 0, 1))


# ---------------------------------------------------------------------------
# Band geometry
# ---------------------------------------------------------------------------

def test_band_margin_and_distance():
    band = AcceptanceBand("m", 100.0, 200.0)
    assert band.contains(150.0)
    assert band.margin(150.0) == pytest.approx(50.0)      # centred → half-width
    assert band.margin_frac(150.0) == pytest.approx(1.0)  # dead centre
    assert band.margin_frac(100.0) == pytest.approx(0.0)  # on edge
    assert band.distance(150.0) == 0.0
    assert band.distance(80.0) == pytest.approx(20.0)
    assert band.distance(260.0) == pytest.approx(60.0)
    assert band.margin_frac(80.0) < 0  # outside → negative


# ---------------------------------------------------------------------------
# The core: finds the in-band point
# ---------------------------------------------------------------------------

def test_sweep_finds_in_band_point():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("metric", 1050.0, 1150.0, window="gen_steady_state"),
    )
    result = run_sweep(spec, linear_metric)

    assert result.status == "recommended"
    assert result.recommended is not None
    assert result.recommended.params == {"v": 1.1}
    assert result.n_in_band == 1
    # Aggregate mean ~1100, comfortably inside [1050,1150].
    assert result.recommended.mean == pytest.approx(1100.0, abs=1.0)
    assert result.recommended.in_band is True
    # The other two points are out of band.
    by_v = {p.params["v"]: p for p in result.points}
    assert by_v[1.0].in_band is False
    assert by_v[1.2].in_band is False


def test_sweep_multiseed_aggregation():
    """Mean + spread are computed across the seeds, and each seed's in-band
    membership is counted."""
    spec = SweepSpec(
        grid={"v": [1.1]},
        seeds=[0, 1, 2, 3, 4, 5],
        band=AcceptanceBand("metric", 1050.0, 1150.0),
    )
    result = run_sweep(spec, linear_metric)
    p = result.points[0]
    assert p.n_seeds == 6
    assert p.seeds_in_band == 6           # all jittered values stay in band
    assert p.mean == pytest.approx(1100.0, abs=0.5)
    assert p.spread > 0.0                 # jitter gives a non-zero spread
    # Single-seed spread is 0.
    one = run_sweep(
        SweepSpec(grid={"v": [1.1]}, seeds=[0],
                  band=AcceptanceBand("metric", 1050.0, 1150.0)),
        linear_metric,
    )
    assert one.points[0].spread == 0.0


def test_sweep_picks_most_centred_when_several_in_band():
    """When multiple points qualify, the one most comfortably centred in the
    band (largest margin) wins, not merely the first."""
    # v=1.0->1000, 1.1->1100, 1.2->1200; band centre 1100 → v=1.1 most centred.
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("metric", 950.0, 1250.0),
    )
    result = run_sweep(spec, linear_metric)
    assert result.n_in_band == 3          # all three inside this wide band
    assert result.recommended.params == {"v": 1.1}   # most centred
    # Ranking is best-first by margin.
    assert result.ranked[0].params == {"v": 1.1}


def test_sweep_none_in_band_reports_nearest():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("metric", 5000.0, 6000.0),   # unreachable
    )
    result = run_sweep(spec, linear_metric)
    assert result.status == "none_in_band"
    assert result.recommended is None
    assert result.n_in_band == 0
    # Nearest = the closest point to the band = highest v (1.2 -> 1200).
    assert result.nearest.params == {"v": 1.2}
    assert result.nearest.distance == pytest.approx(3800.0, abs=1.0)


def test_sweep_reports_ties():
    """Two grid points with identical aggregate metric AND spread are reported
    as a tie; the recommendation is still deterministic."""
    # Two distinct params that map to the SAME metric → genuine tie.
    def degenerate(params, seed):
        return 100.0  # constant, no seed/param dependence

    spec = SweepSpec(
        grid={"v": [1.0, 2.0]},
        seeds=[0, 1],
        band=AcceptanceBand("metric", 50.0, 150.0),
    )
    result = run_sweep(spec, degenerate)
    assert result.status == "tie"
    assert len(result.ties) == 2
    assert {p.params["v"] for p in result.ties} == {1.0, 2.0}
    # Tiebreak is deterministic (sorted-params JSON) → v=1.0 wins.
    assert result.recommended.params == {"v": 1.0}


def test_sweep_zipped_two_params():
    """Coupled (zipped) grid: a and b advance together, not as a product."""
    spec = SweepSpec(
        grid={"a": [1.0, 5.0, 9.0], "b": [1.0, 5.0, 9.0]},
        seeds=[0],
        band=AcceptanceBand("metric", 500.0, 600.0),
        grid_mode="zipped",
    )
    result = run_sweep(spec, coupled_metric)
    # zipped → 3 points: (1,1)=110, (5,5)=550, (9,9)=990. Only (5,5) in band.
    assert len(result.points) == 3
    assert result.recommended.params == {"a": 5.0, "b": 5.0}
    assert result.recommended.mean == pytest.approx(550.0)


def test_sweep_cartesian_two_params_count():
    spec = SweepSpec(
        grid={"a": [1.0, 2.0], "b": [1.0, 2.0, 3.0]},
        seeds=[0],
        band=AcceptanceBand("metric", 0.0, 1e9),
        grid_mode="cartesian",
    )
    result = run_sweep(spec, coupled_metric)
    assert len(result.points) == 6   # 2 × 3 cartesian


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_sweep_is_deterministic():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("metric", 1050.0, 1150.0),
    )
    r1 = run_sweep(spec, linear_metric)
    r2 = run_sweep(spec, linear_metric)
    assert r1.as_dict() == r2.as_dict()
    assert summarize(r1) == summarize(r2)


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

def test_summarize_contains_recommendation_and_table():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("dnaa_pool", 1050.0, 1150.0, window="gen_steady_state"),
    )
    text = summarize(run_sweep(spec, linear_metric))
    assert "dnaa_pool" in text
    assert "gen_steady_state" in text
    assert "Recommendation:" in text
    assert "v=1.1" in text
    # Every grid point appears as a row.
    assert text.count("v=") >= 3


def test_summarize_none_in_band_gives_hint():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1]},
        seeds=[0],
        band=AcceptanceBand("metric", 5000.0, 6000.0),
    )
    text = summarize(run_sweep(spec, linear_metric))
    assert "NONE in band" in text
    assert "widen the grid" in text


def test_as_dict_storage_shape():
    spec = SweepSpec(
        grid={"v": [1.0, 1.1, 1.2]},
        seeds=[0, 1, 2],
        band=AcceptanceBand("metric", 1050.0, 1150.0, window="gen_steady_state"),
    )
    d = run_sweep(spec, linear_metric).as_dict()
    assert d["metric"] == "metric"
    assert d["band"] == [1050.0, 1150.0]
    assert d["window"] == "gen_steady_state"
    assert d["status"] == "recommended"
    assert d["recommended"] == {"v": 1.1}
    assert d["n_in_band"] == 1
    assert len(d["points"]) == 3
    assert all({"params", "mean", "spread", "in_band"} <= set(p) for p in d["points"])
