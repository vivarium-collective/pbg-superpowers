---
name: viva-investigation
description: "Use when grouping multiple Studies under a shared research question — creating, opening, listing, or closing an Investigation, or adding/removing member studies and orchestrating a run across all of them."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <subcmd> [args...]
---

# /viva-investigation

The interface for **Investigations** in the vivarium-workbench: named collections of studies that together answer a higher-level research question.

An Investigation lives at `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` (resolved from `workspace.yaml` `layout:`; `investigations/<slug>/` by default). It lists member studies by slug, carries its own question/hypothesis/description, and links acceptance criteria to specific `expected_behavior[i].name` entries on member studies.

See [`docs/concepts/vivarium-workbench-model.md`](../../docs/concepts/vivarium-workbench-model.md) for the canonical data model.

## See also — viva-expert → investigation → study → run → publish

This skill sits at step 2 of the showcase chain: [`/viva-expert`](../viva-expert/SKILL.md)
(heavy mode) scaffolds a whole investigation via `investigation-from-wrapper`;
each member study is then managed via [`/viva-study`](../viva-study/SKILL.md)
(step 3); individual composites can be smoke-tested directly via
[`/viva-run`](../viva-run/SKILL.md) (step 4); and the workspace is exposed as an
interactive UI — and built into a **published read-only** snapshot
(via `vivarium-workbench-publish` → gh-pages) — via
[`/viva-workbench`](../viva-workbench/SKILL.md) (step 5).

## Layout (investigation-centric, nested)

Studies live **nested under their investigation**:
`investigations/<inv>/studies/<slug>/study.yaml`, each carrying an `investigation: <inv>`
back-ref. The investigation's publication/report lives at `investigations/<inv>/reports/`
(per-investigation — there is **no global repo-wide report**).

- **Resolve a study dir** (nested- and flat-aware): studies live at `$INVESTIGATIONS_DIR/<inv>/studies/<slug>/` (nested) or legacy flat `$STUDIES_DIR/<slug>/`; check the nested path first, then the flat one.
- **Create a new study** under `$INVESTIGATIONS_DIR/<inv>/studies/<slug>/` (write the `investigation:` back-ref).
- Legacy flat `studies/<slug>/` still resolves (back-compat) until a repo is migrated with `viva-migrate-nested`.

This block governs the paths below: where older text says `studies/<slug>/` or `$STUDIES_DIR/<slug>/`, prefer the resolver / the nested path.

**Investigation-owned inputs.** An investigation owns its datasets/references under `investigations/<inv>/inputs/` (e.g. `inputs/datasets/<file>`), recorded in `investigation.yaml`:

```yaml
inputs:
  datasets:
    - inputs/datasets/beulig.csv
  references: []
  expert_docs: []
```

Repo-wide source packages and shared/unused inputs stay global (repo-level `datasets/`, `references/papers.bib`). To migrate existing repo-level datasets, run the `viva-migrate-inputs` console script (`--workspace <ws> [--apply]`): it assigns a dataset to an investigation only when exactly ONE investigation's studies reference it (by filename in `study.yaml`); multi-investigation and unused datasets are reported and left global. Default prints the plan; `--apply` performs the `git mv` and updates `investigation.yaml`.

**NEVER silently add an input the expert did not provide.** `inputs.references`, `inputs.datasets`, and `expert_docs` are the *provided* inputs — things the expert supplied or explicitly approved. If, while working, you find yourself wanting to cite a paper, invoke a mechanism, or lean on a parameter the expert did **not** give you, do **not** add it to `inputs.` and do **not** weave it into the prose as fact. Instead record it under `proposed_inputs:` with `status: pending`, plus the `provenance` (which commit / why it came up) and the `rationale` (what you used it for). The expert then Accepts or Declines each item in the report; on Accept the dashboard promotes a `kind: reference` item into `inputs.references` (a `kind: mechanism` is marked accepted for a human to integrate), on Decline it is marked declined and left out. This keeps the agent from quietly importing outside claims as if they were expert-sanctioned.

```yaml
proposed_inputs:
  _note: "Why this block exists — agent-suggested inputs the expert did NOT provide."
  items:
  - id: <slug>                 # stable id; reference ids double as the bib-key on accept
    kind: reference            # reference | mechanism
    citation: "..."            # kind=reference: the citation text
    summary: "..."             # kind=mechanism: what the mechanism is
    proposed_by: agent
    proposed_at: '2026-06-08'
    related_study: <study-slug>
    rationale: "what it was used for"
    provenance: "which commit / why it came up; NOT provided by the expert"
    status: pending            # pending | accepted | declined  (expert sets via the report)
```


## The Investigation graph (discourse graph)

The dashboard reframes the investigation page as an **Investigation graph**: a discourse/knowledge graph whose nodes are its member studies and whose edges are their `parent_studies` dependencies. The framing is **mechanism-centered** — the investigation's primary artifact is an *evolving mechanistic understanding* of the biology; each study is a **knowledge-producing operation** that generates evidence which updates confidence in mechanism elements. Read each node as **Question (Asks) → Evidence (Finds) → Confidence**:

- **Asks** — the study's `question:`.
- **Finds** — the study's `claim:` (one-line headline of what we now believe), falling back to the top `findings[].summary`.
- **Confidence** — the study's `confidence:` badge (`Accepted | Investigating | Planned | Refuted`), derived from the 6-axis status when unset.
- **Display name** — the study's `title:` (slug, prefix-stripped + humanized, when unset).

