"""Calibration-sweep helper — a parameter grid × multiseed in ONE pass.

Recurring expert-feedback friction (dnaa-replication, pattern #8 in
``docs/conventions/expert-feedback-friction-analysis.md``): the agent tunes a
calibration knob *one value at a time* — "try 1.2e / still overshooting / try
other v + multiseed" — burning the expert's review budget on a search the
framework should do upfront. The ask is concrete: run a parameter grid across
seeds in one pass and report the in-band choice.

This module is the generic engine for that. It is **pure and sim-agnostic**:
the caller supplies a :class:`SweepSpec` (a parameter grid, the seeds, and an
acceptance band on a scalar metric) plus an injected ``run_fn(params, seed) ->
float``. In tests ``run_fn`` is a pure synthetic function with a known optimum;
in real use it is a thin adapter over a study runner (see the module docstring
in the wiring notes / the ``pbg_runner`` seam in ``runner.py``).

It mirrors :mod:`pbg_superpowers.ablation`: orchestration (enumerate the grid,
run each point across seeds, aggregate, score, rank) is fully separated from
execution (the injected ``run_fn``), so the decision logic is deterministic and
unit-testable without touching a simulator.

Storage shape (the model writes the recommendation into ``study.yaml`` — e.g.
as an ``enforced_params`` entry or a chosen variant)::

    calibration_sweep:
      metric: dnaa_atp_pool
      band: [800, 1200]
      window: gen_steady_state
      recommended: {v: 1.4e-3}        # the in-band point
      points:
        - {params: {v: 1.2e-3}, mean: 1450.0, spread: 30.0, in_band: false, ...}
        - {params: {v: 1.4e-3}, mean: 1010.0, spread: 22.0, in_band: true,  ...}
"""
from __future__ import annotations

import itertools
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


__all__ = [
    "AcceptanceBand",
    "SweepSpec",
    "GridPointResult",
    "SweepResult",
    "enumerate_grid",
    "run_sweep",
    "summarize",
]


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AcceptanceBand:
    """A closed band ``[low, high]`` on a scalar metric.

    ``window`` is informational provenance (e.g. ``"gen_steady_state"``) — the
    evaluation window the ``run_fn`` is expected to reduce the metric over. The
    engine never reads it; it is carried through into the result and report so
    the recommendation records *where* the metric was measured.
    """

    metric: str
    low: float
    high: float
    window: str | None = None

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(
                f"AcceptanceBand: high ({self.high}) < low ({self.low})")

    @property
    def width(self) -> float:
        return float(self.high) - float(self.low)

    @property
    def center(self) -> float:
        return (float(self.low) + float(self.high)) / 2.0

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def margin(self, value: float) -> float:
        """Signed distance to the *nearest* band edge.

        Positive when ``value`` is inside the band (how comfortably it sits —
        larger = more robust to drift); zero on an edge; negative outside
        (the gap to the nearest edge, as a negative number)."""
        return min(value - self.low, self.high - value)

    def margin_frac(self, value: float) -> float:
        """:meth:`margin` normalized by the band half-width — scale-free.

        ``1.0`` = dead-centre, ``0.0`` = on an edge, ``< 0`` = outside. A
        degenerate point band (width 0) yields ``0.0`` inside, ``-inf`` outside
        so any in-band point still outranks any out-of-band point."""
        half = self.width / 2.0
        m = self.margin(value)
        if half == 0.0:
            return 0.0 if m == 0.0 else float("-inf")
        return m / half

    def distance(self, value: float) -> float:
        """Unsigned distance from ``value`` to the band (0.0 when inside)."""
        if self.contains(value):
            return 0.0
        return self.low - value if value < self.low else value - self.high


