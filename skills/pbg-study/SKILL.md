---
name: pbg-study
description: Manage Studies (Investigations) — create from a composite, set overview, add variant, set conclusions, open in browser. Wraps /api/investigation-* and /api/open-window.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: new|set-overview|add-variant|set-conclusions|open [args]
---

# pbg-study

Sub-commands for the Studies (a.k.a. Investigations) flow. Each
sub-command wraps one or two `/api/investigation-*` endpoints on the
running dashboard server.

## Common prelude

All sub-commands:

1. Walk up from cwd to find `workspace.yaml`.
2. Read `.pbg/server/server-info` for the dashboard URL — fail with a
   helpful message if absent.

## Sub-commands

### `new <composite-id>`

Create a new Study from a composite (becomes the baseline variant).

POST `/api/investigation-create-from-composite`:

```json
{"composite_name": "<composite-id>"}
```

Returns `{name, spec_path}`. Print the new study's name and offer to open
it via `/pbg-study open <name>`.

### `set-overview <study-name> [--question '...'] [--hypothesis '...'] [--status draft|in-progress|completed|archived] [--topic '...']`

Partial-update the Study's Overview tab. POST
`/api/investigation-set-overview`:

```json
{
  "investigation": "<study-name>",
  "question":      "<optional>",
  "hypothesis":    "<optional>",
  "status":        "<optional, one of draft|in-progress|completed|archived>",
  "topic":         "<optional>"
}
```

Only include the keys the user supplied.

### `add-variant <study-name> <variant-name> --extends <parent> [--params '<json>'] [--description '...']`

Create a derived variant by perturbing an existing one. POST
`/api/investigation-composite-perturb`:

```json
{
  "investigation": "<study-name>",
  "name":          "<variant-name>",
  "extends":       "<parent>",
  "parameters":    { "rate": 0.5, ... },
  "description":   "<optional>"
}
```

### `set-conclusions <study-name> '<markdown>'`

Replace the Conclusions tab content. POST
`/api/investigation-set-conclusions`:

```json
{"investigation": "<study-name>", "conclusions": "<markdown>"}
```

The markdown is canonically structured under H2 headers:
`## Claims`, `## Evidence`, `## Limitations`, `## Next steps`.

### `open <study-name>`

Open the Study in the user's default browser. POST `/api/open-window`:

```json
{"route": "/?focus=investigations&study=<name>"}
```

(Exact route may vary; the dashboard accepts both `?focus=...` and bare
hash anchors. If the focus route is not implemented, falls back to
`/?#investigations`.)

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

# Find workspace root, read server URL
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
cd "$DIR"
URL="$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['url'])")"

sub="${1:-}"; shift || true
case "$sub" in
  new)
    CID="$1"
    BODY=$(python3 -c "import json,sys; print(json.dumps({'composite_name': sys.argv[1]}))" "$CID")
    curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
      "$URL/api/investigation-create-from-composite" | python3 -m json.tool
    ;;

  set-overview)
    NAME="$1"; shift
    JSON="{\"investigation\": \"$NAME\"}"
    while [ $# -gt 0 ]; do
      case "$1" in
        --question)   JSON=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); d['question']=sys.argv[2]; print(json.dumps(d))" "$JSON" "$2"); shift 2 ;;
        --hypothesis) JSON=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); d['hypothesis']=sys.argv[2]; print(json.dumps(d))" "$JSON" "$2"); shift 2 ;;
        --status)     JSON=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); d['status']=sys.argv[2]; print(json.dumps(d))" "$JSON" "$2"); shift 2 ;;
        --topic)      JSON=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); d['topic']=sys.argv[2]; print(json.dumps(d))" "$JSON" "$2"); shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    curl -s -X POST -H "Content-Type: application/json" -d "$JSON" \
      "$URL/api/investigation-set-overview" | python3 -m json.tool
    ;;

  add-variant)
    NAME="$1"; VNAME="$2"; shift 2
    PARENT=""; PARAMS="{}"; DESC=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --extends)     PARENT="$2"; shift 2 ;;
        --params)      PARAMS="$2"; shift 2 ;;
        --description) DESC="$2";   shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 1 ;;
      esac
    done
    [ -n "$PARENT" ] || { echo "--extends <parent> is required"; exit 1; }
    BODY=$(NAME="$NAME" VNAME="$VNAME" PARENT="$PARENT" PARAMS="$PARAMS" DESC="$DESC" python3 -c "
import json, os
b = {'investigation': os.environ['NAME'], 'name': os.environ['VNAME'], 'extends': os.environ['PARENT']}
p = os.environ['PARAMS']
if p and p != '{}': b['parameters'] = json.loads(p)
d = os.environ['DESC']
if d: b['description'] = d
print(json.dumps(b))
")
    curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
      "$URL/api/investigation-composite-perturb" | python3 -m json.tool
    ;;

  set-conclusions)
    NAME="$1"; MD="$2"
    BODY=$(NAME="$NAME" MD="$MD" python3 -c "
import json, os
print(json.dumps({'investigation': os.environ['NAME'], 'conclusions': os.environ['MD']}))
")
    curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
      "$URL/api/investigation-set-conclusions" | python3 -m json.tool
    ;;

  open)
    NAME="$1"
    BODY=$(NAME="$NAME" python3 -c "
import json, os
print(json.dumps({'route': f'/?focus=investigations&study={os.environ[\"NAME\"]}'}))
")
    curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
      "$URL/api/open-window" | python3 -m json.tool
    ;;

  *)
    cat <<EOF
Usage:
  /pbg-study new <composite-id>
  /pbg-study set-overview <study-name> [--question '...'] [--hypothesis '...']
                                       [--status draft|in-progress|completed|archived] [--topic '...']
  /pbg-study add-variant <study-name> <variant-name> --extends <parent>
                                                     [--params '<json>'] [--description '...']
  /pbg-study set-conclusions <study-name> '<markdown>'
  /pbg-study open <study-name>
EOF
    exit 1
    ;;
esac
```

## Example

```text
/pbg-study new pbg_chromosome_rep1.composites.dnaa-binding
# {"name": "dnaa-binding", "spec_path": "investigations/dnaa-binding/spec.yaml"}

/pbg-study set-overview dnaa-binding --question "How does DnaA threshold affect initiation?" --status in-progress

/pbg-study add-variant dnaa-binding low-threshold --extends baseline --params '{"threshold": 30}'

/pbg-study set-conclusions dnaa-binding "## Claims
- Threshold of 50 fits best
## Evidence
- See runs 3-7
## Limitations
- Single-cell only"

/pbg-study open dnaa-binding
```
