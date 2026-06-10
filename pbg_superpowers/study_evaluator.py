"""study_evaluator.py — pure run-data evaluator (B2 increment).

Evaluates study behavior_tests against a RunReader: closed measure/pass_if
DSL → per-test PASS/FAIL/PARTIAL + provenance.  Never writes to study.yaml.

Public API:
    evaluate_study(spec, reader) -> dict[str, dict]
    evaluate_test(test, reader) -> dict

Outcome shapes:
    code path:  {"result": "PASS"|"FAIL", "measured_value": ...,
                 "evaluated_by": "code", "operator": "kind/op", "detail": "..."}
    agent:      {"evaluated_by": "agent", "reason": "..."}
    needs_rerun:{"evaluated_by": "needs_rerun", "reason": "..."}
"""
from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from pbg_emitters import RunReader


# ---------------------------------------------------------------------------
# Closed set: run-data-evaluable measure kinds
# ---------------------------------------------------------------------------

RUN_DATA_KINDS: frozenset[str] = frozenset({
    "range_check_per_generation",
    "generation_average",
    "derived_scalar",
    "per_generation_mass_ratio",
    "oric_initiations_per_generation",
    "rate_match",
    "snapshot_window",
    "count_over_lineage",
    "periodicity_check",
    "per_gen",
})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ObservableNotFound(Exception):
    """Raised when a path token cannot be resolved via RunReader."""


