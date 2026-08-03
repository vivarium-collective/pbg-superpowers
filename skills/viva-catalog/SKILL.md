---
name: viva-catalog
description: Browse and mutate the workspace module catalog — list installed/available modules, install one, or uninstall one. Subcommands list (default), install <pkg>, uninstall <pkg>. Wraps /api/workspace-manifest, /api/catalog-install, /api/catalog-uninstall.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: "[list | install <pkg> | uninstall <pkg>]"
---

# pbg-catalog

Single front door for the workspace catalog. Replaces the trio
`/pbg-list`, `/pbg-install`, `/pbg-uninstall` from v0.8.x.

## Subcommands

| Form | What it does |
|---|---|
| `/viva-catalog`  (no args) | Same as `/viva-catalog list`. |
| `/viva-catalog list` | One-screen workspace summary — composites, studies, registry, installed modules, dirty count. Fetches `/api/workspace-manifest`. |
| `/viva-catalog install <pkg>` | Add a curated `pbg-*` package, install it into the workspace `.venv`, edit `pyproject.toml`, refresh the registry. Wraps `/api/catalog-install`. |
| `/viva-catalog uninstall <pkg>` | Inverse — remove an installed catalog module. Wraps `/api/catalog-uninstall`. |

Both `install` and `uninstall` commit on the workspace's active workstream
branch; ensure a workstream is active first (`Start workstream` in the
dashboard or `POST /api/work-start`).

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

## list

Render a one-screen summary of `/api/workspace-manifest`:

```bash
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

If `dirty_count > 0`, hint that `/viva-status` shows the full paths.

## install

```bash
NAME="${1:-}"
[ -n "$NAME" ] || { echo "Usage: /viva-catalog install <package-name>"; exit 1; }

BODY=$(python3 -c "import json,sys; print(json.dumps({'name': sys.argv[1]}))" "$NAME")
curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/catalog-install" | python3 -m json.tool
```

The endpoint commits via `_active_branch_action` — if no workstream is
active it will fail; ask the user to start one first.

The catalog itself lives at `scripts/_catalog/modules.json` inside the
workspace. Browse names with `jq '.[].name' scripts/_catalog/modules.json`
or via the Registry tab in the dashboard.

## uninstall

```bash
NAME="${1:-}"
[ -n "$NAME" ] || { echo "Usage: /viva-catalog uninstall <package-name>"; exit 1; }

BODY=$(python3 -c "import json,sys; print(json.dumps({'name': sys.argv[1]}))" "$NAME")
curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/catalog-uninstall" | python3 -m json.tool
```

Same workstream-required behavior as `install`.

## Examples

```text
/viva-catalog                       # same as list
/viva-catalog list
/viva-catalog install spatio-flux
/viva-catalog uninstall spatio-flux
```

Sample `list` output:

```text
Workspace: v2ecoli-chromosome-rep1  (branch main, 2 dirty files)
  package_path: pbg_chromosome_rep1
  has_origin:   yes

Composites (5):
  - pbg_chromosome_rep1.composites.dnaa-binding   spec    viz_steps=0
  ...

Studies (2):
  - dnaa-titration [in-progress] variants=4 runs=12
    topic: DnaA binding kinetics

Registry: processes=8 steps=3 emitters=1 visualizations=5 types=12

Skills (11):
  - viva-catalog: Browse and mutate the workspace module catalog ...
```

## Notes

- Replaces the v0.8.x trio `/pbg-list`, `/pbg-install`, `/pbg-uninstall`.
- For an external `pbg-*` repo audit (NOT a workspace module), use the
  maintainer script `python scripts/audit-pbg-repo.py <repo>` (formerly
  the `/pbg-package` skill).
