---
name: viva-navigate
description: Use when you need read-only answers about the workspace knowledge graph without running anything — the AC→study gating matrix and unlinked-AC gaps, which studies cite a source, which findings measure an observable, a study's prerequisite DAG, the ranked "decisions needed" list for an investigation, or a quick workspace/server/git status check.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: status | decisions <inv> | ac-gaps <inv> | source <bib_key> | finding-by-observable <token> | dag <inv> | observable <token> | composite <id>
---

# /viva-navigate

Transversal, **read-only** skill. Queries the workspace **linkage index** — a
derived, ephemeral knowledge graph over the YAML (studies ↔ composites ↔
observables ↔ sources ↔ findings ↔ acceptance ↔ study-DAG). It NEVER writes to
YAML and adds NO AI judgment: it surfaces the deterministic index the
dashboard computes server-side so you don't have to grep.

**Lead with `decisions <inv>`.** When you arrive at an investigation, the first
question is "what needs my decision?" — so run the **decisions-needed scan**
first. It aggregates the divergences/gaps the linkage index already computes into
one ranked list (it makes no new judgment — it gathers + ranks existing signals).
The other subcommands answer the follow-up "where does this link?" questions.

Every subcommand calls the dashboard: `GET /api/linkage-index` (the linkage +
navigate queries, param-dispatched) or `GET /api/needs-attention` (the
decisions-needed scan) — the same deterministic derive the old in-process
helpers computed, now TTL-cached server-side. This requires the dashboard
server to be running (see preamble below).

## Subcommands

| Form | What it does |
|---|---|
| `/viva-navigate status` | Quick "is this a pbg workspace?" status check — workspace detection, server liveness, study count, git state. |
| `/viva-navigate decisions <inv>` | Ranked decisions-needed scan. `GET /api/needs-attention?investigation=<inv>`. |
| `/viva-navigate ac-gaps <inv>` | AC→study gating matrix + unlinked-AC gaps. `GET /api/linkage-index?investigation=<inv>` → `ac_matrix`. |
| `/viva-navigate source <bib_key>` | Studies that cite a bibliography key. `GET /api/linkage-index?source=<bib_key>` → `studies`. |
| `/viva-navigate finding-by-observable <token>` | Findings that measure an observable token. `GET /api/linkage-index?observable=<token>` → `findings`. |
| `/viva-navigate dag <inv>` | Study prerequisite DAG for an investigation. `GET /api/linkage-index?investigation=<inv>` → `dag`. |
| `/viva-navigate observable <token>` | Cross-study observable registry (which composites emit it, which studies use them). `GET /api/linkage-index?observable_registry=<token>` → `studies`, `composites`. |
| `/viva-navigate composite <id>` | What a composite emits + which studies use it. `GET /api/linkage-index?composite=<id>` → `emits`, `used_by_studies`. |

## Common preamble (all subcommands)

```bash
# Walk up to workspace root.
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace"; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "ERROR: dashboard server not running. Run /viva-workbench start"; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
```

### Subcommand: status

Read-only diagnostic. Detects the nearest pbg workspace, checks the
dashboard server, reports study counts, and prints git state.  Works even
when the server is not running — API endpoints are best-effort additions.
Unlike the other subcommands above, `status` does **not** require the
dashboard server to be up (it degrades gracefully) and has its own preamble
below rather than using the "Common preamble" shared by the linkage-index
subcommands.

#### Inputs

None. (Optional: `--path <dir>` to check a specific directory instead of cwd.)

#### Steps

##### 1. Workspace detection

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

##### 2. Dashboard server liveness

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

##### 3. Git state

From the workspace root (or cwd if no workspace found):

```bash
git rev-parse --abbrev-ref HEAD        # branch name
git status --short --porcelain         # dirty-file count
```

Print:

```
git:     branch=<name>  dirty=<N> files
```

##### 4. Studies

Glob `<workspace_root>/studies/*/study.yaml`. For each, read `status:` field.
Print:

```
studies: <N> total  (draft: <n>, in-progress: <n>, completed: <n>)
```

If no `studies/` directory: `studies: none`.

#### Implementation outline

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

#### Example output (workspace found, server dead)

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

#### Example output (no workspace found)

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

---

## decisions

**Lead with this.** Print the ranked **decisions-needed scan** for an
investigation: every divergence/gap SP1–SP4 computed, gathered + ranked by
severity (high → medium → low). One line per item:
`kind · study/ref · action_hint`. Pure deterministic aggregation, AI-free, no
writes — the output is ephemeral.

