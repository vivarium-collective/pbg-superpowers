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
        # Allow target to be a pre-existing empty dir (scaffold_workspace already
        # rejected non-empty); dirs_exist_ok=True lets copytree overlay into it.
        shutil.copytree(src, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    else:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", source, str(target)],
                check=True,
            )
        except subprocess.CalledProcessError:
            # Don't leave a partial clone on disk; subsequent runs would
            # otherwise fail the "exists and is non-empty" guard.
            shutil.rmtree(target, ignore_errors=True)
            raise click.ClickException(f"git clone failed for source: {source}")
        # remove the cloned .git so the new workspace gets a fresh history
        shutil.rmtree(target / ".git", ignore_errors=True)


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


if __name__ == "__main__":
    cli()
