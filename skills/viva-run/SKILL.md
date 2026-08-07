---
name: viva-run
description: Use when the user wants to smoke-test a composite from the workspace catalog directly — run it for N steps and see what observables it emits — without creating or touching a Study.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: <composite-id> [--steps N] [--emit p1,p2,...]
---

# /viva-run

Run a composite (spec or generator) for `N` steps and print a summary of
the emitted observables. Wraps `/api/composite-test-run`.

## See also — viva-expert → investigation → study → run → publish

This skill is step 4 of the showcase chain: it smoke-tests one composite
directly, ad hoc, outside any Study — the fast sibling to
[`/viva-study`](../viva-study/SKILL.md)'s `run-baseline` / `run-variant`
(step 3), which is itself scaffolded by [`/viva-expert`](../viva-expert/SKILL.md)
and grouped by [`/viva-investigation`](../viva-investigation/SKILL.md) (step 2).
Once studies have real runs, [`/viva-workbench`](../viva-workbench/SKILL.md)
(step 5) builds the published read-only snapshot.

<!-- Cross-skill house rule from a study-feedback friction review. General. -->
## House rule: bias to execute

Once a plan or design is approved, **run it** and return the emitted results — not
a description of what you would run, an observer, or a stub. When this run is part
of a study, recording `runs[].outcomes`, running the study's behavior tests, and
reporting are owned by `/viva-study` (see its "bias to execute" house rule).

## Inputs

- `<composite-id>` (required) — the dotted reference
  (e.g. `spatio_flux.composites.metabolism.monod_kinetics`). Use
  `/viva-catalog list` to find IDs.
- `--steps N` (optional) — number of simulation steps. Default `5`.
- `--emit p1,p2,...` (optional) — store paths to emit. Paths use `/` as
  separator (e.g. `stores/fields`). Cascades to descendants. Defaults to
  "emit everything" if omitted.

## Steps

1. Walk up from cwd to find `workspace.yaml`.
2. Read `.pbg/server/server-info` for the dashboard URL.
3. POST to `<url>/api/composite-test-run` with `{"id": "<composite-id>", "steps": <N>, "emit_paths": [...]}` (`emit_paths` optional). **The run is DETACHED** — the POST returns `202 {"run_id": "...", "status": "running"}`, NOT the observables. Do **not** try to read `simulation_id`/`observables` off this response (it doesn't have them; doing so silently reports "0 observables").
4. **Poll** `GET <url>/api/composite-run/<run_id>/status` until `status` is `completed` (or `failed`). Then read the emitted observables from the run directory `.pbg/runs/<run_id>/observables.json` (shape `{"fields": {<observable>: <value>, ...}}`), plus any `report.html` / `viz.json` there. Print the run_id, final status, and the observables (first 20).
5. Suggest follow-ups:
   - `/viva-workbench open --composite <composite-id>` to inspect in the dashboard
   - `/viva-catalog list` if the composite ID was wrong

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

CID=""; STEPS="5"; EMIT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --steps) STEPS="$2"; shift 2 ;;
    --emit)  EMIT="$2";  shift 2 ;;
    -*)      echo "unknown flag: $1" >&2; exit 1 ;;
    *)       CID="$1";   shift ;;
  esac
done
[ -n "$CID" ] || { echo "Usage: /viva-run <composite-id> [--steps N] [--emit p1,p2,...]"; exit 1; }

DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
cd "$DIR"
URL="$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['url'])")"
python3 -m viva_superpowers.server_preflight --url "$URL" || true  # version-skew preflight (warns; never fails)

EMIT_JSON='null'
if [ -n "$EMIT" ]; then
  EMIT_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1].split(',')))" "$EMIT")
fi
BODY=$(python3 -c "
import json, sys
cid, steps, emit = sys.argv[1], int(sys.argv[2]), sys.argv[3]
b = {'id': cid, 'steps': steps}
if emit != 'null':
    b['emit_paths'] = json.loads(emit)
print(json.dumps(b))
" "$CID" "$STEPS" "$EMIT_JSON")

# composite-test-run is DETACHED: POST returns 202 {run_id, status:"running"}.
RUN_ID=$(curl -s -X POST -H "Content-Type: application/json" -d "$BODY" "$URL/api/composite-test-run" \
  | python3 -c "import json,sys; r=json.load(sys.stdin); (sys.stderr.write('ERROR: '+r['error']+'\n'), sys.exit(1)) if 'error' in r else print(r.get('run_id',''))")
[ -n "$RUN_ID" ] || { echo "no run_id returned from composite-test-run" >&2; exit 1; }
echo "run_id: $RUN_ID  (detached; polling status…)"

# Poll the detached run to completion.
ST="running"
for _ in $(seq 1 120); do
  ST=$(curl -s "$URL/api/composite-run/$RUN_ID/status" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','?'))")
  [ "$ST" = "completed" ] && break
  [ "$ST" = "failed" ] && { echo "run failed — see .pbg/runs/$RUN_ID/" >&2; exit 1; }
  sleep 2
done

# The detached runner writes results into the run dir; read observables from there.
python3 -c "
import json, os, sys
run_id, status = sys.argv[1], sys.argv[2]
path = os.path.join('.pbg', 'runs', run_id, 'observables.json')
print('status: ' + status)
if not os.path.exists(path):
    print('(no observables.json at ' + path + ' — check the run dir)'); sys.exit(0)
fields = (json.load(open(path)) or {}).get('fields', {})
print('observables (' + str(len(fields)) + '):')
for k, v in list(fields.items())[:20]:
    print('  - ' + str(k) + ' = ' + str(v))
if len(fields) > 20:
    print('  ... +' + str(len(fields) - 20) + ' more')
" "$RUN_ID" "$ST"
echo
echo "Next: /viva-workbench open --composite $CID  to inspect in the dashboard"
```

## Example

```text
/viva-run pbg_chromosome_rep1.composites.dnaa-binding --steps 10 --emit stores/dnaa
```

Output:

```text
run_id: pbg_chromosome_rep1.composites.dnaa-binding__1786129177__354faf  (detached; polling status…)
status: completed
observables (3):
  - glucose = 9.595111
  - biomass = 0.147911
  - acetate = 0.075864

Next: /viva-workbench open --composite pbg_chromosome_rep1.composites.dnaa-binding  to inspect in the dashboard
```
