---
name: viva-workspace
description: "Scaffold a process-bigraph research workspace. Three modes: (1) upstream-branch — clone a repo and create a workspace branch on top; (2) standalone — clone pbg-template directly; (3) in-place — promote an existing git checkout into a workspace branch without cloning."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <workspace-name> [target-dir] [--upstream <repo>] [--branch <name>] [--in-place]
---

# pbg-workspace

Bootstrap stage. Operates on a brand-new workspace directory.

## Which mode? (decision tree)

Pick one based on the operator's starting state — this collapses the friction
new users hit when "workspace" was ambiguous between three different on-disk
shapes.

| Starting state | Mode | Command |
|---|---|---|
| **No directory yet, no upstream model repo** | standalone | `pbg-workspace <name>` |
| **No directory yet, want to branch off existing repo** | upstream-branch | `pbg-workspace <name> --upstream owner/repo` |
| **Already inside a git checkout you want to promote** | in-place | `pbg-workspace <name> --target . --in-place` |

The in-place mode is the right answer for composite-only repos (`pbg-mem3dg`,
`pbg-membrane-actin-composite`, etc.) that already have their own README,
pyproject, and package — and you want to add workspace artifacts (workspace.yaml,
investigations/, notes/, dashboard scripts) on top of them as a new branch.

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
   - `vwb scaffold-workspace --name "$NAME" --target "$TARGET"`
     (clones / copies the workspace template; runs `template-init.sh` non-interactively).
   - `cd $TARGET && git init -q`
   - `uv venv .venv && source .venv/bin/activate`
   - `uv pip install -e .[dev]` (workspace's own pyproject)
   - `git add -A && git commit -m 'feat(stage-0): workspace bootstrap'`
   - `vwb catalog-add --path "$TARGET" --name "$NAME" --package "$PKG"`
     (registers the workspace in `~/.pbg/workspaces.json` so it appears in the
     dashboard's workspace switcher; idempotent — safe to re-run).

   Note: `vwb` is the vivarium-workbench CLI (installed alongside the dashboard).
   These bootstrap verbs run before any server exists, so they are CLI calls, not
   dashboard `/api/*` requests. The workspace `.venv` only needs the workspace's own
   `pyproject.toml` deps for `pytest` and model imports.
5. **Verify** — `python scripts/lint-workspace.py` must print `workspace lint: OK`.
6. **Report refresh** — `/viva-report` to generate the initial `reports/index.html`.
7. **Next steps** — print a brief summary: workspace is ready; open the dashboard with `bash scripts/serve.sh`. From the dashboard, use the **Registry** tab to install pbg-* modules, **Simulation Setup** to configure observables, and **Build Model** to start a workstream branch.

## Source-of-template options (standalone mode)

- Default: clones `https://github.com/vivarium-collective/pbg-template.git`.
- Override via `--template-source <path-or-url>` or `$PBG_TEMPLATE` env var.
- During development, point at `~/code/pbg-template/` to use the local copy.

### In-place mode (use when scaffolding an existing checkout)

When invoked with `--in-place` inside an EXISTING git checkout (e.g. you cloned
v2ecoli yourself and want to scaffold workspace files on top), the skill:

1. **Pre-flight:**
   - Refuse if `workspace.yaml` already exists in cwd (already a workspace).
   - Refuse if cwd is not inside a git repo (`git rev-parse --is-inside-work-tree`).
2. **Branch:**
   - If `--branch <name>` given, `git checkout -b <branch>`.
   - Otherwise, stay on current branch and warn if it's `main` (suggest a branch
     name like `<repo-name>-workspace`).
3. **Apply scaffolding files** (the same set as standalone-mode bootstrap):
   `workspace.yaml`, `NEXT_STEPS.md`, `scripts/`, `references/`, `experiments/`,
   `pbg_<package_path>/`, `.pbg/schemas/`.
   SKIP files that already exist on the branch (don't overwrite, but DO add any
   missing ones). Generic scaffolding committed by PR #50 style changes may already
   be present; do not overwrite them.
4. **Generate `workspace.yaml`** using the cwd's repo name as the default
   workspace name and `package_path = pbg_<repo_name_normalized>`.
5. Commit: `git add -A && git commit -m "feat(workspace): scaffold {NAME} on top of existing checkout"`.
6. Register in the workspace catalog (`~/.pbg/workspaces.json`):
   `vwb catalog-add --path . --name <name> --package <pkg>`.

**Note:** `vwb scaffold-workspace --in-place` promotes an existing git checkout
into a workspace branch (`--branch <name>` for the branch, `--package <pkg>` for
the package path). The manual steps above remain the documented flow; the verb
is the automated equivalent.

## Safety (mirror spec §12)
- Only modify files inside the new workspace directory.
- Never push, never force-push, never push to main.
- Never `rm -rf` outside the new workspace.
- Use a workspace-local `.venv/`; never `sudo` or global pip.

## Resume
This stage has no prereqs. If a partial scaffold exists, ask: delete-and-retry, abort, or use a different target. Confirm before any deletion.

## See also

- [`docs/concepts/vivarium-workbench-model.md`](../../docs/concepts/vivarium-workbench-model.md) —
  the dashboard's data model and `/api/*` endpoints. Read this to understand what
  `workspace.yaml`, study files, and expert-doc entries must contain before the
  dashboard can render them correctly.
