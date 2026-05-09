---
name: pbg-add-model
description: Register a new model in the workspace. Creates a child GitHub repo (or local-only), adds it as a submodule under models/<name>/, scaffolds the model package, registers in workspace.yaml. Coordinates branches in two repos (workspace + new model).
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep
argument-hint: <model-name> [--remote <git-url>] [--local-only]
---

# pbg-add-model

Stage 1+2 of the canonical PR flow. Coordinated cross-repo operation.

## Prerequisites

- Workspace exists (`workspace.yaml` present and lint-clean).
- Model name not already registered under `workspace.yaml.models`.
- Working tree clean (no uncommitted changes in the workspace repo).
- `git` available; `gh` only required if `--remote` creates a new GitHub repo.

## Lifecycle (per spec §7)

1. **Pre-flight** — read workspace.yaml; refuse if model name conflicts with an existing entry; refuse if working tree dirty (offer commit/stash/abort).
2. **Branch (workspace)** — create `stage/1-add-model` off the workspace `main`.
3. **Create model repo:**
   - If `--remote <url>` is provided: `gh repo create <repo> --private` (or use the URL as-is if it's a pre-created remote). Clone into a temp dir.
   - If `--local-only`: init a fresh repo at `~/code/<model-slug>/`.
4. **Scaffold model:** `python -m pbg_superpowers.scaffold model --model-name <name> --model-slug <slug> --target <model-repo-path>`. Initial commit on model `main` with message `feat(M3-stage-2): model package scaffold`.
5. **Add submodule (workspace):** `git -c protocol.file.allow=always submodule add <remote-or-path> models/<name>`.
6. **Update workspace.yaml** — add an entry under `models.<name>` with `submodule_path`, `remote`, empty `pbg_processes`, `stages.add_model.status: complete`. Validate via `python scripts/lint-workspace.py`.
7. **Branch (model)** — open `stage/2-model-init` off model `main`. (For coordinated PRs: this branch IS the initial scaffold PR if the model repo was just created.)
8. **PR_BODY.md** in both repos — workspace gets the submodule-pointer PR body; model gets the initial-scaffold PR body. Each links the other.
9. **`docs/decisions.yaml`** — append a decision entry (timestamp, skill, target, summary).
10. **Report refresh** — call `/pbg-report` (deferred until Task 21 lands, then this becomes active).
11. **gh handoff** — print `gh pr create` for both repos; offer to run with explicit consent. Never push to `main`. Never force-push.

## Resume / restart

Detect partial state by checking:
- `models/<name>/.git` (or `models/<name>/` as a submodule pointer in `.gitmodules`)
- `workspace.yaml.models.<name>` (any entry)
- Workspace branch `stage/1-add-model` exists

If any are present, ask: resume (continue from where we are) / restart (delete branch, deinit submodule, retry). Restart requires explicit confirmation; logs the discarded SHAs first.

## Safety

Mirror spec §12. Submodule-specific rules:

- Never `git submodule deinit -f` without explicit confirmation.
- If model repo creation fails partway, roll back the submodule pointer commit cleanly (`git reset --soft` to before the partial commit, NOT `--hard`).
- Never delete a model repo's git history.

## Idempotency

Re-running with the same model name on a complete entry is rejected with a clear error message. Re-running on a `stages.add_model.status: in_progress` entry is treated as a resume.