The signals: `uncovered_ac` (high), `verdict_divergence` (high), `param_drift`
(high), `hard_gate` (high — a hard-severity report-card axis making the study's
severity gate FAIL; one item per axis in the gate's `gated_by`),
`test_regression` (high when an axis **broke** pass→fail, medium when it
**regressed** — margin fell — since the last run; from the cross-iteration test
diff), `phantom_observable` (high, **build-gated/optional** — only when an
`observables_for_ref` build callable is injected; the server supplies its
cached one when enabled), `open_feedback` (medium), `stale_finding` (low).

```bash
INV="${1:?Usage: /viva-navigate decisions <inv>}"
curl -sf "$URL/api/needs-attention?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
order = {"high": 0, "medium": 1, "low": 2}
last = None
for it in d["items"]:
    if it["severity"] != last:
        last = it["severity"]
        print(f"\n[{last.upper()}]")
    ref = f"{it[\"study\"]}/{it[\"ref\"]}" if it["study"] else it["ref"]
    print(f"  {it[\"kind\"]} · {ref} · {it[\"action_hint\"]}")
s = d["summary"]["by_severity"]
print(f"\n{s[\"high\"]} high / {s[\"medium\"]} medium / {s[\"low\"]} low "
      f"({d[\"summary\"][\"total\"]} total).")
'
```

## ac-gaps

Print the **AC→study gating matrix** for an investigation: one row per
acceptance criterion with its linked `study`, computed `result`, and a **gap**
flag when the criterion has NO `study:` link. Unlinked criteria are the gaps —
they make the report claim coverage that nothing actually gates (e.g.
`chromosome-cycle-calibration` has 5 acceptance criteria with no `study:`).

```bash
INV="${1:?Usage: /viva-navigate ac-gaps <inv>}"
curl -sf "$URL/api/linkage-index?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
m = d["ac_matrix"]
for r in m["criteria"]:
    flag = "  ⚠ GAP (no study linked)" if r["gap"] else ""
    print(f"- {r[\"behavior\"]:50s} study={r[\"study\"] or \"—\"} result={r[\"result\"]}{flag}")
print(f"\n{len(m[\"gaps\"])} unlinked acceptance criteria (gaps).")
'
```

## source

Print which studies cite a bibliography key (study-level `cites[]` + per-band
cites on tests/readouts).

```bash
KEY="${1:?Usage: /viva-navigate source <bib_key>}"
curl -sf "$URL/api/linkage-index?source=$KEY" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("\n".join(d["studies"]) or "(no studies cite this key)")
'
```

## finding-by-observable

Print which findings measure an observable token (resolved through the
finding's `evidence.from_test` → the test's `measure.{path,field}`).

```bash
TOKEN="${1:?Usage: /viva-navigate finding-by-observable <token>}"
curl -sf "$URL/api/linkage-index?observable=$TOKEN" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for f in d["findings"]:
    print(f"- {f[\"finding\"]}  (study {f[\"study\"]})")
'
```

## dag

Print an investigation's study prerequisite DAG (nodes + prerequisite/enables
edges from each study's `pipeline_gate`).

```bash
INV="${1:?Usage: /viva-navigate dag <inv>}"
curl -sf "$URL/api/linkage-index?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for e in d["dag"]["edges"]:
    print(f"{e[\"from\"]} → {e[\"to\"]}")
'
```

## observable

The **cross-study observable registry**: which composites *emit* an observable
`<token>` and which studies use those composites. Unlike `finding-by-observable`
(which resolves through finding evidence in the YAML), this answers "which
composites actually *emit* this observable, and which studies use those
composites" — so it needs the real composite build behind the server's
`observables_for_ref` callable. Matching reconciles the bulk dialects (a query
for `bulk.ATP[c]` finds a composite leaf `bulk[ATP[c]]`).

> **Triggers a composite build** the first time (cached, ~3s); subsequent
> calls are cheap. The server supplies the build callable — there is no
> client-side equivalent.

```bash
TOKEN="${1:?Usage: /viva-navigate observable <token>}"
curl -sf "$URL/api/linkage-index?observable_registry=$TOKEN" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("studies:   ", ", ".join(d["studies"]) or "(none)")
print("composites:", ", ".join(d["composites"]) or "(none)")
'
```

(Note the distinct `observable_registry=` param — `observable=` is the SP4a
finding-by-observable query above, which returns `findings`.)

## composite

What a composite **emits** + which studies **use** it. Also triggers a
composite build (cached).

```bash
ID="${1:?Usage: /viva-navigate composite <id>}"
curl -sf "$URL/api/linkage-index?composite=$ID" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("emits:", ", ".join(d["emits"]) or "(none)")
print("used by studies:", ", ".join(d["used_by_studies"]) or "(none)")
'
```

## Examples

```text
/viva-navigate status
/viva-navigate decisions chromosome-cycle-calibration
/viva-navigate ac-gaps chromosome-cycle-calibration
/viva-navigate source agmon-2022
/viva-navigate finding-by-observable bulk.ATP[c]
/viva-navigate dag chromosome-cycle-calibration
/viva-navigate observable bulk.ATP[c]
/viva-navigate composite pbg_chromosome_rep1.composites.dnaa-binding
```

## Notes

- **Pure query, AI-free.** Every subcommand hits `/api/linkage-index` or
  `/api/needs-attention` and prints the deterministic result. No model
  judgment, no writes — the index is ephemeral and never persisted into YAML.
- **Requires the dashboard server** — except `status`, which is designed to
  work even when the server (or the workspace itself) is missing, since its
  job is to diagnose exactly that. Every other subcommand has no in-process
  fallback — if `.pbg/server/server-info` is missing, run `/viva-workbench
  start` first.
- Run from the workspace root (the preamble walks up to find it).
