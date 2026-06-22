"""Auto-captured per-run parameter provenance — the exact, resolved parameter
set a run actually used, recorded on the run record and rendered in the report.

Motivation (v2ecoli dnaa-replication expert friction #7, 2026-06-22): the
reviewer repeatedly had to ask *"indicate exactly which parameters were used —
v, kd's, hydrolysis rate"*. The framework already has two adjacent pieces:

* ``enforced_params`` (see :mod:`pbg_superpowers.param_enforcement`) — the
  *declared subset* a study commits to enforcing, plus a gate that verifies
  they were applied; and
* ``runs[].params`` — a *sparse* mechanical mirror of a run's recorded
  ``runs_meta.params_json`` overrides, owned and overwritten by
  :mod:`pbg_superpowers.study_outcomes` on every reconcile.

Neither answers the reviewer's question on its own: ``enforced_params`` is only
the few knobs the author chose to enforce, and ``runs[].params`` is the sparse
override delta (no units, no "what was the effective value"). This module adds
the missing piece: capture the run's **effective, resolved parameter set** —
names + values + units where available — normalize it to a JSON/YAML-safe
shape, and store it under ``runs[].provenance.params`` (a namespace that
parallels the existing ``findings[].provenance`` and, crucially, is *not* in
``study_outcomes._MECHANICAL`` so it survives ``study_outcomes.sync()``).

Design:

* :func:`capture_run_params` is pure and deterministic — it normalizes a
  resolved-state mapping (handling pint/unum quantities, numpy scalars, nested
  containers) into ``{param: {"value": ..., "units": ..., "source": ...}}``.
  The dashboard runner / run-registry record path calls it once per run.
* :func:`write_run_params` stores the captured dict via a ruamel round-trip
  (comments / prose / sibling runs preserved), mirroring
  :func:`pbg_superpowers.study_outcomes._write_runs_preserving_comments`.
* :func:`render_run_params_rows` turns a captured dict (or a whole run record)
  into table-ready rows for the report, flagging the ``enforced`` subset so the
  reviewer sees enforcement status inline. :func:`render_run_params_table_html`
  is a thin convenience that emits those rows as an HTML table.
"""
from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# value normalization (units-aware, JSON/YAML-safe)
# ---------------------------------------------------------------------------

def _coerce_scalar(v: Any) -> Any:
    """Coerce numpy scalars / arrays to plain Python (no hard numpy dep)."""
    try:
        import numpy as np  # local import: numpy is optional
    except ImportError:
        return v
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _split_quantity(v: Any) -> tuple[Any, str | None]:
    """If ``v`` is a units-carrying quantity, return ``(magnitude, unit_str)``;
    otherwise ``(v, None)``.

    Duck-typed so neither pint nor unum is a hard dependency:

    * unum ``Unum`` exposes ``.asNumber()`` + ``.strUnit()``.
    * pint ``Quantity`` exposes ``.magnitude`` + ``.units``.
    """
    if hasattr(v, "asNumber") and hasattr(v, "strUnit"):
        try:
            return v.asNumber(), (v.strUnit() or None)
        except Exception:  # noqa: BLE001 — never let provenance capture raise
            return v, None
    if hasattr(v, "magnitude") and hasattr(v, "units"):
        try:
            return v.magnitude, (str(v.units) or None)
        except Exception:  # noqa: BLE001
            return v, None
    return v, None


def _json_safe(v: Any) -> Any:
    """Recursively coerce ``v`` to a JSON/YAML-serializable value.

    Quantities are flattened to ``"<magnitude> <unit>"`` (nested units would
    otherwise be lost); numpy scalars are unwrapped; containers recurse;
    anything else falls back to ``str``.
    """
    v = _coerce_scalar(v)
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    num, unit = _split_quantity(v)
    if num is not v:  # it was a quantity
        safe = _json_safe(num)
        return f"{safe} {unit}" if unit else safe
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_json_safe(x) for x in v]
    return str(v)


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------

def capture_run_params(
    resolved: dict | None,
    *,
    overrides: Iterable | dict | None = None,
    units: dict | None = None,
    include: Iterable | None = None,
    exclude: Iterable | None = None,
) -> dict:
    """Normalize a run's effective parameter set into a JSON/YAML-safe dict.

    Args:
        resolved: ``{param: value}`` of the run's **effective** parameter set
            (the values actually in force after defaults + overrides resolve).
            Values may be plain numbers / bools / strings, pint or unum
            quantities, numpy scalars, or nested containers.
        overrides: optional param names (a dict or any iterable) the run
            *explicitly set* — used only to tag each param's ``source`` as
            ``"override"`` vs ``"resolved"``.
        units: optional ``{param: unit_str}`` supplying units for params whose
            value does not itself carry them (or overriding a carried unit).
        include / exclude: optional name filters.

    Returns:
        ``{param: {"value": <normalized>, "units": <str> (omitted if None),
        "source": "override" | "resolved"}}``, deterministic in iteration
        order (sorted by param name).
    """
    resolved = dict(resolved or {})
    override_keys = set(overrides or ())
    units_map = dict(units or {})
    include_set = set(include) if include is not None else None
    exclude_set = set(exclude or ())

    out: dict[str, dict] = {}
    for name in sorted(resolved, key=str):
        if include_set is not None and name not in include_set:
            continue
        if name in exclude_set:
            continue
        num, unit = _split_quantity(_coerce_scalar(resolved[name]))
        entry: dict[str, Any] = {"value": _json_safe(num)}
        eff_unit = units_map.get(name) or unit
        if eff_unit:
            entry["units"] = str(eff_unit)
        entry["source"] = "override" if name in override_keys else "resolved"
        out[str(name)] = entry
    return out