These are **study-level** fields — author them per member study via `/viva-study` (see [pbg-study → Investigation-graph fields](../viva-study/SKILL.md)). At Design, set each study's `title:` and wire `parent_studies` with a `relation:` (`leads-to` default → solid edge; `regulatory` / `refutes` → dashed edge; `supports`). At Evaluate/Decide, set `claim:` and (when the derived value is wrong) `confidence:`.

**Confidence rollup.** The investigation aggregates over its members: the graph badges each node with its study-level confidence, and the investigation's `executive.verdict_status` is the higher-level rollup a reviewer lands on first. Keep the two consistent — a `Refuted` study should be reflected in the investigation verdict.

**State-first opening — `executive` is the single source.** The investigation opening is state-first and is rendered from `executive: {what_is_this, verdict, verdict_status, verdict_detail, decisions_needed:[{question, context}]}`. The **same `executive` block** drives the report's Executive summary — do not maintain a second copy. Update `verdict` / `verdict_status` (`in-progress | passed | complete | blocked | failed | planning`) as member studies pass or fail. The framing + argument come from `question:`, `hypothesis:`, and `scientific_argument: {main_claim, evidence_for[], evidence_against[], key_figures[], caveats[]}`.

**parquet-runs / SimulationsDB convention.** For a member study's run to appear in SimulationsDB tagged to its study + investigation, the run's emitter output must live under the per-study path `studies/<slug>/parquet-runs/<run>/` (ParquetEmitter hive) or `studies/<slug>/runs.db` (SQLite, with `emitter_path` recorded). Bespoke runners (`canonical_runs:` scripts) must write there; the dashboard-managed `run-baseline` / `run-variant` flow already does.