class WindowNotSupported(Exception):
    """Raised when a window spec is not in the closed vocabulary."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_study(spec: dict, reader: "RunReader") -> dict[str, dict]:
    """Evaluate all behavior tests in a study spec.

    Args:
        spec:   study YAML parsed as dict; tests keyed by 'tests' or 'behavior_tests'.
        reader: RunReader opened on the run to evaluate against.

    Returns:
        Mapping from test name → outcome dict.
    """
    tests = spec.get("tests") or spec.get("behavior_tests") or []
    results: dict[str, dict] = {}
    for i, test in enumerate(tests):
        name = test.get("name", f"test_{i}")
        results[name] = evaluate_test(test, reader)
    return results


def evaluate_test(test: dict, reader: "RunReader") -> dict:
    """Evaluate a single behavior test against a run.

    Returns one of:
        code outcome: result + measured_value + evaluated_by + operator + detail
        agent bucket: evaluated_by="agent" + reason
        needs_rerun:  evaluated_by="needs_rerun" + reason
    """
    # 1. Require measure block
    measure = test.get("measure")
    if not measure:
        return _agent("missing measure block")

    # 2. Kind must be in the closed run-data set
    kind = measure.get("kind", "")
    if kind not in RUN_DATA_KINDS:
        return _agent(f"non-run-data kind: {kind!r}")

    # 3. Require pass_if block
    pass_if = test.get("pass_if")
    if not pass_if:
        return _agent("missing pass_if block")

    # 4. Op must be in the closed set
    op = pass_if.get("op", "")
    if not _op_supported(op):
        return _agent(f"unsupported op: {op!r}")

    # 5. Require path/field/formula
    path = (measure.get("path") or measure.get("field") or measure.get("formula") or "").strip()
    if not path:
        return _agent("missing path/field/formula in measure")

    # 6. Validate window before touching the reader
    window_spec = (measure.get("window") or "full_lineage_from_gen_0").strip()
    try:
        _validate_window(window_spec)
    except WindowNotSupported as exc:
        return _agent(str(exc))

    # 7. Resolve the observable series
    try:
        series = _resolve_series(path, reader)
    except ObservableNotFound as exc:
        return _agent(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _agent(f"series resolution error: {exc}")

    # 8. Apply window
    try:
        windowed = _apply_window(series, window_spec)
    except WindowNotSupported as exc:
        return _agent(str(exc))

    # 9. Guard against empty/partial data
    if _is_empty_window(windowed):
        return _needs_rerun("empty or partial series data after windowing")

    # 10. Reduce + predicate → outcome
    try:
        return _apply_op(windowed, pass_if, kind, op)
    except Exception as exc:  # noqa: BLE001
        return _agent(f"evaluation error: {exc}")


# ---------------------------------------------------------------------------
# Bucket constructors
# ---------------------------------------------------------------------------

def _agent(reason: str) -> dict:
    return {"evaluated_by": "agent", "reason": reason}


def _needs_rerun(reason: str) -> dict:
    return {"evaluated_by": "needs_rerun", "reason": reason}


def _code_outcome(result: str, measured_value: Any, operator: str, detail: str) -> dict:
    return {
        "result": result,
        "measured_value": measured_value,
        "evaluated_by": "code",
        "operator": operator,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Path / expression resolver
# ---------------------------------------------------------------------------

# Regex for dotted identifiers (e.g. listeners.mass.cell_mass, obs_name, DnaA)
_DOTTED_IDENT = re.compile(r"[A-Za-z_]\w*(?:\.\w+)*")

# Regex for molecule/bulk IDs with brackets (e.g. MONOMER0-160[c], PD03831[c])
# Must match BEFORE the plain ident pattern so the bracket part is captured.
_BRACKET_ID = re.compile(r"[A-Z][A-Z0-9_]*(?:-[A-Z0-9]+)*\[[a-z]+\]")


def _extract_observable_tokens(path: str) -> list[str]:
    """Extract all identifier tokens from an expression/path string.

    Returns unique tokens in order of first appearance.  Both dotted paths
    (listeners.mass.cell_mass) and bracketed molecule IDs (MONOMER0-160[c])
    are recognised.
    """
    seen: set[str] = set()
    tokens: list[str] = []

    # Find bracket-style molecule IDs first
    bracket_spans: set[int] = set()
    for m in _BRACKET_ID.finditer(path):
        tok = m.group(0)
        bracket_spans.update(range(m.start(), m.end()))
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)

    # Then find dotted/simple identifiers, skipping already-matched spans
    for m in _DOTTED_IDENT.finditer(path):
        if any(i in bracket_spans for i in range(m.start(), m.end())):
            continue
        tok = m.group(0)
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)

    return tokens


def _resolve_series(path: str, reader: "RunReader") -> pl.DataFrame:
    """Resolve an observable path or arithmetic expression to a series.

    Args:
        path:   Observable path (e.g. ``listeners.mass.cell_mass``) or a
                simple arithmetic expression over observables
                (e.g. ``a / (b + c)``).  Literal numbers (``* 2``) are allowed.
        reader: RunReader opened on the target run.

    Returns:
        Polars DataFrame with columns ``[generation, time, abs_time, value]``.

    Raises:
        ObservableNotFound: If any token in *path* cannot be resolved via
            the reader (KeyError or any other exception from ``series()``).
    """
    tokens = _extract_observable_tokens(path)
    if not tokens:
        raise ObservableNotFound(f"no observable tokens found in path: {path!r}")

    # Resolve each token — fail fast on the first that cannot be fetched
    resolved: dict[str, pl.DataFrame] = {}
    for token in tokens:
        try:
            s = reader.series(token)
            resolved[token] = s
        except KeyError:
            raise ObservableNotFound(f"observable {token!r} not resolvable")
        except Exception as exc:  # noqa: BLE001
            raise ObservableNotFound(f"observable {token!r} not resolvable: {exc}") from exc

    # If there is exactly one observable AND the path is just that token
    # (no surrounding arithmetic), return the series directly.
    if len(resolved) == 1:
        sole_token = list(resolved.keys())[0]
        if path.strip() == sole_token:
            return list(resolved.values())[0]

    # Either multiple observables OR a single observable embedded in an
    # arithmetic expression (e.g. "obs.a / 2") → evaluate the full expression.
    return _eval_expression(path, resolved)


def _eval_expression(expr: str, token_series: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Evaluate a multi-observable arithmetic expression over aligned series.

    Substitutes each token with a safe Python identifier ``_v0``, ``_v1``, …,
    parses the result with :py:func:`ast.parse`, and evaluates it using numpy
    array arithmetic — no ``eval`` of user-supplied code.
    """
    import numpy as np

    keys = list(token_series.keys())

    # Build substituted expression string (_v0, _v1, …) for ast.parse
    subst = expr
    for i, token in enumerate(keys):
        subst = subst.replace(token, f"_v{i}")

    # Align all series on (generation, abs_time) via inner join
    first = token_series[keys[0]]
    joined = first.rename({"value": "_v0"})
    for i, token in enumerate(keys[1:], 1):
        other = token_series[token].select(
            ["generation", "abs_time", pl.col("value").alias(f"_v{i}")]
        )
        joined = joined.join(other, on=["generation", "abs_time"], how="inner")

    # Collect numpy arrays for each variable
    np_vars: dict[str, np.ndarray] = {
        f"_v{i}": joined[f"_v{i}"].to_numpy() for i in range(len(keys))
    }

    # Safe AST evaluation
    try:
        tree = ast.parse(subst, mode="eval")
        result_vals: Any = _eval_ast_node(tree.body, np_vars)
    except Exception as exc:
        raise ObservableNotFound(f"expression evaluation failed: {exc}") from exc

    if not isinstance(result_vals, np.ndarray):
        result_vals = np.full(len(joined), float(result_vals))

    return joined.select(["generation", "time", "abs_time"]).with_columns(
        pl.Series("value", result_vals, dtype=pl.Float64)
    )


