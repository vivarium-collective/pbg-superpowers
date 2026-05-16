---
name: pbg-study
description: Manage Studies in the dashboard — full CRUD for baseline composites, variants, interventions, and runs. Includes fill-overview to draft question/hypothesis/objective/description from plan and expert PDFs. Wraps the v3 /api/study-* endpoints.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: new|fill-overview|set-objective|set-conclusion|baseline-add|baseline-remove|run-baseline|variant-add|variant-set-params|variant-delete|run-variant|intervention-add|intervention-update|intervention-delete|open [args]
---

# pbg-study

The end-to-end interface for **Studies** in the vivarium-dashboard. A Study is a self-contained research unit holding one-or-more baseline composites, variants (parameter perturbations), interventions (text-described conditions), runs, and visualizations.

See [`docs/concepts/vivarium-dashboard-model.md`](../../docs/concepts/vivarium-dashboard-model.md) for the canonical data model.

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`. Fail if not found.
2. Read `.pbg/server/server-info` for the dashboard URL. If absent, fail with: "Run `/pbg-server start` first."

## Tests on a Study (v4 schema)

A v4 Study has a `tests/` subdirectory containing pytest files. The dashboard
runs them via `POST /api/study-tests-run {study}` and writes a summary back to
`study.yaml.tests.last_results`. The Tests tab on the Study detail page shows
per-test pass/fail with expandable tracebacks.

Tests use a `run` pytest fixture provided by `vivarium_dashboard.testing`:

```python
# studies/<slug>/tests/conftest.py
from vivarium_dashboard.testing import run  # noqa: F401

# studies/<slug>/tests/test_steady_state.py
def test_dnaA_count_in_range(run):
    assert 300 <= run.final("DnaA_count") <= 800
```

`Run` exposes: `.observable(name) → np.ndarray`, `.final(name)`, `.initial(name)`,
`.cv(name)`, `.params`, `.seed`, `.status`, `.n_steps`, `.variant`, `.composite`,
`.trajectory` (pandas DataFrame).

For studies that need to parametrize across all runs, set
`study.yaml.tests.data_source: all_runs` and use the `runs` fixture
(parametrized) instead.

## Cross-study dependencies (parent_studies)

A study can declare ordering against other studies in the workspace via
the optional `parent_studies:` field. Each entry is either a bare slug
or an object `{study, condition}` where `condition` is one of
`tests-passed` | `ran` | `complete` (default `tests-passed` when omitted).

```yaml
# studies/dnaa-02-atp-hydrolysis/study.yaml
parent_studies:
  - dnaa-01-expression-dynamics                       # legacy: tests-passed
  - {study: dnaa-03-box-binding, condition: ran}      # object: parent must have ≥1 run
```

The dashboard's `GET /api/investigations` resolves these to per-study
`blocked` + `blocked_by` (parent + condition + missing-diagnostic), and
the Studies tab's `Dependencies` sort (default) topologically orders
the cards. Cards show `Depends on:` / `Blocks:` link chips and a
`🔒 blocked` pill with diagnostics in the tooltip when blocked.

A parent slug that doesn't resolve to a real study shows up as
`parent-not-found` in `blocked_by`, so dead references are visible.

## Sub-commands

### Overview (set objective + conclusion)

#### `new <composite-id>`

Create a new Study seeded with one baseline composite.

POST `/api/study-new`:

```json
{"composite_name": "<composite-id>"}
```

Returns `{name, spec_path}`. Print the new study's name and offer to open it via `/pbg-study open <name>`.

#### `set-objective <study-name> '<text>'`

Replace the Study's objective. POST `/api/study-set-objective`:

```json
{"study": "<study-name>", "text": "<text>"}
```

#### `set-conclusion <study-name> '<markdown>'`

Replace the Study's conclusion. POST `/api/study-set-conclusion`:

```json
{"study": "<study-name>", "text": "<markdown>"}
```

The markdown is canonically structured under H2 headers: `## Claims`, `## Evidence`, `## Limitations`, `## Next steps`.

#### `fill-overview <slug> [--from-plan <path>] [--from-expert <path>...] [--fields <comma-list>] [--dry-run]`