# ---------------------------------------------------------------------------
# write (ruamel round-trip — preserves comments / prose / sibling runs)
# ---------------------------------------------------------------------------

def _study_yaml_path(study: Path | str) -> Path:
    p = Path(study)
    return p / "study.yaml" if p.is_dir() else p


def write_run_params(
    study: Path | str,
    run_name: str,
    captured: dict,
    *,
    captured_at: str | None = None,
    source: str | None = None,
) -> bool:
    """Store ``captured`` params on ``runs[].provenance.params`` for ``run_name``.

    Uses a ruamel round-trip so YAML comments, prose, and every other run are
    preserved (mirrors
    :func:`pbg_superpowers.study_outcomes._write_runs_preserving_comments`).
    ``provenance`` is intentionally NOT one of
    :data:`pbg_superpowers.study_outcomes._MECHANICAL`, so a later
    ``study_outcomes.sync()`` will not clobber it.

    Args:
        study: a study directory or a path to its ``study.yaml``.
        run_name: the ``runs[].name`` to write under.
        captured: the dict returned by :func:`capture_run_params`.
        captured_at: ISO date string (defaults to today).
        source: optional free-text note on how the params were captured
            (e.g. ``"dashboard-runner"``), stored as ``provenance.params_source``.

    Returns:
        ``True`` once written.

    Raises:
        LookupError: if ``run_name`` is not present in the study's ``runs[]``.
    """
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

    from . import study_io

    study_yaml = _study_yaml_path(study)

    ryaml = YAML()
    ryaml.preserve_quotes = True
    ryaml.width = 4096  # avoid line-wrap reflow on long prose values

    rt_spec = ryaml.load(study_yaml.read_text(encoding="utf-8"))
    if rt_spec is None:
        raise LookupError(f"{study_yaml}: empty or unparseable study spec")

    runs = rt_spec.get("runs")
    target = None
    if isinstance(runs, list):
        for r in runs:
            if isinstance(r, dict) and r.get("name") == run_name:
                target = r
                break
    if target is None:
        raise LookupError(
            f"{study_yaml}: no run named {run_name!r} in runs[] "
            f"(found: {[r.get('name') for r in runs] if isinstance(runs, list) else None})"
        )

    prov = target.get("provenance")
    if not isinstance(prov, dict):
        prov = CommentedMap()
        target["provenance"] = prov

    # Build params as a CommentedMap of CommentedMaps for clean block output.
    params_map = CommentedMap()
    for name, entry in captured.items():
        row = CommentedMap()
        for k in ("value", "units", "source"):
            if k in entry:
                row[k] = entry[k]
        params_map[name] = row
    prov["params"] = params_map
    prov["params_captured_at"] = captured_at or date.today().isoformat()
    if source:
        prov["params_source"] = source

    buf = StringIO()
    ryaml.dump(rt_spec, buf)
    study_io.atomic_write(study_yaml, buf.getvalue())
    return True


# ---------------------------------------------------------------------------
# render (table-ready structure for the report)
# ---------------------------------------------------------------------------

def _captured_from(source: dict) -> dict:
    """Accept either a captured-params dict or a whole run record and return
    the captured-params dict (``{param: {value, units, source}}``)."""
    if not isinstance(source, dict):
        return {}
    prov = source.get("provenance")
    if isinstance(prov, dict) and isinstance(prov.get("params"), dict):
        return prov["params"]
    # Already a captured dict? (values are {value: ...} entries)
    if source and all(
        isinstance(v, dict) and "value" in v for v in source.values()
    ):
        return source
    return {}


def render_run_params_rows(source: dict, *, enforced: Iterable | dict | None = None) -> list[dict]:
    """Table-ready rows for a run's captured params.

    Args:
        source: a captured-params dict (from :func:`capture_run_params`) OR a
            whole ``runs[]`` record (its ``provenance.params`` is used).
        enforced: optional param names (dict or iterable) that the study
            *enforces* (e.g. ``enforced_params`` keys via
            :func:`pbg_superpowers.param_enforcement.load_enforced_params`);
            matching rows get ``enforced=True``.

    Returns:
        Rows sorted by param name, each
        ``{"param", "value", "units", "source", "enforced"}``.
    """
    captured = _captured_from(source)
    enforced_set = set(enforced or ())
    rows: list[dict] = []
    for name in sorted(captured, key=str):
        entry = captured[name] or {}
        rows.append({
            "param": name,
            "value": entry.get("value"),
            "units": entry.get("units"),
            "source": entry.get("source", "resolved"),
            "enforced": name in enforced_set,
        })
    return rows


def _esc(v: Any) -> str:
    import html
    return html.escape("" if v is None else str(v))


def render_run_params_table_html(
    source: dict,
    *,
    enforced: Iterable | dict | None = None,
    caption: str | None = None,
) -> str:
    """Render the captured params as a self-contained HTML ``<table>``.

    Thin convenience over :func:`render_run_params_rows` for direct embedding;
    the rows function is the canonical "table-ready structure" a Jinja template
    would consume instead. Returns an empty string when there are no params.
    """
    rows = render_run_params_rows(source, enforced=enforced)
    if not rows:
        return ""
    parts = ['<table class="run-params">']
    if caption:
        parts.append(f"<caption>{_esc(caption)}</caption>")
    parts.append(
        "<thead><tr><th>parameter</th><th>value</th><th>units</th>"
        "<th>source</th><th>enforced</th></tr></thead><tbody>"
    )
    for r in rows:
        units = _esc(r["units"]) if r["units"] else ""
        enforced_cell = "✓" if r["enforced"] else ""
        parts.append(
            f"<tr><td>{_esc(r['param'])}</td><td>{_esc(r['value'])}</td>"
            f"<td>{units}</td><td>{_esc(r['source'])}</td>"
            f"<td>{enforced_cell}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)
