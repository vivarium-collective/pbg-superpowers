"""Scaffold a workspace by cloning/copying pbg-template and rendering it.

Two modes:
- Local source (path) — copies the directory tree
- Remote source (git URL) — git clone --depth 1

After source acquisition, runs template-init.sh non-interactively with the
workspace name piped on stdin.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

import click


DEFAULT_REMOTE = "https://github.com/eagmon/pbg-template.git"


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
        # cp -R into target (target should not yet exist or must be empty)
        shutil.copytree(src, target, dirs_exist_ok=False, ignore=shutil.ignore_patterns(".git"))
    else:
        subprocess.run(
            ["git", "clone", "--depth", "1", source, str(target)],
            check=True,
        )
        # remove the cloned .git so the new workspace gets a fresh history
        shutil.rmtree(target / ".git", ignore_errors=True)


def _render(target: Path, workspace_name: str) -> None:
    init_script = target / "template-init.sh"
    if not init_script.exists():
        raise click.ClickException(f"template-init.sh missing in source: {init_script}")
    subprocess.run(
        ["bash", str(init_script)],
        input=f"{workspace_name}\n",
        text=True, cwd=target, check=True,
    )


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


if __name__ == "__main__":
    cli()
