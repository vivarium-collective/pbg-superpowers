"""Scaffold a workspace by cloning/copying pbg-template and rendering it.

Two modes:
- Local source (path) — copies the directory tree
- Remote source (git URL) — git clone --depth 1

After source acquisition, runs template-init.sh non-interactively with the
workspace name piped on stdin.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from pathlib import Path

import click


# Requires pbg-template at the payload-boundary restructure (commit on or
# after 2026-05-12) or later — earlier versions lack the template/ subdir
# and will fail with "missing template/ payload subdir".
DEFAULT_REMOTE = "https://github.com/vivarium-collective/pbg-template.git"


def _looks_like_path(s: str) -> bool:
    """Heuristic: source is a local path if it starts with /, ~, ., or is an existing dir."""
    if s.startswith(("/", "~", ".")):
        return True
    p = Path(s)
    return p.exists() and p.is_dir()


def _resolve_source(source: str | None) -> str:
    if source:
        return source
    env = os.environ.get("PBG_TEMPLATE")
    if env:
        return env
    return DEFAULT_REMOTE


def _acquire(source: str, target: Path) -> None:
    if _looks_like_path(source):
        src = Path(os.path.expanduser(source)).resolve()
        if not src.is_dir():
            raise click.ClickException(f"local template source not a directory: {src}")
        payload = src / "template"
        if not payload.is_dir():
            raise click.ClickException(
                f"local template source missing template/ payload subdir: {src}. "
                "Update pbg-template to v0.5+ which separates payload from dev infra."
            )
        shutil.copytree(payload, target, dirs_exist_ok=True)
    else:
        # Git URL — clone the whole repo to a tmp dir, then copy just template/.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "checkout"
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", source, str(tmp_path)],
                    check=True,
                )
            except subprocess.CalledProcessError:
                raise click.ClickException(f"git clone failed for source: {source}")
            payload = tmp_path / "template"
            if not payload.is_dir():
                raise click.ClickException(
                    f"remote template {source} missing template/ payload subdir."
                )
            shutil.copytree(payload, target, dirs_exist_ok=True)


def _render(target: Path, workspace_name: str) -> None:
    init_script = target / "template-init.sh"
    if not init_script.exists():
        raise click.ClickException(f"template-init.sh missing in source: {init_script}")
    try:
        subprocess.run(
            ["bash", str(init_script)],
            input=f"{workspace_name}\n",
            text=True, cwd=target, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise click.ClickException(
            f"template-init.sh exited {e.returncode} (workspace name: {workspace_name})"
        ) from e


def scaffold_workspace(target: Path, workspace_name: str, source: str | None = None) -> Path:
    """Public entry point. Returns the target path on success."""
    if target.exists() and any(target.iterdir()):
        raise click.ClickException(f"{target} exists and is non-empty")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = _resolve_source(source)
    _acquire(src, target)
    _render(target, workspace_name)
    return target


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--name", required=True, help="Workspace name")
@click.option("--target", required=True, type=click.Path(path_type=Path), help="Target directory (must not exist or be empty)")
@click.option("--template-source", default=None, help="Path or git URL of pbg-template (default: $PBG_TEMPLATE or upstream)")
def workspace(name: str, target: Path, template_source: str | None) -> None:
    out = scaffold_workspace(target, name, template_source)
    click.echo(f"workspace scaffolded at {out}")


_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _render_text(text: str, substitutions: dict) -> str:
    """Replace `{{ key }}` (with or without internal whitespace) using substitutions dict."""
    return _PLACEHOLDER.sub(lambda m: str(substitutions.get(m.group(1), m.group(0))), text)


def _render_template_tree(src: Path, dst: Path, substitutions: dict) -> None:
    """Copy src → dst rendering .j2 files. .keep files stay as empty markers."""
    if dst.exists():
        if not dst.is_dir():
            raise click.ClickException(f"{dst} exists and is not a directory")
        if any(dst.iterdir()):
            raise click.ClickException(f"{dst} exists and is non-empty")
    dst.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = src_file.relative_to(src)
        out_rel = Path(str(rel).removesuffix(".j2"))
        out_path = dst / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if src_file.suffix == ".j2":
            out_path.write_text(_render_text(src_file.read_text(), substitutions))
        else:
            shutil.copy2(src_file, out_path)


def _rename_placeholder_pkg(target: Path, slug: str) -> None:
    """Rename the literal `pbg_<model>` dir to `pbg_<slug>`."""
    placeholder = target / "pbg_<model>"
    if placeholder.exists():
        placeholder.rename(target / f"pbg_{slug}")


@cli.command()
@click.option("--model-name", required=True, help="Human-readable model name (e.g. ecoli-replication)")
@click.option("--model-slug", required=True, help="Python-importable slug (e.g. ecoli_replication)")
@click.option("--target", required=True, type=click.Path(path_type=Path),
              help="Target directory (must not exist or be empty)")
def model(model_name: str, model_slug: str, target: Path) -> None:
    from ._resources import resource_dir
    src = resource_dir("templates") / "model"
    if not src.is_dir():
        raise click.ClickException(f"model template missing at {src}")
    _render_template_tree(src, target, {
        "model_name": model_name,
        "model_slug": model_slug,
    })
    _rename_placeholder_pkg(target, model_slug)
    click.echo(f"model scaffolded at {target}")


@cli.command("import-model")
@click.option("--workspace", required=True, type=click.Path(path_type=Path),
              help="Workspace root (must contain workspace.yaml).")
@click.option("--name", required=True, help="Catalog name for this import.")
@click.option("--source", required=True, help="Git URL or local path of the external repo.")
@click.option("--ref", default="main", help="Git ref (tag, branch, commit) to pin (default: main).")
@click.option("--mode", required=True,
              type=click.Choice(["reference", "fork-source", "in-place"]),
              help="reference (read-only), fork-source (catalog only), or in-place (submodule under models/).")
@click.option("--description", default=None, help="Optional human-readable description.")
def import_model(workspace: Path, name: str, source: str, ref: str,
                 mode: str, description: str | None) -> None:
    """Register an external model in the workspace's imports catalog.

    For mode='reference': also adds <source> as a submodule under external/<name>/
    (or copies it if <source> is a local path).

    For mode='fork-source': only registers the catalog entry; no checkout happens
    until /pbg-add-model --from-import <name> consumes it.

    For mode='in-place': adds <source> as a submodule under models/<name>/ and
    marks the model entry external=true. Use this when you want to operate
    on an existing model repo without forking.
    """
    from .imports import register_import
    from .workspace_yaml import load_workspace, save_workspace

    ws = workspace.resolve()
    if not (ws / "workspace.yaml").exists():
        raise click.ClickException(f"workspace.yaml missing at {ws}")

    # Compute the path on disk (mode-dependent)
    if mode == "reference":
        path = f"external/{name}"
    elif mode == "in-place":
        path = f"models/{name}"
    else:
        path = None

    # 1. Register in catalog (validates schema)
    register_import(
        ws, name=name, source=source, ref=ref, mode=mode,
        path=path, description=description,
    )

    # 2. For reference + in-place modes: actually add the submodule
    if mode in ("reference", "in-place"):
        target_dir = ws / path
        if target_dir.exists():
            click.echo(f"target {path} already exists; skipping submodule add", err=True)
        else:
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "-C", str(ws),
                 "-c", "protocol.file.allow=always",
                 "submodule", "add", source, path],
                check=True,
            )
            # Pin to ref
            subprocess.run(
                ["git", "-C", str(target_dir), "checkout", ref],
                check=True,
            )

    # 3. For in-place mode: also mark the model as external in workspace.yaml.models
    if mode == "in-place":
        ws_data = load_workspace(ws / "workspace.yaml")
        models = ws_data.setdefault("models", {})
        models[name] = {
            "submodule_path": path,
            "remote": source,
            "pbg_processes": [],
            "stages": {"add_model": {"status": "complete", "pr": None, "completed": "2026-05-09"}},
            "external": True,
        }
        save_workspace(ws / "workspace.yaml", ws_data)

    click.echo(f"import '{name}' registered (mode={mode})")


if __name__ == "__main__":
    cli()