Draft the `question`, `hypothesis`, `objective`, and/or `description` fields of an existing study by reading its linked plan and expert documents, then write them via the API after user confirmation.

**Arguments:**

- `<slug>` (required) — study slug under `studies/<slug>/`. Abort with a clear error pointing at `/pbg-study new` if the directory or `study.yaml` is absent.
- `--from-plan <path>` (optional) — path to a planning PDF or markdown that decomposes the study's intent. If absent, look inside `references/expert/` for a file whose name matches `<slug>` or contains the word "plan".
- `--from-expert <path>` (optional, repeatable) — additional expert-knowledge PDFs or markdown files. If absent, consult `workspace.yaml.expert_docs` and use any entry whose `claims_supported` list overlaps with the study's `parent_studies` or `id`.
- `--fields <comma-list>` (optional) — restrict drafting to a subset of `question,hypothesis,objective,description`. Default: all four.
- `--dry-run` (optional) — print the proposed diff and stop without writing anything.

**Behavior (steps Claude follows when running this subcommand):**

1. **Resolve study.** Read `studies/<slug>/study.yaml`. If the study doesn't exist, abort: "Study '<slug>' not found. Run `/pbg-study new` to create it."

2. **Discover source docs.** Resolve `--from-plan` and each `--from-expert` path (relative to the workspace root). If neither flag is given:
   - Scan `references/expert/` for files whose filename (lowercased, without extension) contains the slug or the substring "plan".
   - Also check `workspace.yaml` under `expert_docs` for any entry whose `claims_supported` overlaps with the study's `id` or `parent_studies`.
   - If no docs are found, warn the user and offer to continue with only the study.yaml context.

3. **Read source material.** Use the Read tool on each resolved doc. If a doc is a PDF, read all pages.

4. **Draft each requested field.** For each field in `--fields` (default: all four):

   - `question:` — One paragraph (at most four sentences), scientifically framed as a measurable prediction, ending with `?`. When the plan names a specific section or heading that motivates the question, cite it parenthetically (e.g., "per §3.2 of the plan"). Keep it concise.

   - `hypothesis:` — One paragraph stating the predicted outcome. Include quantitative thresholds (counts, fractions, timescales) **only when they appear explicitly in the source documents**. If the source is qualitative, write "approximately X to Y, per <citation>" rather than fabricating precision. Do not inflate specificity.

   - `objective:` — One paragraph in imperative present tense naming what the study will build, measure, or test (e.g., "Simulate … and measure … to determine …").

   - `description:` — Two to four paragraphs providing scientific context, citing source sections by their heading names. Structure: background, mechanism of interest, why this study, expected outcome.

   Each draft is a plain string suitable for direct insertion into `study.yaml`.

5. **Print preview.** Show a unified diff for each drafted field:
   - If the field currently has a user-authored value, display: `existing:` block then `proposed:` block, with a note that the default action is replace.
   - If the field is empty or missing, display `(empty) → <proposed>`.

6. **Confirm with the user.** Accept three responses:
   - `yes` — proceed to write.
   - `no` — abort without writing; print "No changes made."
   - `edit <field> <new-prompt>` — re-draft only that field using the new prompt, then repeat the preview for it before asking again. Loop until the user says `yes` or `no`.

7. **Write via API.** POST `/api/study-set-overview` with only the fields being written:

   ```json
   {"study": "<slug>", "question": "...", "hypothesis": "...", "objective": "...", "description": "..."}
   ```

   The endpoint accepts partial bodies — omit any field not being updated. After the POST, verify by fetching `/api/study/<slug>` and printing the resulting values of the written fields so the user can confirm what landed.

8. **Report.** Print a one-line summary per field: field name, character count before and after, and confirmation that the dashboard now shows the new value.

**Notes for Claude when running fill-overview:**

- Be conservative with hypothesis thresholds. Only state numbers that appear explicitly in the source docs. Prefer "approximately" phrasing over invented precision.
- A `question:` field longer than four sentences is too long — revise.
- If a field already has user-authored content that is substantively different from the draft, present both side-by-side and let the user decide before overwriting.
- `/api/study-set-overview` is the canonical endpoint. The legacy alias `/api/investigation-set-overview` exists for backwards compatibility but should not be used in new code.

