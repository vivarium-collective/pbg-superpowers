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
  to the override file (used by ``/pbg-report --force``).
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
    """Per-study context handed to each check function."""

    ws_root: Path
    slug: str
    spec: dict
    findings: list[LintFinding] = field(default_factory=list)

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


_OVERRIDE_FILE_REL = Path(".pbg") / "report-lint-overrides.json"


def override_path(ws_root: Path) -> Path:
    """Where the override JSON lives, relative to the workspace root."""
    return ws_root / _OVERRIDE_FILE_REL


def load_overrides(ws_root: Path) -> set[str]:
    """Return the set of override keys currently logged for this workspace.

    Missing file is treated as an empty set (no overrides).
    """
    path = override_path(ws_root)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    overrides = data.get("overrides") or []
    return {entry["key"] for entry in overrides if isinstance(entry, dict) and "key" in entry}


def write_override(
    ws_root: Path,
    finding: LintFinding,
    *,
    reason: str = "force-published via /pbg-report --force",
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
            data = json.loads(path.read_text())
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
# Discovery: walk a workspace and yield (slug, spec) pairs
# ---------------------------------------------------------------------------


def _iter_study_specs(ws_root: Path) -> Iterator[tuple[str, dict]]:
    """Yield (slug, parsed-yaml) for every study under the workspace.

    Looks under ``<ws_root>/studies/<slug>/study.yaml`` first, then falls
    back to the legacy ``<ws_root>/investigations/<slug>/spec.yaml``.
    Silently skips unparseable YAML (the report renderer reports those
    separately; the linter focuses on content checks).
    """
    studies_dir = ws_root / "studies"
    if studies_dir.is_dir():
        for child in sorted(studies_dir.iterdir()):
            if not child.is_dir():
                continue
            spec_path = child / "study.yaml"
            if not spec_path.is_file():
                continue
            try:
                data = yaml.safe_load(spec_path.read_text()) or {}
            except yaml.YAMLError:
                continue
            slug = data.get("name") or child.name
            yield slug, data
    invs_dir = ws_root / "investigations"
    if invs_dir.is_dir():
        for child in sorted(invs_dir.iterdir()):
            if not child.is_dir():
                continue
            spec_path = child / "spec.yaml"
            if not spec_path.is_file():
                continue
            try:
                data = yaml.safe_load(spec_path.read_text()) or {}
            except yaml.YAMLError:
                continue
            slug = data.get("name") or child.name
            yield slug, data


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


CHECKS = (
    "incomplete_summaries",
    "status_contradictions",
    "missing_provenance",
    "unresolved_placeholders",
    "duplicate_modal_phrases",
    "truncated_takeaways",
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
# Public API
# ---------------------------------------------------------------------------


_CHECK_FUNCTIONS = (
    _check_incomplete_summaries,
    _check_status_contradictions,
    _check_missing_provenance,
    _check_unresolved_placeholders,
    _check_duplicate_modal_phrases,
    _check_truncated_takeaways,
)


def lint_workspace_report(ws_root: Path) -> list[LintFinding]:
    """Run every Pass B check against every study in the workspace.

    Returns a flat list of findings. Sort: error before warning before
    info; within each level, sorted by study_slug then field_path so the
    output is stable across runs.
    """
    out: list[LintFinding] = []
    for slug, spec in _iter_study_specs(ws_root):
        ctx = _LintContext(ws_root=ws_root, slug=slug, spec=spec)
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
    if not lines:
        lines.append("OK — no lint findings.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI: python -m pbg_superpowers.report_linter
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
        prog="python -m pbg_superpowers.report_linter",
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
    args = p.parse_args(argv)

    ws_root = Path(args.ws).resolve()
    if not (ws_root / "workspace.yaml").is_file():
        print(f"ERROR: no workspace.yaml under {ws_root}", file=sys.stderr)
        return 2

    findings = lint_workspace_report(ws_root)
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