> **Canonical run index is `.pbg/runs.jsonl`.** The per-workspace run INDEX
> (across studies) is now `.pbg/runs.jsonl`, written via
> `vivarium_workbench.lib.run_log` (workbench #612) — the dashboard
> dual-writes `runs_meta` (sqlite, per-study) + `.pbg/runs.jsonl`
> (workspace-wide). Bespoke `canonical_runs` scripts should record events via
> `run_log.append_run_event` rather than relying on a study-local `runs.db`
> alone. (This is a pointer, not a migration — the `runs.db` prose above
> stays as-is.)


## Multi-realization claims

An investigation may hold **more than one realization of the same claim** at
different fidelity levels — e.g. a phenomenological realization (a scalar
rate/knob) alongside a mechanistic realization (the same behavior emergent
from a finer-grained process). Both are first-class members; the finer one
does not replace the coarser one, it **refines** it.

- Declare the relationship with `parent_studies[].relation: refines` (see the
  `relation` enum in [pbg-study → Investigation-graph fields](../viva-study/SKILL.md)),
  pointing from the finer (refining) study back to the coarser one it refines.
- On the finer study, name the coarser realization's passing behaviors it must
  reproduce, and whether it currently does:

  ```yaml
  refinement:
    must_preserve:
      - {coarse_study: <coarse-slug>, behavior: <coarse-behavior-name>, note: "…"}
    satisfaction: PASSED   # PASSED | FAILED | PENDING
  ```

- **Re-check `satisfaction` whenever either realization changes** — a `refines`
  edge is a standing obligation, not a one-time note at authoring time.

## Investigation ≡ branch ≡ worktree

An Investigation slug is also a **git branch name** and a **worktree directory name**. The three are kept in 1:1 correspondence so that parallel agents can each work on a different Investigation without trampling each other's files, runtime DBs (`.pbg/composite-runs.db`), or dashboard ports.

- `new <slug>` creates `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` AND the git branch `<slug>`, then commits the new YAML on that branch.
- `open <slug>` creates (or reuses) a worktree at `.pbg/worktrees/<slug>/` checked out to branch `<slug>`. By default it also boots a per-worktree dashboard server (one server per worktree — intentional parallelism).
- The cross-worktree sidebar switcher in the dashboard reads `~/.pbg/servers/*.json` so every worktree's dashboard sees every other live worktree's Investigation as a clickable row.

## Write strategy

The vivarium-workbench exposes POST `/api/investigation-create` for the initial scaffold (it emits a v2-shape `investigation.yaml` with the narrative spine commented in as TODO placeholders — executive, scientific_argument, biological_story, at_a_glance, glossary, guidelines). Update subcommands write YAML directly to disk using an atomic tmp-file + rename pattern, because the dashboard doesn't yet expose mutation endpoints for the narrative-spine fields. Read paths use GET `/api/investigation-summaries` and GET `/api/investigation/<name>`.

## Rigor (investigation level)

An investigation should defend its claims against a skeptical reader; the
dashboard computes an **evidence & rigor scorecard** and the report surfaces it.
At the investigation level, declare `competing_frameworks: [{name, relation}]`
(compare your interpretive lens to alternatives) and include at least one member
study with `kind: adversarial` (a system that should NOT qualify — the metric
passes by rejecting it), so **adversarial coverage**, **falsification exposure**,
and **comparative framing** all read `ok`. Drive each member study toward 8/8 per
the per-study checklist. Full guide:
[`docs/conventions/rigor-checklist.md`](../../docs/conventions/rigor-checklist.md).
`pbg-autopoiesis` is the reference (5/5 investigation, every study 8/8).

Every member study must also reference a **REAL registered composite**
(`baseline[].composite` resolves in the registry — run `/viva-catalog` to see
them) and **persist its runs via an emitter** (sqlite / parquet / xarray, or a
run-db reference). Both are linted: an unresolved composite is flagged via
`report_linter.unresolved_composite_refs`, and a study with runs but no emitter
earns a `run_persistence` rigor `gap` + a `runs_without_emitter` warning.

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`. Fail with a clear message if not found.
2. Set `WORKSPACE_ROOT` to that directory.
3. Resolve workspace directories from `workspace.yaml`'s optional `layout:` map (honors flat or nested workspaces; conventional names when absent) — a plain config read, no server needed:

   ```bash
   eval "$(WS="$WORKSPACE_ROOT" python3 -c "
   import os, yaml
   ws = os.environ['WS']
   layout = (yaml.safe_load(open(os.path.join(ws, 'workspace.yaml'))) or {}).get('layout') or {}
   defaults = {'studies': 'studies', 'investigations': 'investigations',
               'references': 'references', 'reports': 'reports', 'datasets': 'datasets'}
   for key, dflt in defaults.items():
       print('export %s_DIR=%s' % (key.upper(), os.path.join(ws, layout.get(key, dflt))))
   ")"
   ```

   This exports `$INVESTIGATIONS_DIR`, `$STUDIES_DIR`, `$REPORTS_DIR`, etc. (each = absolute path). Use these variables for the studies/investigations/references/reports paths below — do NOT hardcode `investigations/`, `studies/`, `reports/`. (The hidden `.pbg/` machine-state dir stays at the workspace root by default — use it literally.)
4. Investigation files live at `$INVESTIGATIONS_DIR/<slug>/investigation.yaml`.

No server-info check is required for read/write operations (files are written directly). Server is only used if you add a `list` display that needs resolved-study data from `/api/investigation-summaries`.

## Slug validation

All `<slug>` arguments must match `^[a-z0-9][a-z0-9_-]*$`. Reject with a clear error otherwise.

## Sub-commands

### `new <slug>`

Create `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` with placeholder fields, create a matching git branch `<slug>`, and commit the new YAML on it.

**Steps:**

1. Validate slug format. Fail if invalid.
2. Check `$INVESTIGATIONS_DIR/<slug>/investigation.yaml` does NOT already exist. Fail with "Investigation '<slug>' already exists at $INVESTIGATIONS_DIR/<slug>/investigation.yaml. Use set-overview to update fields." if it does.
3. Check no git branch named `<slug>` exists (`git show-ref --verify --quiet refs/heads/<slug>`). Fail with: "Branch '<slug>' already exists. Pick a different slug or rename the existing branch." if it does.
4. Create branch `<slug>` from current HEAD and switch to it: `git checkout -b <slug>`.
5. Create the `$INVESTIGATIONS_DIR/<slug>/` directory if absent.
6. Write `investigation.yaml` as a v2-shape scaffold with the narrative spine commented in as TODO placeholders. Prefer the dashboard's `/api/investigation-create` endpoint when a server is running (it uses the canonical scaffolder); fall back to writing the body directly when offline:

```yaml
# <slug>/investigation.yaml — schema v2
schema_version: 2
name: <slug>
title: "<slug> (untitled)"
created: '<YYYY-MM-DD>'
status: planning

# Front matter
# question: |
#   (the overarching research question)
# hypothesis: |
#   (predicted outcome across the full study sequence)
# lead: |
#   (3-4 sentence front-of-textbook intro)

# Narrative spine (uncomment + fill as the investigation matures)
# executive:           # state-first opening AND report Executive summary (single source)
#   what_is_this: ""
#   verdict: ""
#   verdict_status: in-progress   # in-progress | passed | complete | blocked | failed | planning
#   verdict_detail: ""
#   decisions_needed: []          # [{question, context}]
# inputs:              # per-investigation owned inputs (Inputs page)
#   datasets: []       # [{name, path, supports_claims}]
#   references: []     # bibkeys (joined against the shared papers.bib)
#   expert_docs: []    # [{name, path}]
# scientific_argument: # structured claim/evidence
#   main_claim: ""
#   evidence_for: []
#   evidence_against: []
#   key_figures: []
#   caveats: []
# biological_story: |
#   (multi-paragraph plain-English mechanism narrative)
# at_a_glance:         # one-line role per member study
#   - {study: <slug>, role: ""}
# how_to_read: |
#   (evaluator tips)
# glossary:
#   - {term: "TERM", definition: "..."}
# guidelines:          # investigation-wide rules
#   literature_anchors: []
#   parameter_catalog: []
#   calibration_targets: []

studies: []
expert_docs: []
acceptance_criteria: []
```

All v2 narrative-spine fields are optional per `investigation.schema.json`, so the scaffold validates on day one. The user opts in by uncommenting + filling sections. See `template/NEXT_STEPS.md` in pbg-template for the full pattern + when to fill each.

7. `git add "$INVESTIGATIONS_DIR/<slug>/investigation.yaml"` then commit: `git commit -m "feat(investigation): scaffold <slug>"`. Do NOT push — the user pushes manually when ready.
8. Print: `Created branch '<slug>' + $INVESTIGATIONS_DIR/<slug>/investigation.yaml (committed). Use /viva-investigation open <slug> to create a worktree and start a dashboard, or /viva-investigation add-study <slug> <study-slug> to add member studies.`

**Rollback on failure:** if step 4 succeeds but a later step fails, the assistant must `git checkout -` back to the previous branch and `git branch -D <slug>` to leave the repo in a clean state before reporting the error.

**Atomic write pattern:**

```python
import os, yaml

# $INVESTIGATIONS_DIR was exported by the prelude (step 3).
path = os.path.join(os.environ["INVESTIGATIONS_DIR"], slug, "investigation.yaml")
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w") as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
os.replace(tmp, path)
```

---

### `open <slug> [--no-server] [--share-artifacts] [--no-share-artifacts]`

Create (or re-use) a git worktree for branch `<slug>` at the standard location `.pbg/worktrees/<slug>/`, then optionally start a per-worktree dashboard server in it. Auto-symlinks expensive-to-rebuild artifacts from a sibling worktree (closes friction #6 — `out/cache/` rebuilds taking minutes per new worktree).

**Steps:**

1. Validate slug format.
2. Check branch `<slug>` exists (`git show-ref --verify --quiet refs/heads/<slug>`). If not, fail with: `No branch named '<slug>'. Create it first with /viva-investigation new <slug>, or rename an existing branch with git branch -m <old> <slug>.`
3. Compute `worktree_path = .pbg/worktrees/<slug>`.
4. If `worktree_path` already exists AND is registered as a git worktree (check `git worktree list --porcelain`), print: `Worktree already exists at <worktree_path> (branch <slug>).` and skip to step 6.
5. Otherwise, run `git worktree add <worktree_path> <slug>`. Surface any git error verbatim (most common: branch already checked out elsewhere — the standard worktree path is the only sanctioned mount point, so the user should `git worktree remove` the conflicting one first).
6. **Share artifacts from a sibling worktree.** Read `workspace.yaml.runtime.shared_artifacts:` — a list of paths (relative to workspace root) that are expensive to rebuild and worth sharing across worktrees. Default if the field is absent: `["out/cache"]` (matches v2ecoli's ParCa-cache convention; harmless on workspaces that don't have one). For each declared path:
   1. Skip if the target already exists in the new worktree (whether as file, dir, or symlink).
   2. Search for a sibling worktree (any other entry from `git worktree list --porcelain`, plus the main checkout) that has the path **populated** — non-empty dir or non-zero file. Skip if none found.
   3. **With `--share-artifacts`:** create a relative symlink from `<worktree_path>/<artifact>` → the sibling's path. Print `linked: <artifact> → <sibling>/<artifact>`.
   4. **With `--no-share-artifacts`:** skip silently.
   5. **Default (neither flag):** print a recommendation line per candidate — `would link: <artifact> → <sibling>/<artifact> (re-run with --share-artifacts to apply, or --no-share-artifacts to silence)`. Don't act. The friction author's "offer to symlink or copy" intent — discoverable, opt-in.
7. Unless `--no-server` is given, start a dashboard server in the new worktree:
   ```bash
   cd "<worktree_path>" && bash scripts/serve.sh &
   ```
   The server self-registers in `~/.pbg/servers/<name>.<hash>.json` on boot. Wait briefly (poll `~/.pbg/servers/` up to ~5 s) and capture the URL for printing. If no record appears, print: `Server did not register within 5s — check scripts/serve.sh logs.` and continue (worktree is still usable).
8. Print summary:
   ```
   Worktree:    <worktree_path>
   Branch:      <slug>
   Artifacts:   <linked-count> linked from <sibling>  (omit if zero)
   Dashboard:   <url>           (omit if --no-server)
   ```

**Why symlink, not copy.** ParCa caches under `out/cache/` are read-only after build; the runners only ever read them. Symlinks save disk and stay current if the source worktree rebuilds. The friction note offered "symlink or copy" — copy is implementable as a future `--copy-artifacts` flag if anyone needs isolation.

**Schema.** `workspace.yaml.runtime.shared_artifacts:` is a free-form list of workspace-relative paths. Examples:

```yaml
runtime:
  shared_artifacts:
    - out/cache                    # v2ecoli ParCa cache (default if field absent)
    - out/cache-stage1-heuristic   # extra condition caches
    - data/precomputed             # other workspaces' equivalents
```

**Standard location rationale.** Putting all worktrees under `.pbg/worktrees/` (a) keeps them close to the parent checkout for discovery and (b) lives inside the `.pbg/` dir which is already conventionally git-ignored by workspace scaffolds, so the worktree directories themselves never accidentally show up in the parent's `git status`.

---

### `list`

List all investigations in the workspace.

**Steps:**

1. Glob `$INVESTIGATIONS_DIR/*/investigation.yaml`.
2. For each file: load YAML, extract `name`, `title`, `status`, `len(studies)`.
3. Sort by `name` alphabetically.
4. Print one line per investigation:

```
<slug>  <title>  <status>  <n_studies> studies
```

If no investigations exist, print: `No investigations found. Run /viva-investigation new <slug> to create one.`

---

### `add-study <inv-slug> <study-slug>`

Append a study slug to an investigation's `studies:` list.

**Steps:**

1. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail if absent.
2. Check `<study-slug>` is not already in `studies[]`. Fail: "Study '<study-slug>' is already in investigation '<inv-slug>'." if duplicate.
3. Warn (do NOT refuse) if `$STUDIES_DIR/<study-slug>/study.yaml` does not exist: "Warning: $STUDIES_DIR/<study-slug>/study.yaml not found. The study slug will be added but may not resolve in the dashboard."
4. Append `<study-slug>` to `studies[]`.
5. Atomic write.
6. Print: `Added '<study-slug>' to investigation '<inv-slug>' (now <N> studies).`

---

### `remove-study <inv-slug> <study-slug>`

Remove a study slug from an investigation's `studies:` list.

**Steps:**

1. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail if absent.
2. If `<study-slug>` is not in `studies[]`, print: "Study '<study-slug>' is not in investigation '<inv-slug>'. No changes made." and exit without error.
3. Remove `<study-slug>` from `studies[]`.
4. Atomic write.
5. Print: `Removed '<study-slug>' from investigation '<inv-slug>' (now <N> studies).`

This command does NOT modify acceptance_criteria that reference the removed study — those are left in place and the user is notified: "Note: acceptance_criteria still references '<study-slug>'. Update or remove those entries manually."

---

### `set-overview <inv-slug> [--title T] [--question Q] [--hypothesis H] [--description D]`

Update one or more overview fields on an investigation. Each flag is optional; only specified fields are written.

**Steps:**

1. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail if absent.
2. Parse flags. Require at least one flag — fail with usage if none given.
3. For each provided flag, update the corresponding YAML field. Do not touch unspecified fields.
4. Atomic write.
5. Print which fields were updated and their new character counts.

**Example:**

```bash
/viva-investigation set-overview dnaa-replication \
  --title "DnaA / Replication Initiation" \
  --question "Can the DnaA mechanistic model reproduce once-per-generation timing?"
```

---

### `set-status <inv-slug> <status>`

Update the `status:` field on an investigation.

**Valid statuses:** `planned` | `running` | `ran` | `complete` | `failed` | `invalid` | `archived`

**Steps:**

1. Validate `<status>` against the allowed set. Fail with a list of valid values if not recognized.
2. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail if absent.
3. Set `status: <status>`.
4. Atomic write.
5. Print: `Set status of '<inv-slug>' to '<status>'.`

---

### `scaffold-from-plan <plan.pdf> [--name <slug>] [--studies-prefix <prefix>] [--dry-run]`

The marquee subcommand. Read a plan PDF and auto-generate a complete Investigation + constituent Studies.

**Steps:**

#### 1. Read the plan PDF

Use the Read tool on `<plan.pdf>` (resolve relative to `WORKSPACE_ROOT` if not absolute). For large PDFs (>10 pages), read all pages. Also check `workspace.yaml.expert_docs` for entries whose `path` matches the same file, and read any cross-referenced supporting PDFs if available.

#### 2. Derive the investigation slug

If `--name <slug>` is provided, use it (validate slug format). Otherwise, derive from the PDF filename (e.g., `chromosome-replication-plan.pdf` → `chromosome-replication`). Fail if the derived slug does not match `^[a-z0-9][a-z0-9_-]*$`.

#### 3. Decompose the plan

Using the plan content, identify:

**Investigation overview:**
- `title` — concise human-readable title (≤60 chars).
- `question` — the overarching research question (one paragraph).
- `hypothesis` — predicted outcome across the full study sequence; include quantitative thresholds only if they appear explicitly in the plan.
- `description` — two-to-four paragraphs: background, mechanism, study sequence rationale, expected outcome.
- `expert_docs` — names of `workspace.yaml.expert_docs` entries that are relevant (match by keyword scan; leave empty if none match).

**Per-phase studies:**

For each phase/stage/section in the plan that represents a discrete implementation step:
- `study-slug` — derived from the phase name: strip noise words, lowercase, kebab-case, prepend `--studies-prefix` if provided. Keep the phase number prefix (e.g., "Phase 1: DnaA Expression Dynamics" + prefix `dnaa-` → `dnaa-01-expression-dynamics`).
- `question` — one paragraph, measurable, ending with `?`.
- `hypothesis` — one paragraph stating the expected outcome.
- `objective` — imperative present tense: "Simulate … and measure … to determine …".
- `description` — two-to-four paragraphs.
- `expected_behavior` — list of **behavior-grammar** `(given, measure, expect)` entries — `{name, en, measure: {kind, …}, expect: {op, …}, status: stub}` — from the plan's acceptance criteria, behavioral requirements, or success metrics for this phase. `status: stub` is correct before the Build phase (the acceptance band is filled when the test is built out). Use the DSL name convention: `<process>-<observable>-<condition>` (e.g., `dnaa-count-in-mass-spec-range`). Generate at least one entry per study. The flat `{observable, condition, rationale}` shape is **rejected by the dashboard loader** — do not emit it.
- `inputs` — wire the ordering DAG linearly by default: each study gets a top-level `inputs: [{artifact: <prev-slug>, from: <prev-slug>}]` naming the previous study (the canonical DAG-edge form; the edge set is the `from:` slugs). The user can edit dependencies after scaffolding. (The legacy `parent_studies` field still works as back-compat but the linter warns to migrate to `inputs.from`.)
- `status: planned` for all generated studies.

**Investigation acceptance_criteria:**

For each study, pick the most important `expected_behavior` entry (the one that gates the next phase) and emit a `{study: <slug>, behavior: <name>}` pair in the investigation's `acceptance_criteria`.

#### 4. Print preview tree

```
Would create:

  $INVESTIGATIONS_DIR/<name>/investigation.yaml
  $STUDIES_DIR/<study-1-slug>/study.yaml
  $STUDIES_DIR/<study-2-slug>/study.yaml
  ...

Proceed? [yes / no / edit]
```

In `--dry-run` mode: print the full YAML content of each file (clearly separated by `---\n# <path>\n`) and stop. Do not write anything.

#### 5. Confirm and write

- `yes` — proceed. For each file: if the path already exists, print "Skipping <path> (already exists)" and continue. Write all non-existing files using the atomic pattern. Print the summary line when done.
- `no` — print "Aborted. No files written." and exit.
- `edit <field> <new-prompt>` — re-generate just that field using the new prompt, print the updated preview, and ask again.

#### 6. Summary

```
Created investigation '<name>' with N studies. Run /viva-workbench start then open the Investigations tab.
```

#### 7. Name the execution vehicle

Scaffolding writes specs, not implementations — the member studies still need to
be built out. Name the execution vehicle rather than leaving the user to
improvise one: offer to build the members out via
**`superpowers:subagent-driven-development`** (recommended when the member
studies are independent — check the `parent_studies` DAG just written; studies
with no dependency edge between them are parallelizable) or sequentially by
hand, one study at a time, when the chain is linear or the studies are tightly
coupled.

**Study YAML shape to emit for each phase:**

```yaml
schema_version: 3
name: <study-slug>
status: planned

question: |
  <question>

hypothesis: |
  <hypothesis>

objective: |
  <objective>

description: |
  <description>

inputs:                                            # canonical DAG edges (edge set = the `from:` slugs)
  - {artifact: <prev-slug>, from: <prev-slug>}      # omit for the first study

expected_behavior:
  - name: <behavior-name>            # DSL slug: <process>-<observable>-<condition>
    en: "<one-sentence English prediction>"
    given:
      condition: <condition>        # or {run: baseline, window: full}
    measure:
      kind: observable-comparison   # design-stage placeholder measure
      observable: <observable>
    expect:
      op: within-tolerance
      note: Acceptance band set when this test is built out (design-stage stub).
    status: stub                    # pre-Build placeholder; promote to `implemented` at Build

baseline:
  - name: baseline
    composite: <pkg>.composites.<TODO>   # replace with a real registered composite (see /viva-catalog)
variants: []
interventions: []
runs: []
```

> **Why these shapes.** The dashboard loader (`load_spec`) hard-rejects a flat
> `expected_behavior: {observable, condition, rationale}` entry and an empty
> `baseline: []` — a scaffolded study with either then fails to render ("localhost
> didn't send any data"). Emit the `(given, measure, expect)` grammar with
> `status: stub`, and a single placeholder baseline entry (a `<TODO>` composite
> path is fine pre-Build — it renders, and `/viva-report`'s linter nudges you to
> wire a real one). See `docs/concepts/expected-behavior-grammar.md`.

> **schema_version: 3 caveat.** This scaffold emits `schema_version: 3`, but
> `model_settings` is only read by the Build tab on a **v4** study (see
> `/viva-study` § Render completeness) — a top-level `model_settings:` on a
> v3 study is authored-but-inert. If a phase's studies will carry calibrated
> parameters, migrate them to v4 (`schema_version: 4`, params under
> `conditions.model_settings`) once they leave the design stage, rather than
> authoring `model_settings` here where it silently won't render.

**Notes for Claude when running scaffold-from-plan:**

- Be conservative with hypothesis thresholds — only use numbers that appear explicitly in the plan.
- A question longer than four sentences is too long.
- If `--studies-prefix` is provided, all study slugs must start with it.
- If phase numbers appear in the plan (Phase 1, Phase 2, …), reflect them as `01-`, `02-`, … in the slug.
- For the `expert_docs` list on the investigation, scan `workspace.yaml.expert_docs[].name` values and include any that appear relevant. Do not invent names.
- The first study in the linear chain has no `inputs` edges (omit the list or leave it empty).

---

### `run <inv-slug> [--studies a,b,...] [--entry <name>] [--dry-run] [--keep-going]`

Run the investigation's bespoke-script studies in declaration order by calling `/viva-study run-script` for each member. The investigation-level orchestrator the dnaa-biology session asked for in friction note 2026-05-27 #1 — replaces the manual "enumerate studies, find each `sims/run_*.py`, invent CLI args, run by hand" loop.

**Arguments:**

- `<inv-slug>` (required) — investigation slug.
- `--studies a,b,c` (optional) — restrict to this comma-separated subset of member slugs (preserving declaration order). Default: every member of `investigation.yaml.studies`.
- `--entry <name>` (optional) — pass `--entry <name>` through to each `pbg-study run-script` call (so all members run the same named entry, e.g. `--entry smoke`). Default: each study runs its own `default: true` entry.
- `--dry-run` (optional) — print the planned commands; don't execute.
- `--keep-going` (optional) — continue to the next study when one fails (`make -k`-style). Default: stop on first non-zero exit and propagate it.

**Flow:**

1. Common prelude (find `workspace.yaml`, resolve workspace dirs, read `.pbg/server/server-info`).
2. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail with a clear message if absent.
3. Resolve the run list:
   - Start from `investigation.yaml.studies` in declared order.
   - If `--studies` is given, intersect (preserving the investigation's order, not the flag's order); fail if any flag-named slug is absent from the investigation.
4. For each study slug, classify it:
   - **`runnable`** — `$STUDIES_DIR/<slug>/study.yaml` exists AND has a non-empty `canonical_runs:` list. Will be run.
   - **`no-recipe`** — `study.yaml` exists but `canonical_runs:` is missing/empty. Skipped (addresses friction #9 — dnaa-05 / dnaa-06 have only spec, no `sims/`).
   - **`missing`** — `study.yaml` absent. Skipped with a warning.
5. Print the plan: a numbered list of `[runnable|no-recipe|missing] <slug>` lines + the planned `python <script> <args...>` for each runnable one.
6. If `--dry-run`: exit 0 after the plan.
7. Otherwise execute each runnable in order via `/viva-study run-script <slug> [--entry <name>]`. Stream stdout/stderr through. On non-zero exit:
   - Without `--keep-going`: stop, print `failed at <slug> (exit N)`, exit N.
   - With `--keep-going`: log the failure, continue to the next study, exit with the count of failures at the end.
8. Final summary: `ran <K>/<N> studies (<S> skipped, <F> failed)` and a one-line per-study verdict table.

```bash
# Run every study with a canonical_runs block
/viva-investigation run dnaa-replication

# Smoke-only across the full chain (fast validation)
/viva-investigation run dnaa-replication --entry smoke

# Re-run a subset, don't bail on the first failure
/viva-investigation run dnaa-replication --studies dnaa-01-expression-dynamics,dnaa-02-atp-hydrolysis --keep-going

# Preview without running
/viva-investigation run dnaa-replication --dry-run
```

The orchestrator is intentionally thin — it does not write to `runs.db`, doesn't manage parallelism, doesn't retry. Each member study's runner owns its own composite construction, emitter wiring, and (when relevant) `parquet_emitter()` lifecycle (see PR #88 — `emit.bind(composite)` for auto-flush on exit).

> **Member studies without `canonical_runs:`.** Some studies live as spec-only chapters of an investigation (parameter foundation, deferred-implementation phases). The orchestrator silently skips them — see the `no-recipe` classification above. If you want to assert that every study must be runnable, lift the check at the investigation level (e.g. a `policy: all-studies-runnable` toggle on `investigation.yaml`). Not implemented; raise it if needed.

> **Composite-shaped studies (no `canonical_runs:`).** A study whose runner is the dashboard's in-process `/api/study-run-baseline` executor doesn't need a `canonical_runs:` block — the orchestrator can't run it either (different execution surface). For now those studies appear as `no-recipe` and are skipped. A future extension could detect `baseline:` and call `/api/study-run-baseline` directly; out of scope for this iteration.

---

### `refresh-viz <inv-slug> [--studies a,b,...]`

Re-render registered charts across the investigation's member studies by orchestrating `/viva-study refresh-viz` on each one. Mirrors how the `run` subcommand iterates members — the same inclusion/exclusion logic applies.

**Arguments:**

- `<inv-slug>` (required) — investigation slug.
- `--studies a,b,c` (optional) — restrict to this comma-separated subset of member slugs (preserving declaration order). Default: every member of `investigation.yaml.studies`.

**Flow:**

1. Common prelude (find `workspace.yaml`, resolve workspace dirs).
2. Load `$INVESTIGATIONS_DIR/<inv-slug>/investigation.yaml`. Fail with a clear message if absent.
3. Resolve the study list (same intersection logic as `run`; fail if any `--studies` slug is absent from the investigation).
4. For each study slug in order, call `/viva-study refresh-viz <slug>`.
5. Collect per-chart result lists from each study and print a per-study summary:

   ```
   <slug>  rendered: N  needs_manual_refresh: M  error: K
   ```

6. Final summary: `refreshed <N> studies — <total_rendered> charts rendered, <total_errors> errors, <total_needs_manual> need manual refresh`.

Studies that have no `runs.db` or no `visualizations[]` entries are skipped with a one-line notice; this is not treated as an error.

```bash
# Refresh all studies in the investigation
/viva-investigation refresh-viz dnaa-replication

# Refresh a subset
/viva-investigation refresh-viz dnaa-replication --studies dnaa-01-expression-dynamics,dnaa-02-atp-hydrolysis
```

---

### `close <slug> [--dry-run] [--no-pr] [--skip-report] [--json]`

Close an investigation: render the workspace report, copy it into `$INVESTIGATIONS_DIR/<slug>/report.html` (so it lands as a git-tracked artifact), stamp the investigation YAML with `status: closed`, `closed_at`, `report_url`, and a populated `contributors[]`, commit on the investigation branch, and open a PR. **Never auto-merges** — stops after `gh pr create`; the user clicks merge in the GitHub UI per the standing no-auto-merge instruction.

**Arguments:**

- `<slug>` (required) — investigation slug. Per the Investigation ≡ branch convention, the git branch must be named `<slug>`.
- `--dry-run` (optional) — print the proposed actions; do not render, write, commit, push, or open a PR.
- `--no-pr` (optional) — skip the `gh pr create` step entirely (offline / no-remote use).
- `--skip-report` (optional) — don't re-render the workspace report; just stamp the YAML and commit. Useful when the report was rendered manually moments before.
- `--json` (optional) — emit the result (slug, branch, contributors, actions, pr_url) as JSON instead of plain text.

**What gets recorded in `contributors[]`:**

1. **Humans** — derived from `git log --pretty='%an|%ae|%H' <main>..<branch>`. Each unique (name, email) pair becomes one entry with `kind: human`, `roles: [implementer]`, and `commits: <count>`.
2. **Agents (via Co-Authored-By trailer)** — commits on the branch whose body contains `Co-Authored-By: <name> <email>` where the email is `*@noreply.anthropic.com`, contains `bot`, or has `ci` as a name-part are added with `kind: agent`, `roles: [agent_runner]`.
3. **Agents (via the `.pbg/` agent-sessions dir)** — every JSON file under `.pbg/agent-sessions/<id>.json` with shape `{agent_name, session_id, ...}` is grouped by `agent_name` and added (or merged into an existing entry) with `sessions[]` populated.

**User edits are preserved.** If you've previously curated `roles` or `notes` on a contributor entry, re-running close keeps those — only `commits` and `sessions` are refreshed.

**Steps (server-side, via `POST /api/iset-close`):**

The whole close mechanic — resolve workspace + investigation YAML, verify the
branch, derive contributors, render the workspace report (unless
`--skip-report`), copy it to `$INVESTIGATIONS_DIR/<slug>/report.html`, stamp
`investigation.yaml` (`status: closed`, `closed_at`, `report_url`,
`contributors`), commit on the investigation branch, and (unless `--no-pr`)
open/refresh a PR (**never `--auto`**) — runs server-side in the workspace:

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"slug": "<slug>", "dry_run": <bool>, "no_pr": <bool>, "skip_report": <bool>}' \
  "$URL/api/iset-close" | python3 -m json.tool
```

Map the flags: `--dry-run`→`dry_run:true`, `--no-pr`→`no_pr:true`,
`--skip-report`→`skip_report:true`. A 404 means the investigation or its branch
doesn't exist (per the Investigation ≡ branch convention).

The response is a `CloseResult` (`{slug, branch, contributors, actions, pr_url,
dry_run}`) listing every action taken (or proposed, in dry-run), the contributor
list, and the PR URL. With `--json`, print it verbatim; otherwise summarize the
actions + contributors + PR URL for the user.

**Example:**

```bash
# Standard close — render report, stamp YAML, commit, open PR.
/viva-investigation close dnaa-replication

# Dry-run to see what would happen.
/viva-investigation close dnaa-replication --dry-run

# Close without re-rendering the report (already rendered).
/viva-investigation close dnaa-replication --skip-report

# Close offline — no remote interaction.
/viva-investigation close dnaa-replication --no-pr
```

The close mechanic runs server-side via `POST /api/iset-close` (the workbench backs it with the same `close_investigation` compute); the dashboard's "Close investigation" button posts to the same endpoint, so the skill and the UI share one path. Because close renders the report + reads `git log`, the dashboard server must be running (`/viva-workbench start`).

---

## Implementation outline (YAML write helper)

The Python snippet below is the canonical atomic-write helper. Inline it wherever a subcommand needs to write a YAML file.

```python
import os, yaml, tempfile

def atomic_write_yaml(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=100)
    os.replace(tmp, path)
```

## Examples

```text
# Create a new empty investigation (also creates branch + commits YAML)
/viva-investigation new dnaa-replication

# Open an isolated worktree for that investigation + boot a dashboard
/viva-investigation open dnaa-replication

# Open the worktree without starting a server (e.g., for a scripted run)
/viva-investigation open dnaa-replication --no-server

# List all investigations
/viva-investigation list

# Add an existing study to an investigation
/viva-investigation add-study dnaa-replication dnaa-01-expression-dynamics

# Remove a study from an investigation
/viva-investigation remove-study dnaa-replication dnaa-06-seqa-sequestration

# Update overview fields
/viva-investigation set-overview dnaa-replication \
  --title "DnaA / Replication Initiation" \
  --question "Can a DnaA-driven model reproduce once-per-generation initiation timing?"

# Change status
/viva-investigation set-status dnaa-replication running

# Scaffold a full investigation + studies from a plan PDF (preview only)
/viva-investigation scaffold-from-plan references/expert/chromosome_replication_plan.pdf \
  --name dnaa-replication \
  --studies-prefix dnaa- \
  --dry-run

# Scaffold and write
/viva-investigation scaffold-from-plan references/expert/chromosome_replication_plan.pdf \
  --name dnaa-replication \
  --studies-prefix dnaa-
```

## Required investigation narrative (lint-gated)

Every investigation report must carry three AUTHORED narrative sections —
`executive`, `scientific_argument`, and `biological_story`. The linter
(`investigation_narrative_spine_required`) warns for each missing one. A
genuinely slim investigation may opt out per-section:

```yaml
narrative_spine_skip: [scientific_argument, biological_story]
narrative_spine_skip_reason: "single-study screen; full narrative not warranted"
```

("Decisions needed" and "Suggested additions" are framework-computed signals,
not author-required.)
