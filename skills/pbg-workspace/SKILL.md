---
name: pbg-workspace
description: Scaffold a process-bigraph research workspace by cloning the pbg-template repo and initialising it. Runs the workspace_bootstrap stage end-to-end with a clean PR-flow contract.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <workspace-name> [target-dir]
---

# pbg-workspace

Stage 0 of the canonical PR flow. Operates on a brand-new workspace directory.

## Prerequisites
- Target directory must not exist or must be empty.
- `git` and (optionally) `uv` available on PATH.

## Lifecycle (per spec §7)
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

   Note: subsequent `/pbg-*` skills invoke the plugin via `python -m pbg_superpowers.scaffold`
   (or other module paths) from the Claude Code host environment, NOT from inside the
   workspace `.venv`. The workspace `.venv` only needs to install the workspace's own
   `pyproject.toml` deps for `pytest` and model imports.
5. **Verify** — `python scripts/lint-workspace.py` must print `workspace lint: OK`.
6. **PR_BODY.md** — write at workspace root with the bootstrap checklist.
7. **Update workspace.yaml** — already marked complete by `template-init.sh`; nothing to do.
8. **Report refresh** — `/pbg-report` (deferred until Tasks 20-21 land).
9. **gh handoff** — print exact `gh pr create` command and offer to run (only with explicit user approval).

## Source-of-template options

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
