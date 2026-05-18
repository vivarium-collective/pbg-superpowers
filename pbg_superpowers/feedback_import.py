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


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("source", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--workspace", type=click.Path(path_type=Path, file_okay=False),
              default=Path.cwd(),
              help="Workspace root (contains investigations/). Defaults to CWD.")
@click.option("--no-create", is_flag=True,
              help="Refuse to create investigations/<inv>/feedback/ if it doesn't exist.")
def cli(source: Path, workspace: Path, no_create: bool) -> None:
    """Import an inline-feedback yaml into investigations/<inv>/feedback/.

    SOURCE is the yaml file downloaded by the inline-feedback widget.
    """
    payload = _read_feedback_yaml(source)
    inv = payload["meta"]["investigation"]
    n_sections = len(payload["annotations"])
    n_entries = sum(len(v or []) for v in payload["annotations"].values())

    inv_dir = workspace / "investigations" / inv
    if not inv_dir.is_dir():
        raise click.ClickException(
            f"investigations/{inv}/ does not exist under {workspace}. "
            "Either run this from the correct workspace or pass --workspace."
        )
    fb_dir = inv_dir / "feedback"
    if not fb_dir.is_dir():
        if no_create:
            raise click.ClickException(
                f"{fb_dir} does not exist (and --no-create was set)."
            )
        fb_dir.mkdir(parents=True, exist_ok=False)

    slug = _timestamp_slug(payload["meta"].get("generated_at"))
    target = fb_dir / f"{slug}.yaml"
    # If a same-second collision happens, suffix with a counter so we
    # never overwrite earlier feedback.
    if target.exists():
        for i in range(1, 100):
            cand = fb_dir / f"{slug}-{i:02d}.yaml"
            if not cand.exists():
                target = cand
                break

    target.write_text(yaml.safe_dump(payload, sort_keys=False))
    click.echo(
        f"Imported {n_entries} annotation(s) across {n_sections} section(s) "
        f"for investigation {inv!r} → {target.relative_to(workspace)}"
    )


if __name__ == "__main__":
    cli()
