---
name: pbg-import-models
description: "Register external models in the workspace's imports catalog. Three modes: reference (read-only submodule under external/), fork-source (catalog-only, seeds /pbg-add-model --from-import), in-place (submodule under models/ with external: true marker, used when operating against an existing model repo). Workspace stage 0.5 — runs once before /pbg-add-model."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <import-name> --source <url> --ref <ref> --mode <reference|fork-source|in-place> [--description <text>]
---

# pbg-import-models

Workspace stage 0.5 of the canonical PR flow. Operates in the workspace repo. Runs **before** `/pbg-add-model` to declare which existing models the workspace will reference, fork from, or operate-in-place against.

## Prerequisites

- `stages.workspace_bootstrap.status` is `complete`.
- Working tree clean in the workspace repo.

## Modes

**`reference`** — read-only reference to an existing model. Adds `<source>` as a submodule under `external/<name>/`. The workspace never modifies it; stage skills can READ it for citation, comparison, or cherry-pick (`/pbg-add-model --from-import <name>` later copies selected files).

**`fork-source`** — catalog-only registration; no checkout happens. Use this when you plan to call `/pbg-add-model <new-model> --from-import <name>` later and want the catalog to record provenance, but don't need the source on disk yet.

**`in-place`** — submodule under `models/<name>/` AND a `models.<name>` entry with `external: true`. Use this when you want to operate on an existing model repo without forking — subsequent `/pbg-pull-processes`, `/pbg-baseline`, and `/pbg-phase` invocations will work against this submodule and target its upstream remote for PRs. Coordination state (phases plan, deliverables) lives at `models-overlay/<name>/` (workspace-owned), keeping the external repo clean.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if workspace_bootstrap not complete or working tree dirty.
2. **Branch** — `stage/0.5-import-models` in the workspace.
3. **Walkthrough** — terminal-first; mirror to dashboard if `/pbg-server` is running. For each import:
   - Prompt for: `name` (catalog alias), `source` (git URL or local path), `ref` (tag/branch/commit; default `main`), `mode` (reference / fork-source / in-place), optional `description`.
   - Refuse if `name` is already in the catalog (offer overwrite with explicit confirmation).
4. **Execute** — invoke the helper:
   ```bash
   python -m pbg_superpowers.scaffold import-model \
     --workspace . --name <name> --source <url> --ref <ref> --mode <mode> [--description <text>]
   ```
   This:
   - Validates and writes the catalog entry to `workspace.yaml.imports.<name>`.
   - For `reference` mode: `git submodule add <source> external/<name>/` and checks out `<ref>`.
   - For `in-place` mode: `git submodule add <source> models/<name>/`, checks out `<ref>`, and adds a `models.<name>` entry with `external: true`.
   - For `fork-source` mode: catalog only.
5. **For in-place mode**, also create the workspace-owned overlay dir: `mkdir -p models-overlay/<name>/{phases,reports/assets,deliverables}` with placeholder `.keep` files. This is where the workspace's coordination metadata for this external model lives.
6. **Validate** — run `python scripts/lint-workspace.py` — must print `workspace lint: OK`.
7. **`PR_BODY.md`** — list the imports added with mode, source, and (for reference / in-place) the resolved path. Note any imports that were skipped because the target dir already existed.
8. **Append to `docs/decisions.yaml`** — one entry per import: `{timestamp, skill: pbg-import-models, target: <name>, summary: "registered <mode> import from <source>@<ref>"}`.
9. **Report refresh** — `/pbg-report` (workspace dashboard now lists imports under the model registry panel; deferred until report.py adds an imports section in v0.2).
10. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Safety (per spec §12)

- Submodule sources can be malicious. Refuse to add submodules from URLs the user hasn't explicitly vetted; prompt with the source URL and require confirmation before each `git submodule add`.
- Never `git submodule deinit -f` an existing import without explicit confirmation.
- For `reference` mode imports under `external/`: stage skills must NEVER write into this directory. Treat it as read-only at the OS level if needed.
- For `in-place` mode: the workspace MUST NOT push directly to the upstream remote without explicit consent (same `gh pr create` discipline as every other stage).

## Idempotency

Re-running with a name already in the catalog refuses unless `--overwrite` is given. Re-running with the same args on an already-cloned submodule is a no-op (the helper detects the existing target dir and skips).

## Examples

Register a read-only reference to v2ecoli:
```
/pbg-import-models v2ecoli \
  --source https://github.com/eagmon/v2ecoli.git \
  --ref v0.5.2 \
  --mode reference \
  --description "Whole-cell E. coli model"
```

Register a seed for a future fork:
```
/pbg-import-models legacy-replication \
  --source git@github.com:lab/replication-old.git \
  --ref main \
  --mode fork-source \
  --description "Seed for chromosome-replication-init"
```

Operate on an existing repo in-place (no fork):
```
/pbg-import-models upstream-ecoli \
  --source git@github.com:lab/ecoli-shared.git \
  --ref develop \
  --mode in-place
```
