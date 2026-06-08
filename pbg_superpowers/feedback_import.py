"""Import an inline-feedback yaml downloaded from an investigation report.

The downloadable investigation HTML carries a self-contained widget
(see vivarium-dashboard's static/walkthrough.js) that lets an offline
evaluator leave inline annotations on each section and save them as a
single yaml file. This CLI takes that file and drops it into the
workspace at ``investigations/<inv>/feedback/<ts>.yaml`` — the path
the dashboard scans when surfacing feedback in-context.

Usage:
    pbg-feedback-import <path/to/feedback-*.yaml>

By default it writes into the current working directory's
``investigations/`` tree. Override with ``--workspace``.

The incoming yaml's ``meta.investigation`` field decides the target
folder, so a single file can never escape its own investigation. If the
target folder doesn't exist the import refuses (no surprise directories).
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from pbg_superpowers.workspace_paths import WorkspacePaths


def _read_feedback_yaml(path: Path) -> dict:
    if not path.is_file():
        raise click.ClickException(f"feedback file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise click.ClickException(f"{path} is not valid yaml: {e}") from e
    if not isinstance(data, dict):
        raise click.ClickException(f"{path}: expected a mapping at the top level")
    meta = data.get("meta") or {}
    if not isinstance(meta, dict) or not meta.get("investigation"):
        raise click.ClickException(
            f"{path}: missing meta.investigation — was this file produced by the "
            "inline-feedback widget?"
        )
    annotations = data.get("annotations")
    if annotations is None:
        annotations = {}
    if not isinstance(annotations, dict):
        raise click.ClickException(
            f"{path}: annotations must be a mapping (section_id → list[entry])"
        )
    return {"meta": meta, "annotations": annotations}


def _feedback_files(inv_dir: Path) -> list[Path]:
    """All feedback yaml files for an investigation, oldest-first.

    Covers both layouts that exist in the wild:
      - ``feedback/<ts>.yaml``        — written by ``pbg-feedback-import``
      - ``feedback-<date>/feedback.yaml`` — a dated round folder (the dnaa
        investigation keeps its rounds this way, alongside a PLAN.md)
    """
    out: list[Path] = []
    fb_dir = inv_dir / "feedback"
    if fb_dir.is_dir():
        out.extend(sorted(fb_dir.glob("*.yaml")))
    for round_dir in sorted(inv_dir.glob("feedback-*")):
        if round_dir.is_dir():
            f = round_dir / "feedback.yaml"
            if f.is_file():
                out.append(f)
    return out


def load_investigation_feedback(workspace: Path | str, investigation: str) -> dict:
    """Aggregate every imported feedback annotation for an investigation.

    Returns ``{section_id: [annotation, ...]}`` where each annotation is
    ``{author, text, ts, report_id}`` and the lists are newest-first. Section
    ids match the widget's element ids (e.g.
    ``study-dnaa-00-parameter-foundation-embeds``), so a caller can attach a
    study's feedback by matching the ``study-<slug>`` prefix.

    v2ecoli expert-feedback round 1 (2026-05-21): feedback was imported and
    stored but never surfaced back into the report — so the reviewer's points
    lived in a yaml nobody saw. This reader is the shared core that the
    dashboard uses to render imported feedback per study (Thread B.1), closing
    the loop so the next generation visibly answers it.
    """
    inv_dir = WorkspacePaths.load(workspace).investigations / investigation
    by_section: dict[str, list[dict]] = {}
    for path in _feedback_files(inv_dir):
        try:
            data = yaml.safe_load(path.read_text())
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("meta") or {}
        report_id = meta.get("report_id") if isinstance(meta, dict) else None
        annotations = data.get("annotations") or {}
        if not isinstance(annotations, dict):
            continue
        for section_id, entries in annotations.items():
            if not isinstance(entries, list):
                continue
            bucket = by_section.setdefault(section_id, [])
            for e in entries:
                if not isinstance(e, dict):
                    continue
                bucket.append({
                    "author": e.get("author") or "",
                    "text": e.get("text") or "",
                    "ts": e.get("ts") or "",
                    "report_id": report_id,
                })
    # Newest-first within each section (ts is ISO-8601, lexically sortable).
    for entries in by_section.values():
        entries.sort(key=lambda a: a.get("ts") or "", reverse=True)
    return by_section


def feedback_for_study(feedback_by_section: dict, study_slug: str) -> list[dict]:
    """Flatten the annotations targeting one study's sections, newest-first.

    Matches section ids of the form ``study-<slug>`` (optionally with a
    ``-embeds`` / ``-charts`` / … suffix). Each returned annotation gains a
    ``section`` field naming the originating section id.
    """
    prefix = "study-" + study_slug
    out: list[dict] = []
    for section_id, entries in (feedback_by_section or {}).items():
        if section_id == prefix or section_id.startswith(prefix + "-"):
            for e in entries:
                out.append({**e, "section": section_id})
    out.sort(key=lambda a: a.get("ts") or "", reverse=True)
    return out


def _timestamp_slug(iso_ts: str | None) -> str:
    """Derive a filesystem-safe slug from the widget's generated_at timestamp.

    Falls back to "now" if the timestamp is missing or malformed.
    """
    if iso_ts:
        try:
            t = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        except ValueError:
            t = datetime.now(timezone.utc)
    else:
        t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H-%M-%SZ")


class FeedbackImportError(ValueError):
    """Raised by write_feedback_payload on a bad payload / missing inv dir."""


def _validate_payload(payload: dict) -> dict:
    """Normalize + validate a ``{meta, annotations}`` feedback payload.

    Shared by the CLI (file source) and the dashboard's direct-submit
    endpoint (JSON body). Raises FeedbackImportError on a malformed payload.
    """
    if not isinstance(payload, dict):
        raise FeedbackImportError("expected a mapping at the top level")
    meta = payload.get("meta") or {}
    if not isinstance(meta, dict) or not meta.get("investigation"):
        raise FeedbackImportError(
            "missing meta.investigation — was this produced by the "
            "inline-feedback widget?")
    annotations = payload.get("annotations")
    if annotations is None:
        annotations = {}
    if not isinstance(annotations, dict):
        raise FeedbackImportError(
            "annotations must be a mapping (section_id → list[entry])")
    out = {"meta": meta, "annotations": annotations}
    # Preserve offline-action keys so the persisted yaml is a faithful copy
    # (and so a re-import can re-apply them if needed).
    for k in ("proposed_input_decisions", "study_seed_requests"):
        v = payload.get(k)
        if isinstance(v, list) and v:
            out[k] = v
    return out


def write_feedback_payload(workspace: Path | str, payload: dict,
                           *, create: bool = True) -> Path:
    """Write a feedback payload to ``investigations/<inv>/feedback/<ts>.yaml``.

    The shared writer behind both ``pbg-feedback-import`` (file source) and
    the dashboard's direct-submit endpoint (B.2). ``payload`` is
    ``{meta:{investigation, generated_at?, ...}, annotations:{...}}``. Returns
    the written path. Never overwrites earlier feedback — same-second
    collisions get a numeric suffix.

    Raises :class:`FeedbackImportError` for a malformed payload or when the
    investigation directory doesn't exist (and, if ``create`` is False, when
    the feedback/ subdir doesn't exist).
    """
    workspace = Path(workspace)
    payload = _validate_payload(payload)
    inv = payload["meta"]["investigation"]
    inv_dir = WorkspacePaths.load(workspace).investigations / inv
    if not inv_dir.is_dir():
        raise FeedbackImportError(
            f"investigations/{inv}/ does not exist under {workspace}.")
    fb_dir = inv_dir / "feedback"
    if not fb_dir.is_dir():
        if not create:
            raise FeedbackImportError(f"{fb_dir} does not exist.")
        fb_dir.mkdir(parents=True, exist_ok=True)

    slug = _timestamp_slug(payload["meta"].get("generated_at"))
    target = fb_dir / f"{slug}.yaml"
    if target.exists():
        for i in range(1, 100):
            cand = fb_dir / f"{slug}-{i:02d}.yaml"
            if not cand.exists():
                target = cand
                break
    target.write_text(yaml.safe_dump(payload, sort_keys=False))
    return target


def apply_offline_actions(workspace: Path | str, payload: dict) -> dict:
    """Apply offline Accept/Decline + Add-to-investigation actions on import.

    The inline-feedback widget, when a downloaded report is opened over
    ``file://`` (no dashboard server to POST to), records the reviewer's
    button clicks into the feedback yaml under two top-level keys:

      * ``proposed_input_decisions: [{item_id, decision, ts}]`` — the
        Accept/Decline clicks on ``proposed_inputs.items``.
      * ``study_seed_requests: [{proposal_id|title, parent, targets, ts}]`` —
        the "+ Add to investigation" clicks on follow-up study proposals.

    This applies them using the SAME logic the live dashboard endpoints use,
    so the offline path converges with the online one:

      * decisions → ``vivarium_dashboard.server._decide_proposed_input_for_test``
        (promotes a ``kind:reference`` into ``inputs.references`` on accept,
        marks declined otherwise);
      * seed requests → ``vivarium_dashboard.lib.study_seed.seed_followup_study``
        (spawns the child study node).

    Returns a report dict ``{decisions:[...], seeds:[...], errors:[...]}``.
    Requires ``vivarium_dashboard`` to be importable; if it is not, the
    actions are surfaced (not silently dropped) via ``errors``.
    """
    workspace = Path(workspace)
    inv = (payload.get("meta") or {}).get("investigation")
    decisions_in = payload.get("proposed_input_decisions") or []
    seeds_in = payload.get("study_seed_requests") or []
    report: dict = {"decisions": [], "seeds": [], "errors": []}
    if not decisions_in and not seeds_in:
        return report

    try:
        from vivarium_dashboard.server import _decide_proposed_input_for_test
        from vivarium_dashboard.lib.study_seed import seed_followup_study
    except Exception as e:  # pragma: no cover - import-environment dependent
        msg = (f"vivarium_dashboard not importable ({e}); "
               f"{len(decisions_in)} decision(s) + {len(seeds_in)} seed "
               "request(s) parsed but NOT applied — apply them manually.")
        report["errors"].append(msg)
        report["decisions"] = list(decisions_in)
        report["seeds"] = list(seeds_in)
        return report

    for d in decisions_in:
        if not isinstance(d, dict):
            continue
        item_id = str(d.get("item_id") or "")
        decision = d.get("decision")
        try:
            resp, code = _decide_proposed_input_for_test(
                workspace, inv, item_id, decision)
            if code == 200:
                report["decisions"].append(
                    {"item_id": item_id, "decision": decision, **{
                        k: resp[k] for k in ("status", "kind", "added_reference")
                        if k in resp}})
            else:
                report["errors"].append(
                    f"decision {item_id!r}={decision!r}: {resp.get('error', code)}")
        except Exception as e:
            report["errors"].append(f"decision {item_id!r}={decision!r}: {e}")

    for s in seeds_in:
        if not isinstance(s, dict):
            continue
        parent = s.get("parent")
        proposal_id = s.get("proposal_id") or None
        title = s.get("title") or proposal_id or "(untitled)"
        if not parent:
            report["errors"].append(
                f"seed request {title!r}: missing 'parent' study — cannot seed.")
            continue
        try:
            new_name = seed_followup_study(
                workspace, parent, proposal_id=proposal_id)
            report["seeds"].append(
                {"title": title, "parent": parent, "new_study_name": new_name})
        except Exception as e:
            report["errors"].append(f"seed request {title!r} (parent {parent!r}): {e}")

    return report


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("source", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--workspace", type=click.Path(path_type=Path, file_okay=False),
              default=Path.cwd(),
              help="Workspace root (contains investigations/). Defaults to CWD.")
@click.option("--no-create", is_flag=True,
              help="Refuse to create investigations/<inv>/feedback/ if it doesn't exist.")
@click.option("--no-apply", is_flag=True,
              help="Store the feedback yaml but do NOT apply offline "
                   "proposed_input_decisions / study_seed_requests.")
def cli(source: Path, workspace: Path, no_create: bool, no_apply: bool) -> None:
    """Import an inline-feedback yaml into investigations/<inv>/feedback/.

    SOURCE is the yaml file downloaded by the inline-feedback widget. Inline
    annotations are stored; offline Accept/Decline and Add-to-investigation
    actions (recorded when the report was opened over file://) are applied
    unless ``--no-apply`` is given.
    """
    payload = _read_feedback_yaml(source)
    # _read_feedback_yaml only returns {meta, annotations}; re-read the raw
    # doc so the offline-action keys survive to apply_offline_actions.
    raw = yaml.safe_load(source.read_text()) or {}
    payload["proposed_input_decisions"] = raw.get("proposed_input_decisions") or []
    payload["study_seed_requests"] = raw.get("study_seed_requests") or []
    inv = payload["meta"]["investigation"]
    n_sections = len(payload["annotations"])
    n_entries = sum(len(v or []) for v in payload["annotations"].values())
    try:
        target = write_feedback_payload(workspace, payload, create=not no_create)
    except FeedbackImportError as e:
        raise click.ClickException(str(e)) from e
    click.echo(
        f"Imported {n_entries} annotation(s) across {n_sections} section(s) "
        f"for investigation {inv!r} → {target.relative_to(workspace)}"
    )

    if no_apply:
        n_d = len(payload["proposed_input_decisions"])
        n_s = len(payload["study_seed_requests"])
        if n_d or n_s:
            click.echo(f"Skipped applying {n_d} decision(s) + {n_s} seed "
                       "request(s) (--no-apply).")
        return

    report = apply_offline_actions(workspace, payload)
    for d in report["decisions"]:
        extra = (f" → added reference {d['added_reference']!r}"
                 if d.get("added_reference") else "")
        click.echo(f"  {d['decision']}ed proposed input {d['item_id']!r}{extra}")
    for s in report["seeds"]:
        click.echo(f"  seeded study {s['new_study_name']!r} from {s['title']!r} "
                   f"(parent {s['parent']!r})")
    for err in report["errors"]:
        click.echo(f"  ! {err}", err=True)


if __name__ == "__main__":
    cli()