def _eval_ast_node(node: ast.expr, names: dict) -> Any:
    """Safely evaluate an AST expression node using only arithmetic operations.

    Allowed node types: Constant, Name, BinOp (+, -, *, /), UnaryOp (+, -).
    All other node types raise :py:exc:`ValueError`.
    """
    import numpy as np

    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise ValueError(f"unknown variable {node.id!r}")
        return names[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left, names)
        right = _eval_ast_node(node.right, names)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        raise ValueError(f"unsupported operator: {type(op).__name__}")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand, names)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
    raise ValueError(f"unsupported AST node type: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Window vocabulary
# ---------------------------------------------------------------------------

_FROM_GEN_RE = re.compile(r"^from_generation_(\d+)$")
_PEAK_FROM_GEN_RE = re.compile(r"^peak_of_each_cycle_from_gen_(\d+)$")

_KNOWN_WINDOWS = frozenset({
    "full_lineage_from_gen_0",
    "every_generation",
    "peak_of_each_cycle",
    "gen_steady_state",
})


def _validate_window(window_spec: str) -> None:
    """Raise WindowNotSupported if the window is not in the closed vocabulary."""
    if window_spec in _KNOWN_WINDOWS:
        return
    if _FROM_GEN_RE.match(window_spec):
        return
    if _PEAK_FROM_GEN_RE.match(window_spec):
        return
    raise WindowNotSupported(f"unsupported window: {window_spec!r}")


# WindowResult type: tuple of (kind_str, data)
#   ("flat",           pl.DataFrame)          — flat series (all ticks)
#   ("per_gen_all",    dict[int, pl.DataFrame])— one DF per gen (all ticks of that gen)
#   ("per_gen_scalar", dict[int, float])       — one scalar per gen

def _apply_window(series: pl.DataFrame, window_spec: str) -> tuple:
    """Apply window to a series DataFrame.

    Returns a ``(kind, data)`` tuple for downstream consumption.

    Raises:
        WindowNotSupported: for unrecognised window specs.
    """
    if window_spec == "full_lineage_from_gen_0":
        return ("flat", series)

    if window_spec == "every_generation":
        from pbg_emitters import by_generation
        return ("per_gen_all", by_generation(series))

    m = _FROM_GEN_RE.match(window_spec)
    if m:
        n = int(m.group(1))
        return ("flat", series.filter(pl.col("generation") >= n))

    if window_spec == "gen_steady_state":
        return ("flat", series.filter(pl.col("generation") >= 3))

    if window_spec == "peak_of_each_cycle":
        peaks = (
            series
            .group_by("generation")
            .agg(pl.col("value").max().alias("value"))
            .sort("generation")
        )
        return ("per_gen_scalar", {int(g): float(v) for g, v in peaks.iter_rows()})

    m2 = _PEAK_FROM_GEN_RE.match(window_spec)
    if m2:
        n = int(m2.group(1))
        filtered = series.filter(pl.col("generation") >= n)
        peaks = (
            filtered
            .group_by("generation")
            .agg(pl.col("value").max().alias("value"))
            .sort("generation")
        )
        return ("per_gen_scalar", {int(g): float(v) for g, v in peaks.iter_rows()})

    raise WindowNotSupported(f"unsupported window: {window_spec!r}")


def _is_empty_window(windowed: tuple) -> bool:
    """Return True if the windowed result contains no data."""
    kind, data = windowed
    if kind == "flat":
        return len(data) == 0
    return len(data) == 0  # works for both dict types


# ---------------------------------------------------------------------------
# Closed pass_if operator set
# ---------------------------------------------------------------------------

_SUPPORTED_OPS: frozenset[str] = frozenset({
    "range",
    "in_range",
    "in_range_every_generation",
    "generation_average_in_range",
    "<=", ">=", "<", ">", "==", "!=", "eq",
    "in_set",
    "cv_below",
    "median_within_tolerance",
    "periodic_doubling_every_generation",
    "exactly_one_initiation_per_generation",
})


def _op_supported(op: str) -> bool:
    return op in _SUPPORTED_OPS


def _flat_values(data: Any, window_kind: str) -> list[float]:
    """Extract a flat list of float values from a windowed result."""
    if window_kind == "flat":
        return data["value"].cast(pl.Float64).to_list()
    if window_kind == "per_gen_scalar":
        return list(data.values())
    if window_kind == "per_gen_all":
        vals: list[float] = []
        for df in data.values():
            vals.extend(df["value"].cast(pl.Float64).to_list())
        return vals
    return []


def _apply_op(windowed: tuple, pass_if: dict, kind: str, op: str) -> dict:
    """Apply a pass_if predicate to windowed data.

    Returns a code outcome dict or an agent/needs_rerun dict.
    """
    window_kind, data = windowed
    label = f"{kind}/{op}"

    # -- range / in_range --
    if op in ("range", "in_range"):
        vals = _flat_values(data, window_kind)
        measured = float(pl.Series(vals, dtype=pl.Float64).mean())
        low = float(pass_if["low"])
        high = float(pass_if["high"])
        ok = low <= measured <= high
        return _code_outcome(
            result="PASS" if ok else "FAIL",
            measured_value=round(measured, 6),
            operator=label,
            detail=(f"{measured:.4g} in [{low}, {high}]" if ok
                    else f"{measured:.4g} not in [{low}, {high}]"),
        )

    # -- in_range_every_generation / generation_average_in_range --
    if op in ("in_range_every_generation", "generation_average_in_range"):
        low = float(pass_if["low"])
        high = float(pass_if["high"])

        if window_kind == "per_gen_scalar":
            gen_vals: dict[int, float] = data
        elif window_kind == "per_gen_all":
            gen_vals = {g: float(df["value"].cast(pl.Float64).mean())
                        for g, df in data.items()}
        elif window_kind == "flat":
            gen_vals = {}
            for g in sorted(data["generation"].unique().to_list()):
                sub = data.filter(pl.col("generation") == g)
                gen_vals[int(g)] = float(sub["value"].cast(pl.Float64).mean())
        else:
            return _agent(f"unexpected window kind for {op}: {window_kind!r}")

        if not gen_vals:
            return _needs_rerun("no generation data for in_range_every_generation")

        per_gen: dict[int, tuple[bool, float]] = {
            g: (low <= v <= high, v) for g, v in gen_vals.items()
        }
        all_pass = all(ok for ok, _ in per_gen.values())
        failing = [(g, round(v, 3)) for g, (ok, v) in per_gen.items() if not ok]

        return _code_outcome(
            result="PASS" if all_pass else "FAIL",
            measured_value={g: round(v, 4) for g, (_, v) in per_gen.items()},
            operator=label,
            detail=(f"all {len(gen_vals)} gens in [{low}, {high}]" if all_pass
                    else f"gens out of [{low}, {high}]: {failing}"),
        )

    # -- scalar comparators --
    if op in ("<=", ">=", "<", ">", "==", "!=", "eq"):
        vals = _flat_values(data, window_kind)
        measured = float(pl.Series(vals, dtype=pl.Float64).mean())
        target = float(pass_if.get("value", 0))
        effective_op = "==" if op == "eq" else op
        comparators = {
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
            "<":  lambda a, b: a < b,
            ">":  lambda a, b: a > b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        ok = comparators[effective_op](measured, target)
        return _code_outcome(
            result="PASS" if ok else "FAIL",
            measured_value=round(measured, 6),
            operator=label,
            detail=f"{measured:.4g} {effective_op} {target}",
        )

    # -- in_set --
    if op == "in_set":
        vals = _flat_values(data, window_kind)
        measured = float(pl.Series(vals, dtype=pl.Float64).mean())
        target_set = set(pass_if.get("set", []))
        ok = measured in target_set
        return _code_outcome(
            result="PASS" if ok else "FAIL",
            measured_value=round(measured, 6),
            operator=label,
            detail=(f"{measured} in {target_set}" if ok
                    else f"{measured} not in {target_set}"),
        )

    # -- cv_below --
    if op == "cv_below":
        vals = _flat_values(data, window_kind)
        if len(vals) < 2:
            return _needs_rerun("too few data points to compute CV")
        s = pl.Series(vals, dtype=pl.Float64)
        mean_val = float(s.mean())
        if mean_val == 0.0:
            return _agent("cannot compute CV: mean is zero")
        std_val = float(s.std())
        cv = std_val / abs(mean_val)
        threshold = float(pass_if["cv_threshold"])
        ok = cv < threshold
        return _code_outcome(
            result="PASS" if ok else "FAIL",
            measured_value=round(cv, 6),
            operator=label,
            detail=f"CV={cv:.4f} {'<' if ok else '>='} {threshold}",
        )

    # -- median_within_tolerance --
    if op == "median_within_tolerance":
        vals = _flat_values(data, window_kind)
        if not vals:
            return _needs_rerun("empty series for median_within_tolerance")
        median_val = float(pl.Series(vals, dtype=pl.Float64).median())
        target = float(pass_if["target"])
        tol = float(pass_if["tolerance_fraction"])
        if target == 0.0:
            return _agent("cannot compute median_within_tolerance: target is zero")
        rel_err = abs(median_val - target) / abs(target)
        ok = rel_err <= tol
        return _code_outcome(
            result="PASS" if ok else "FAIL",
            measured_value=round(median_val, 6),
            operator=label,
            detail=(f"median={median_val:.4g}, "
                    f"|{median_val:.4g}-{target}|/|{target}|={rel_err:.4f} "
                    f"{'<=' if ok else '>'} {tol}"),
        )

    # -- periodic_doubling_every_generation --
    if op == "periodic_doubling_every_generation":
        tol = float(pass_if.get("tolerance", 0.2))

        if window_kind == "per_gen_all":
            gen_data: dict[int, pl.DataFrame] = data
        elif window_kind == "flat":
            from pbg_emitters import by_generation
            gen_data = by_generation(data)
        else:
            return _agent(f"periodic_doubling requires per-gen data, got: {window_kind!r}")

        if not gen_data:
            return _needs_rerun("no generation data for periodic_doubling")

        per_gen_ratios: dict[int, float] = {}
        for g, df in gen_data.items():
            arr = df["value"].cast(pl.Float64).to_numpy()
            if len(arr) < 2:
                continue
            min_v = float(arr.min())
            max_v = float(arr.max())
            if min_v <= 0.0:
                per_gen_ratios[g] = float("nan")
            else:
                per_gen_ratios[g] = max_v / min_v

        # Exclude NaN entries
        valid = {g: r for g, r in per_gen_ratios.items() if r == r}  # nan != nan
        if not valid:
            return _needs_rerun("insufficient per-gen data for periodic_doubling")

        per_gen_ok = {g: (abs(r - 2.0) <= tol * 2.0, r) for g, r in valid.items()}
        all_pass = all(ok for ok, _ in per_gen_ok.values())
        failing = [(g, round(r, 3)) for g, (ok, r) in per_gen_ok.items() if not ok]

        return _code_outcome(
            result="PASS" if all_pass else "FAIL",
            measured_value={g: round(r, 4) for g, (_, r) in per_gen_ok.items()},
            operator=label,
            detail=(f"all gens: doubling ratio within {tol * 2.0:.2f} of 2.0" if all_pass
                    else f"gens outside tolerance: {failing}"),
        )

    # -- exactly_one_initiation_per_generation --
    if op == "exactly_one_initiation_per_generation":
        if window_kind == "per_gen_all":
            gen_data_2: dict[int, pl.DataFrame] = data
        elif window_kind == "flat":
            from pbg_emitters import by_generation
            gen_data_2 = by_generation(data)
        else:
            return _agent(f"exactly_one_initiation requires per-gen data, got: {window_kind!r}")

        if not gen_data_2:
            return _needs_rerun("no generation data for exactly_one_initiation")

        per_gen_counts = {g: float(df["value"].cast(pl.Float64).sum())
                          for g, df in gen_data_2.items()}
        per_gen_ok_2 = {g: (c == 1.0, c) for g, c in per_gen_counts.items()}
        all_pass_2 = all(ok for ok, _ in per_gen_ok_2.values())
        failing_2 = [(g, c) for g, (ok, c) in per_gen_ok_2.items() if not ok]

        return _code_outcome(
            result="PASS" if all_pass_2 else "FAIL",
            measured_value={g: c for g, (_, c) in per_gen_ok_2.items()},
            operator=label,
            detail=("all gens have exactly 1 initiation" if all_pass_2
                    else f"gens with != 1 initiation: {failing_2}"),
        )

    # Should never reach here — _op_supported guards above
    return _agent(f"unhandled op: {op!r}")
