---
name: pbg-investigation
description: "Manage Investigations — named collections of Studies grouped under a shared research question. Subcommands: new, list, add-study, remove-study, set-overview, set-status, scaffold-from-plan."
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: <subcmd> [args...]
---

# pbg-investigation

The interface for **Investigations** in the vivarium-dashboard: named collections of studies that together answer a higher-level research question.

An Investigation lives at `investigations/<slug>/investigation.yaml`. It lists member studies by slug, carries its own question/hypothesis/description, and links acceptance criteria to specific `expected_behavior[i].name` entries on member studies.

See [`docs/concepts/vivarium-dashboard-model.md`](../../docs/concepts/vivarium-dashboard-model.md) for the canonical data model.

## Write strategy

The vivarium-dashboard does **not** yet expose POST/PUT endpoints for investigation YAML (only GET `/api/iset-list` and GET `/api/iset/<name>` exist). All write subcommands write YAML directly to disk using an atomic tmp-file + rename pattern.

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`. Fail with a clear message if not found.
2. Set `WORKSPACE_ROOT` to that directory.
3. Investigation files live at `$WORKSPACE_ROOT/investigations/<slug>/investigation.yaml`.

No server-info check is required for read/write operations (files are written directly). Server is only used if you add a `list` display that needs resolved-study data from `/api/iset-list`.

## Slug validation

All `<slug>` arguments must match `^[a-z0-9][a-z0-9_-]*$`. Reject with a clear error otherwise.

## Sub-commands

### `new <slug>`

Create `investigations/<slug>/investigation.yaml` with placeholder fields.

**Steps:**

1. Validate slug format. Fail if invalid.
2. Check `investigations/<slug>/investigation.yaml` does NOT already exist. Fail with "Investigation '<slug>' already exists at investigations/<slug>/investigation.yaml. Use set-overview to update fields." if it does.
3. Create the `investigations/<slug>/` directory if absent.
4. Write `investigation.yaml` with:

```yaml
schema_version: 1
name: <slug>
title: "<slug> (untitled)"
created: '<YYYY-MM-DD>'  # today's date
status: planned

question: |
  (TODO: state the overarching research question)

hypothesis: |
  (TODO: state the predicted outcome)

description: |
  (TODO: describe the multi-study arc)

studies: []

expert_docs: []

acceptance_criteria: []
```

5. Print: `Created investigations/<slug>/investigation.yaml. Use /pbg-investigation add-study <slug> <study-slug> to add member studies.`

**Atomic write pattern:**

```python
import os, yaml, tempfile

path = os.path.join(workspace_root, "investigations", slug, "investigation.yaml")
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w") as f:
    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
