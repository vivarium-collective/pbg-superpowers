---
name: viva-explore
description: Use when the user wants to visually inspect a specific composite spec id in the dashboard's Composite Explorer — e.g. after running or authoring a composite and wanting to see its wiring in focus mode.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: <spec-id>
---

# /viva-explore — Launch the Composite Explorer for one spec

Open the dashboard's Composite Explorer page focused on one composite spec, starting the dashboard server first if needed.

## Inputs

- `<spec-id>` (required) — e.g., `pbg_chromosome_rep1.composites.dnaa-binding`

## Steps

1. Walk up from the current directory to find `workspace.yaml`. Fail with a clear message if not found.
2. Check whether `.pbg/server/server-info` exists and the URL inside it responds to `GET /api/composites` with HTTP 200. If yes, reuse that server.
3. Otherwise, run `bash scripts/serve.sh` in the background. Poll `.pbg/server/server-info` for up to 30 seconds. If it never appears, dump the server stdout/stderr and exit non-zero.
4. Read the URL from `server-info` (the `url` field).
5. Open `<url>?focus=composite-explore&id=<spec-id>` in the user's default browser (`open` on macOS, `xdg-open` on Linux, `start` on Windows).

## Implementation script

```bash
#!/usr/bin/env bash
set -euo pipefail

SPEC_ID="${1:-}"
if [ -z "$SPEC_ID" ]; then
  echo "Usage: /viva-explore <spec-id>" >&2
  exit 1
fi

# Walk up looking for workspace.yaml
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
if [ ! -f "$DIR/workspace.yaml" ]; then
  echo "ERROR: not inside a pbg workspace (no workspace.yaml found up the tree)" >&2
  exit 1
fi
cd "$DIR"

INFO=".pbg/server/server-info"
NEED_START=0
if [ -f "$INFO" ]; then
  URL="$(python3 -c "import json,sys; print(json.load(open('$INFO'))['url'])" 2>/dev/null || echo '')"
  if [ -n "$URL" ] && curl -sf -o /dev/null --max-time 2 "$URL/api/composites"; then
    : # server is alive, reuse
  else
    NEED_START=1
  fi
else
  NEED_START=1
fi

if [ "$NEED_START" = "1" ]; then
  echo "starting dashboard server via scripts/serve.sh..."
  rm -f "$INFO"
  bash scripts/serve.sh > /tmp/viva-explore-server.log 2>&1 &
  for i in $(seq 1 60); do
    [ -f "$INFO" ] && break
    sleep 0.5
  done
  if [ ! -f "$INFO" ]; then
    echo "ERROR: server did not start within 30 seconds" >&2
    echo "--- server log ---" >&2
    cat /tmp/viva-explore-server.log >&2 || true
    exit 1
  fi
  URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
fi

FULL_URL="${URL}?focus=composite-explore&id=${SPEC_ID}"

# Cross-platform browser launch
if command -v open >/dev/null; then
  open "$FULL_URL"
elif command -v xdg-open >/dev/null; then
  xdg-open "$FULL_URL"
elif command -v start >/dev/null; then
  start "$FULL_URL"
else
  echo "No browser launcher found. Open this URL manually:"
  echo "  $FULL_URL"
fi
echo "Composite Explorer opened: $FULL_URL"
```

## Reference

The explorer page UI is described in `pbg-template/docs/superpowers/specs/2026-05-11-composite-explorer-workbench-design.md` and the implementation plan in `pbg-template/docs/superpowers/plans/2026-05-11-composite-explorer-workbench.md`.

## Example

```bash
/viva-explore pbg_caspule.composites.bond-network-with-viz
```

Opens the bond-network-with-viz composite in a focus-mode window. The dashboard's other tabs (Workspace inputs, Registry, etc.) are hidden — only the Composite Explorer is visible.
