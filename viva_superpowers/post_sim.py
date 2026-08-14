"""Shared post-simulation Step family: Analysis, Visualization, ReportCard.

Moved from v2ecoli (``v2ecoli/workflow/post_sim.py``,
``v2ecoli/workflow/analysis.py``, ``v2ecoli/workflow/report_cards/__init__.py``)
as the study Evaluate-stage substrate: any workspace can build post-simulation
analyses / visualizations / report cards on these bases without depending on
v2ecoli.

The v2ecoli bases subclassed ``v2ecoli.steps.base.V2Step`` — process-bigraph's
``Step`` plus an error-swallowing ``invoke()`` (catches exceptions from
``update()`` and returns an empty update, so one broken Step doesn't crash the
Composite's step cascade). Importing ``V2Step`` here would drag a v2ecoli
dependency into this shared package, so the bases below subclass pbg's
``Step`` directly and carry that same ``invoke()`` guard **verbatim, in the
same place the original had it**:

  - ``VisualizationStep`` / ``ReportCardStep`` never overrode ``invoke()`` in
    v2ecoli (they inherited ``V2Step``'s swallow-on-error behavior), so they
    define it explicitly here with the same try/except guard.
  - ``Analysis`` / ``AnalysisStep`` explicitly overrode ``V2Step.invoke()`` in
    v2ecoli to fail loudly (a broken ``analyze()`` must surface, not silently
    return ``{}``); that override is preserved here unchanged.

Registries: each base auto-registers named subclasses (``__init_subclass__``)
into its own kind-specific registry (``ANALYSIS_REGISTRY``,
``VISUALIZATION_REGISTRY``, ``REPORT_CARD_REGISTRY``) AND funnels into the
unified ``POST_SIM_REGISTRY`` so a single flush can discover every post-sim
output kind-tagged from one place. Abstract bases (subclasses that don't set
their own ``name``) register nowhere.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from process_bigraph.composite import Step, SyncUpdate

KINDS = ("analysis", "visualization", "report_card")

# name -> {"cls": <Step subclass>, "kind": <one of KINDS>}
POST_SIM_REGISTRY: dict[str, dict] = {}

# kind-specific registries. Populated by each base's __init_subclass__ for any
# subclass that defines its own ``name``.
ANALYSIS_REGISTRY: dict[str, type] = {}
VISUALIZATION_REGISTRY: dict[str, type] = {}
REPORT_CARD_REGISTRY: dict[str, type] = {}

# scale name -> human description of the result slice it consumes
ANALYSIS_SCALES: dict[str, str] = {
    "single": "one cell's timeseries",
    "multidaughter": "sister cells from one division",
    "multigeneration": "cells across a lineage's generations",
    "multiseed": "cells across seeds of one variant",
    "multivariant": "cells across all variants",
}


def register_post_sim(cls, kind: str, name: "str | None" = None) -> None:
    """Register a post-sim Step subclass under ``name`` (default ``cls.name``)
    with its ``kind``. No-op when the resolved name is falsy (abstract bases).
    Raises ValueError for an unknown kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown post-sim kind {kind!r}; expected one of {KINDS}")
    nm = name if name is not None else getattr(cls, "name", "")
    if not nm:
        return
    POST_SIM_REGISTRY[nm] = {"cls": cls, "kind": kind}


def iter_post_sim(kind: "str | None" = None) -> list:
    """[(name, cls), ...] sorted by name, optionally filtered to one kind."""
    out = [(nm, e["cls"]) for nm, e in POST_SIM_REGISTRY.items()
           if kind is None or e["kind"] == kind]
    return sorted(out, key=lambda t: t[0])


