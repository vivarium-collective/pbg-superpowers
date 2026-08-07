---
name: viva-status
description: Use when starting work in a directory and needing to know whether it's a viva workspace, or when troubleshooting workspace detection or dashboard-server status — reports workspace.yaml presence, dashboard-server liveness, study count, active branch, and git status.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: (no args)
---

# /viva-status

Read-only diagnostic skill. Detects the nearest pbg workspace, checks the
dashboard server, reports study counts, and prints git state.  Works even
when the server is not running — API endpoints are best-effort additions.

## Inputs

None. (Optional: `--path <dir>` to check a specific directory instead of cwd.)

## Steps

### 1. Workspace detection

Walk up from cwd (or `--path`) looking for `workspace.yaml`:

```bash
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
```

**If found:**

```
✓ workspace: <name>
  path:         <absolute path to workspace root>
  package:      <package_path>
  schema_ver:   <schema_version>
  imports:      <N imports listed>
  expert_docs:  <N expert docs>
```

**If NOT found:**

```
✗ no workspace.yaml in /path/to/cwd or any ancestor directory
  -> this directory is not a pbg workspace.
```

Then check `~/.pbg/workspaces.json` for registered workspaces and print them:

```
catalog (~/.pbg/workspaces.json): 3 registered workspaces:
  - v2ecoli-workspace  /Users/you/code/v2ecoli-workspace  (last_opened: 2026-05-15)
  - viva-munk          /Users/you/code/viva-munk          (last_opened: 2026-05-15)
  - viva-biomodels     /Users/you/code/viva-biomodels
next:
  /viva-workspace <name> --upstream <repo>   # scaffold a sibling workspace
  /viva-workspace <name> --in-place          # turn this existing checkout into a workspace
  cd <path>                                 # open an existing workspace
```

If `~/.pbg/workspaces.json` is absent or empty, print `catalog: no registered workspaces`.

### 2. Dashboard server liveness

Probe the running **vivarium-workbench** server directly (the inline check
below): read `<workspace_root>/.pbg/server/server-info` (written by
`/viva-workbench start`) and TCP-probe its URL. Prefix the result with
`server: ` so the consolidated status block stays a one-screen summary.

If `<workspace_root>/.pbg/server/server-info` is absent, print
`server:  not running` and skip the API-endpoint best-effort calls below.

If workspace was not found but cwd has a stale
`.pbg/server/server-info`, surface that as a separate one-liner:

```
stale .pbg/server/server-info in cwd: yes (pid=<N> not running — safe to delete)
```

When the server is alive, hit the three best-effort API endpoints to
enrich the rest of the status output:

- `GET /api/work-status`
- `GET /api/dirty-status`
- `GET /api/workspace-manifest`

Render workstream / dirty-files info as the existing implementation
outline below shows.

### 3. Git state

From the workspace root (or cwd if no workspace found):

```bash
git rev-parse --abbrev-ref HEAD        # branch name
git status --short --porcelain         # dirty-file count
```

Print:

```
git:     branch=<name>  dirty=<N> files
```

### 4. Studies

Glob `<workspace_root>/studies/*/study.yaml`. For each, read `status:` field.
Print:

```
studies: <N> total  (draft: <n>, in-progress: <n>, completed: <n>)
```

If no `studies/` directory: `studies: none`.

---

## Implementation outline

> The dashboard-server portion below probes the running vivarium-workbench
> server (started by `/viva-workbench start`) via its `.pbg/server/server-info`
> record — a self-contained TCP probe, no separate server skill required.

