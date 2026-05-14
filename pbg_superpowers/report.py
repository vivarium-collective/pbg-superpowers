"""Render reports/index.html for workspace and per-model targets."""
from __future__ import annotations
import json
import shutil
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ._resources import resource_dir


def _env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        keep_trailing_newline=True,
    )


def _copy_assets(target_assets_dir: Path) -> None:
    """Copy static assets (style.css, render-helpers.js, optional client.js)."""
    target_assets_dir.mkdir(parents=True, exist_ok=True)
    src = resource_dir("templates") / "_assets"
    for name in ("style.css", "render-helpers.js"):
        shutil.copy2(src / name, target_assets_dir / name)
    # Optional: copy client.js for live mode if it exists in the plugin
    try:
        client_js = resource_dir("server") / "client.js"
    except RuntimeError:
        return
    if client_js.exists():
        shutil.copy2(client_js, target_assets_dir / "client.js")


def render_workspace_report(ws_root: Path, *, today: str | None = None) -> Path:
    """Build <ws_root>/reports/index.html from workspace.yaml + decisions log."""
    today = today or date.today().isoformat()
    ws = yaml.safe_load((ws_root / "workspace.yaml").read_text())
    decisions_file = ws_root / "docs" / "decisions.yaml"
    decisions = (
        (yaml.safe_load(decisions_file.read_text()) or {}).get("decisions", [])
        if decisions_file.exists() else []
    )
    env = _env(resource_dir("templates") / "workspace" / "reports")
    tpl = env.get_template("index.html.j2")
    out = ws_root / "reports" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    _copy_assets(ws_root / "reports" / "assets")
    out.write_text(tpl.render(
        workspace_name=ws["name"],
        generated_at=today,
        models=ws.get("models", {}),
        decisions=decisions,
    ))
    return out


def render_model_report(
    ws_root: Path, model_name: str,
    registry: dict, pbg_doc: dict | None = None,
    *, today: str | None = None,
) -> Path:
    """Build models/<model>/reports/index.html from workspace.yaml entry + registry + doc."""
    today = today or date.today().isoformat()
    ws = yaml.safe_load((ws_root / "workspace.yaml").read_text())
    model = ws["models"][model_name]
    env = _env(resource_dir("templates") / "model" / "reports")
    tpl = env.get_template("index.html.j2")
    out = ws_root / "models" / model_name / "reports" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    _copy_assets(ws_root / "models" / model_name / "reports" / "assets")
    out.write_text(tpl.render(
        model_name=model_name,
        generated_at=today,
        registry=registry,
        pbg_doc_json=json.dumps(pbg_doc or {}, indent=2),
    ))
    return out
