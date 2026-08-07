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
3. POST to `<url>/api/composite-test-run`:
   ```json
   {
     "id":      "<composite-id>",
     "steps":   <N>,
     "emit_paths": ["stores/fields", ...]   // optional
   }
   ```
4. Parse the response. Print:
   - `simulation_id`
   - Number of steps run
   - List of emitted observable paths (truncated to first 20)
   - `viz_html` paths bundled with the run (if any)
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

RESP=$(curl -s -X POST -H "Content-Type: application/json" -d "$BODY" "$URL/api/composite-test-run")
echo "$RESP" | python3 -c '
import json, sys
r = json.load(sys.stdin)
if "error" in r:
    print(f"ERROR: {r[\"error\"]}")
    sys.exit(1)
print(f"simulation_id: {r.get(\"simulation_id\",\"?\")}")
print(f"steps:         {r.get(\"steps\",\"?\")}")
obs = r.get("emitted_paths") or r.get("observables") or []
print(f"observables ({len(obs)}):")
for o in obs[:20]:
    print(f"  - {o}")
if len(obs) > 20: print(f"  ... +{len(obs)-20} more")
viz = r.get("viz_html") or []
if viz:
    print(f"viz_html ({len(viz)}):")
    for v in viz: print(f"  - {v}")
'
echo
echo "Next: /viva-workbench open --composite $CID  to inspect in the dashboard"
```

## Example

```text
/viva-run pbg_chromosome_rep1.composites.dnaa-binding --steps 10 --emit stores/dnaa
```

Output:

```text
simulation_id: sim-2026-05-13T12:34:56Z
steps:         10
observables (3):
  - stores/dnaa
  - stores/dnaa/free
  - stores/dnaa/bound
viz_html (1):
  - reports/runs/sim-...html

Next: /viva-workbench open --composite pbg_chromosome_rep1.composites.dnaa-binding  to inspect in the dashboard
```
