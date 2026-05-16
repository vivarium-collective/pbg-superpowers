---
name: pbg-workspace
description: Scaffold a process-bigraph research workspace. In the recommended upstream-branch mode, clones an upstream repo (e.g. vivarium-collective/v2ecoli) and creates a fresh branch off its main with workspace scaffolding committed on top. Falls back to standalone mode (pbg-template clone) when --upstream is omitted.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <workspace-name> [target-dir] [--upstream <repo>] [--branch <name>]
---

# pbg-workspace

Bootstrap stage. Operates on a brand-new workspace directory.

## Prerequisites
- Target directory must not exist or must be empty.
- `git` and (optionally) `uv` available on PATH.
- When `--upstream` is provided: `gh` CLI present and authenticated (`gh auth status`).

## Lifecycle — Step-by-step

### Upstream-branch mode (recommended when --upstream is provided)

1. **Pre-flight**: validate upstream-repo format (`owner/name`), confirm `gh` CLI present, confirm `gh auth ok`.
2. **Clone the upstream** into the target dir: `gh repo clone <upstream> <target>`.
3. **Create + checkout a fresh branch** off main: `git -C <target> checkout -b <branch> origin/main`.
   - Default branch name: kebab-case of the workspace name (e.g. `my-workspace`).
   - Override with `--branch <name>`.
4. **Apply workspace scaffolding files** (the same set as standalone-mode bootstrap) on top of the branch.
5. Commit: `git add -A && git commit -m "feat(workspace): scaffold ${NAME} workspace from pbg-template"`.
6. The workspace is now a branch of the upstream repo ready to develop on. Push via the dashboard's
   `/api/work-link-branch` or `git push -u origin <branch>`.
7. Register in workspace catalog same as standalone mode (see step 4 of standalone mode below).

### Standalone mode (when --upstream is omitted)

1. **Pre-flight** — refuse if target dir exists and is non-empty.
2. **Branch (n/a)** — there is no parent branch yet; the bootstrap will create the workspace's `main`.
3. **Walkthrough** — confirm the workspace name, the parent directory, and (optionally) override the template source.
4. **Edits + commits**:
   - `python -m pbg_superpowers.scaffold workspace --name $NAME --target $TARGET`
     (clones / copies pbg-template; runs `template-init.sh` non-interactively).
   - `cd $TARGET && git init -q`
   - `uv venv .venv && source .venv/bin/activate`
   - `uv pip install -e .[dev]` (workspace's own pyproject)
   - `git add -A && git commit -m 'feat(stage-0): workspace bootstrap'`
   - `python -m pbg_superpowers.workspace_catalog add --path "$TARGET" --name "$NAME" --package "$PKG"`
     (registers the workspace in `~/.pbg/workspaces.json` so it appears in the
     dashboard's workspace switcher; idempotent — safe to re-run).

   Note: subsequent `/pbg-*` skills invoke the plugin via `python -m pbg_superpowers.scaffold`
   (or other module paths) from the Claude Code host environment, NOT from inside the
   workspace `.venv`. The workspace `.venv` only needs to install the workspace's own
   `pyproject.toml` deps for `pytest` and model imports.
5. **Verify** — `python scripts/lint-workspace.py` must print `workspace lint: OK`.
6. **Report refresh** — `/pbg-report` to generate the initial `reports/index.html`.
7. **Next steps** — print a brief summary: workspace is ready; open the dashboard with `bash scripts/serve.sh`. From the dashboard, use the **Registry** tab to install pbg-* modules, **Simulation Setup** to configure observables, and **Build Model** to start a workstream branch.

## Source-of-template options (standalone mode)

- Default: clones `https://github.com/vivarium-collective/pbg-template.git`.
- Override via `--template-source <path-or-url>` or `$PBG_TEMPLATE` env var.
- During development, point at `~/code/pbg-template/` to use the local copy.

## Safety (mirror spec §12)
- Only modify files inside the new workspace directory.
- Never push, never force-push, never push to main.
- Never `rm -rf` outside the new workspace.
- Use a workspace-local `.venv/`; never `sudo` or global pip.

## Resume
This stage has no prereqs. If a partial scaffold exists, ask: delete-and-retry, abort, or use a different target. Confirm before any deletion.