### Baseline composites

#### `baseline-add <study-name> --name <n> --composite <id> [--params '<json>']`

Append a composite to the Study's baseline list. POST `/api/study-baseline-add`:

```json
{
  "study":     "<study-name>",
  "name":      "<unique-in-baseline>",
  "composite": "<pkg.composites.x>",
  "params":    { "k": 1, ... }
}
```

`name` must be unique within the Study's baseline. 409 on duplicate.

#### `baseline-remove <study-name> --name <n>`

Remove a baseline composite by name. POST `/api/study-baseline-remove`:

```json
{"study": "<study-name>", "name": "<baseline-entry-name>"}
```

Refuses with 409 if any variant has `base_composite` pointing to the entry (error body includes `dependents: [...]` listing the blocking variants). Refuses with 400 if removal would leave the baseline empty.

#### `run-baseline <study-name> [--composite <name>] [--steps N]`

Run a baseline composite. POST `/api/study-run-baseline`:

```json
{"study": "<study-name>", "composite": "<baseline-entry-name>", "steps": 5}
```

`composite` is the entry name in `baseline[]`. If omitted, defaults to `baseline[0]`.

### Variants

#### `variant-add <study-name> --name <n> --base-composite <baseline-name> [--params '<json>']`

Add a variant (a perturbation of a baseline composite). POST `/api/study-variant-add`:

```json
{
  "study":               "<study-name>",
  "name":                "<unique-variant-name>",
  "base_composite":      "<baseline-entry-name>",
  "parameter_overrides": { "k": 2, ... }
}
```

`base_composite` must reference an existing entry in `baseline[]`. 404 on unknown.

#### `variant-set-params <study-name> --variant <n> --params '<json>'`

Replace (not merge) a variant's parameter overrides. POST `/api/study-variant-set-params`:

```json
{"study": "<study-name>", "variant": "<n>", "parameter_overrides": {...}}
```

#### `variant-delete <study-name> --variant <n>`

Remove a variant. POST `/api/study-variant-delete`:

```json
{"study": "<study-name>", "variant": "<n>"}
```

#### `run-variant <study-name> --variant <n> [--steps N]`

Run a variant. The server resolves the variant's `base_composite` against the Study's baseline list and layers `parameter_overrides` on top. POST `/api/study-run-variant`:

```json
{"study": "<study-name>", "variant": "<n>", "steps": 5}
```

### Interventions

Interventions are text-described experimental conditions. Currently text-only: no data link to variants or runs (deferred).

#### `intervention-add <study-name> --name <n> [--description '<text>']`

POST `/api/study-intervention-add`:

```json
{"study": "<study-name>", "name": "<n>", "description": "<text>"}
```

#### `intervention-update <study-name> --name <n> --description '<text>'`

POST `/api/study-intervention-update`:

```json
{"study": "<study-name>", "name": "<n>", "description": "<text>"}
```

#### `intervention-delete <study-name> --name <n>`

POST `/api/study-intervention-delete`:

```json
{"study": "<study-name>", "name": "<n>"}
```

### Open in browser

#### `open <study-name>`

Open the Study's detail page in the user's default browser. POST `/api/open-window`:

```json
{"route": "/studies/<name>"}
```

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- Common prelude ----------------------------------------------------
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace" >&2; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "Run /pbg-server start first." >&2; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"

# Helper: build a body dict from key=value flags + post to an endpoint.
post() {
  local path="$1"; shift
  local body="$1"; shift
  curl -sf -X POST -H "Content-Type: application/json" -d "$body" "$URL$path" | python3 -m json.tool
}

sub="${1:-}"; shift || true