```bash
#!/usr/bin/env bash
set -uo pipefail

# 1. Walk up to find workspace.yaml
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done

if [ ! -f "$DIR/workspace.yaml" ]; then
  echo "✗ no workspace.yaml in $PWD or any ancestor directory"
  echo "  -> this directory is not a pbg workspace."
  # Catalog
  python3 -c "
import json, os
cat = os.path.expanduser('~/.pbg/workspaces.json')
try:
    data = json.load(open(cat))
    ws_list = data.get('workspaces', data) if isinstance(data, dict) else data
    if not ws_list:
        print('catalog: no registered workspaces')
    else:
        print(f'catalog (~/.pbg/workspaces.json): {len(ws_list)} registered workspaces:')
        items = ws_list.items() if isinstance(ws_list, dict) else [(w.get('name','?'), w) for w in ws_list]
        for name, info in items:
            path = info.get('path', '') if isinstance(info, dict) else info
            last = info.get('last_opened', '') if isinstance(info, dict) else ''
            suffix = f'  (last_opened: {last})' if last else ''
            print(f'  - {name:<24} {path}{suffix}')
except FileNotFoundError:
    print('catalog: no registered workspaces')
" 2>/dev/null
  echo "next:"
  echo "  /viva-workspace <name> --upstream <repo>   # scaffold a sibling workspace"
  echo "  /viva-workspace <name> --in-place          # promote this checkout into a workspace"
  # Check for stale server-info in cwd
  if [ -f "$PWD/.pbg/server/server-info" ]; then
    PID=$(python3 -c "import json; print(json.load(open('$PWD/.pbg/server/server-info')).get('pid','-'))" 2>/dev/null || echo "-")
    echo "stale .pbg/server/server-info in cwd: yes (pid=$PID not running — safe to delete)"
  fi
  exit 0
fi

WS_ROOT="$DIR"
cd "$WS_ROOT"

# Print workspace identity
python3 -c "
import yaml, json, sys
ws = yaml.safe_load(open('workspace.yaml'))
name = ws.get('name','?')
pkg  = ws.get('package_path','')
ver  = ws.get('schema_version','?')
imports = ws.get('imports', {}) or {}
n_imports = len(imports) if isinstance(imports, dict) else len(imports)
expert_docs = ws.get('expert_docs', []) or []
print(f'✓ workspace: {name}')
print(f'  path:         $WS_ROOT')
print(f'  package:      {pkg}')
print(f'  schema_ver:   {ver}')
print(f'  imports:      {n_imports}')
print(f'  expert_docs:  {len(expert_docs)}')
"

# 2. Server liveness
INFO=".pbg/server/server-info"
URL="" PID="" PORT="" ALIVE=false
if [ -f "$INFO" ]; then
  read -r URL PID PORT ALIVE < <(python3 -c "
import json, socket
info = json.load(open('$INFO'))
url = info.get('url','')
pid = info.get('pid','-')
port_raw = info.get('port') or url.split(':')[-1].rstrip('/')
try:
    port = int(str(port_raw).split('/')[-1])
    s = socket.create_connection(('127.0.0.1', port), timeout=1)
    s.close()
    alive = 'true'
except Exception:
    alive = 'false'
    port = port_raw
print(url, pid, port, alive)
" 2>/dev/null)
  if [ "$ALIVE" = "true" ]; then
    echo "server:  $URL  pid=$PID  [alive]"
  else
    echo "server:  $URL  pid=$PID  [DEAD — safe to delete .pbg/server/server-info]"
  fi
else
  echo "server:  not running"
fi

# 3. Git state
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
DIRTY=$(git status --short --porcelain 2>/dev/null | wc -l | tr -d ' ')
echo "git:     branch=$BRANCH  dirty=$DIRTY files"

# 4. Studies
python3 -c "
import glob, yaml
from collections import Counter
files = sorted(glob.glob('studies/*/study.yaml'))
if not files:
    print('studies: none')
else:
    statuses = []
    for f in files:
        try:
            d = yaml.safe_load(open(f)) or {}
            statuses.append(d.get('status','unknown'))
        except Exception:
            statuses.append('parse-error')
    c = Counter(statuses)
    parts = ', '.join(f\"{k}: {v}\" for k,v in sorted(c.items()))
    print(f'studies: {len(files)} total  ({parts})')
" 2>/dev/null

# 5. API endpoints (best-effort, only when server alive)
if [ "$ALIVE" = "true" ] && [ -n "$URL" ]; then
  WS_STATUS=$(curl -sf "$URL/api/work-status"        || echo '{}')
  DIRTY_API=$( curl -sf "$URL/api/dirty-status"       || echo '{}')
  MANIFEST=$(  curl -sf "$URL/api/workspace-manifest" || echo '{}')
  WS_STATUS="$WS_STATUS" DIRTY_API="$DIRTY_API" MANIFEST="$MANIFEST" python3 <<'PY'
import json, os
ws  = json.loads(os.environ.get("WS_STATUS","{}") or "{}")
d   = json.loads(os.environ.get("DIRTY_API","{}") or "{}")
m   = json.loads(os.environ.get("MANIFEST","{}") or "{}")
if ws.get("active"):
    pr = ws.get("pr_url") or "none"
    print(f"workstream: active  branch={ws.get('branch','?')}  base={ws.get('base','main')}  "
          f"commits_ahead={ws.get('commits_ahead',0)}  unpushed={ws.get('unpushed',0)}")
    print(f"            PR: {pr}")
else:
    print("workstream: none")
files = d.get("files") or []
if files:
    print(f"dirty ({len(files)}):")
    for f in files[:20]:
        print(f"  {f.get('status','??'):2}  {f.get('path','')}")
    if len(files) > 20:
        print(f"  ... +{len(files)-20} more")
skills_n = len(m.get("skills") or [])
if skills_n:
    print(f"skills installed: {skills_n}")
PY
fi
```

## Example output (workspace found, server dead)

```text
✓ workspace: v2ecoli
  path:         /Users/you/code/v2ecoli
  package:      v2ecoli
  schema_ver:   2
  imports:      0
  expert_docs:  2
server:  http://127.0.0.1:61341  pid=60307  [DEAD — safe to delete .pbg/server/server-info]
git:     branch=dnaa-replication-studies  dirty=3 files
studies: 6 total  (draft: 6)
```

## Example output (no workspace found)

```text
✗ no workspace.yaml in /Users/you/code/v2ecoli or any ancestor directory
  -> this directory is not a pbg workspace.
catalog (~/.pbg/workspaces.json): 3 registered workspaces:
  - v2ecoli-workspace      /Users/you/code/v2ecoli-workspace  (last_opened: 2026-05-15)
  - viva-munk              /Users/you/code/viva-munk          (last_opened: 2026-05-15)
  - viva-biomodels         /Users/you/code/viva-biomodels
next:
  /viva-workspace <name> --upstream <repo>   # scaffold a sibling workspace
  /viva-workspace <name> --in-place          # promote this checkout into a workspace
stale .pbg/server/server-info in cwd: yes (pid=60307 not running — safe to delete)
```
