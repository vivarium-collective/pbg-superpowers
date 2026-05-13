---
name: pbg-list
description: One-screen situational awareness for the current pbg workspace — composites, studies, registry, installed modules, dirty count. Fetches /api/workspace-manifest.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: (no args)
---

# pbg-list

Show a structured summary of the workspace state. Wraps the
`/api/workspace-manifest` endpoint so the agent can answer "what's in this
workspace?" in one shot, without stitching together ten separate API
calls.

## Inputs

None.

## Steps

1. Walk up from the current directory to find `workspace.yaml`. Fail with
   a clear message if not found.
2. Read `.pbg/server/server-info`. If absent, tell the user to run
   `/pbg-server start` first.
3. GET `<url>/api/workspace-manifest`.
4. Render a one-screen summary:

   ```text
   Workspace: <name>  (branch <branch>, <dirty_count> dirty files)
     package_path: <package_path>
     has_origin:   <yes|no>

   Composites (<N>):
     - <id>  <kind>  viz_steps=<viz_step_count>   <description prefix>
     ...

   Studies (<N>):
     - <name> [<status>] variants=<n_variants> runs=<n_runs>
       topic: <topic>
     ...

   Registry:
     processes=<n>  steps=<n>  emitters=<n>  visualizations=<n>  types=<n>

   Skills (<N>):
     - <name>: <description>
     ...
   ```

5. If `dirty_count > 0`, hint that `/pbg-status` shows full paths.

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

# Find workspace root
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace"; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "ERROR: dashboard server not running. Run /pbg-server start"; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"

curl -sf "$URL/api/workspace-manifest" | python3 -c '
import json, sys
d = json.load(sys.stdin)
w = d.get("workspace", {})
print(f"Workspace: {w.get(\"name\",\"?\")}  (branch {w.get(\"branch\",\"?\")}, {d.get(\"health\",{}).get(\"dirty_count\",0)} dirty files)")
print(f"  package_path: {w.get(\"package_path\",\"\")}")
print(f"  has_origin:   {\"yes\" if w.get(\"has_origin\") else \"no\"}")
comps = d.get("composites") or []
print(f"\nComposites ({len(comps)}):")
for c in comps[:20]:
    print(f"  - {c[\"id\"]}  {c.get(\"kind\",\"spec\")}  viz_steps={c.get(\"viz_step_count\",0)}   {(c.get(\"description\") or \"\")[:60]}")
if len(comps) > 20: print(f"  ... +{len(comps)-20} more")
studies = d.get("studies") or []
print(f"\nStudies ({len(studies)}):")
for s in studies:
    print(f"  - {s[\"name\"]} [{s.get(\"status\",\"?\")}] variants={s.get(\"n_variants\",0)} runs={s.get(\"n_runs\",0)}")
    if s.get("topic"): print(f"    topic: {s[\"topic\"]}")
r = d.get("registry") or {}
print(f"\nRegistry: processes={r.get(\"process_count\",0)} steps={r.get(\"step_count\",0)} emitters={r.get(\"emitter_count\",0)} visualizations={r.get(\"visualization_count\",0)} types={r.get(\"type_count\",0)}")
sk = d.get("skills") or []
print(f"\nSkills ({len(sk)}):")
for s in sk:
    print(f"  - {s[\"name\"]}: {(s.get(\"description\") or \"\")[:80]}")
'
```

## Example

```text
/pbg-list
```

Sample output:

```text
Workspace: v2ecoli-chromosome-rep1  (branch main, 2 dirty files)
  package_path: pbg_chromosome_rep1
  has_origin:   yes

Composites (5):
  - pbg_chromosome_rep1.composites.dnaa-binding   spec    viz_steps=0
  - pbg_chromosome_rep1.composites.chromosome-partition   spec  viz_steps=1
  ...

Studies (2):
  - dnaa-titration [in-progress] variants=4 runs=12
    topic: DnaA binding kinetics

Registry: processes=8 steps=3 emitters=1 visualizations=5 types=12

Skills (10):
  - pbg-server: Manage the local HTTP server ...
  - pbg-list:  One-screen situational awareness ...
```