@dataclass(frozen=True)
class SweepSpec:
    """A calibration sweep: a parameter grid × seeds, scored against a band.

    Args:
        grid: ``{param_name: [values...]}``. One or more params. With
            ``grid_mode="cartesian"`` (default) the sweep runs the full
            cartesian product; with ``"zipped"`` it runs the element-wise zip
            (all value lists must share one length) — useful for coupled knobs
            that move together.
        seeds: the seeds to repeat each grid point over (multiseed). Each grid
            point is scored on the across-seed aggregate, not a single draw.
        band: the :class:`AcceptanceBand` the aggregated metric must fall in.
        grid_mode: ``"cartesian"`` | ``"zipped"``.
    """

    grid: Mapping[str, Sequence[Any]]
    seeds: Sequence[int]
    band: AcceptanceBand
    grid_mode: str = "cartesian"

    def __post_init__(self) -> None:
        if self.grid_mode not in ("cartesian", "zipped"):
            raise ValueError(
                f"grid_mode must be 'cartesian' or 'zipped', got {self.grid_mode!r}")
        if not self.grid:
            raise ValueError("SweepSpec.grid is empty — nothing to sweep")
        for name, values in self.grid.items():
            if not isinstance(values, (list, tuple)) or len(values) == 0:
                raise ValueError(
                    f"grid[{name!r}] must be a non-empty list of values")
        if self.grid_mode == "zipped":
            lengths = {len(v) for v in self.grid.values()}
            if len(lengths) != 1:
                raise ValueError(
                    "grid_mode='zipped' requires all value lists to share one "
                    f"length; got {{name: len}} = "
                    f"{ {k: len(v) for k, v in self.grid.items()} }")
        if not self.seeds:
            raise ValueError("SweepSpec.seeds is empty — need at least one seed")


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------

@dataclass
class GridPointResult:
    """One grid point's aggregate across all seeds."""

    params: dict[str, Any]
    seed_values: dict[int, float]   # {seed: metric value}
    mean: float
    spread: float                   # population stdev across seeds (0 for n=1)
    n_seeds: int
    seeds_in_band: int              # how many individual seeds landed in band
    in_band: bool                   # is the *aggregate* (mean) in band?
    margin: float                   # band.margin(mean) — signed, raw units
    margin_frac: float              # band.margin_frac(mean) — scale-free
    distance: float                 # band.distance(mean) — 0 inside

    def as_dict(self) -> dict:
        return {
            "params": dict(self.params),
            "mean": self.mean,
            "spread": self.spread,
            "n_seeds": self.n_seeds,
            "seeds_in_band": self.seeds_in_band,
            "in_band": self.in_band,
            "margin": self.margin,
            "margin_frac": self.margin_frac,
            "distance": self.distance,
        }


@dataclass
class SweepResult:
    """The full sweep outcome: every point, ranked, with a recommendation."""

    band: AcceptanceBand
    points: list[GridPointResult]            # in grid-enumeration order
    ranked: list[GridPointResult]            # best first
    recommended: GridPointResult | None      # top in-band point, or None
    ties: list[GridPointResult] = field(default_factory=list)
    status: str = "none_in_band"             # recommended | tie | none_in_band

    @property
    def n_in_band(self) -> int:
        return sum(1 for p in self.points if p.in_band)

    @property
    def nearest(self) -> GridPointResult | None:
        """The point closest to the band (the ``recommended`` one when some
        point is in band; otherwise the least-out-of-band point — the hint for
        where to widen the grid)."""
        return self.ranked[0] if self.ranked else None

    def as_dict(self) -> dict:
        return {
            "metric": self.band.metric,
            "band": [self.band.low, self.band.high],
            "window": self.band.window,
            "status": self.status,
            "recommended": (
                dict(self.recommended.params) if self.recommended else None),
            "ties": [dict(p.params) for p in self.ties],
            "n_in_band": self.n_in_band,
            "points": [p.as_dict() for p in self.points],
        }


# ---------------------------------------------------------------------------
# Grid enumeration
# ---------------------------------------------------------------------------

