"""Publish-asset templater for the read-only workbench dashboard.

`vivarium-workbench add-dashboard` is referenced in scaffold comments and
docs but is NOT a real CLI subcommand — the "publish assets" it's supposed
to scaffold (``scripts/publish_dashboard.sh`` +
``.github/workflows/publish-dashboard.yml``) are plain templated files.
This module fills that gap: it renders the two assets from the canonical
pbg-biomodels reference (the first workspace to wire up the read-only
dashboard publish flow) into any workspace.

    from viva_superpowers.publish_assets import emit

    emit(workspace_dir, name="viva-fenics")
    # -> writes scripts/publish_dashboard.sh (chmod 0o755) and
    #    .github/workflows/publish-dashboard.yml, base_path defaulting to
    #    "/viva-fenics/dashboard"
"""

from __future__ import annotations

from pathlib import Path

import jinja2

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_SCRIPT_TEMPLATE = "publish_dashboard.sh.j2"
_WORKFLOW_TEMPLATE = "publish-dashboard.yml.j2"

_SCRIPT_MODE = 0o755


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def emit(
    workspace_dir: Path | str,
    name: str,
    base_path: str | None = None,
    interactive_url: str | None = None,
) -> list[Path]:
    """Render the publish-dashboard assets into ``workspace_dir``.

    Writes:
      - ``scripts/publish_dashboard.sh`` (chmod 0o755, executable)
      - ``.github/workflows/publish-dashboard.yml``

    ``base_path`` defaults to ``/<name>/dashboard`` (the workbench's static
    SPA base path once published to ``gh-pages:dashboard/``).
    ``interactive_url`` is optional (a link back to the source repo shown in
    the dashboard chrome); when omitted, the built script omits
    ``--interactive-url``.

    Creates parent directories as needed. Returns the list of written paths.
    """
    ws = Path(workspace_dir).resolve()
    resolved_base_path = base_path or f"/{name}/dashboard"
    ctx = {
        "name": name,
        "base_path": resolved_base_path,
        "interactive_url": interactive_url,
    }

    env = _env()

    script_path = ws / "scripts" / "publish_dashboard.sh"
    workflow_path = ws / ".github" / "workflows" / "publish-dashboard.yml"

    script_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)

    script_path.write_text(env.get_template(_SCRIPT_TEMPLATE).render(**ctx))
    script_path.chmod(_SCRIPT_MODE)

    workflow_path.write_text(env.get_template(_WORKFLOW_TEMPLATE).render(**ctx))

    return [script_path, workflow_path]
