---
name: pbg-install
description: Install a package from the workspace's module catalog. Wraps /api/catalog-install — adds a submodule (or PyPI install), pip-installs into .venv, edits pyproject.toml deps, and refreshes the registry.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: <package-name>
---

# pbg-install

Install one module from the curated catalog
(`scripts/_catalog/modules.json`) into the current workspace. This is the
agentic equivalent of clicking "Install" on the Registry tab.

## Inputs

- `<package-name>` (required) — must match a `name` field in
  `scripts/_catalog/modules.json`. Use `/pbg-list` (Skills/Registry
  sections aren't quite the catalog — see Notes) or read the catalog
  directly to discover names.

## Steps

1. Walk up from cwd to find `workspace.yaml`.
2. Read `.pbg/server/server-info` for the dashboard URL.
3. Verify the workspace has an active workstream (the install endpoint
   commits via `_active_branch_action`). If absent, suggest the user
   click `Start workstream` in the dashboard or run the equivalent API
   call (`/api/work-start`).
4. POST `/api/catalog-install`:
   ```json
   {"name": "<package-name>"}
   ```
5. Wait for the response (can be slow — pip install + submodule add).
   Print:
   - install_mode (`pypi` or `submodule`)
   - commit_sha (short)
   - any out_of_sync warnings

## Notes

- The catalog lives at `scripts/_catalog/modules.json` in each workspace.
- Both PyPI and git-submodule modes are supported; the catalog entry
  picks (`pypi_name` ⇒ PyPI install, otherwise editable submodule).
- This skill does **not** by itself surface the catalog. Browse it via
  `cat scripts/_catalog/modules.json | jq '.[].name'` or the Registry
  tab.

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-}"
[ -n "$NAME" ] || { echo "Usage: /pbg-install <package-name>"; exit 1; }

DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
cd "$DIR"
URL="$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['url'])")"

BODY=$(python3 -c "import json,sys; print(json.dumps({'name': sys.argv[1]}))" "$NAME")
curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/catalog-install" | python3 -m json.tool
```

## Example

```text
/pbg-install spatio-flux
```

Output:

```json
{
  "ok": true,
  "install_mode": "submodule",
  "commit_sha": "a1b2c3d",
  "log": "Successfully installed spatio-flux ..."
}
```
