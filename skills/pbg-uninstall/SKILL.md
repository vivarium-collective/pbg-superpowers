---
name: pbg-uninstall
description: Uninstall a package from the current workspace. Wraps /api/catalog-uninstall — removes the submodule (or PyPI install), edits pyproject.toml deps, and refreshes the registry.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: <package-name>
---

# pbg-uninstall

Inverse of `/pbg-install`. Removes a previously-installed catalog module
from the workspace.

## Inputs

- `<package-name>` (required) — the same `name` field as used in
  `/pbg-install`.

## Steps

1. Walk up from cwd to find `workspace.yaml`.
2. Read `.pbg/server/server-info` for the dashboard URL.
3. Verify the workspace has an active workstream (the uninstall endpoint
   commits the change). If absent, prompt the user to start one.
4. POST `/api/catalog-uninstall`:
   ```json
   {"name": "<package-name>"}
   ```
5. Print the response:
   - `commit_sha` (short)
   - paths that were removed from `pyproject.toml` / `workspace.yaml`
   - any cleanup warnings

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-}"
[ -n "$NAME" ] || { echo "Usage: /pbg-uninstall <package-name>"; exit 1; }

DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
cd "$DIR"
URL="$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['url'])")"

BODY=$(python3 -c "import json,sys; print(json.dumps({'name': sys.argv[1]}))" "$NAME")
curl -s -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/catalog-uninstall" | python3 -m json.tool
```

## Example

```text
/pbg-uninstall spatio-flux
```

Output:

```json
{
  "ok": true,
  "commit_sha": "e5f6g7h",
  "removed_paths": ["external/spatio-flux"]
}
```

After running, both the Available modules card and the Installed modules
list on the dashboard refresh automatically (the manifest endpoint
re-reads `workspace.yaml` on each request).
