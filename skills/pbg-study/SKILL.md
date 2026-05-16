---
name: pbg-study
description: Manage Studies in the dashboard — full CRUD for baseline composites, variants, interventions, and runs. Wraps the v3 /api/study-* endpoints.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: new|set-objective|set-conclusion|baseline-add|baseline-remove|run-baseline|variant-add|variant-set-params|variant-delete|run-variant|intervention-add|intervention-update|intervention-delete|open [args]
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