class Analysis(Step):
    """Visualization-like analysis: reads sim output via a DuckDB connection +
    the ParCa ``sim_data``, and emits a rendered ``view`` (HTML) plus optional
    ``data`` (map). Faithful native ports of vEcoli's ``plot()`` analyses build
    on this base (cf. the record-based ``AnalysisStep`` for emitted-observable
    analyses). Subclasses set ``scale`` + ``name`` and implement ``analyze``.

    Live, non-serializable handles (``conn``, ``sim_data``) are injected by the
    runner into the state dict passed to ``update``; ``inputs()`` declares them
    for discoverability with a permissive ("any") type.
    """

    scale: str = "single"
    config_schema: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.scale not in ANALYSIS_SCALES:
            raise ValueError(
                f"{cls.__name__}.scale={cls.scale!r} not in {sorted(ANALYSIS_SCALES)}")
        if "name" in cls.__dict__:
            ANALYSIS_REGISTRY[cls.name] = cls
        if "name" in cls.__dict__:
            register_post_sim(cls, "analysis")

    def inputs(self):
        return {
            "conn": "any", "history_sql": "string",
            "config_sql": "string", "success_sql": "string",
            "sim_data": "any", "validation_data": "any",
            "variant_metadata": "any",
        }

    def outputs(self):
        return {"view": "string", "data": "map"}

    def analyze(self, *, conn, history_sql, sim_data, **ctx) -> dict:
        """Return {"view": <html str>, "data": <map>} (either key optional)."""
        raise NotImplementedError

    def invoke(self, state, interval=None):
        # Fail loudly (like AnalysisStep): a broken analyze() must surface.
        return SyncUpdate(self.update(state))

    def update(self, state, interval=None):
        kwargs = {k: state.get(k) for k in self.inputs()}
        out = self.analyze(**kwargs) or {}
        return {"view": out.get("view", ""), "data": out.get("data", {})}


