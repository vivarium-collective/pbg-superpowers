---
name: pbg-status
description: Quick workspace health check — active branch, dirty files (full paths), server status, workstream/PR state.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: (no args)
---

# pbg-status

Textual equivalent of the dashboard's workspace-strip — useful when you
want the same info without opening a browser.

## Inputs

None.

## Steps

1. Walk up from the current directory to find `workspace.yaml`.
2. Read `.pbg/server/server-info` for the dashboard URL + PID.
   - If absent: report "server not running" (everything else still works
     via direct git/yaml reads, but skip the API calls).
3. Hit, in parallel, these endpoints:
   - `GET /api/work-status` — active workstream branch, commits ahead,
     unpushed count, PR number/URL.
   - `GET /api/dirty-status` — full porcelain list of uncommitted files.
   - `GET /api/workspace-manifest` — workspace identity + skill list.
4. Render:

   ```text
   Workspace:    <name> @ <branch>
   Server:       <url>  pid=<pid>
   Workstream:   <active|none>  base=<base>  commits_ahead=<n>  unpushed=<n>
                 PR: <pr_url or 'none'>
   Dirty (<n>):
     <status>  <path>
     ...
   Skills installed: <n>
   ```

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace"; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
if [ -f "$INFO" ]; then
  URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
  PID="$(python3 -c "import json; print(json.load(open('$INFO'))['pid'])")"
else
  URL=""
  PID=""
fi

# Pull the three API endpoints (best-effort)
if [ -n "$URL" ]; then
  WS_STATUS=$(curl -sf "$URL/api/work-status"        || echo '{}')
  DIRTY=$(    curl -sf "$URL/api/dirty-status"       || echo '{}')
  MANIFEST=$( curl -sf "$URL/api/workspace-manifest" || echo '{}')
else
  WS_STATUS='{}' DIRTY='{}' MANIFEST='{}'
fi

WS_STATUS="$WS_STATUS" DIRTY="$DIRTY" MANIFEST="$MANIFEST" URL="$URL" PID="$PID" python3 <<'PY'
import json, os
ws  = json.loads(os.environ["WS_STATUS"]  or "{}")
d   = json.loads(os.environ["DIRTY"]      or "{}")
m   = json.loads(os.environ["MANIFEST"]   or "{}")
mw  = m.get("workspace", {}) or {}
print(f"Workspace:    {mw.get('name','?')} @ {mw.get('branch','?')}")
print(f"Server:       {os.environ['URL'] or '(not running)'}  pid={os.environ['PID'] or '-'}")
if ws.get("active"):
    pr = ws.get("pr_url") or "none"
    print(f"Workstream:   active  branch={ws.get('branch','?')}  base={ws.get('base','main')}  "
          f"commits_ahead={ws.get('commits_ahead',0)}  unpushed={ws.get('unpushed',0)}")
    print(f"              PR: {pr}")
else:
    print("Workstream:   none")
files = d.get("files") or []
print(f"Dirty ({len(files)}):")
for f in files[:30]:
    print(f"  {f.get('status','??'):2}  {f.get('path','')}")
if len(files) > 30:
    print(f"  ... +{len(files)-30} more")
print(f"Skills installed: {len(m.get('skills') or [])}")
PY
```

## Example

```text
/pbg-status
```

Output:

```text
Workspace:    v2ecoli-chromosome-rep1 @ feat/dnaa-titration
Server:       http://127.0.0.1:53770  pid=31019
Workstream:   active  branch=feat/dnaa-titration  base=main  commits_ahead=3  unpushed=3
              PR: none
Dirty (2):
  M   pbg_chromosome_rep1/composites/foo.yaml
  ??  notes/scratch.md
Skills installed: 10
```