os.replace(tmp, path)
```

---

### `list`

List all investigations in the workspace.

**Steps:**

1. Glob `investigations/*/investigation.yaml` relative to `WORKSPACE_ROOT`.
2. For each file: load YAML, extract `name`, `title`, `status`, `len(studies)`.
3. Sort by `name` alphabetically.
4. Print one line per investigation:

```
<slug>  <title>  <status>  <n_studies> studies
```

If no investigations exist, print: `No investigations found. Run /pbg-investigation new <slug> to create one.`

---

### `add-study <inv-slug> <study-slug>`

Append a study slug to an investigation's `studies:` list.

**Steps:**

1. Load `investigations/<inv-slug>/investigation.yaml`. Fail if absent.
2. Check `<study-slug>` is not already in `studies[]`. Fail: "Study '<study-slug>' is already in investigation '<inv-slug>'." if duplicate.
3. Warn (do NOT refuse) if `studies/<study-slug>/study.yaml` does not exist: "Warning: studies/<study-slug>/study.yaml not found. The study slug will be added but may not resolve in the dashboard."
4. Append `<study-slug>` to `studies[]`.
5. Atomic write.
6. Print: `Added '<study-slug>' to investigation '<inv-slug>' (now <N> studies).`

---

### `remove-study <inv-slug> <study-slug>`

Remove a study slug from an investigation's `studies:` list.

**Steps:**

1. Load `investigations/<inv-slug>/investigation.yaml`. Fail if absent.
2. If `<study-slug>` is not in `studies[]`, print: "Study '<study-slug>' is not in investigation '<inv-slug>'. No changes made." and exit without error.
3. Remove `<study-slug>` from `studies[]`.
4. Atomic write.
5. Print: `Removed '<study-slug>' from investigation '<inv-slug>' (now <N> studies).`

This command does NOT modify acceptance_criteria that reference the removed study — those are left in place and the user is notified: "Note: acceptance_criteria still references '<study-slug>'. Update or remove those entries manually."

---

### `set-overview <inv-slug> [--title T] [--question Q] [--hypothesis H] [--description D]`

Update one or more overview fields on an investigation. Each flag is optional; only specified fields are written.

**Steps:**

1. Load `investigations/<inv-slug>/investigation.yaml`. Fail if absent.
2. Parse flags. Require at least one flag — fail with usage if none given.
3. For each provided flag, update the corresponding YAML field. Do not touch unspecified fields.
4. Atomic write.
5. Print which fields were updated and their new character counts.

**Example:**

```bash
/pbg-investigation set-overview dnaa-replication \
  --title "DnaA / Replication Initiation" \
  --question "Can the DnaA mechanistic model reproduce once-per-generation timing?"
```

---

### `set-status <inv-slug> <status>`

Update the `status:` field on an investigation.

**Valid statuses:** `planned` | `running` | `ran` | `complete` | `failed` | `invalid` | `archived`

**Steps:**

1. Validate `<status>` against the allowed set. Fail with a list of valid values if not recognized.
2. Load `investigations/<inv-slug>/investigation.yaml`. Fail if absent.
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
- `expected_behavior` — list of `{name, observable, condition, rationale}` entries from the plan's acceptance criteria, behavioral requirements, or success metrics for this phase. Use the DSL name convention: `<process>-<observable>-<condition>` (e.g., `dnaa-count-in-mass-spec-range`). Generate at least one entry per study.
- `parent_studies` — wire linearly by default (each study depends on the previous with `condition: tests-passed`). The user can edit dependencies after scaffolding.
- `status: planned` for all generated studies.

**Investigation acceptance_criteria:**

For each study, pick the most important `expected_behavior` entry (the one that gates the next phase) and emit a `{study: <slug>, behavior: <name>}` pair in the investigation's `acceptance_criteria`.

#### 4. Print preview tree

```
Would create:

  investigations/<name>/investigation.yaml
  studies/<study-1-slug>/study.yaml
  studies/<study-2-slug>/study.yaml
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
Created investigation '<name>' with N studies. Run /pbg-server start then open the Investigations tab.
```

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

parent_studies:
  - {study: <prev-slug>, condition: tests-passed}   # omit for the first study

expected_behavior:
  - name: <behavior-name>
    observable: <observable>
    condition: <condition>
    rationale: |
      <rationale>

baseline: []
variants: []
interventions: []
runs: []
```

**Notes for Claude when running scaffold-from-plan:**

- Be conservative with hypothesis thresholds — only use numbers that appear explicitly in the plan.
- A question longer than four sentences is too long.
- If `--studies-prefix` is provided, all study slugs must start with it.
- If phase numbers appear in the plan (Phase 1, Phase 2, …), reflect them as `01-`, `02-`, … in the slug.
- For the `expert_docs` list on the investigation, scan `workspace.yaml.expert_docs[].name` values and include any that appear relevant. Do not invent names.
- The first study in the linear chain has no `parent_studies` (or an empty list).

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
# Create a new empty investigation
/pbg-investigation new dnaa-replication

# List all investigations
/pbg-investigation list

# Add an existing study to an investigation
/pbg-investigation add-study dnaa-replication dnaa-01-expression-dynamics

# Remove a study from an investigation
/pbg-investigation remove-study dnaa-replication dnaa-06-seqa-sequestration

# Update overview fields
/pbg-investigation set-overview dnaa-replication \
  --title "DnaA / Replication Initiation" \
  --question "Can a DnaA-driven model reproduce once-per-generation initiation timing?"

# Change status
/pbg-investigation set-status dnaa-replication running

# Scaffold a full investigation + studies from a plan PDF (preview only)
/pbg-investigation scaffold-from-plan references/expert/chromosome_replication_plan.pdf \
  --name dnaa-replication \
  --studies-prefix dnaa- \
  --dry-run

# Scaffold and write
/pbg-investigation scaffold-from-plan references/expert/chromosome_replication_plan.pdf \
  --name dnaa-replication \
  --studies-prefix dnaa-
```