case "$sub" in
  new)
    CID="$1"
    BODY=$(python3 -c "import json,sys; print(json.dumps({'composite_name': sys.argv[1]}))" "$CID")
    post "/api/study-new" "$BODY"
    ;;

  set-objective)
    NAME="$1"; TEXT="$2"
    BODY=$(NAME="$NAME" TEXT="$TEXT" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'text': os.environ['TEXT']}))")
    post "/api/study-set-objective" "$BODY"
    ;;

  set-conclusion)
    NAME="$1"; MD="$2"
    BODY=$(NAME="$NAME" MD="$MD" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'text': os.environ['MD']}))")
    post "/api/study-set-conclusion" "$BODY"
    ;;

  fill-overview)
    # fill-overview is a Claude-driven subcommand. The shell case dispatches it,
    # but the actual work (reading docs, drafting fields, confirm loop, POST) is
    # performed by the host Claude instance following the prose steps in SKILL.md
    # rather than by this bash script.  The case arm below is a no-op placeholder
    # so the usage block does not fire; Claude handles everything in-context.
    SLUG="${1:-}"
    [ -n "$SLUG" ] || { echo "ERROR: fill-overview requires a study slug." >&2; exit 1; }
    # Claude: follow the "fill-overview" behavior steps in SKILL.md starting at
    # step 1 (Resolve study). The remaining flags (--from-plan, --from-expert,
    # --fields, --dry-run) are parsed from "$@" by Claude inline.
    ;;

  baseline-add)
    NAME="$1"; shift
    BNAME=""; COMPOSITE=""; PARAMS="{}"
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)      BNAME="$2";     shift 2 ;;
        --composite) COMPOSITE="$2"; shift 2 ;;
        --params)    PARAMS="$2";    shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$BNAME" ] && [ -n "$COMPOSITE" ] || { echo "--name and --composite required"; exit 1; }
    BODY=$(NAME="$NAME" BNAME="$BNAME" COMPOSITE="$COMPOSITE" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['BNAME'],
  'composite': os.environ['COMPOSITE'],
  'params': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-baseline-add" "$BODY"
    ;;

  baseline-remove)
    NAME="$1"; shift
    BNAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) BNAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$BNAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" BNAME="$BNAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'name': os.environ['BNAME']}))")
    post "/api/study-baseline-remove" "$BODY"
    ;;

  run-baseline)
    NAME="$1"; shift
    COMPOSITE=""; STEPS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --composite) COMPOSITE="$2"; shift 2 ;;
        --steps)     STEPS="$2";     shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    BODY=$(NAME="$NAME" COMPOSITE="$COMPOSITE" STEPS="$STEPS" python3 -c "
import json, os
b = {'study': os.environ['NAME']}
if os.environ['COMPOSITE']: b['composite'] = os.environ['COMPOSITE']
if os.environ['STEPS']: b['steps'] = int(os.environ['STEPS'])
print(json.dumps(b))")
    post "/api/study-run-baseline" "$BODY"
    ;;

  variant-add)
    NAME="$1"; shift
    VNAME=""; BASE=""; PARAMS="{}"
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)            VNAME="$2";  shift 2 ;;
        --base-composite)  BASE="$2";   shift 2 ;;
        --params)          PARAMS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] && [ -n "$BASE" ] || { echo "--name and --base-composite required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" BASE="$BASE" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['VNAME'],
  'base_composite': os.environ['BASE'],
  'parameter_overrides': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-variant-add" "$BODY"
    ;;

  variant-set-params)
    NAME="$1"; shift
    VNAME=""; PARAMS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2";  shift 2 ;;
        --params)  PARAMS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] && [ -n "$PARAMS" ] || { echo "--variant and --params required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" PARAMS="$PARAMS" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'variant': os.environ['VNAME'],
  'parameter_overrides': json.loads(os.environ['PARAMS']),
}))")
    post "/api/study-variant-set-params" "$BODY"
    ;;

  variant-delete)
    NAME="$1"; shift
    VNAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] || { echo "--variant required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'variant': os.environ['VNAME']}))")
    post "/api/study-variant-delete" "$BODY"
    ;;

  run-variant)
    NAME="$1"; shift
    VNAME=""; STEPS=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --variant) VNAME="$2"; shift 2 ;;
        --steps)   STEPS="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$VNAME" ] || { echo "--variant required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" STEPS="$STEPS" python3 -c "
import json, os
b = {'study': os.environ['NAME'], 'variant': os.environ['VNAME']}
if os.environ['STEPS']: b['steps'] = int(os.environ['STEPS'])
print(json.dumps(b))")
    post "/api/study-run-variant" "$BODY"
    ;;

  intervention-add)
    NAME="$1"; shift
    INAME=""; DESC=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)        INAME="$2"; shift 2 ;;
        --description) DESC="$2";  shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" DESC="$DESC" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['INAME'],
  'description': os.environ['DESC'],
}))")
    post "/api/study-intervention-add" "$BODY"
    ;;

  intervention-update)
    NAME="$1"; shift
    INAME=""; DESC=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name)        INAME="$2"; shift 2 ;;
        --description) DESC="$2";  shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] && [ -n "$DESC" ] || { echo "--name and --description required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" DESC="$DESC" python3 -c "
import json, os
print(json.dumps({
  'study': os.environ['NAME'],
  'name': os.environ['INAME'],
  'description': os.environ['DESC'],
}))")
    post "/api/study-intervention-update" "$BODY"
    ;;

  intervention-delete)
    NAME="$1"; shift
    INAME=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) INAME="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$INAME" ] || { echo "--name required"; exit 1; }
    BODY=$(NAME="$NAME" INAME="$INAME" python3 -c "
import json, os
print(json.dumps({'study': os.environ['NAME'], 'name': os.environ['INAME']}))")
    post "/api/study-intervention-delete" "$BODY"
    ;;

  open)
    NAME="$1"
    BODY=$(NAME="$NAME" python3 -c "
import json, os
print(json.dumps({'route': f'/studies/{os.environ[\"NAME\"]}'}))")
    post "/api/open-window" "$BODY"
    ;;

  *)
    cat <<EOF