class AnalysisStep(Step):
    """Base for result-consuming analysis Steps.

    Subclasses set ``scale`` (one of ANALYSIS_SCALES) and implement
    ``analyze(rows) -> dict``. ``rows`` is a list of emitted result records
    (dicts shaped like the partitioned parquet rows / in-state snapshots) for
    the slice this scale covers. The Step's update() reads ``results`` from
    state and writes the analysis output to ``analysis``.
    """

    scale: str = "single"
    config_schema: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.scale not in ANALYSIS_SCALES:
            raise ValueError(
                f"{cls.__name__}.scale={cls.scale!r} not in {sorted(ANALYSIS_SCALES)}")
        # Register concrete analyses (those declaring their own ``name``).
        if "name" in cls.__dict__:
            ANALYSIS_REGISTRY[cls.name] = cls
        if "name" in cls.__dict__:
            register_post_sim(cls, "analysis")

    def inputs(self):
        return {"results": "list"}

    def outputs(self):
        return {"analysis": "map"}

    def analyze(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    def invoke(self, state, interval=None):
        # Analyses should fail loudly: unlike the simulation Steps (whose
        # error-swallowing invoke() keeps the step cascade alive), a broken
        # or unimplemented analyze() must surface, not silently return {}.
        return SyncUpdate(self.update(state))

    def update(self, state, interval=None):
        rows = state.get("results") or []
        return {"analysis": self.analyze(rows)}


class VisualizationStep(Step):
    """A post-sim visualization Step: emits a rendered ``view`` (HTML) + ``data``
    (map), like ``Analysis`` but tagged ``kind="visualization"`` so the flush can
    route it distinctly. Subclasses set ``name`` and implement
    ``render(study) -> (html, data) | None``. Inputs default to a StudyContext;
    override ``inputs()`` to consume the run extraction instead."""

    name: str = ""
    config_schema: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("name"):
            VISUALIZATION_REGISTRY[cls.name] = cls
            register_post_sim(cls, "visualization")

    def inputs(self):
        return {"study": "any"}

    def outputs(self):
        return {"view": "string", "data": "map"}

    def render(self, study) -> "tuple[str, dict] | None":
        raise NotImplementedError

    def update(self, state, interval=None):
        study = state.get("study")
        res = self.render(study)
        if not res:
            return {"view": "", "data": {}}
        view, data = res
        return {"view": view, "data": data}

    def invoke(self, state, interval=None):
        # v2ecoli's V2Step guard, carried verbatim: catch errors from missing
        # data so one broken visualization doesn't crash the step cascade.
        try:
            update = self.update(state)
        except Exception:
            update = {}
        return SyncUpdate(update)


class ReportCardStep(Step):
    """A report card as a visualization-like Step (sibling of ``Analysis`` and
    ``VisualizationStep``): emits ``view`` (HTML) + ``data`` (verdict map). Unlike
    ``Analysis`` — which consumes a live DuckDB sim-output connection — a report
    card's input is a ``StudyContext`` (the study's spec + dir), so cards grade
    run-free. Subclasses set ``name`` and implement ``applies(study)`` +
    ``build(study) -> (verdict_dict, html) | None``. A named subclass auto-registers
    in ``REPORT_CARD_REGISTRY`` and, kind-tagged, in ``POST_SIM_REGISTRY``.

    Gating convention: a card's verdict dict is free-form (existing cards are
    not required to change), but a card intended to gate a study's Evaluate
    stage should shape its verdict as ``{"status": "pass"|"fail"|"warn",
    "checks": [...], "summary": <str>}`` so a generic gate can read
    ``data["status"]`` without knowing the card. ``checks`` is a list of
    per-check detail dicts (card-defined shape); ``summary`` is a short
    human-readable readout of the verdict.
    """

    name: str = ""
    config_schema: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("name"):
            REPORT_CARD_REGISTRY[cls.name] = cls
            register_post_sim(cls, "report_card")

    def inputs(self):
        return {"study": "any"}

    def outputs(self):
        return {"view": "string", "data": "map"}

    def applies(self, study) -> bool:
        return True

    def build(self, study) -> "tuple[dict, str] | None":
        """Return ``(verdict_json_dict, html_str)`` or None. Subclasses override."""
        raise NotImplementedError

    def update(self, state, interval=None):
        study = state.get("study")
        res = self.build(study) if study is not None else None
        if not res:
            return {"view": "", "data": {}}
        verdict, html = res
        return {"view": html, "data": verdict}

    def invoke(self, state, interval=None):
        # v2ecoli's V2Step guard, carried verbatim: catch errors from missing
        # data so one broken card doesn't crash the step cascade.
        try:
            update = self.update(state)
        except Exception:
            update = {}
        return SyncUpdate(update)


def _sanitize(obj: Any) -> Any:
    """Replace non-finite floats with None, recursively (bundle JSON.parse safe)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


@dataclass
class StudyContext:
    study_name: str
    study_dir: Path
    spec: dict
    ws_root: Path

    @classmethod
    def load(cls, ws_root: Path, study_name: str) -> "StudyContext":
        sd = ws_root / "workspace" / "studies" / study_name
        spec_path = sd / "study.yaml"
        spec = {}
        if spec_path.is_file():
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        return cls(study_name=study_name, study_dir=sd, spec=spec, ws_root=ws_root)

    def run_zarr_paths(self) -> list[Path]:
        return sorted(self.study_dir.glob("runs.*.zarr"))

    @property
    def card_dir(self) -> Path:
        return self.study_dir / "viz" / "report_card"


def write_card(ctx: StudyContext, name: str, verdict: dict, html: str) -> Path:
    """Write <card>.html + <card>.verdict.json into the study's report_card dir.
    Returns the html path. Verdict is sanitized + written with allow_nan=False."""
    d = ctx.card_dir
    d.mkdir(parents=True, exist_ok=True)
    html_path = d / f"{name}.html"
    html_path.write_text(html, encoding="utf-8")
    (d / f"{name}.verdict.json").write_text(
        json.dumps(_sanitize(verdict), indent=1, allow_nan=False) + "\n",
        encoding="utf-8")
    return html_path


def prune(ctx: StudyContext, keep: set[str]) -> list[str]:
    """Delete <card>.html (+ sibling .verdict.json) under the study's report_card
    dir whose stem is not in `keep`. Returns pruned stems. Touches only that dir."""
    d = ctx.card_dir
    pruned: list[str] = []
    if not d.is_dir():
        return pruned
    for html in sorted(d.glob("*.html")):
        stem = html.name[: -len(".html")]
        if stem not in keep:
            html.unlink()
            vf = html.with_name(stem + ".verdict.json")
            if vf.is_file():
                vf.unlink()
            pruned.append(stem)
    return pruned


def applicable(ctx: StudyContext, core, only: "str | None" = None) -> list:
    """Instantiated report-card Steps to emit for a study. If the study spec lists
    `report_cards:`, only those names are eligible; otherwise every registered card
    is eligible. A card is emitted when eligible AND its applies(ctx) is True.
    `only` (a name, or None/'all') narrows to a single card. `core` is a
    bigraph-schema core (built once by the caller) used to instantiate Steps."""
    declared = ctx.spec.get("report_cards")
    want = None if (only in (None, "all")) else {only}
    out = []
    for nm, cls in REPORT_CARD_REGISTRY.items():
        if want is not None and nm not in want:
            continue
        if declared is not None and nm not in declared:
            continue
        try:
            step = cls({}, core=core)
            if step.applies(ctx):
                out.append(step)
        except Exception:  # noqa: BLE001 — one broken card never aborts selection
            continue
    return out
