---
name: pbg-data
description: Curate datasets and paper references for a model. Adds dataset entries (path or URL+sha256) under datasets/_index.yaml, BibTeX entries under references/papers.bib, and claim mappings under references/claims.yaml. Per-paper notes go in references/notes/<key>.md.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob Grep WebFetch
argument-hint: <model-name>
---

# pbg-data

Stages 4+5 (combined) of the canonical PR flow. Operates in the workspace repo.

## Prerequisites

- Model exists in `workspace.yaml.models`.
- `stages.add_model.status` is `complete`.
- Working tree clean in the workspace repo.

## Lifecycle (per spec §7)

1. **Pre-flight** — refuse if prerequisites unmet.
2. **Branch** — `stage/4-data` in the workspace.
3. **Walkthrough**:
   - **Datasets:** prompt for name, source (filesystem path or URL), and the model claims this dataset serves. Validate path exists or fetch+sha256-pin. Append to `datasets/_index.yaml`.
   - **References:** paste BibTeX or fetch a DOI; persist to `references/papers.bib`. Validate keys are unique and not silently overwriting.
   - **Claim mappings:** edit `references/claims.yaml` to map each claim ID (e.g. `phase-2.dnaA-fires-at-threshold`) to one or more BibTeX keys.
   - **Per-paper notes:** open editor for `references/notes/<bibkey>.md`. One markdown file per BibTeX key.
4. **Validate:** run `python scripts/lint-workspace.py` — must print `workspace lint: OK`.
5. **Update workspace.yaml** — mark `models.<name>.stages.data.status = complete`. If any datasets were added, also append to top-level `datasets:` list.
6. **PR_BODY.md** — list datasets added, references added, and claim mappings.
7. **Report refresh** — `/pbg-report` (deferred until Task 21 lands).
8. **gh handoff** — print `gh pr create`; offer to run with explicit consent.

## Safety

- For URL+checksum datasets: fetch, hash, compare; never store secrets in URLs.
- For BibTeX: validate keys are unique; refuse to overwrite existing entries silently. If a duplicate key is detected, abort with a clear diff and let the user reconcile.
- Never commit large binary blobs without confirmation. Default rule: files <10MB tracked in git directly under a per-dataset subdir; larger files use `url:` + `sha256:` pointers.
- `WebFetch` is allowed only for fetching paper metadata or open dataset URLs; never for credentialed endpoints.

## Idempotency

Re-running on a complete `stages.data` is treated as an extension — append-only updates to `datasets/_index.yaml`, `papers.bib`, and `claims.yaml`. Existing entries are not overwritten without explicit confirmation.