Usage:
  /pbg-study new <composite-id>
  /pbg-study fill-overview <slug> [--from-plan <path>] [--from-expert <path>...] [--fields <comma-list>] [--dry-run]
  /pbg-study set-objective <study-name> '<text>'
  /pbg-study set-conclusion <study-name> '<markdown>'

  /pbg-study baseline-add    <study-name> --name <n> --composite <id> [--params '<json>']
  /pbg-study baseline-remove <study-name> --name <n>
  /pbg-study run-baseline    <study-name> [--composite <n>] [--steps N]

  /pbg-study variant-add        <study-name> --name <n> --base-composite <baseline-name> [--params '<json>']
  /pbg-study variant-set-params <study-name> --variant <n> --params '<json>'
  /pbg-study variant-delete     <study-name> --variant <n>
  /pbg-study run-variant        <study-name> --variant <n> [--steps N]

  /pbg-study intervention-add    <study-name> --name <n> [--description '<text>']
  /pbg-study intervention-update <study-name> --name <n> --description '<text>'
  /pbg-study intervention-delete <study-name> --name <n>

  /pbg-study open <study-name>
EOF
    exit 1
    ;;
esac
```

## Examples

```text
# Create a study from a composite
/pbg-study new pbg_chromosome_rep1.composites.dnaa-binding

# Draft question, hypothesis, objective, description from plan + expert PDFs
/pbg-study fill-overview dnaa-01 --from-plan references/expert/dnaa-plan.pdf
# Restrict to just question and hypothesis, dry-run first
/pbg-study fill-overview dnaa-01 --fields question,hypothesis --dry-run
# Provide extra expert doc
/pbg-study fill-overview dnaa-01 --from-plan references/expert/dnaa-plan.pdf --from-expert references/expert/grimwade2007.pdf

# Set the objective
/pbg-study set-objective dnaa-binding "Does DnaA threshold gate initiation?"

# Add a second baseline composite to compare
/pbg-study baseline-add dnaa-binding --name alt --composite pbg_chromosome_rep1.composites.alt-binding

# Add a low-threshold variant of the original baseline
/pbg-study variant-add dnaa-binding --name low --base-composite dnaa-binding --params '{"threshold": 30}'

# Run the variant
/pbg-study run-variant dnaa-binding --variant low

# Record a textual intervention
/pbg-study intervention-add dnaa-binding --name heat-shock --description "+10C for 5 min at t=10"

# Write conclusions
/pbg-study set-conclusion dnaa-binding "## Claims
- Threshold of 50 fits best
## Evidence
- See runs 3-7
## Limitations
- Single-cell only
## Next steps
- Multi-cell run"

# Open in browser
/pbg-study open dnaa-binding
```