def enumerate_grid(
    grid: Mapping[str, Sequence[Any]], mode: str = "cartesian"
) -> list[dict[str, Any]]:
    """Expand a parameter grid into a list of concrete ``{param: value}`` points.

    ``mode="cartesian"`` → the full product (every combination). ``mode="zipped"``
    → element-wise (the i-th value of every param together); all value lists
    must share one length. Insertion order of ``grid`` is preserved, so the
    enumeration is deterministic.
    """
    names = list(grid.keys())
    value_lists = [list(grid[n]) for n in names]
    if mode == "cartesian":
        combos: Iterable[tuple] = itertools.product(*value_lists)
    elif mode == "zipped":
        combos = zip(*value_lists)
    else:
        raise ValueError(f"unknown grid mode {mode!r}")
    return [dict(zip(names, combo)) for combo in combos]


def _point_sort_key(params: Mapping[str, Any]) -> str:
    """Deterministic tiebreak key — params as a sorted JSON string."""
    return json.dumps(params, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Aggregation + scoring
# ---------------------------------------------------------------------------

def _aggregate_point(
    params: dict[str, Any],
    seeds: Sequence[int],
    band: AcceptanceBand,
    run_fn: Callable[[dict[str, Any], int], float],
) -> GridPointResult:
    """Run one grid point across all seeds and reduce to a scored record."""
    seed_values: dict[int, float] = {}
    for seed in seeds:
        seed_values[seed] = float(run_fn(dict(params), seed))

    values = list(seed_values.values())
    mean = statistics.fmean(values)
    spread = statistics.pstdev(values) if len(values) > 1 else 0.0
    seeds_in_band = sum(1 for v in values if band.contains(v))

    return GridPointResult(
        params=dict(params),
        seed_values=seed_values,
        mean=mean,
        spread=spread,
        n_seeds=len(values),
        seeds_in_band=seeds_in_band,
        in_band=band.contains(mean),
        margin=band.margin(mean),
        margin_frac=band.margin_frac(mean),
        distance=band.distance(mean),
    )


def _rank_key(p: GridPointResult) -> tuple:
    """Total order for ranking, best first (use as ``sorted`` key).

    1. in-band points before out-of-band (``not in_band`` ascending).
    2. larger margin_frac first (most comfortably centred → robust to drift).
       For out-of-band points margin_frac is negative, so the least-bad
       (closest to the band) sorts first among them too.
    3. tighter spread first (more reproducible across seeds).
    4. deterministic params tiebreak so equal points never reorder.
    """
    return (
        not p.in_band,
        -p.margin_frac,
        p.spread,
        _point_sort_key(p.params),
    )


def _find_ties(ranked: list[GridPointResult], *, rel_tol: float, abs_tol: float
               ) -> list[GridPointResult]:
    """In-band points statistically indistinguishable from the best one.

    A tie = same in-band status AND margin_frac AND spread within tolerance as
    the top-ranked point. Returns [] when there is no genuine tie (the best
    point is strictly better). The returned list INCLUDES the best point."""
    if not ranked or not ranked[0].in_band:
        return []
    best = ranked[0]
    tied = [best]
    for p in ranked[1:]:
        if not p.in_band:
            break
        if (math.isclose(p.margin_frac, best.margin_frac, rel_tol=rel_tol, abs_tol=abs_tol)
                and math.isclose(p.spread, best.spread, rel_tol=rel_tol, abs_tol=abs_tol)):
            tied.append(p)
        else:
            break
    return tied if len(tied) > 1 else []


# ---------------------------------------------------------------------------
# Public API: run_sweep
# ---------------------------------------------------------------------------

def run_sweep(
    spec: SweepSpec,
    run_fn: Callable[[dict[str, Any], int], float],
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-12,
) -> SweepResult:
    """Execute a calibration sweep in one pass and recommend the in-band point.

    Enumerates ``spec.grid`` (cartesian or zipped), runs every grid point across
    every seed via the injected ``run_fn(params, seed) -> float``, aggregates
    each point across its seeds (mean + spread), scores each against
    ``spec.band``, and ranks them.

    The recommendation is the in-band point with the largest scale-free margin
    (most comfortably centred in the band → most robust to drift), breaking ties
    by the tightest across-seed spread. When several in-band points are
    statistically indistinguishable (margin and spread equal within tolerance)
    they are reported in ``result.ties`` and ``status == "tie"``. When NO point's
    aggregate falls in the band, ``recommended is None`` and
    ``status == "none_in_band"`` — ``result.nearest`` then points at the closest
    grid point (the hint for where to widen the grid).

    Pure orchestration: deterministic given a deterministic ``run_fn``.
    """
    points = [
        _aggregate_point(params, list(spec.seeds), spec.band, run_fn)
        for params in enumerate_grid(spec.grid, spec.grid_mode)
    ]

    ranked = sorted(points, key=_rank_key)

    in_band = [p for p in ranked if p.in_band]
    recommended = in_band[0] if in_band else None
    ties = _find_ties(ranked, rel_tol=rel_tol, abs_tol=abs_tol)

    if recommended is None:
        status = "none_in_band"
    elif ties:
        status = "tie"
    else:
        status = "recommended"

    return SweepResult(
        band=spec.band,
        points=points,
        ranked=ranked,
        recommended=recommended,
        ties=ties,
        status=status,
    )


# ---------------------------------------------------------------------------
# Public API: summarize
# ---------------------------------------------------------------------------

def _fmt(x: float) -> str:
    """Compact numeric formatting for the report table."""
    if isinstance(x, float) and (abs(x) >= 1e4 or (0 < abs(x) < 1e-3)):
        return f"{x:.3g}"
    return f"{x:.4g}" if isinstance(x, float) else str(x)


def _fmt_params(params: Mapping[str, Any]) -> str:
    return ", ".join(f"{k}={_fmt(v)}" for k, v in params.items())


def summarize(result: SweepResult) -> str:
    """Format a sweep result as a small report-ready table + one-line verdict.

    The table lists every grid point best-first: params, across-seed mean ±
    spread, seeds-in-band, and the scale-free margin. The final line is the
    recommendation (or a 'none in band' / 'tie' note)."""
    band = result.band
    where = f" @ {band.window}" if band.window else ""
    lines: list[str] = []
    lines.append(
        f"Calibration sweep — metric '{band.metric}'{where}, "
        f"band [{_fmt(band.low)}, {_fmt(band.high)}]")

    header = f"{'':2}{'params':<28}{'mean':>12}{'spread':>10}{'in-band':>9}{'margin':>9}"
    lines.append(header)
    lines.append("-" * len(header))
    rec = result.recommended
    tie_set = {id(p) for p in result.ties}
    for p in result.ranked:
        if rec is not None and id(p) == id(rec):
            mark = "* "
        elif id(p) in tie_set:
            mark = "~ "
        else:
            mark = "  "
        seeds_frac = f"{p.seeds_in_band}/{p.n_seeds}"
        flag = "yes" if p.in_band else "no"
        lines.append(
            f"{mark}{_fmt_params(p.params):<28}"
            f"{_fmt(p.mean):>12}{_fmt(p.spread):>10}"
            f"{flag:>4}({seeds_frac:>3}){p.margin_frac:>9.3g}")

    lines.append("")
    if result.status == "recommended" and rec is not None:
        lines.append(
            f"Recommendation: {_fmt_params(rec.params)} "
            f"(mean {_fmt(rec.mean)} ± {_fmt(rec.spread)}, "
            f"{rec.seeds_in_band}/{rec.n_seeds} seeds in band).")
    elif result.status == "tie" and rec is not None:
        tied = " | ".join(_fmt_params(p.params) for p in result.ties)
        lines.append(
            f"Recommendation: {_fmt_params(rec.params)} "
            f"(TIE — {len(result.ties)} points indistinguishable: {tied}; "
            f"picked by deterministic tiebreak).")
    else:
        near = result.nearest
        hint = (f" Closest point: {_fmt_params(near.params)} "
                f"(mean {_fmt(near.mean)}, distance {_fmt(near.distance)} "
                f"from band) — widen the grid toward it."
                if near is not None else "")
        lines.append(f"Recommendation: NONE in band.{hint}")

    return "\n".join(lines)
