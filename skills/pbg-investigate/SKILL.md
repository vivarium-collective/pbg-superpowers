---
name: pbg-investigate
description: Launch or re-run an Investigation in the dashboard. Ensures the dashboard server is up, posts to /api/investigation-run, opens the Investigations tab in focus mode. Usage `/pbg-investigate <name>`.
---

# /pbg-investigate — Run an Investigation

Open the dashboard's Investigations tab focused on one investigation, executing it if needed.

## Inputs

- `<name>` (required) — directory name under `investigations/`, e.g. `dnaa-binding-baseline`.

## Steps

1. Walk up from the current directory to find `workspace.yaml`. Fail clearly if not found.
2. Verify `investigations/<name>/spec.yaml` exists. If not, exit with a clear error.
3. Check whether `.pbg/server/server-info` exists and the URL inside it responds to `/api/composites` with HTTP 200. If yes, reuse. Otherwise, run `bash scripts/serve.sh` in the background and poll for `server-info` up to 30 seconds.
4. POST `/api/investigation-run` with `{"name": <name>}` and wait for completion.
5. Open `<url>/#investigations` in the user's default browser.
6. Print the summary returned by the server (n_runs, n_visualizations, status).

## Implementation

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "Usage: /pbg-investigate <name>" >&2
  exit 1
fi

DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace" >&2; exit 1; }
cd "$DIR"

[ -f "investigations/$NAME/spec.yaml" ] || {
  echo "ERROR: investigations/$NAME/spec.yaml not found" >&2; exit 1; }

INFO=".pbg/server/server-info"
URL=""
if [ -f "$INFO" ]; then
  URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])" 2>/dev/null || echo '')"
  if [ -n "$URL" ] && ! curl -sf -o /dev/null --max-time 2 "$URL/api/composites"; then
    URL=""
  fi
fi
if [ -z "$URL" ]; then
  echo "starting dashboard server..."
  rm -f "$INFO"
  bash scripts/serve.sh > /tmp/pbg-investigate-server.log 2>&1 &
  for i in $(seq 1 60); do
    [ -f "$INFO" ] && break; sleep 0.5
  done
  [ -f "$INFO" ] || { cat /tmp/pbg-investigate-server.log; exit 1; }
  URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
fi

echo "Running investigation '$NAME'..."
SUMMARY=$(curl -sf -X POST "$URL/api/investigation-run" \
            -H 'Content-Type: application/json' \
            -d "{\"name\":\"$NAME\"}")
echo "Summary: $SUMMARY"

OPEN_URL="$URL/#investigations"
if command -v open >/dev/null; then open "$OPEN_URL"
elif command -v xdg-open >/dev/null; then xdg-open "$OPEN_URL"
elif command -v start >/dev/null; then start "$OPEN_URL"
else echo "Open this URL: $OPEN_URL"; fi
```
