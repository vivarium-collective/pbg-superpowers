#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:?usage: start-server.sh <workspace-dir>}"
WORKSPACE="$(cd "$WORKSPACE" && pwd)"  # normalize to absolute path
STATE="${WORKSPACE}/.pbg/server"
mkdir -p "${STATE}/content" "${STATE}/state"

# Pick a free port (Python: bind to :0, ask the kernel for the port, close)
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')

# Write server-info BEFORE starting the server so consumers can read it immediately
cat > "${STATE}/server-info" <<EOF
{"port": ${PORT}, "host": "127.0.0.1", "url": "http://localhost:${PORT}",
 "screen_dir": "${STATE}/content", "state_dir": "${STATE}/state"}
EOF

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

nohup python3 "${PLUGIN_ROOT}/server/server.py" \
  --workspace "${WORKSPACE}" --port "${PORT}" \
  > "${STATE}/server.log" 2>&1 &

echo $! > "${STATE}/server.pid"

# Brief grace period so callers polling the port don't get ECONNREFUSED.
sleep 0.5

echo "{\"port\":${PORT},\"url\":\"http://localhost:${PORT}\"}"
