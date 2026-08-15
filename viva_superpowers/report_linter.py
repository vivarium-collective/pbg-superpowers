"""Pre-publication linter for workspace study reports.

Pass B of the infrastructure-feedback roadmap (the "report linting"
requirement, verbatim from the feedback PDF):

  Run a pre-publication lint pass for incomplete summaries, duplicate modal
  phrases, missing fields, unresolved placeholders, contradictory badges,
  and truncated takeaways.

  Acceptance: lint failures block report publication unless explicitly
  overridden and logged.

Public surface:

- ``LintFinding`` dataclass — one finding (level, study_slug, field_path,
  message, override_key).
- ``lint_workspace_report(ws_root)`` — returns ``list[LintFinding]`` over
  every study under ``<ws_root>/studies/`` (and the legacy
  ``investigations/<slug>/spec.yaml``).
- ``load_overrides(ws_root)`` — read ``.pbg/report-lint-overrides.json``.
- ``write_override(ws_root, finding)`` — append a finding's override_key
  to the override file (used by ``/viva-report --force``).
- ``has_blocking_errors(findings, overrides)`` — convenience predicate.

The override file shape (``<ws_root>/.pbg/report-lint-overrides.json``):

    {
      "schema_version": 1,
      "overrides": [
        {
          "key": "<override_key>",
          "added_at": "2026-05-17T15:14:00",
          "reason": "manually reviewed — placeholder is intentional"
        }
      ]
    }

When the linter runs, any error-level finding whose ``override_key``
appears in ``overrides[].key`` is downgraded to a warning. Anything not
in the override file remains an error and blocks publication.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import yaml

from viva_superpowers.band_provenance import has_numeric_band as _is_numeric_band
from viva_superpowers.bibtex import bib_keys
from viva_superpowers.rigor import run_is_emitter_backed
from viva_superpowers.workspace_paths import WorkspacePaths


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintFinding:
    """One linter finding.

    Attributes:
        level: ``error`` (blocks publication), ``warning``, or ``info``.
        study_slug: The study slug the finding pertains to (or ``"<workspace>"``
            for workspace-level findings).
        field_path: Dotted path to the offending field (e.g.
            ``conclusion_logic.if_primary_tests_pass``).
        message: Human-readable explanation.
        override_key: Stable string suitable for an override file. Built
            from ``check_name + study_slug + field_path`` so it is stable
            across linter runs as long as the underlying violation is the
            same one.
        check: Internal check identifier (one of the keys in CHECKS).
    """

    level: str
    study_slug: str
    field_path: str
    message: str
    override_key: str
    check: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _LintContext:
    """Per-study context handed to each check function.

    ``ws_cache`` is a plain dict shared by every ``_LintContext`` built
    within a single ``lint_workspace_report()`` call (all studies AND
    investigations in that run point at the *same* dict instance). It
    memoizes the workspace-global scans (bib keys, expert-doc names, viz
    classes) that depend only on ``ws_root`` — not on the study — so each
    scan runs at most once per lint run instead of once per study. See
    ``_cached()`` below and ``lint_workspace_report()``, which is the only
    place a fresh ``ws_cache`` is minted.
    """

    ws_root: Path
    slug: str
    spec: dict
    findings: list[LintFinding] = field(default_factory=list)
    strict: bool = False
    ws_cache: dict = field(default_factory=dict)

    def add(
        self,
        *,
        level: str,
        field_path: str,
        message: str,
        check: str,
    ) -> None:
        key = _override_key(check=check, slug=self.slug, field_path=field_path)
        self.findings.append(
            LintFinding(
                level=level,
                study_slug=self.slug,
                field_path=field_path,
                message=message,
                override_key=key,
                check=check,
            )
        )


# ---------------------------------------------------------------------------
# Phase-aware completeness gating (issue #97)
# ---------------------------------------------------------------------------

# A study advances Design -> Build -> Simulate -> Evaluate -> Decide. A study
# in early Design legitimately has no planned runs, simulation set, or variants
# yet — the processes it tests aren't built. Firing completeness *warnings* on
# those fields conflates "Design-stage, correctly sparse" with "should be
# filled," which inflates the warning count and buries the actionable findings.
_PHASE_ORDER = {"Design": 0, "Build": 1, "Simulate": 2, "Evaluate": 3, "Decide": 4}


def _phase_index(spec: dict) -> int | None:
    """Numeric rank of the study's ``phase``; ``None`` when unset/unknown.

    ``None`` means 'no phase signal' — callers preserve the pre-#97 behavior
    (warn) rather than silently suppressing.
    """
    phase = spec.get("phase")
    if not isinstance(phase, str) or not phase.strip():
        return None
    return _PHASE_ORDER.get(phase.strip().capitalize())


def _completeness_level(spec: dict, *, warn_at: str) -> str:
    """Level for a completeness check, gated on the study's phase.

    - phase unknown          -> ``"warning"`` (no phase signal; keep old behavior)
    - phase >= ``warn_at``    -> ``"warning"`` (genuinely overdue)
    - phase <  ``warn_at``    -> ``"info"``    (correctly sparse for its stage)
    """
    idx = _phase_index(spec)
    if idx is None:
        return "warning"
    return "warning" if idx >= _PHASE_ORDER[warn_at] else "info"


# ---------------------------------------------------------------------------
# Override-key derivation
# ---------------------------------------------------------------------------


def _override_key(*, check: str, slug: str, field_path: str) -> str:
    """Stable hash for an override entry.

    A short 12-char hex digest of ``check|slug|field_path``. Keeps the file
    grep-friendly while being deterministic across linter runs.
    """
    raw = f"{check}|{slug}|{field_path}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"{check}:{slug}:{digest}"


# ---------------------------------------------------------------------------
# Override file IO
# ---------------------------------------------------------------------------


_OVERRIDE_FILE_NAME = "report-lint-overrides.json"


def override_path(ws_root: Path) -> Path:
    """Where the override JSON lives, relative to the workspace root."""
    return WorkspacePaths.load(ws_root).pbg / _OVERRIDE_FILE_NAME


def load_overrides(ws_root: Path) -> set[str]:
    """Return the set of override keys currently logged for this workspace.

    Missing file is treated as an empty set (no overrides).
    """
    path = override_path(ws_root)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    overrides = data.get("overrides") or []
    return {entry["key"] for entry in overrides if isinstance(entry, dict) and "key" in entry}


def write_override(
    ws_root: Path,
    finding: LintFinding,
    *,
    reason: str = "force-published via /viva-report --force",
    now: _dt.datetime | None = None,
) -> Path:
    """Append a single override entry; idempotent (won't double-add).

    Returns the path to the override file.
    """
    now = now or _dt.datetime.now()
    path = override_path(ws_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"schema_version": 1, "overrides": []}
    else:
        data = {"schema_version": 1, "overrides": []}
    data.setdefault("schema_version", 1)
    data.setdefault("overrides", [])
    keys = {e.get("key") for e in data["overrides"]}
    if finding.override_key not in keys:
        data["overrides"].append({
            "key": finding.override_key,
            "added_at": now.isoformat(timespec="seconds"),
            "reason": reason,
            # Embedded provenance — lets a reviewer find the original violation
            # without re-running the linter against an older workspace snapshot.
            "check": finding.check,
            "study_slug": finding.study_slug,
            "field_path": finding.field_path,
            "message": finding.message,
        })
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    return path


def has_blocking_errors(
    findings: Iterable[LintFinding],
    overrides: set[str] | None = None,
) -> bool:
    """True iff any error-level finding remains after override application."""
    overrides = overrides or set()
    for f in findings:
        if f.level == "error" and f.override_key not in overrides:
            return True
    return False


def apply_overrides(
    findings: Iterable[LintFinding],
    overrides: set[str],
) -> list[LintFinding]:
    """Downgrade error-level findings whose key is overridden to warnings.

    Returns a NEW list (does not mutate input). Useful for surfacing the
    fact that an override was applied without dropping the finding entirely.
    """
    out: list[LintFinding] = []
    for f in findings:
        if f.level == "error" and f.override_key in overrides:
            out.append(LintFinding(
                level="warning",
                study_slug=f.study_slug,
                field_path=f.field_path,
                message=f"[overridden] {f.message}",
                override_key=f.override_key,
                check=f.check,
            ))
        else:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Real-composite resolution (pure helper — registry supplied by the caller)
# ---------------------------------------------------------------------------


def _collect_composite_refs(spec: dict) -> list[str]:
    """Every composite identifier a study spec REFERENCES, de-duplicated in
    discovery order.

    Collected from the canonical reference sites:

    * ``baseline[].composite`` (a single dict or a list of dicts),
    * ``conditions.baseline.composite`` and ``conditions.variants[].composite``,
    * ``simulation_set[].composite`` and ``simulation_set[].base_model``.

    Variant ``base_composite`` (which names a *baseline* by name, not a
    registered composite id) is intentionally NOT collected.
    """
    refs: list[str] = []

    def _add(v) -> None:
        if isinstance(v, str) and v.strip():
            refs.append(v.strip())

    baseline = (spec or {}).get("baseline")
    for b in (baseline if isinstance(baseline, list) else [baseline]):
        if isinstance(b, dict):
            _add(b.get("composite"))

    conditions = (spec or {}).get("conditions")
    if isinstance(conditions, dict):
        cb = conditions.get("baseline")
        for b in (cb if isinstance(cb, list) else [cb]):
            if isinstance(b, dict):
                _add(b.get("composite"))
        variants = conditions.get("variants")
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, dict):
                    _add(v.get("composite"))

    sim_set = (spec or {}).get("simulation_set")
    if isinstance(sim_set, list):
        for s in sim_set:
            if isinstance(s, dict):
                _add(s.get("composite"))
                _add(s.get("base_model"))

    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def unresolved_composite_refs(spec: dict, known_composite_ids) -> list[str]:
    """Return the composite references a study DECLARES that are NOT in the
    caller-supplied set of known (registered) composite ids.

    Contract
    --------
    This helper is PURE: it has no access to a composite registry. The canonical
    signal that a study references a *real* composite is that its
    ``baseline[].composite`` (and the other reference sites collected by
    :func:`_collect_composite_refs`) resolves in the workspace registry. Because
    :mod:`viva_superpowers.rigor` / this linter run on specs alone and cannot know
    the registry, the CALLER (the dashboard, which owns ``/api/composites``)
    passes ``known_composite_ids`` — the set/iterable of every registered
    composite id — and this function returns every declared reference absent from
    that set, de-duplicated and in declaration order. An empty result means all
    referenced composites resolve.

    Passing an empty / ``None`` ``known_composite_ids`` returns ALL declared
    refs (every reference is "unresolved" against an empty registry) — callers
    that don't yet have a registry should treat that as "unknown", not "all bad".
    """
    known = set(known_composite_ids or ())
    return [r for r in _collect_composite_refs(spec) if r not in known]


# ---------------------------------------------------------------------------
# Discovery: walk a workspace and yield (slug, spec) pairs
# ---------------------------------------------------------------------------


def _iter_study_specs(ws_root: Path) -> Iterator[tuple[str, dict]]:
    """Yield (slug, parsed-yaml) for every study under the workspace.

    Looks under ``<ws_root>/studies/<slug>/study.yaml`` first, then falls
    back to the legacy ``<ws_root>/investigations/<slug>/spec.yaml``.
    Silently skips unparseable YAML (the report renderer reports those
    separately; the linter focuses on content checks).
    """
    wp = WorkspacePaths.load(ws_root)
    studies_dir = wp.studies
    if studies_dir.is_dir():
        for child in sorted(studies_dir.iterdir()):
            if not child.is_dir():
                continue
            spec_path = child / "study.yaml"
            if not spec_path.is_file():
                continue
            try:
                data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            slug = data.get("name") or child.name
            yield slug, data
    invs_dir = wp.investigations
    if invs_dir.is_dir():
        for child in sorted(invs_dir.iterdir()):
            if not child.is_dir():
                continue
            spec_path = child / "spec.yaml"
            if not spec_path.is_file():
                continue
            try:
                data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            slug = data.get("name") or child.name
            yield slug, data


def _iter_investigation_specs(ws_root: Path) -> Iterator[tuple[str, dict]]:
    """Yield (slug, parsed-yaml) for every modern v2 investigation under the
    workspace — ``<ws_root>/investigations/<slug>/investigation.yaml``.

    These carry the investigation-level narrative spine (executive /
    scientific_argument / biological_story) the report renders, distinct from
    the per-study specs in :func:`_iter_study_specs`.
    """
    wp = WorkspacePaths.load(ws_root)
    invs_dir = wp.investigations
    if not invs_dir.is_dir():
        return
    for child in sorted(invs_dir.iterdir()):
        if not child.is_dir():
            continue
        spec_path = child / "investigation.yaml"
        if not spec_path.is_file():
            continue
        try:
            data = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        yield (data.get("name") or child.name), data


# Investigation-level narrative spine — REQUIRED report sections (each can be
# explicitly skipped for a genuinely slim investigation via
# ``narrative_spine_skip: [...]``). These are the AUTHORED sections of the
# investigation report; the computed sections (Decisions needed, Suggested
# additions) are framework signals, not author-required, so they're excluded.
_REQUIRED_INVESTIGATION_SECTIONS = (
    ("executive", "Executive summary"),
    ("scientific_argument", "Scientific argument"),
    ("biological_story", "Biology — the mechanism"),
)


def _inv_section_present(spec: dict, key: str) -> bool:
    """True when an investigation has authored content for a narrative section."""
    v = spec.get(key)
    if key == "biological_story":
        return isinstance(v, str) and bool(v.strip())
    if key == "executive":
        ex = v if isinstance(v, dict) else {}
        return bool(_is_nonempty(ex.get("what_is_this")) or _is_nonempty(ex.get("verdict")))
    if key == "scientific_argument":
        sa = v if isinstance(v, dict) else {}
        return bool(_is_nonempty(sa.get("main_claim")))
    return bool(v)


def _check_investigation_narrative_spine(ctx: "_LintContext") -> None:
    """REQUIRE the investigation-level narrative sections (Executive summary,
    Scientific argument, Biology) — unless explicitly skipped.

    Default severity is ``warning`` (blocking, publication-gating) so these
    sections are effectively required. A genuinely slim investigation opts out
    per-section by listing the section key in ``narrative_spine_skip: [...]``
    (optionally with a ``narrative_spine_skip_reason``); a skipped section is
    treated as satisfied. This is the "required, but explicitly skippable"
    contract.
    """
    spec = ctx.spec or {}
    skip = spec.get("narrative_spine_skip") or []
    if not isinstance(skip, list):
        skip = []
    skip_set = {str(s).strip().lower() for s in skip}
    for key, label in _REQUIRED_INVESTIGATION_SECTIONS:
        if key in skip_set or _inv_section_present(spec, key):
            continue
        ctx.add(
            level="warning",
            field_path=key,
            message=(
                f"Investigation is missing the REQUIRED narrative section "
                f"'{label}' (`{key}`). Author it for a reviewer-ready report, "
                f"or — for a genuinely slim investigation — explicitly opt out "
                f"by adding '{key}' to `narrative_spine_skip: [...]` "
                f"(optionally with `narrative_spine_skip_reason`)."
            ),
            check="investigation_narrative_spine_required",
        )


_INVESTIGATION_CHECK_FUNCTIONS = (
    _check_investigation_narrative_spine,
)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


CHECKS = (
    # Render-guarantee: the spec loads through the dashboard's own load_spec(),
    # so "passes lint" implies "renders" (#96). Error: fails to render.
    "render_blocked",
    "incomplete_summaries",
    "status_contradictions",
    "missing_provenance",
    "unresolved_placeholders",
    "duplicate_modal_phrases",
    "truncated_takeaways",
    # Pass 10A findings linter additions
    "decide_phase_missing_findings",
    "finding_without_evidence",
    # Empty finding statement renders as "(no statement)" + an empty Key-takeaways
    # bullet (dnaa-replication 2026-06-07). Error: every finding must be filled in.
    "finding_without_statement",
    "finding_cites_unknown_bib_key",
    "finding_references_unknown_expert_doc",
    # Band provenance (stage 3a): expert-sourced bands should carry structured cites
    "band_test_missing_cites",
    "band_cites_unknown_bib_key",
    # Derive-on-read status drift (v2ecoli round-2 #2)
    "status_out_of_date_vs_runs",
    # Forward-drift: declares done/passed but records no runs (dnaa-replication
    # 2026-05-31 — reviewer couldn't tell if studies had actually run)
    "status_claims_done_no_runs_recorded",
    # Future-proofing: study has runs but none persisted via an emitter
    "runs_without_emitter",
    # A passed study that hedges its conclusion ("should"/"likely"/"seems") —
    # the wording symptom of a claim resting on something other than evidence.
    "hedged_verdict_when_passed",
    # Reviewer-facing clarity strip ambiguities (single-sourced from
    # study_status.study_clarity_summary): ran-but-tests-pending, gate↔test drift
    "reviewer_clarity_ambiguity",
    # Chart's stamped source run != the study's latest run (or unrendered /
    # untracked-on-disk). Supersedes the mtime-based figure_stale_vs_run.
    # warning by default; error under --strict.
    "viz_stale_vs_latest_run",
    # S3: v4 narrative-spine nudge — info-level reminder of missing dnaa-style sections
    "narrative_spine_completeness",
    # Investigation-level narrative sections REQUIRED (skippable via
    # narrative_spine_skip) — warning-level (publication-gating)
    "investigation_narrative_spine_required",
    # Expert-handoff readiness — every study card in a generated report
    # should show baseline composites, variants planned, simulation
    # runs planned, readouts, runs, tests, and visualizations. When a
    # study YAML has any of those blocks empty/absent, the report ends
    # up with empty sections that the expert can't critique.  These
    # warnings flag the gap pre-publication.  All warning-level (non-
    # blocking) — a study CAN publish without them, but the expert will
    # see "TBD" rather than concrete content.
    "missing_baseline",
    "missing_variants",
    "missing_planned_runs",
    "missing_readouts",
    "missing_visualizations",
    # Build / Simulations tab readiness — the dashboard's study-detail
    # template renders the Build tab from `conditions.{baseline,variants,
    # model_settings}` (or legacy model_change / implementation_requirements)
    # and the Simulations tab from `simulation_set:`. A study without
    # those v4 fields renders those tabs BLANK even when v3 fields
    # `baseline:` + `variants:` + `planned_runs:` are populated.
    "missing_conditions_block",
    "missing_simulation_set",
    # SP2b-ii: readout migration status — migratable (info) + needs_human (warning)
    "readout_migration_status",
    # Wave 3a: workflow-typing enums (next_action_type / study_type) — soft
    "next_action_type_missing",
    "next_action_type_unknown",
    "study_type_unknown",
    # Wave 3b: claim_scope / generality / lifecycle_state enums + floor — soft
    "claim_scope_unknown",
    "generality_axis_unknown",
    "generality_level_unknown",
    "lifecycle_state_unknown",
    "lifecycle_state_below_floor",
)


# --- 1. incomplete_summaries -----------------------------------------------


def _check_incomplete_summaries(ctx: _LintContext) -> None:
    """Any study marked evaluation_status: evaluated but missing conclusion_logic content."""
    if ctx.spec.get("evaluation_status") != "evaluated":
        return
    cl = ctx.spec.get("conclusion_logic") or {}
    if not isinstance(cl, dict):
        cl = {}
    # Consider it "content" if any of the canonical sub-objects exist and are non-empty.
    has_content = any(
        _is_nonempty(cl.get(k))
        for k in (
            "if_primary_tests_pass",
            "if_primary_tests_fail",
            "if_pass",
            "if_fail",
        )
    )
    if not has_content:
        ctx.add(
            level="error",
            field_path="conclusion_logic",
            message=(
                "Study is marked evaluation_status: evaluated but "
                "conclusion_logic is empty. Every evaluated study must "
                "have a conclusion mapping (if_primary_tests_pass / "
                "if_primary_tests_fail)."
            ),
            check="incomplete_summaries",
        )


def _is_nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (str, list, dict, tuple, set)):
        return bool(v)
    return True


# --- 2. status_contradictions ----------------------------------------------


def _check_status_contradictions(ctx: _LintContext) -> None:
    spec = ctx.spec
    gate = spec.get("gate_status")
    evalst = spec.get("evaluation_status")
    sim = spec.get("simulation_status")
    impl = spec.get("implementation_status")
    review = spec.get("expert_review_status")

    if gate == "passed" and evalst == "failed_evaluation":
        ctx.add(
            level="error",
            field_path="gate_status",
            message=(
                "gate_status: passed but evaluation_status: failed_evaluation. "
                "A study cannot have passed the pipeline gate while its "
                "evaluation has failed."
            ),
            check="status_contradictions",
        )
    if sim == "not_run" and evalst == "evaluated":
        ctx.add(
            level="error",
            field_path="evaluation_status",
            message=(
                "simulation_status: not_run but evaluation_status: evaluated. "
                "There is nothing to evaluate."
            ),
            check="status_contradictions",
        )
    if impl == "not_started" and sim in {"running", "ran"}:
        ctx.add(
            level="error",
            field_path="simulation_status",
            message=(
                f"implementation_status: not_started but simulation_status: {sim}. "
                "Code that wasn't written cannot be running or ran."
            ),
            check="status_contradictions",
        )
    if review == "approved" and gate in {"blocked", "needs_calibration"}:
        ctx.add(
            level="error",
            field_path="expert_review_status",
            message=(
                f"expert_review_status: approved but gate_status: {gate}. "
                "An approved review should not coexist with a blocked or "
                "needs-calibration pipeline gate."
            ),
            check="status_contradictions",
        )


# --- 3. missing_provenance -------------------------------------------------


def _check_missing_provenance(ctx: _LintContext) -> None:
    """Each finding with evaluation_status: evaluated (or evidence.from_run) must have run_ids."""
    spec = ctx.spec
    findings = spec.get("findings") or []
    if not isinstance(findings, list):
        return
    study_evaluated = spec.get("evaluation_status") == "evaluated"
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        evidence = f.get("evidence") or {}
        from_run = bool(evidence.get("from_run")) if isinstance(evidence, dict) else False
        if not (study_evaluated or from_run):
            continue
        prov = f.get("provenance") or {}
        run_ids = prov.get("run_ids") if isinstance(prov, dict) else None
        if not run_ids:
            fid = f.get("id", f"<index-{idx}>")
            ctx.add(
                level="error",
                field_path=f"findings[{idx}].provenance.run_ids",
                message=(
                    f"Finding {fid!r} is run-derived (study is evaluated "
                    "or evidence.from_run set) but provenance.run_ids "
                    "is empty. An evaluated finding without run IDs "
                    "cannot be re-checked against the underlying data."
                ),
                check="missing_provenance",
            )


# --- 4. unresolved_placeholders --------------------------------------------


_PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bXXX\b", re.IGNORECASE),
    re.compile(r"\[fill in\]", re.IGNORECASE),
    re.compile(r"<insert>", re.IGNORECASE),
)


# Path leaves that are slug-shaped (identifiers, kebab-case names) — skip
# placeholder checks on them. A study LITERALLY named "TBD" would otherwise
# always trip the linter.
_SKIP_PLACEHOLDER_PATH_LEAVES = frozenset({
    "name", "id", "slug", "composite", "kind", "study", "parameter",
    "study_slug", "proposal_id", "field_path", "evaluator_version",
})


def _check_unresolved_placeholders(ctx: _LintContext) -> None:
    for path, value in _walk_strings(ctx.spec):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf in _SKIP_PLACEHOLDER_PATH_LEAVES:
            continue
        for pat in _PLACEHOLDER_PATTERNS:
            m = pat.search(value)
            if m:
                ctx.add(
                    level="error",
                    field_path=path,
                    message=(
                        f"Unresolved placeholder {m.group(0)!r} in field "
                        f"{path!r}. Either fill in the content or remove the "
                        "placeholder before publishing."
                    ),
                    check="unresolved_placeholders",
                )
                break  # one finding per offending string is enough


def _walk_strings(obj, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield (dotted-path, string-value) for every string leaf in obj."""
    if isinstance(obj, str):
        if prefix:
            yield prefix, obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{prefix}.{k}" if prefix else str(k))
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{prefix}[{i}]")
        return
    # other scalar — skip


# --- 5. duplicate_modal_phrases --------------------------------------------


def _char_similarity(a: str, b: str) -> float:
    """Cheap >90% similarity check based on char-set Jaccard + length ratio.

    True if at least 90% of the (lower-cased, whitespace-normalized)
    characters of each string are present in the other AND the shorter
    string is at least 70% the length of the longer (avoids flagging
    "ok" inside a 200-char paragraph).
    """
    na = re.sub(r"\s+", " ", a.lower().strip())
    nb = re.sub(r"\s+", " ", b.lower().strip())
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Length-ratio gate: very different lengths are not "duplicate phrases".
    sa, sb = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(sa) / max(len(sb), 1) < 0.7:
        return 0.0
    # Use difflib SequenceMatcher for fast char-level similarity.
    import difflib
    return difflib.SequenceMatcher(a=na, b=nb).ratio()


def _check_duplicate_modal_phrases(ctx: _LintContext) -> None:
    """Any pair of behavior_tests[].description >90% identical."""
    tests = ctx.spec.get("behavior_tests") or []
    if not isinstance(tests, list):
        return
    descs: list[tuple[int, str, str]] = []  # (index, name, description)
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            continue
        d = t.get("description")
        if isinstance(d, str) and d.strip():
            descs.append((i, t.get("name", f"<index-{i}>"), d))
    for ai in range(len(descs)):
        for bi in range(ai + 1, len(descs)):
            ia, na, da = descs[ai]
            ib, nb, db = descs[bi]
            ratio = _char_similarity(da, db)
            if ratio >= 0.90:
                ctx.add(
                    level="warning",
                    field_path=f"behavior_tests[{ib}].description",
                    message=(
                        f"behavior_tests {nb!r} description is {ratio:.0%} "
                        f"similar to {na!r} (likely copy-paste residue). "
                        "Reword one of them to clarify the distinct test "
                        "intent."
                    ),
                    check="duplicate_modal_phrases",
                )


# --- 6. truncated_takeaways ------------------------------------------------


_TAKEAWAY_KEYS_CL_NEW = ("if_primary_tests_pass", "if_primary_tests_fail")
_TAKEAWAY_KEYS_CL_OLD = ("if_pass", "if_fail")
_MIN_TAKEAWAY_LEN = 20

# Within conclusion_logic.if_primary_tests_{pass,fail}, only these subkeys
# carry narrative takeaways that should be terminated/long. Keys like
# `implementation_status`, `pipeline_unblocks` (list), `diagnose` (list)
# are not single-sentence takeaways and should not be flagged.
_NARRATIVE_SUBKEYS = frozenset({"biological_validation", "block_downstream", "summary"})


def _check_truncated_takeaways(ctx: _LintContext) -> None:
    cl = ctx.spec.get("conclusion_logic") or {}
    if not isinstance(cl, dict):
        return
    # Inspect both shapes — old plain string keys and new object-with-fields keys.
    for k in _TAKEAWAY_KEYS_CL_OLD:
        v = cl.get(k)
        if isinstance(v, str):
            _flag_if_truncated(ctx, f"conclusion_logic.{k}", v)
    for k in _TAKEAWAY_KEYS_CL_NEW:
        v = cl.get(k)
        if not isinstance(v, dict):
            continue
        for sk, sv in v.items():
            if sk not in _NARRATIVE_SUBKEYS:
                continue
            if isinstance(sv, str):
                _flag_if_truncated(ctx, f"conclusion_logic.{k}.{sk}", sv)


def _flag_if_truncated(ctx: _LintContext, path: str, value: str) -> None:
    s = value.strip()
    if not s:
        # Empty strings are caught by incomplete_summaries (when the parent is empty)
        # — don't double-flag.
        return
    if len(s) < _MIN_TAKEAWAY_LEN:
        ctx.add(
            level="error",
            field_path=path,
            message=(
                f"Takeaway at {path!r} is only {len(s)} chars (<{_MIN_TAKEAWAY_LEN}). "
                "Likely a truncated or stub takeaway — write a complete sentence."
            ),
            check="truncated_takeaways",
        )
        return
    if s[-1] not in ".!?\")]'":
        ctx.add(
            level="error",
            field_path=path,
            message=(
                f"Takeaway at {path!r} does not end with a terminal "
                "punctuation mark (. ! ?). Likely truncated mid-sentence."
            ),
            check="truncated_takeaways",
        )


# ---------------------------------------------------------------------------
# Pass 10A — findings-protocol checks
# ---------------------------------------------------------------------------


def _cached(ctx: "_LintContext", key: str, compute):
    """Memoize a workspace-global scan for the lifetime of one lint run.

    ``ctx.ws_cache`` is shared across every ``_LintContext`` created inside
    a single ``lint_workspace_report()`` call, so a scan that depends only
    on ``ctx.ws_root`` (not on the individual study) runs at most once per
    lint run — instead of once per study — while staying lazy: it's only
    computed the first time a check actually needs it.

    Scoped to one call, not module-level: a fresh ``ws_cache`` dict is
    minted on every ``lint_workspace_report()`` invocation, so this can
    never serve stale data across two separate lint runs even if the
    workspace's files changed in between.
    """
    if key not in ctx.ws_cache:
        ctx.ws_cache[key] = compute()
    return ctx.ws_cache[key]


def _bib_keys_for_workspace(ws_root: Path) -> set[str]:
    """Every @entry key declared in the workspace bibliography.

    Delegates to the shared :func:`viva_superpowers.bibtex.bib_keys` so the
    publish-gate linter and the verify gate agree on file + parser.
    """
    return bib_keys(ws_root)


def _expert_doc_names_for_workspace(ws_root: Path) -> set[str]:
    """Set of expert_docs[].name from workspace.yaml. Empty if absent."""
    ws_yaml = ws_root / "workspace.yaml"
    if not ws_yaml.is_file():
        return set()
    try:
        data = yaml.safe_load(ws_yaml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    docs = data.get("expert_docs") or []
    out: set[str] = set()
    if isinstance(docs, list):
        for d in docs:
            if isinstance(d, dict) and isinstance(d.get("name"), str):
                out.add(d["name"])
    return out


def _check_decide_phase_missing_findings(ctx: _LintContext) -> None:
    """Phase=Decide OR (simulation_status=ran AND evaluation_status=evaluated)
    with zero findings is a Pass 10A error.
    """
    spec = ctx.spec
    findings = spec.get("findings") or []
    if findings:
        return
    phase = spec.get("phase")
    sim = spec.get("simulation_status")
    evalst = spec.get("evaluation_status")
    triggered = phase == "Decide" or (sim == "ran" and evalst == "evaluated")
    if not triggered:
        return
    ctx.add(
        level="error",
        field_path="findings",
        message=(
            "Study reached Decide/Evaluated but has no findings[]. "
            f"Run `/viva-study findings {ctx.slug}` to draft them."
        ),
        check="decide_phase_missing_findings",
    )


def _check_finding_without_evidence(ctx: _LintContext) -> None:
    """A biological/computational finding with no evidence.from_run AND no
    evidence.from_test cannot be linked back to an artifact. Warning."""
    findings = ctx.spec.get("findings") or []
    if not isinstance(findings, list):
        return
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        kind = f.get("kind")
        if kind not in {"biological", "computational"}:
            continue
        ev = f.get("evidence") or {}
        if not isinstance(ev, dict):
            ev = {}
        has_link = bool(ev.get("from_run") or ev.get("from_test"))
        if has_link:
            continue
        fid = f.get("id", f"<index-{idx}>")
        ctx.add(
            level="warning",
            field_path=f"findings[{idx}].evidence",
            message=(
                f"Finding {fid!r} claims a {kind} status but has no "
                "evidence.from_run and no evidence.from_test. Add a link "
                "to the run / behavior_test that produced it."
            ),
            check="finding_without_evidence",
        )


def _check_finding_without_statement(ctx: _LintContext) -> None:
    """A finding with no `statement` renders as '(no statement)' in the report
    and produces an empty Key-takeaways bullet. Every finding must carry a
    one-to-two-sentence statement. Error (blocking)."""
    findings = ctx.spec.get("findings") or []
    if not isinstance(findings, list):
        return
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        stmt = f.get("statement")
        if isinstance(stmt, str) and stmt.strip():
            continue
        fid = f.get("id", f"<index-{idx}>")
        ctx.add(
            level="error",
            field_path=f"findings[{idx}].statement",
            message=(
                f"Finding {fid!r} has no statement. It renders as "
                "'(no statement)' in the report and produces an empty "
                "Key-takeaways bullet. Add a one-to-two sentence statement "
                "describing what was found."
            ),
            check="finding_without_statement",
        )


def _check_finding_cites_unknown_bib_key(ctx: _LintContext) -> None:
    """Any expected.cites entry not in references/papers.bib is an error."""
    findings = ctx.spec.get("findings") or []
    if not isinstance(findings, list):
        return
    known = _cached(ctx, "bib_keys", lambda: _bib_keys_for_workspace(ctx.ws_root))
    if not known:
        # No bibliography to compare against — surface nothing rather than
        # spamming errors. Authors who reference bib_keys without papers.bib
        # are caught by other parts of the report pipeline.
        return
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        expected = f.get("expected") or {}
        if not isinstance(expected, dict):
            continue
        cites = expected.get("cites") or []
        if not isinstance(cites, list):
            continue
        for cidx, key in enumerate(cites):
            if not isinstance(key, str):
                continue
            if key not in known:
                fid = f.get("id", f"<index-{idx}>")
                ctx.add(
                    level="error",
                    field_path=f"findings[{idx}].expected.cites[{cidx}]",
                    message=(
                        f"Finding {fid!r} cites unknown bib_key {key!r}. "
                        "Add it to references/papers.bib first."
                    ),
                    check="finding_cites_unknown_bib_key",
                )


def _check_finding_references_unknown_expert_doc(ctx: _LintContext) -> None:
    """expert_reference.doc must resolve to a workspace.yaml.expert_docs[] entry."""
    findings = ctx.spec.get("findings") or []
    if not isinstance(findings, list):
        return
    known = _cached(ctx, "expert_doc_names", lambda: _expert_doc_names_for_workspace(ctx.ws_root))
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        ref = f.get("expert_reference") or {}
        if not isinstance(ref, dict):
            continue
        doc = ref.get("doc")
        if not isinstance(doc, str):
            continue
        if doc in known:
            continue
        fid = f.get("id", f"<index-{idx}>")
        ctx.add(
            level="error",
            field_path=f"findings[{idx}].expert_reference.doc",
            message=(
                f"Finding {fid!r} references unknown expert doc {doc!r}. "
                "Add it to workspace.yaml.expert_docs[] first."
            ),
            check="finding_references_unknown_expert_doc",
        )


# ---------------------------------------------------------------------------
# Wave 3a — workflow-typing soft checks (critique #7 / #10)
# ---------------------------------------------------------------------------


def _workflow_typing_enums() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The (next_action_type, study_type) enums, imported defensively so a
    missing/renamed source module degrades to a built-in copy rather than
    crashing the lint run."""
    try:
        from viva_superpowers.seed_from_followup import NEXT_ACTION_TYPES
    except Exception:  # noqa: BLE001
        NEXT_ACTION_TYPES = (
            "replicate", "calibrate", "ablate", "adversarially_probe",
            "refine_representation", "split_hypothesis", "retire_hypothesis",
            "escalate_model",
        )
    try:
        from viva_superpowers.rigor import STUDY_TYPES
    except Exception:  # noqa: BLE001
        STUDY_TYPES = (
            "exploratory", "confirmatory", "diagnostic", "adversarial", "standard",
        )
    return tuple(NEXT_ACTION_TYPES), tuple(STUDY_TYPES)


def _check_workflow_typing(ctx: _LintContext) -> None:
    """Soft checks for the wave-3a workflow-typing enums (critique #7 / #10).

    All warning-level (additive / optional fields — existing studies with
    free-text ``next_action`` and no ``study_type`` keep validating):

    - a finding (or followup proposal) sets ``next_action`` but no
      ``next_action_type`` — mirrors the mechanism_origin gap nudge.
    - ``next_action_type`` is set to a value outside the enum.
    - ``study_type`` (or its ``kind`` / ``study_kind`` aliases) is set to a
      value outside the enum.
    """
    spec = ctx.spec
    next_action_types, study_types = _workflow_typing_enums()

    def _check_action(container: dict, path: str) -> None:
        na = container.get("next_action")
        nat = container.get("next_action_type")
        has_na = isinstance(na, str) and na.strip()
        has_nat = isinstance(nat, str) and nat.strip()
        if has_na and not has_nat:
            ctx.add(
                level="warning",
                field_path=f"{path}.next_action_type",
                message=(
                    "next_action is set but next_action_type is absent. Add a "
                    f"machine-readable next_action_type (one of {list(next_action_types)}) "
                    "so the action is filterable; the free-text next_action stays "
                    "as the rationale."
                ),
                check="next_action_type_missing",
            )
        if has_nat and nat.strip() not in next_action_types:
            ctx.add(
                level="warning",
                field_path=f"{path}.next_action_type",
                message=(
                    f"next_action_type {nat.strip()!r} is not a recognised value. "
                    f"Expected one of {list(next_action_types)}."
                ),
                check="next_action_type_unknown",
            )

    findings = spec.get("findings") or []
    if isinstance(findings, list):
        for idx, f in enumerate(findings):
            if isinstance(f, dict):
                _check_action(f, f"findings[{idx}]")

    # followup proposals — both the v3 list and the discovery_implications nest.
    for sect in ("followup_proposals", "followup_study_proposals"):
        items = spec.get(sect) or []
        if isinstance(items, list):
            for idx, p in enumerate(items):
                if isinstance(p, dict):
                    _check_action(p, f"{sect}[{idx}]")
    di = spec.get("discovery_implications")
    if isinstance(di, dict):
        items = di.get("followup_study_proposals") or []
        if isinstance(items, list):
            for idx, p in enumerate(items):
                if isinstance(p, dict):
                    _check_action(p, f"discovery_implications.followup_study_proposals[{idx}]")

    # study_type enum (critique #10) — honor the kind / study_kind aliases.
    raw_st = spec.get("study_type") or spec.get("kind") or spec.get("study_kind")
    if isinstance(raw_st, str) and raw_st.strip() and raw_st.strip().lower() not in study_types:
        field = "study_type" if spec.get("study_type") else (
            "kind" if spec.get("kind") else "study_kind"
        )
        ctx.add(
            level="warning",
            field_path=field,
            message=(
                f"{field} {raw_st.strip()!r} is not a recognised study_type. "
                f"Expected one of {list(study_types)}."
            ),
            check="study_type_unknown",
        )


# ---------------------------------------------------------------------------
# Wave 3b — claim_scope / generality / lifecycle_state soft checks (#21/#22/#25)
# ---------------------------------------------------------------------------


def _wave3b_enums() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """The (claim_scopes, generality_axes, generality_levels, lifecycle_states)
    enums, imported defensively so a missing/renamed source module degrades to
    a built-in copy rather than crashing the lint run."""
    try:
        from viva_superpowers.rigor import (
            CLAIM_SCOPES, GENERALITY_AXES, GENERALITY_LEVELS,
        )
    except Exception:  # noqa: BLE001
        CLAIM_SCOPES = (
            "local-implementation", "mechanism", "behavioral", "theoretical", "generality",
        )
        GENERALITY_AXES = (
            "parameter_regime", "initial_conditions", "discretization", "geometry",
            "alt_implementation", "independent_authoring",
        )
        GENERALITY_LEVELS = ("instance_specific", "mechanism", "framework")
    try:
        from viva_superpowers.study_verdict import LIFECYCLE_STATES
    except Exception:  # noqa: BLE001
        LIFECYCLE_STATES = (
            "observation", "candidate-explanation", "tested-vs-alternatives",
            "provisional-claim", "generalized", "retired", "superseded",
        )
    return (tuple(CLAIM_SCOPES), tuple(GENERALITY_AXES),
            tuple(GENERALITY_LEVELS), tuple(LIFECYCLE_STATES))


def _check_finding_scope_generality_lifecycle(ctx: _LintContext) -> None:
    """Soft (warning-level) validation of the wave-3b per-finding enums and the
    lifecycle floor (critique #21 / #22 / #25). All additive/optional — a study
    with none of these fields validates silently.

    - ``claim_scope`` outside the enum → warning.
    - ``generality.axes_tested`` value outside the enum → warning.
    - ``generality.level`` outside the enum → warning.
    - ``lifecycle_state`` outside the enum → warning.
    - authored ``lifecycle_state`` BELOW the derived floor → warning (#25).
    """
    findings = ctx.spec.get("findings") or []
    if not isinstance(findings, list):
        return
    claim_scopes, gen_axes, gen_levels, lifecycle_states = _wave3b_enums()

    # Defensive import of the lifecycle-floor helper.
    try:
        from viva_superpowers.study_verdict import lifecycle_below_floor
    except Exception:  # noqa: BLE001
        lifecycle_below_floor = None  # type: ignore

    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        fid = f.get("id", f"<index-{idx}>")

        # claim_scope enum (#21)
        cs = f.get("claim_scope")
        if isinstance(cs, str) and cs.strip() and cs.strip().lower() not in claim_scopes:
            ctx.add(
                level="warning",
                field_path=f"findings[{idx}].claim_scope",
                message=(
                    f"Finding {fid!r} claim_scope {cs.strip()!r} is not a recognised value. "
                    f"Expected one of {list(claim_scopes)}."
                ),
                check="claim_scope_unknown",
            )

        # generality enums (#22)
        gen = f.get("generality")
        if isinstance(gen, dict):
            axes = gen.get("axes_tested")
            if isinstance(axes, list):
                for aidx, ax in enumerate(axes):
                    if isinstance(ax, str) and ax.strip() and ax.strip() not in gen_axes:
                        ctx.add(
                            level="warning",
                            field_path=f"findings[{idx}].generality.axes_tested[{aidx}]",
                            message=(
                                f"Finding {fid!r} generality axis {ax.strip()!r} is not a "
                                f"recognised value. Expected one of {list(gen_axes)}."
                            ),
                            check="generality_axis_unknown",
                        )
            lvl = gen.get("level")
            if isinstance(lvl, str) and lvl.strip() and lvl.strip() not in gen_levels:
                ctx.add(
                    level="warning",
                    field_path=f"findings[{idx}].generality.level",
                    message=(
                        f"Finding {fid!r} generality.level {lvl.strip()!r} is not a recognised "
                        f"value. Expected one of {list(gen_levels)}."
                    ),
                    check="generality_level_unknown",
                )

        # lifecycle_state enum + floor (#25)
        ls = f.get("lifecycle_state")
        if isinstance(ls, str) and ls.strip():
            if ls.strip().lower() not in lifecycle_states:
                ctx.add(
                    level="warning",
                    field_path=f"findings[{idx}].lifecycle_state",
                    message=(
                        f"Finding {fid!r} lifecycle_state {ls.strip()!r} is not a recognised value. "
                        f"Expected one of {list(lifecycle_states)}."
                    ),
                    check="lifecycle_state_unknown",
                )
            elif lifecycle_below_floor is not None:
                floor = lifecycle_below_floor(f, ctx.spec)
                if floor:
                    ctx.add(
                        level="warning",
                        field_path=f"findings[{idx}].lifecycle_state",
                        message=(
                            f"Finding {fid!r} authored lifecycle_state {ls.strip()!r} sits below "
                            f"the derived floor {floor!r} (the rigor signals already justify a more "
                            "mature state). Raise lifecycle_state to at least the floor."
                        ),
                        check="lifecycle_state_below_floor",
                    )


# ---------------------------------------------------------------------------
# Pass 10B — band provenance checks (stage 3a)
# ---------------------------------------------------------------------------


# _is_numeric_band: see the top-of-file import — was a local reimplementation
# here that disagreed with band_provenance.py / rigor.py (this one didn't
# count pass_if.value, so a value-style test was invisible to the
# /viva-cite-bands citation-gap worklist yet counted as "sourced" in rigor's
# gate). Now a single import of the canonical band_provenance.has_numeric_band.


def _check_band_test_missing_cites(ctx: _LintContext) -> None:
    """Numeric-band behavior_tests[] / tests[] without cites → warning.

    Expert-sourced acceptance bands (e.g. ``[0.2, 0.5]`` from Boesen 2024)
    should carry a ``cites: [bib_key]`` so the band's source is machine-
    linked rather than buried in prose notes.  This is a *warning* (not an
    error) because it nudges rather than blocks — back-compat with all
    existing uncited studies.
    """
    for section in ("behavior_tests", "tests"):
        items = ctx.spec.get(section) or []
        if not isinstance(items, list):
            continue
        for idx, test in enumerate(items):
            if not isinstance(test, dict):
                continue
            if not _is_numeric_band(test):
                continue
            cites = test.get("cites") or []
            if cites:  # has at least one cite — silent
                continue
            name = test.get("name", f"<index-{idx}>")
            ctx.add(
                level="warning",
                field_path=f"{section}[{idx}]",
                message=(
                    f"Test {name!r} has a numeric acceptance band but no cites. "
                    "Add cites: [bib_key] sourcing the band so its provenance is "
                    "machine-linked (not just prose). See references/papers.bib."
                ),
                check="band_test_missing_cites",
            )


def _check_band_cites_unknown_bib_key(ctx: _LintContext) -> None:
    """cites on behavior_tests, tests, readouts, and calibration_anchor must
    resolve against ``references/papers.bib``.

    Mirrors ``_check_finding_cites_unknown_bib_key``: silent when no
    ``papers.bib`` exists, error otherwise.
    """
    known = _cached(ctx, "bib_keys", lambda: _bib_keys_for_workspace(ctx.ws_root))
    if not known:
        # No bibliography to compare against — silent (same contract as finding check).
        return

    # behavior_tests[] and tests[]
    for section in ("behavior_tests", "tests"):
        items = ctx.spec.get(section) or []
        if not isinstance(items, list):
            continue
        for idx, test in enumerate(items):
            if not isinstance(test, dict):
                continue
            name = test.get("name", f"<index-{idx}>")
            # Direct cites on the test
            cites = test.get("cites") or []
            if isinstance(cites, list):
                for cidx, key in enumerate(cites):
                    if isinstance(key, str) and key not in known:
                        ctx.add(
                            level="error",
                            field_path=f"{section}[{idx}].cites[{cidx}]",
                            message=(
                                f"Test {name!r} cites unknown bib_key {key!r}. "
                                "Add it to references/papers.bib first."
                            ),
                            check="band_cites_unknown_bib_key",
                        )
            # calibration_anchor.cites
            anch = test.get("calibration_anchor") or {}
            if isinstance(anch, dict):
                anch_cites = anch.get("cites") or []
                if isinstance(anch_cites, list):
                    for cidx, key in enumerate(anch_cites):
                        if isinstance(key, str) and key not in known:
                            ctx.add(
                                level="error",
                                field_path=f"{section}[{idx}].calibration_anchor.cites[{cidx}]",
                                message=(
                                    f"Test {name!r} calibration_anchor cites unknown bib_key "
                                    f"{key!r}. Add it to references/papers.bib first."
                                ),
                                check="band_cites_unknown_bib_key",
                            )

    # readouts[]
    readouts = ctx.spec.get("readouts") or []
    if isinstance(readouts, list):
        for idx, ro in enumerate(readouts):
            if not isinstance(ro, dict):
                continue
            name = ro.get("name", f"<index-{idx}>")
            cites = ro.get("cites") or []
            if isinstance(cites, list):
                for cidx, key in enumerate(cites):
                    if isinstance(key, str) and key not in known:
                        ctx.add(
                            level="error",
                            field_path=f"readouts[{idx}].cites[{cidx}]",
                            message=(
                                f"Readout {name!r} cites unknown bib_key {key!r}. "
                                "Add it to references/papers.bib first."
                            ),
                            check="band_cites_unknown_bib_key",
                        )


# ---------------------------------------------------------------------------
# 11. visualization_address_unresolved
# ---------------------------------------------------------------------------


import re as _re

_VIZ_CLASS_RE = _re.compile(r"^\s*class\s+(\w+)\s*[\(:]", _re.MULTILINE)
_VIZ_DEF_RE = _re.compile(r"^\s*def\s+update_(\w+)\s*\(", _re.MULTILINE)


def _viz_classes_in_workspace(ws_root: Path) -> set[str]:
    """Scan every <ws_root>/*/visualizations/ and <ws_root>/visualizations/
    for class definitions and `update_*` factory functions. Returns the set
    of names that a `local:<Name>` address could resolve to.

    Static analysis only — no module import. For `update_foo_bar` the helper
    yields both `foo_bar` and `FooBar` (the `as_visualization` decorator
    derives the registered class name from the function's snake_case
    suffix, and dashboard usage uses either form).
    """
    out: set[str] = set()
    candidates: list[Path] = []
    try:
        children = list(ws_root.iterdir())
    except OSError:
        return out
    for child in children:
        if not child.is_dir():
            continue
        v = child / "visualizations"
        if v.is_dir():
            candidates.append(v)
    direct = ws_root / "visualizations"
    if direct.is_dir():
        candidates.append(direct)
    for d in candidates:
        for py in d.rglob("*.py"):
            try:
                src = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for m in _VIZ_CLASS_RE.finditer(src):
                out.add(m.group(1))
            for m in _VIZ_DEF_RE.finditer(src):
                snake = m.group(1)
                pascal = "".join(part.capitalize() for part in snake.split("_"))
                out.add(snake)
                out.add(pascal)
    return out


def _check_visualization_addresses(ctx: _LintContext) -> None:
    """Each ``study.visualizations[].address`` of the form ``local:<Name>``
    must resolve to a class declared somewhere under a workspace
    ``<package>/visualizations/`` directory. Otherwise the dashboard renders
    the entry as text with no chart and gives no clue why.

    Dotted-path addresses (``pkg.module.ClassName``) are intentionally NOT
    checked here — that would require importing arbitrary workspace code
    inside the linter. Authors of dotted addresses should test them with
    ``/viva-study preview-viz``.
    """
    viz = ctx.spec.get("visualizations") or []
    if not isinstance(viz, list):
        return
    known: set[str] | None = None  # lazy: only scan the FS when needed
    for idx, v in enumerate(viz):
        if not isinstance(v, dict):
            continue
        addr = v.get("address")
        # mem3dg-readdy friction #26: study.yaml.visualizations entries
        # missing `address:` would 500 at render time with KeyError:
        # 'address'. The error surfaces inside the rendered viz iframe and
        # is invisible to anyone not opening the dashboard. Catch it at
        # lint time instead, naming the workspace.yaml.visualizations[].class
        # cross-reference as the natural fix.
        if not isinstance(addr, str) or not addr:
            viz_name = v.get("name", f"<index-{idx}>")
            ctx.add(
                level="error",
                field_path=f"visualizations[{idx}].address",
                message=(
                    f"Visualization {viz_name!r} has no `address:` field. "
                    "The dashboard's renderer raises KeyError('address') and "
                    "produces an error-stub HTML iframe (invisible to lint, "
                    "visible in the dashboard). Add `address: local:<ClassName>` "
                    "pointing at a class in <package>/visualizations/, or set "
                    "`workspace.yaml.visualizations[].class` and reference it "
                    "from the study by name."
                ),
                check="visualization_address_missing",
            )
            continue
        if not addr.startswith("local:"):
            continue  # dotted paths out of scope
        cls = addr[len("local:"):].strip()
        if not cls:
            continue
        if known is None:
            known = _cached(ctx, "viz_classes", lambda: _viz_classes_in_workspace(ctx.ws_root))
        if cls in known:
            continue
        viz_name = v.get("name", f"<index-{idx}>")
        ctx.add(
            level="error",
            field_path=f"visualizations[{idx}].address",
            message=(
                f"Visualization {viz_name!r} address {addr!r} is not registered. "
                f"No class {cls!r} was found under any workspace "
                f"<package>/visualizations/ directory. Add the class there, "
                f"or change the address to a dotted module path "
                f"(e.g. 'viva_superpowers.visualizations.TimeSeriesFromObservables')."
            ),
            check="visualization_address_unresolved",
        )


# ---------------------------------------------------------------------------
# 12. dag_edges_legacy_and_canonical_both_set
# ---------------------------------------------------------------------------


def _parent_slug(entry) -> str | None:
    """Pull the parent slug out of either legacy entry shape (bare-string or
    ``{study: <slug>}`` dict)."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("study"), str):
        return entry["study"]
    return None


def _inputs_from_slugs(spec) -> set[str]:
    """Canonical DAG edges: the set of ``from:`` slugs across the top-level
    ``inputs:`` list (each entry is ``{artifact: <slug>, from: <slug>}``)."""
    return {
        e["from"]
        for e in (spec.get("inputs") or [])
        if isinstance(e, dict) and e.get("from")
    }


# How to spell the canonical form in author-facing messages. Single-sourced so
# every DAG-edge finding recommends the same migration target.
_INPUTS_FROM_HINT = (
    "a top-level `inputs:` list of `{artifact: <slug>, from: <slug>}` entries "
    "(the DAG edge set is the `from:` slugs)"
)


def _check_dag_edges_legacy_and_canonical_both_set(ctx: _LintContext) -> None:
    """A study should declare its DAG edges via the canonical top-level
    ``inputs:`` list — each entry ``{artifact: <slug>, from: <slug>}``, the
    edge set being the ``from:`` slugs. This is the form the v2ecoli workspace
    conformance test now REQUIRES (it asserts ``parent_studies`` and
    ``pipeline_gate.prerequisites`` are both absent).

    The two older forms — ``parent_studies`` (oldest) and
    ``pipeline_gate.prerequisites`` (interim) — are now BOTH legacy. They are
    still accepted as back-compat, so this check never hard-errors on them;
    it only warns to migrate to ``inputs.from``.

    Findings shapes (all warnings — legacy never blocks):

    - only a legacy field set (no ``inputs.from``): migrate warning.
    - legacy + canonical set, legacy ⊆ canonical: the legacy field is
      redundant — drop it (warning).
    - legacy + canonical set, legacy has slugs NOT in canonical: the extra
      legacy edges are silently ignored downstream — reconcile (warning).
    """
    canonical = _inputs_from_slugs(ctx.spec)

    parent_raw = ctx.spec.get("parent_studies") or []
    pg = ctx.spec.get("pipeline_gate") or {}
    prereq_raw = pg.get("prerequisites") if isinstance(pg, dict) else None

    legacy_parent = {s for s in (_parent_slug(e) for e in parent_raw) if s}
    legacy_prereq = {s for s in (_parent_slug(e) for e in (prereq_raw or [])) if s}
    legacy = legacy_parent | legacy_prereq

    # Which legacy field(s) are present, spelled for the message. The first is
    # used as the finding's field_path anchor.
    legacy_fields: list[str] = []
    if legacy_parent:
        legacy_fields.append("parent_studies")
    if legacy_prereq:
        legacy_fields.append("pipeline_gate.prerequisites")
    field_anchor = legacy_fields[0] if legacy_fields else "inputs"
    legacy_names = " and ".join(f"`{f}`" for f in legacy_fields)

    if not legacy:
        # Either canonical-only (clean) or nothing declared — no finding.
        return

    if not canonical:
        ctx.add(
            level="warning",
            field_path=field_anchor,
            message=(
                f"Study declares DAG edges via the legacy {legacy_names} "
                f"field. Migrate to {_INPUTS_FROM_HINT}. The legacy field is "
                "still accepted as a back-compat fallback, but the canonical "
                "form is `inputs.from` (v2ecoli workspace conformance requires "
                "it and rejects the legacy fields)."
            ),
            check="dag_edges_legacy_only",
        )
        return

    # Both canonical and legacy are set.
    if legacy <= canonical:
        ctx.add(
            level="warning",
            field_path=field_anchor,
            message=(
                f"Study declares parents in both the legacy {legacy_names} "
                f"field and the canonical `inputs.from` set — the legacy "
                "entries are already covered by `inputs.from`. Drop the "
                f"legacy {legacy_names} field; DAG edges live in "
                f"{_INPUTS_FROM_HINT}."
            ),
            check="dag_edges_legacy_redundant",
        )
    else:
        ctx.add(
            level="warning",
            field_path=field_anchor,
            message=(
                "Study declares conflicting DAG edges: the legacy "
                f"{legacy_names} field lists {sorted(legacy)} but the "
                f"canonical `inputs.from` set lists {sorted(canonical)}. "
                "Downstream reads only `inputs.from`, so the extra legacy "
                f"edges are silently ignored. Reconcile into {_INPUTS_FROM_HINT}."
            ),
            check="dag_edges_legacy_and_canonical_disagree",
        )


# ---------------------------------------------------------------------------
# 13. status_legacy_only — F1 (multi-axis status canonical)
# ---------------------------------------------------------------------------


_MULTI_AXIS_STATUS_FIELDS = (
    "design_status",
    "implementation_status",
    "simulation_status",
    "evaluation_status",
    "gate_status",
    "expert_review_status",
)


def _check_status_legacy_only(ctx: _LintContext) -> None:
    """A study should set at least one Pass A multi-axis status field
    (design_status, implementation_status, simulation_status,
    evaluation_status, gate_status, expert_review_status) instead of the
    legacy `status` enum. The dashboard's effective_status() helper still
    falls back to `status` for back-compat, but the legacy field can't
    carry the orthogonal-axes semantics — a study can be
    `simulation_status: ran` AND `evaluation_status: failed_evaluation`
    at the same time, which a single `status` can't express.

    Fires a warning when `status` is set and NO multi-axis field is set.
    Silent when at least one multi-axis field is set (regardless of
    whether `status` is ALSO set — the dashboard prefers the multi-axis
    value, so redundancy here is harmless drift, not a foot-gun).
    """
    legacy = ctx.spec.get("status")
    if not legacy:
        return
    has_multi_axis = any(ctx.spec.get(f) for f in _MULTI_AXIS_STATUS_FIELDS)
    if has_multi_axis:
        return
    ctx.add(
        level="warning",
        field_path="status",
        message=(
            f"Study uses the legacy `status: {legacy!r}` field with no "
            "multi-axis status set. The canonical fields are the six "
            "Pass A axes (design_status, implementation_status, "
            "simulation_status, evaluation_status, gate_status, "
            "expert_review_status). The dashboard still reads `status` "
            "as a back-compat fallback, but the legacy enum can't carry "
            "the orthogonal-axes semantics — e.g. a study can be "
            "simulation_status:ran AND evaluation_status:failed_evaluation "
            "simultaneously, which `status` alone cannot express."
        ),
        check="status_legacy_only",
    )


# ---------------------------------------------------------------------------
# 14. runs_yaml_vs_db_drift — F2 (runs.db is canonical)
# ---------------------------------------------------------------------------


def _runs_db_path(ws_root: Path, slug: str) -> Path:
    return WorkspacePaths.load(ws_root).studies / slug / "runs.db"


def _runs_db_run_ids(ws_root: Path, slug: str) -> set[str]:
    """Return the set of run_ids in studies/<slug>/runs.db (runs_meta +
    simulations). Empty set if the DB is missing or broken."""
    db = _runs_db_path(ws_root, slug)
    if not db.is_file():
        return set()
    import sqlite3 as _sql
    out: set[str] = set()
    try:
        conn = _sql.connect(str(db))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "runs_meta" in tables:
            for r in conn.execute("SELECT run_id FROM runs_meta"):
                out.add(r[0])
        if "simulations" in tables:
            for r in conn.execute("SELECT simulation_id FROM simulations"):
                out.add(r[0])
        conn.close()
    except _sql.Error:
        return set()
    return out


def _runs_db_rows(ws_root: Path, slug: str) -> list[dict]:
    """Return [{run_id, status}] from studies/<slug>/runs.db runs_meta.

    Empty list if the DB is missing/broken. Used to derive simulation
    status from execution state (status-drift check).
    """
    db = _runs_db_path(ws_root, slug)
    if not db.is_file():
        return []
    import sqlite3 as _sql
    out: list[dict] = []
    try:
        conn = _sql.connect(str(db))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "runs_meta" in tables:
            for r in conn.execute("SELECT run_id, status FROM runs_meta"):
                out.append({"run_id": r[0], "status": r[1]})
        conn.close()
    except _sql.Error:
        return []
    return out


def _check_status_out_of_date_vs_runs(ctx: _LintContext) -> None:
    """v2ecoli round-2 friction #2: a report shipped a "planning" status after
    all studies had executed. Derive the observable status from runs.db and
    flag any stored axis (or a legacy planning headline) that contradicts it,
    so the drift is caught pre-publication instead of by the expert.
    """
    try:
        from viva_superpowers import study_status as _ss
    except ImportError:
        return
    rows = _runs_db_rows(ctx.ws_root, ctx.slug)
    for dis in _ss.status_disagreements(ctx.spec, rows):
        ctx.add(
            level="error",
            field_path=dis.get("axis", "status"),
            message=dis.get("message", "status is out of date relative to runs"),
            check="status_out_of_date_vs_runs",
        )


def _check_status_claims_done_but_no_runs_recorded(ctx: _LintContext) -> None:
    """Forward-drift: a study DECLARES completion/pass but records no runs.

    ``status_disagreements`` deliberately ignores this direction — a stored
    ``ran`` with an empty *local* runs.db is ambiguous, because the db may live
    in a different checkout. But when the study's OWN spec carries no ``runs:``
    block AND runs.db is empty, there is nothing in-repo backing the claim, so
    the derive-on-read ``simulation_status`` resolves to ``not_run`` and the
    report renders the study as "pending / not run" even though its headline
    says passed.

    This is the gap a reviewer hit on v2ecoli dnaa-replication (Rashmi,
    2026-05-31): "I think the first study is passed. But I am not sure whether
    it ran the simulations or not. Tests still show pending." The two
    foundational studies declared ``status: completed`` / ``gate_status:
    passed`` but had no ``runs:`` block, so the report showed them as not-run.
    Warning-level (non-blocking): the fix is to record a ``runs:`` block with
    parquet provenance, or to correct the status to match what actually ran.
    """
    spec = ctx.spec
    legacy = str(spec.get("status") or "").strip().lower()
    claims_done = (
        legacy in {"completed", "complete", "done", "passed"}
        or spec.get("gate_status") == "passed"
        or spec.get("evaluation_status") == "evaluated"
        or spec.get("simulation_status") == "ran"
    )
    if not claims_done:
        return
    # "Run provenance" = the author recorded SOMETHING about execution: a
    # `runs:` block (what derive_simulation_status actually reads), or at least
    # a `simulation_set:` / `planned_runs:` block. Only flag when ALL of these
    # are absent and runs.db is empty — i.e. the study claims done but records
    # nothing whatsoever about what ran (the dnaa-0/1 pre-migration state).
    has_evidence = any(
        isinstance(spec.get(k), list) and len(spec.get(k)) > 0
        for k in ("runs", "simulation_set", "planned_runs")
    )
    if has_evidence:
        return
    try:
        if _runs_db_rows(ctx.ws_root, ctx.slug):
            return  # runs.db has rows → backed by local execution state
    except Exception:
        pass
    claimed_by = (
        "gate_status: passed" if spec.get("gate_status") == "passed"
        else "evaluation_status: evaluated"
        if spec.get("evaluation_status") == "evaluated"
        else "simulation_status: ran" if spec.get("simulation_status") == "ran"
        else f"status: {spec.get('status')!r}"
    )
    ctx.add(
        level="warning",
        field_path="runs",
        message=(
            f"study declares completion ({claimed_by}) but records no runs "
            "anywhere — no `runs:`, `simulation_set:`, or `planned_runs:` block "
            "and runs.db has no rows. With no `runs:` block, simulation_status "
            "derives to not_run and the report shows this study as "
            "not-run/pending despite the passing headline. Add a `runs:` block "
            "with parquet provenance (see another study's `runs:` for the "
            "shape) or correct the status to match what actually ran."
        ),
        check="status_claims_done_no_runs_recorded",
    )


def _check_reviewer_clarity_ambiguities(ctx: _LintContext) -> None:
    """Surface anything that would render ambiguously on the reviewer-facing
    run/test/verdict strip — single-sourced from
    ``study_status.study_clarity_summary`` so the linter flags exactly what the
    report would show unclearly. Covers the "ran but every test renders pending"
    and "gate passed but a test FAILED" cases (the dnaa-replication 2026-05-31
    feedback). The "declares done but no runs" case is left to
    ``status_claims_done_no_runs_recorded`` to avoid double-flagging.
    """
    try:
        from viva_superpowers import study_status as _ss
    except ImportError:
        return
    summary = _ss.study_clarity_summary(ctx.spec, ctx.spec.get("runs"))
    for note in summary.get("ambiguities", []):
        if "no runs are recorded" in note or "renders as" in note:
            continue  # handled by status_claims_done_no_runs_recorded
        ctx.add(
            level="warning",
            field_path="runs[].outcomes" if "pending" in note else "gate_status",
            message=f"reviewer-facing clarity: {note}",
            check="reviewer_clarity_ambiguity",
        )


def _check_viz_stale_vs_latest_run(ctx: _LintContext) -> None:
    """Charts whose source run != the study's latest run (or unrendered), and
    on-disk charts not in visualizations[]. warning by default; error under --strict.

    Supersedes the older mtime-based ``figure_stale_vs_run`` check: this uses the
    chart's stamped ``source_run_id`` provenance (viz_freshness) against the
    study's latest run in runs.db (run_registry), which is far more precise than
    comparing file mtimes.
    """
    from .viz_freshness import chart_freshness, manifest_diff
    from .run_registry import latest_run
    spec = ctx.spec
    study_dir = ctx.ws_root / "studies" / ctx.slug
    latest = latest_run(study_dir / "runs.db")
    entries = spec.get("visualizations") or []

    stale = []
    for e in entries:
        if not (e or {}).get("chart"):
            continue  # legacy address-only entries aren't chart-provenance-tracked
        state = chart_freshness(study_dir, e, latest)
        if state in ("stale", "unrendered"):
            stale.append((e.get("name"), state))
    untracked = list(manifest_diff(study_dir, entries)["untracked"])
    if not stale and not untracked:
        return

    # Fold the per-chart findings into ONE per-study finding so viz hygiene
    # stops dominating the gap count (gaps = error + warning) and the readiness
    # panel leads with substantive findings (needs_human readouts, uncited
    # bands). Demoted to INFO by default — a nudge, not a publication gap — but
    # still promoted to ERROR under --strict so the publish gate is preserved.
    level = "error" if getattr(ctx, "strict", False) else "info"
    parts = []
    if untracked:
        parts.append(
            f"{len(untracked)} chart(s) on disk not registered in visualizations[] "
            "(register with a render: command or remove)"
        )
    if stale:
        names = ", ".join(f"{n!r} ({s})" for n, s in stale)
        parts.append(
            f"{len(stale)} registered visualization(s) stale/unrendered vs the "
            f"study's latest run — {names} (run /viva-study refresh-viz)"
        )
    ctx.add(level=level, field_path="visualizations",
            message="; ".join(parts) + ".",
            check="viz_stale_vs_latest_run")


def _check_runs_yaml_vs_db_drift(ctx: _LintContext) -> None:
    """Per F2, runs.db is the canonical record of which runs exist. The
    `study.yaml.runs[]` field stays in the schema as a soft-deprecated
    back-compat shim — the dashboard still reads it as a fallback count,
    but new runs land only in runs.db.

    Drift is a foot-gun in two directions:

    - WARNING: `runs[]` has run_ids that runs.db does NOT have. Either
      the run records were copied from a previous workspace without
      copying runs.db, or the DB was wiped and the yaml wasn't —
      either way the dashboard will keep showing those runs but the
      Runs tab can't pull their metadata. Tell the user to either
      restore runs.db or migrate (drop the legacy entries).

    - INFO: `runs[]` and runs.db both list the same run_ids. Redundant
      but not broken — the workspace is mid-migration. Migrate at next
      edit.

    Silent when:
    - `runs[]` is absent or empty (the F2 target state).
    - runs.db doesn't exist AND `runs[]` is also empty (pristine study).
    """
    yaml_runs = ctx.spec.get("runs") or []
    if not yaml_runs:
        return

    yaml_ids = {
        r.get("run_id") for r in yaml_runs
        if isinstance(r, dict) and r.get("run_id")
    }
    if not yaml_ids:
        return  # malformed entries — out of scope

    db_ids = _runs_db_run_ids(ctx.ws_root, ctx.slug)
    yaml_only = yaml_ids - db_ids

    if yaml_only:
        ctx.add(
            level="warning",
            field_path="runs",
            message=(
                f"study.yaml.runs[] lists {len(yaml_only)} run_id(s) absent "
                f"from runs.db: {sorted(yaml_only)[:3]}"
                + (" …" if len(yaml_only) > 3 else "")
                + ". F2: runs.db is the canonical source of truth. The "
                "dashboard reads runs[] as a back-compat fallback, but "
                "metadata (params, started_at, log_path) only lives in "
                "runs.db. Either restore the runs.db rows or migrate by "
                "dropping these entries from study.yaml.runs[]."
            ),
            check="runs_yaml_vs_db_drift",
        )
        return

    # All yaml ids are also in db_ids — redundant entries from a legacy
    # write path. Migration is to drop runs[] entirely.
    ctx.add(
        level="info",
        field_path="runs",
        message=(
            f"study.yaml.runs[] redundantly lists {len(yaml_ids)} run_id(s) "
            "that runs.db already records. F2 makes runs.db canonical — "
            "drop study.yaml.runs[] at the next edit. The dashboard reads "
            "it only as a back-compat fallback count."
        ),
        check="runs_yaml_vs_db_redundant",
    )


def _check_runs_without_emitter(ctx: _LintContext) -> None:
    """Soft-WARN: a study records runs but none are persisted via an emitter.

    Future-proofing (composites + emitters): every investigation should persist
    its run trajectories via an emitter (sqlite / parquet / xarray) so results are
    reproducible from disk, not just summarised. A run record evidences this by
    carrying an ``emitter`` or a run-db reference (see
    :func:`viva_superpowers.rigor.run_is_emitter_backed`) — the same predicate the
    ``run_persistence`` rigor dimension uses.

    Warning-level (non-blocking). Silent when:

    - the study records no ``runs[]`` (nothing to persist), or
    - at least one run record IS emitter-backed, or
    - ``studies/<slug>/runs.db`` exists with rows on disk — the canonical
      persistence (F2) is present even if the YAML records don't restate it, so
      warning would be a false positive.
    """
    runs = [r for r in (ctx.spec.get("runs") or []) if isinstance(r, dict)]
    if not runs:
        return
    if any(run_is_emitter_backed(r) for r in runs):
        return
    # Canonical persistence may live in runs.db even when the YAML records omit
    # the emitter field — don't warn when the DB has rows on disk.
    try:
        if _runs_db_rows(ctx.ws_root, ctx.slug):
            return
    except Exception:  # noqa: BLE001 — defensive: a missing/locked DB is not "persisted"
        pass
    ctx.add(
        level="warning",
        field_path="runs",
        message=(
            f"study records {len(runs)} run(s) but none are persisted via an emitter "
            "(no run carries emitter: sqlite/parquet/xarray or a run-db reference, and "
            "runs.db has no rows). Persist run trajectories via the workspace emitter so "
            "results are reproducible from disk, not just summarised."
        ),
        check="runs_without_emitter",
    )


# ---------------------------------------------------------------------------
# v4 narrative-spine completeness check
# ---------------------------------------------------------------------------


# The 14 v4 narrative-spine sections plus their v3 fallbacks (where one
# exists). The 7 ★ sections are the ones a reviewer most needs at the top
# of the rendered report; the other 7 are encouraged but optional.
#
# Each entry: (canonical_field, fallback_field_or_None, is_star).
# - canonical_field is the v4 field name.
# - fallback_field is the v3/legacy field that satisfies the section (so a
#   v3 spec with question + behavior_tests + baseline isn't flagged for
#   missing report/study_card/conditions — it just gets the v4-only fields
#   reported as missing).
# - is_star indicates whether this is a top-of-report ★ section.

_NARRATIVE_SECTIONS = (
    # Executive layer
    ("runtime",                      None,                  False),
    ("report",                       None,                  True),
    ("study_card",                   None,                  True),
    # Framing layer
    ("question",                     "purpose.question",    True),
    ("assumptions",                  "key_assumptions",     False),
    ("conditions",                   "baseline",            True),
    ("enforced_params",              None,                  False),
    # Validation layer
    ("behavior_tests",               "expected_behavior",   True),
    ("readouts",                     "observables",         True),
    ("biological_summary",           None,                  False),
    ("literature_anchors",           None,                  False),
    # Implementation + decisions layer
    ("model_change",                 None,                  False),
    ("implementation_requirements",  None,                  False),
    ("design_pivot_required",        None,                  False),
    ("conclusion_verdicts",          None,                  True),
)


def _is_present(spec: dict, dotted_path: str) -> bool:
    """True iff dotted_path resolves to a non-empty value on spec."""
    cur = spec
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return _is_nonempty(cur)


def _check_narrative_spine_completeness(ctx: _LintContext) -> None:
    """v4 narrative-spine nudge — info-level reminder of which dnaa-style
    sections the study has not authored yet.

    Emits ONE finding per study aggregating ALL missing sections, rather
    than 14 separate findings, so the report shows
    "narrative incomplete: 4 sections missing (report, study_card, ...)".
    Severity is `info` — this lint is a nudge, not a publication blocker;
    a v3 study with question + behavior_tests + baseline still validates
    and can publish, it just won't have the dnaa-style narrative spine.

    See docs/concepts/vivarium-workbench-model.md#v4-narrative-spine for
    the full section list and authoring guidance.
    """
    # Skip workspace-level pseudo-specs (the iterator may include a
    # workspace.yaml-aggregate row that doesn't correspond to a study).
    if ctx.slug == "<workspace>":
        return

    missing_star: list[str] = []
    missing_other: list[str] = []
    for canonical, fallback, is_star in _NARRATIVE_SECTIONS:
        if _is_present(ctx.spec, canonical):
            continue
        if fallback and _is_present(ctx.spec, fallback):
            continue
        (missing_star if is_star else missing_other).append(canonical)

    if not missing_star and not missing_other:
        return

    n_missing = len(missing_star) + len(missing_other)
    star_str = (
        f" ★ {', '.join(missing_star)}"
        if missing_star else ""
    )
    other_str = (
        f" · other: {', '.join(missing_other)}"
        if missing_other else ""
    )
    ctx.add(
        level="info",
        field_path="(narrative spine)",
        message=(
            f"narrative incomplete: {n_missing} of {len(_NARRATIVE_SECTIONS)} "
            f"v4 sections missing.{star_str}{other_str}. "
            "See docs/concepts/vivarium-workbench-model.md#v4-narrative-spine "
            "for the full pattern, or /viva-study fill-overview <slug> "
            "--include-narrative to draft them from plan + expert PDFs."
        ),
        check="narrative_spine_completeness",
    )


# ---------------------------------------------------------------------------
# Expert-handoff readiness — every study card in a generated report should
# show baseline composites, variants planned, simulation runs planned,
# readouts, runs, tests, and visualizations. When any of these blocks is
# absent or empty, the expert reviewer sees a blank section instead of
# planned content they can critique. These five warnings flag the gap
# pre-publication.
#
# All warning-level (non-blocking). The study can still publish; the
# nudge is to add scaffolded content (variant ideas, planned runs,
# placeholder viz with mockup data) so the report tells a complete
# story before the runs land.
# ---------------------------------------------------------------------------


def _check_missing_baseline(ctx: _LintContext) -> None:
    """Warning when a study has no baseline composite(s) declared.

    The dashboard's run-runner needs at least one baseline to know what
    to simulate; the report renderer uses baselines to populate the
    "Conditions" panel of each study card.  An empty/absent baseline
    means the expert sees no concrete starting point.
    """
    if ctx.slug == "<workspace>":
        return
    baseline = ctx.spec.get("baseline")
    has_v3_baseline = isinstance(baseline, list) and len(baseline) > 0
    # v4 conditions.baseline alternative shape
    conditions = ctx.spec.get("conditions") or {}
    cond_baseline = conditions.get("baseline") if isinstance(conditions, dict) else None
    has_v4_baseline = isinstance(cond_baseline, dict) and bool(cond_baseline.get("composite"))
    if has_v3_baseline or has_v4_baseline:
        return
    ctx.add(
        level=_completeness_level(ctx.spec, warn_at="Build"),
        field_path="baseline",
        message=(
            "Study has no baseline composite declared. Every study card in "
            "the generated report should show at least one concrete baseline "
            "(`baseline: [{name, composite, params}]` for v3, or "
            "`conditions.baseline: {composite, params}` for v4) so the "
            "expert reviewer knows what's being simulated. Scaffold one even "
            "if the composite path is a placeholder — see /viva-study baseline-add."
        ),
        check="missing_baseline",
    )


def _check_missing_variants(ctx: _LintContext) -> None:
    """Warning when a study has no `variants:` planned.

    Variants are the planned perturbations / configurations the study
    will run. A study with no variants reads to the expert as "design
    incomplete — no specific experimental conditions yet."
    """
    if ctx.slug == "<workspace>":
        return
    variants = ctx.spec.get("variants") or []
    # v4 alternate location
    conditions = ctx.spec.get("conditions") or {}
    v4_variants = conditions.get("variants") if isinstance(conditions, dict) else []
    if (isinstance(variants, list) and len(variants) > 0) or \
       (isinstance(v4_variants, list) and len(v4_variants) > 0):
        return
    ctx.add(
        level=_completeness_level(ctx.spec, warn_at="Build"),
        field_path="variants",
        message=(
            "Study has no variants declared. Variants are the planned "
            "perturbations / configurations to be tested (parameter sweeps, "
            "alternative conditions, perturbation experiments). A study "
            "with no variants reads to a reviewer as 'design incomplete'. "
            "Scaffold ≥1 variant via /viva-study variant-add — even a "
            "single 'reference' variant with the published parameters is "
            "better than an empty list."
        ),
        check="missing_variants",
    )


def _check_missing_planned_runs(ctx: _LintContext) -> None:
    """Warning when a study has no `planned_runs:` and no `runs:`.

    `planned_runs[]` documents the experiments the study WILL execute
    (with status: planned + n_steps + brief details). `runs[]` is for
    completed runs. A study with neither tells the expert nothing about
    what's been run or what's planned.
    """
    if ctx.slug == "<workspace>":
        return
    planned = ctx.spec.get("planned_runs") or []
    runs = ctx.spec.get("runs") or []
    if (isinstance(planned, list) and len(planned) > 0) or \
       (isinstance(runs, list) and len(runs) > 0):
        return
    ctx.add(
        level=_completeness_level(ctx.spec, warn_at="Simulate"),
        field_path="planned_runs",
        message=(
            "Study has no planned_runs[] and no runs[]. Document the "
            "experiments the study will execute (status: planned, with "
            "n_steps + 1-sentence details) so the expert sees the "
            "planned methodology + compute scope. Use planned_runs[] for "
            "what's coming, runs[] for what's completed."
        ),
        check="missing_planned_runs",
    )


def _check_missing_readouts(ctx: _LintContext) -> None:
    """Warning when a study has no `readouts:` field/content.

    `readouts` describes what the study actually measures — the
    observables that the tests in `expected_behavior` evaluate against.
    Without it, the test rows reference concepts the expert reviewer has
    no anchor for.
    """
    if ctx.slug == "<workspace>":
        return
    readouts = ctx.spec.get("readouts")
    if isinstance(readouts, str) and readouts.strip():
        return
    if isinstance(readouts, list) and len(readouts) > 0:
        return
    ctx.add(
        level=_completeness_level(ctx.spec, warn_at="Simulate"),
        field_path="readouts",
        message=(
            "Study has no readouts declared. Describe what the study "
            "actually measures (the observables the expected_behavior "
            "tests evaluate against) so the expert reviewer has anchors "
            "for the test rows. Free-form string or list of strings."
        ),
        check="missing_readouts",
    )


def _check_missing_conditions_block(ctx: _LintContext) -> None:
    """Warning when a study has no `conditions:` block populated.

    The dashboard's study-detail template (`study-detail.html`) renders
    the "Build" tab from `conditions.baseline` + `conditions.variants` +
    `conditions.model_settings`. Without those, the Build tab is blank
    even if the legacy v3 `baseline:` + `variants:` lists are populated.

    The cleanest path is to use v4 `conditions:` from the start so the
    Build tab is informative.
    """
    if ctx.slug == "<workspace>":
        return
    cond = ctx.spec.get("conditions") or {}
    if not isinstance(cond, dict):
        cond = {}
    has_baseline   = isinstance(cond.get("baseline"), dict) and bool(cond["baseline"].get("composite"))
    has_variants   = isinstance(cond.get("variants"), list)   and len(cond["variants"]) > 0
    has_settings   = isinstance(cond.get("model_settings"), list) and len(cond["model_settings"]) > 0
    # Also accept legacy Build-tab fields as a partial fallback.
    has_legacy = bool(ctx.spec.get("model_change")) or bool(ctx.spec.get("implementation_requirements"))
    if has_baseline or has_variants or has_settings or has_legacy:
        return
    ctx.add(
        level="warning",
        field_path="conditions",
        message=(
            "Study has no `conditions:` block (or legacy `model_change` / "
            "`implementation_requirements`). The dashboard's study-detail "
            "Build tab renders from `conditions.{baseline,variants,"
            "model_settings}`. Without it the Build tab is BLANK for "
            "this study, even if v3 `baseline:` + `variants:` are "
            "populated. Add at minimum a `conditions.baseline.composite` "
            "value; see the study lint-checks + data-model reference in "
            "docs/concepts/vivarium-workbench-model.md."
        ),
        check="missing_conditions_block",
    )


def _check_missing_simulation_set(ctx: _LintContext) -> None:
    """Warning when a study has no `simulation_set:` entries.

    The dashboard's study-detail template renders the "Simulations" tab
    from `simulation_set:` (a list of detailed run specs: name, kind,
    status, base_model, duration_steps, seeds, metrics, pass_fail_tests).
    Without it, the Simulations tab is blank.
    """
    if ctx.slug == "<workspace>":
        return
    ss = ctx.spec.get("simulation_set") or []
    if isinstance(ss, list) and len(ss) > 0:
        return
    ctx.add(
        level=_completeness_level(ctx.spec, warn_at="Simulate"),
        field_path="simulation_set",
        message=(
            "Study has no `simulation_set:` entries. The dashboard's "
            "study-detail Simulations tab renders from this list (each "
            "entry: name, kind, status, base_model, duration_steps, "
            "seeds, metrics, pass_fail_tests). Without it the "
            "Simulations tab is BLANK. For studies that have v3 "
            "`planned_runs:` instead, translate each entry into a "
            "`simulation_set` entry (the v3 field stays as back-compat)."
        ),
        check="missing_simulation_set",
    )


def _check_missing_visualizations(ctx: _LintContext) -> None:
    """Warning when a study has no `visualizations:` entries.

    Visualizations are the cards the dashboard / generated report
    renders inline. A study with no viz entries gives the expert no
    figure to review. For studies pre-run, scaffold ≥1 PLANNED-mockup
    viz showing what the chart WILL look like when real data lands.
    """
    if ctx.slug == "<workspace>":
        return
    # A study "has a visualization" via any of the surfaces the dashboard
    # actually renders: declared visualizations[], declared
    # embed_visualizations[], or auto-discovered HTML in the canonical
    # reports/figures/<slug>/ (and studies/<slug>/{charts,viz}/).
    viz = ctx.spec.get("visualizations") or []
    if isinstance(viz, list) and len(viz) > 0:
        return
    embeds = ctx.spec.get("embed_visualizations") or []
    if isinstance(embeds, list) and len(embeds) > 0:
        return
    wp = WorkspacePaths.load(ctx.ws_root)
    on_disk = (
        any((wp.reports / "figures" / ctx.slug).glob("*.html"))
        if (wp.reports / "figures" / ctx.slug).is_dir() else False
    )
    for sub in ("charts", "viz"):
        d = wp.studies / ctx.slug / sub
        if d.is_dir() and any(d.iterdir()):
            on_disk = True
    if on_disk:
        return
    ctx.add(
        level="warning",
        field_path="visualizations",
        message=(
            "Study has no visualization on any rendered surface — no "
            "visualizations[] / embed_visualizations[] declared and no figure in "
            "reports/figures/<slug>/ or studies/<slug>/{charts,viz}/. Add ≥1 so "
            "the expert reviewer sees concrete figures — real charts for completed "
            "runs, or PLANNED-mockup viz (with synthetic data + explanatory "
            "caption) for studies still in design. The dashboard renders viz "
            "inline in the study card, so this is the most visible expert-facing "
            "surface."
        ),
        check="missing_visualizations",
    )


def _check_machine_projected_tests(ctx: _LintContext) -> None:
    """Warning when v4 tests[] look auto-projected from expected_behavior[].

    Symptom: every `tests[i].name` matches an `expected_behavior[j].name`,
    AND the `tests[i]` entries are missing the hand-authored markers (no
    `classification`, no real `pass_if`, measure looks like a stringified
    dict). The dashboard renders these as "AI slop" cards: Claim is just
    the slug echoed, Measure shows {expr: "{kind: 'observable-comparison',
    observable: 'process-bigraph-process'}"}, status UNCLASSIFIED.

    The expected pattern: 3-5 hand-authored v4 tests per study with real
    falsifiable claims, classification (primary/supporting/diagnostic/
    regression), structured measure dicts, and pass_if criteria.
    """
    if ctx.slug == "<workspace>":
        return
    tests = ctx.spec.get("tests")
    eb = ctx.spec.get("expected_behavior")
    if not isinstance(tests, list) or len(tests) == 0:
        return
    if not isinstance(eb, list) or len(eb) == 0:
        return

    eb_names = {(e or {}).get("name") for e in eb if isinstance(e, dict)}
    matched = 0
    slop_signals = 0
    for t in tests:
        if not isinstance(t, dict):
            continue
        if t.get("name") in eb_names:
            matched += 1
        # Slop signals: no classification AND measure is a single-key dict
        # like {expr: "<stringified content>"} (the auto-projection shape).
        if not t.get("classification"):
            m = t.get("measure")
            if isinstance(m, dict) and set(m.keys()) <= {"expr"}:
                slop_signals += 1

    # Trip if EITHER (a) >=80% of tests share a name with expected_behavior
    # AND >=80% show the slop signals, OR (b) every single test is slop-signaled.
    n = len(tests)
    if n == 0:
        return
    name_overlap = matched / n
    slop_fraction = slop_signals / n
    if not (slop_fraction >= 0.8 or (name_overlap >= 0.8 and slop_fraction >= 0.5)):
        return

    ctx.add(
        level="warning",
        field_path="tests",
        message=(
            f"v4 tests[] look auto-projected from expected_behavior[] "
            f"(name overlap {matched}/{n}={int(100*name_overlap)}%, "
            f"missing classification + stringified measure on "
            f"{slop_signals}/{n}={int(100*slop_fraction)}% of entries). "
            "Auto-projection produces 'AI slop' cards: Claim is just the slug, "
            "Measure is a dict-stringified-as-string, status UNCLASSIFIED. "
            "Replace with 3-5 hand-authored v4 tests per study: real falsifiable "
            "claims with quantitative thresholds, classification "
            "(primary|supporting|diagnostic|regression), structured measure "
            "dicts (source/observable/reduce/units), pass_if criteria, "
            "requires_simulation pointers, and bib cites."
        ),
        check="machine_projected_tests",
    )


def _check_readout_migration_status(ctx: _LintContext) -> None:
    """Surface each study's readout migration status (SP2b-ii).

    Calls the pure ``readout_migration_status`` (a dry-run — no write) and
    emits findings when readouts are not yet canonical:

    - ``migratable`` (resolvable, canonical form differs) → INFO suggestion to
      run ``/viva-study migrate-readouts <slug>`` (the safe auto-canonicalize).
    - ``needs_human`` (unresolvable prose/derived) → WARNING: these can't be
      parsed and must be re-authored against the composite's real observables
      (``/viva-study check-observables`` + ``GET /api/observables``). This is
      the surface for the 37 ``unresolved`` readouts SP2b-i flagged.

    Silent when both buckets are empty (every readout already canonical).
    The WRITE happens only via the skills; this check is read-only.
    """
    if ctx.slug == "<workspace>":
        return
    study_dir = WorkspacePaths.load(ctx.ws_root).studies / ctx.slug
    if not (study_dir / "study.yaml").is_file():
        return  # legacy investigations/<slug>/spec.yaml — no study.yaml to migrate
    from viva_superpowers.readout_migration import readout_migration_status
    status = readout_migration_status(study_dir)
    migratable = status.get("migratable") or []
    # The migration surface is mis-dialect readouts (prose ·-groups, derived,
    # ambiguous identifiers). A readout with NO selector field at all is a
    # plain authoring gap (descriptive-only), not a migration target — that's
    # covered by the missing-readouts nudge, so exclude it here.
    needs_human = [
        h for h in (status.get("needs_human") or [])
        if "no identifier, store_path, or index_by field found" not in (h.get("reason") or "")
    ]

    if migratable:
        names = ", ".join(r.get("name", "<unnamed>") for r in migratable)
        ctx.add(
            level="info",
            field_path="readouts",
            message=(
                f"{len(migratable)} readout(s) can be safely canonicalized "
                f"({names}). Run `/viva-study migrate-readouts {ctx.slug}` to "
                "rewrite them to the canonical index_by form (meaning-"
                "preserving, comment-safe). /viva-report also canonicalizes "
                "migratable readouts before rendering."
            ),
            check="readout_migration_status",
        )

    if needs_human:
        names = ", ".join(h.get("name", "<unnamed>") for h in needs_human)
        ctx.add(
            level="warning",
            field_path="readouts",
            message=(
                f"{len(needs_human)} readout(s) can't be parsed into a canonical "
                f"selector (needs_human: {names}). These are never auto-guessed — "
                "re-author each against the composite's real observables via "
                "`/viva-study check-observables` + `GET /api/observables` "
                "(`/viva-study migrate-readouts` drives this). Until then they "
                "stay unresolved and can't be evaluated."
            ),
            check="readout_migration_status",
        )


def _check_speculative_readout_paths(ctx: _LintContext) -> None:
    """Warning when a readout claims `path:` that doesn't resolve on disk.

    Symptom: readouts[i] has `path: out/trajectories/foo.csv` (looks
    authoritative) AND the file doesn't exist (resolves to nothing). The
    Path column in the dashboard reads as a real artifact location when
    it's just a planning hint. Reviewers can't tell what's real.

    Status: implemented + no file at path = ERROR (mislabel).
    Status: planned + speculative path with no TBD marker = WARNING.
    """
    if ctx.slug == "<workspace>":
        return
    readouts = ctx.spec.get("readouts")
    if not isinstance(readouts, list):
        return
    for i, r in enumerate(readouts):
        if not isinstance(r, dict):
            continue
        path = (r.get("path") or "").strip()
        status = (r.get("status") or "").strip().lower()
        if not path:
            continue
        # Skip readouts whose path explicitly marks itself as TBD or planned.
        low = path.lower()
        if low.startswith("tbd") or " — planned at " in path.lower() or "(planned)" in low:
            continue
        # Try to resolve against the workspace root.
        full = ctx.ws_root / path
        exists = full.exists()
        if not exists and "*" in path:
            # Glob fallback (handles e.g. out/trajectories/millard_*.csv)
            parts = path.split("/")
            for j, part in enumerate(parts):
                if "*" in part:
                    base = ctx.ws_root / "/".join(parts[:j]) if j > 0 else ctx.ws_root
                    pattern = "/".join(parts[j:])
                    try:
                        exists = any(base.glob(pattern))
                    except Exception:
                        exists = False
                    break
        if exists:
            continue

        if status == "implemented":
            ctx.add(
                level="error",
                field_path=f"readouts[{i}].path",
                message=(
                    f"Readout '{r.get('name', '<unnamed>')}' has status: implemented "
                    f"but path {path!r} does not resolve on disk. Either the artifact "
                    f"was never persisted (demote status to 'planned' + change path "
                    f"to 'TBD'), or the path is wrong (fix it). 'implemented' implies "
                    f"the data exists at the claimed location — reviewers will click."
                ),
                check="speculative_readout_path",
            )
        else:
            ctx.add(
                level="warning",
                field_path=f"readouts[{i}].path",
                message=(
                    f"Readout '{r.get('name', '<unnamed>')}' is status: {status or '<unset>'} "
                    f"with speculative path {path!r} (no file resolves). The Path "
                    f"column in the dashboard reads as authoritative — reviewers "
                    f"will click and find nothing. Prefix with 'TBD' or '(planned)' "
                    f"so the speculative nature is visible, e.g. "
                    f"'TBD — planned at {path}'."
                ),
                check="speculative_readout_path",
            )


def _check_visualization_files(ctx: _LintContext) -> None:
    """Guard against the silent "figure exists but never renders" failure.

    The dashboard auto-discovers a study's interactive figures ONLY from the
    canonical ``<ws_root>/reports/figures/<slug>/*.html``. Three ways an author
    silently ends up with an invisible figure, each caught here as a warning:

      1. A declared ``embed_visualizations[].url`` whose file does not exist
         under the workspace.
      2. A declared ``visualizations[].address: image:<path>`` whose file does
         not exist relative to the study directory.
      3. An HTML figure parked in the look-alike
         ``<ws_root>/workspace/reports/figures/<slug>/`` (a common mistake) that
         the canonical auto-discovery will never see.

    All warning-level: a figure that doesn't render is a quality gap, not a
    schema error, and the author may be mid-authoring.
    """
    if ctx.slug == "<workspace>":
        return
    wp = WorkspacePaths.load(ctx.ws_root)
    slug = ctx.slug
    canonical = wp.reports / "figures" / slug

    # 1. embed_visualizations[].url must resolve to a real file.
    embeds = ctx.spec.get("embed_visualizations") or []
    if isinstance(embeds, list):
        for i, emb in enumerate(embeds):
            if not isinstance(emb, dict):
                continue
            url = str(emb.get("url") or "").strip()
            if not url or url.startswith(("http://", "https://")):
                continue  # remote/external — not ours to verify
            target = ctx.ws_root / url.lstrip("/")
            if not target.is_file():
                ctx.add(
                    level="warning",
                    field_path=f"embed_visualizations[{i}].url",
                    message=(
                        f"Embed {emb.get('name') or url!r} points at {url!r}, which "
                        f"does not exist under the workspace — the figure will not "
                        f"render. Write it to reports/figures/{slug}/<name>.html "
                        f"(the canonical, auto-discovered location)."
                    ),
                    check="viz_file_missing",
                )

    # 2. visualizations[].address: image:<path> must resolve (relative to study dir).
    study_dir = wp.studies / slug
    viz = ctx.spec.get("visualizations") or []
    if isinstance(viz, list):
        for i, v in enumerate(viz):
            if not isinstance(v, dict):
                continue
            addr = str(v.get("address") or "").strip()
            if not addr.startswith("image:"):
                continue  # local:/dotted addresses handled elsewhere
            relp = addr[len("image:"):].strip()
            if not relp or relp.startswith(("http://", "https://", "/")):
                continue
            if not (study_dir / relp).is_file():
                ctx.add(
                    level="warning",
                    field_path=f"visualizations[{i}].address",
                    message=(
                        f"Visualization {v.get('name') or addr!r} references {addr!r}, "
                        f"but no file exists at {relp!r} relative to the study "
                        f"directory — it will not render."
                    ),
                    check="viz_file_missing",
                )

    # 3. Misplaced figures: HTML under the look-alike workspace/reports/figures/
    #    that the canonical auto-discovery will never surface.
    alt = ctx.ws_root / "workspace" / "reports" / "figures" / slug
    try:
        same = alt.resolve() == canonical.resolve()
    except OSError:
        same = False
    if alt.is_dir() and not same:
        orphans = [
            p.name for p in sorted(alt.glob("*.html"))
            if not (canonical / p.name).is_file()
        ]
        if orphans:
            ctx.add(
                level="warning",
                field_path="reports/figures",
                message=(
                    f"Figure(s) {', '.join(orphans)} live in the non-canonical "
                    f"workspace/reports/figures/{slug}/ — the dashboard does NOT "
                    f"auto-discover there, so they will not render. Move them to "
                    f"reports/figures/{slug}/."
                ),
                check="viz_misplaced",
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_HEDGE_WORDS = re.compile(
    r"\b(should|probably|likely|presumably|seems?|appears? to|"
    r"expected to|ought to|might)\b",
    re.IGNORECASE,
)


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def _check_hedged_verdict_when_passed(ctx: _LintContext) -> None:
    """A study whose authored ``gate_status`` is ``passed`` should state its
    conclusion in the indicative, not the conditional. Hedge words ("should",
    "likely", "seems", "expected to") in the conclusion of a PASSED study are the
    wording symptom obra's verification-before-completion skill flags — a pass
    resting on "should" is a claim, not a result. Warning-level; the fix is to
    state the result plainly or downgrade the verdict.
    """
    if str(ctx.spec.get("gate_status") or "").strip().lower() != "passed":
        return
    for fieldname in ("conclusion_logic", "executive"):
        block = ctx.spec.get(fieldname)
        if not block:
            continue
        for text in _iter_strings(block):
            m = _HEDGE_WORDS.search(text)
            if m:
                ctx.add(
                    level="warning",
                    field_path=fieldname,
                    message=(
                        f"passed study hedges its conclusion with {m.group(0)!r} — "
                        "state the result in the indicative or downgrade the "
                        "verdict; a pass resting on hedged language is a claim, "
                        "not evidence."
                    ),
                    check="hedged_verdict_when_passed",
                )
                break  # one finding per field is enough


def _dashboard_render_error(ws_root: Path, slug: str) -> str | None:
    """Ask the running workbench whether ``slug`` loads, via ``GET /api/study/<slug>``.

    Returns the loader's error message when the dashboard rejects the spec (its
    detail page won't render), or ``None`` when it loads, the server isn't
    running, or the check can't be performed.

    The compute lives in the workbench; the plugin reaches it over HTTP (stdlib
    ``urllib``), never by importing it — importing ``vivarium_workbench`` back
    into the plugin would reintroduce the dependency cycle and break the
    ``study_audit --gate`` step that runs ``--no-install-package
    vivarium-workbench`` (see ``tests/test_no_workbench_import.py``).

    Factored out so the check below is unit-testable by monkeypatching this one
    function.
    """
    import json as _json
    import urllib.error
    import urllib.request

    from viva_superpowers.server_preflight import read_server_url

    url = read_server_url(ws_root)
    if not url:
        return None  # server not running → render check unavailable, skip
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/study/{slug}", method="GET"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            resp.read()
        return None  # 200 → renders
    except urllib.error.HTTPError as e:
        if e.code != 500:
            return None  # 400 invalid slug / 404 not found → not a render block
        try:
            body = _json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        err = body.get("error") or ""
        # Only spec-load failures — not transient I/O — count as render-blocked.
        return err if "InvestigationSpecError" in err else None
    except Exception:  # noqa: BLE001 — server unreachable mid-lint, timeout, …
        return None


def _check_renders_via_dashboard(ctx: _LintContext) -> None:
    """Render-guarantee: confirm the study loads through the dashboard (#96).

    The other checks are static YAML analysis; a spec can pass every one of them
    yet still fail to render, because the dashboard's ``load_spec`` rejects it
    (empty baseline, wrong ``expected_behavior`` shape, …) and the study-detail
    route then returns an error instead of the page. Ask the running workbench
    (``GET /api/study/<slug>``) so "passes lint" implies "renders".

    When the server isn't running (e.g. a standalone lint run in CI) the check
    skips silently rather than failing.
    """
    if ctx.slug == "<workspace>":
        return
    err = _dashboard_render_error(ctx.ws_root, ctx.slug)
    if err:
        ctx.add(
            level="error",
            field_path="<render>",
            message=(
                f"Study does not load in the dashboard: {err} — the static lint "
                "passed, but the dashboard's loader rejects this spec, so its "
                "detail page will not render. Fix the field named in the error."
            ),
            check="render_blocked",
        )


_CHECK_FUNCTIONS = (
    _check_renders_via_dashboard,
    _check_incomplete_summaries,
    _check_status_contradictions,
    _check_missing_provenance,
    _check_unresolved_placeholders,
    _check_duplicate_modal_phrases,
    _check_truncated_takeaways,
    _check_decide_phase_missing_findings,
    _check_finding_without_evidence,
    _check_finding_without_statement,
    _check_finding_cites_unknown_bib_key,
    _check_finding_references_unknown_expert_doc,
    # Band provenance (stage 3a)
    _check_band_test_missing_cites,
    _check_band_cites_unknown_bib_key,
    _check_visualization_addresses,
    _check_visualization_files,
    _check_dag_edges_legacy_and_canonical_both_set,
    _check_status_legacy_only,
    _check_runs_yaml_vs_db_drift,
    _check_status_out_of_date_vs_runs,
    _check_status_claims_done_but_no_runs_recorded,
    _check_runs_without_emitter,
    _check_reviewer_clarity_ambiguities,
    _check_viz_stale_vs_latest_run,
    _check_narrative_spine_completeness,
    # Expert-handoff readiness (warning-level — see CHECKS comment block)
    _check_missing_baseline,
    _check_missing_variants,
    _check_missing_planned_runs,
    _check_missing_readouts,
    _check_missing_visualizations,
    _check_missing_conditions_block,
    _check_missing_simulation_set,
    # Anti-slop & honesty checks (added 2026-05-25 after pdmp-* feedback)
    _check_machine_projected_tests,
    _check_speculative_readout_paths,
    # SP2b-ii: readout migration status (migratable + needs_human)
    _check_readout_migration_status,
    # Wave 3a: workflow-typing enums (next_action_type / study_type)
    _check_workflow_typing,
    # Wave 3b: claim_scope / generality / lifecycle_state enums + floor
    _check_finding_scope_generality_lifecycle,
    # Hedged verdict: a passed study whose conclusion hedges ("should"/"likely")
    _check_hedged_verdict_when_passed,
)


def lint_workspace_report(ws_root: Path, *, strict: bool = False) -> list[LintFinding]:
    """Run every Pass B check against every study in the workspace.

    Returns a flat list of findings. Sort: error before warning before
    info; within each level, sorted by study_slug then field_path so the
    output is stable across runs.

    ``strict`` promotes opt-in warning-level checks (e.g.
    ``viz_stale_vs_latest_run``) to error level.

    Workspace-global scans (bib keys, expert-doc names, viz classes) depend
    only on ``ws_root`` — not on the individual study — so a single
    ``ws_cache`` dict is minted here and shared by every ``_LintContext``
    built in this call (studies and investigations alike). Each scan then
    runs at most once per call to this function, instead of once per
    study. See ``_cached()``. The dict is scoped to this one call — a
    fresh one every time ``lint_workspace_report()`` runs — so it can
    never serve stale data across two separate lint runs.
    """
    out: list[LintFinding] = []
    ws_cache: dict = {}
    for slug, spec in _iter_study_specs(ws_root):
        ctx = _LintContext(ws_root=ws_root, slug=slug, spec=spec, strict=strict, ws_cache=ws_cache)
        for fn in _CHECK_FUNCTIONS:
            try:
                fn(ctx)
            except Exception as e:  # noqa: BLE001
                # A buggy check shouldn't crash the whole lint run; surface it
                # as an info finding so reviewers can still see something.
                ctx.add(
                    level="info",
                    field_path="<linter>",
                    message=f"Linter check {fn.__name__} raised {e!r} on study {slug!r}.",
                    check="linter_internal_error",
                )
        out.extend(ctx.findings)

    # Investigation-level checks (the modern v2 investigation.yaml narrative
    # spine) — run on investigation specs, not studies.
    for slug, spec in _iter_investigation_specs(ws_root):
        ctx = _LintContext(ws_root=ws_root, slug=slug, spec=spec, strict=strict, ws_cache=ws_cache)
        for fn in _INVESTIGATION_CHECK_FUNCTIONS:
            try:
                fn(ctx)
            except Exception as e:  # noqa: BLE001
                ctx.add(
                    level="info",
                    field_path="<linter>",
                    message=f"Linter check {fn.__name__} raised {e!r} on investigation {slug!r}.",
                    check="linter_internal_error",
                )
        out.extend(ctx.findings)

    level_order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda f: (level_order.get(f.level, 99), f.study_slug, f.field_path))
    return out


def format_findings(findings: Iterable[LintFinding]) -> str:
    """Render findings as a human-readable plain-text report."""
    lines: list[str] = []
    by_level: dict[str, list[LintFinding]] = {}
    for f in findings:
        by_level.setdefault(f.level, []).append(f)
    for lvl in ("error", "warning", "info"):
        entries = by_level.get(lvl, [])
        if not entries:
            continue
        lines.append(f"[{lvl.upper()}] ({len(entries)})")
        for f in entries:
            lines.append(f"  {f.study_slug}: {f.field_path} — {f.message}")
            lines.append(f"    override_key: {f.override_key}")
    n_blocking = len(by_level.get("error", [])) + len(by_level.get("warning", []))
    n_info = len(by_level.get("info", []))
    if not lines:
        lines.append("OK — no lint findings.")
    elif n_blocking == 0:
        # Only info-level nudges (e.g. v4 narrative-spine completeness):
        # explicitly state publication isn't blocked so the user can tell
        # at a glance.
        lines.append(f"OK — no blocking findings ({n_info} info-level nudges shown above).")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI: python -m viva_superpowers.report_linter
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry: lint a workspace and report findings.

    Exit code:
      0 — clean (no blocking errors after overrides applied), or --force given.
      1 — blocking errors remain.
      2 — usage / IO error.
    """
    import argparse
    import sys

    p = argparse.ArgumentParser(
        prog="python -m viva_superpowers.report_linter",
        description="Pre-publication report linter for workspace studies.",
    )
    p.add_argument(
        "--ws", "--workspace",
        dest="ws",
        default=".",
        help="Path to the workspace root (default: current directory).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Log blocking errors to .pbg/report-lint-overrides.json and exit 0.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON instead of plain text.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Promote opt-in warning checks (e.g. viz_stale_vs_latest_run) to errors.",
    )
    args = p.parse_args(argv)

    ws_root = Path(args.ws).resolve()
    if not (ws_root / "workspace.yaml").is_file():
        print(f"ERROR: no workspace.yaml under {ws_root}", file=sys.stderr)
        return 2

    findings = lint_workspace_report(ws_root, strict=args.strict)
    overrides = load_overrides(ws_root)
    visible = apply_overrides(findings, overrides)

    if args.json:
        print(json.dumps([f.to_dict() for f in visible], indent=2))
    else:
        print(format_findings(visible))

    blocking = [f for f in findings if f.level == "error" and f.override_key not in overrides]
    if not blocking:
        return 0
    if args.force:
        for f in blocking:
            write_override(ws_root, f)
        print(
            f"--force: logged {len(blocking)} blocking finding(s) to "
            f"{override_path(ws_root).relative_to(ws_root)}",
            file=sys.stderr,
        )
        return 0
    print(
        f"BLOCKING: {len(blocking)} error-level finding(s) — refusing publication. "
        "Re-run with --force to log overrides and proceed.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
