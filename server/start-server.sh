#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:?usage: start-server.sh <workspace-dir>}"
WORKSPACE="$(cd "$WORKSPACE" && pwd)"  # normalize to absolute path
STATE="${WORKSPACE}/.pbg/server"
mkdir -p "${STATE}/content" "${STATE}/state"

# Resolve a Python interpreter that has the server's runtime deps (yaml).
# Order: workspace venv (matches the rest of the pbg-template scaffold flow),
# fall back to whatever python3 is on PATH. Using bare `python3` previously
# meant system Python — which on most macOS installs has no pyyaml — and the
# server crashed on import inside nohup, leaving stale server-info/server.pid.
if [ -x "${WORKSPACE}/.venv/bin/python3" ]; then
    PY="${WORKSPACE}/.venv/bin/python3"
elif [ -x "${WORKSPACE}/.venv/bin/python" ]; then
    PY="${WORKSPACE}/.venv/bin/python"
else
    PY="$(command -v python3 || true)"
fi
if [ -z "${PY}" ] || [ ! -x "${PY}" ]; then
    echo "ERROR: start-server.sh found no python3 (looked at ${WORKSPACE}/.venv/bin/python3 and \$PATH)" >&2
    exit 2
fi

# Recover from stale state left by a server that crashed during boot.
# (server-info gets written before nohup starts; if the child dies on import,
# we never reach the cleanup path and stop refuses to run.)
if [ -f "${STATE}/server.pid" ]; then
    OLD_PID="$(cat "${STATE}/server.pid" 2>/dev/null || true)"
    if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null; then
        echo "ERROR: pbg-server already running (PID ${OLD_PID}); run stop first" >&2
        exit 3
    fi
    # PID file present but the process is gone — stale; clean up and continue.
    rm -f "${STATE}/server.pid" "${STATE}/server-info"
fi

# Pick a free port (Python: bind to :0, ask the kernel for the port, close)
PORT=$("${PY}" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')

# Write server-info BEFORE starting the server so consumers can read it immediately
cat > "${STATE}/server-info" <<EOF
{"port": ${PORT}, "host": "127.0.0.1", "url": "http://localhost:${PORT}",
 "screen_dir": "${STATE}/content", "state_dir": "${STATE}/state"}
EOF

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

nohup "${PY}" "${PLUGIN_ROOT}/server/server.py" \
  --workspace "${WORKSPACE}" --port "${PORT}" \
  > "${STATE}/server.log" 2>&1 &

SERVER_PID=$!
echo "${SERVER_PID}" > "${STATE}/server.pid"

# Brief grace period so callers polling the port don't get ECONNREFUSED.
# Also gives us a chance to detect immediate-crash imports (e.g. missing yaml).
sleep 0.5

if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    LOG_TAIL="$(tail -20 "${STATE}/server.log" 2>/dev/null || true)"
    rm -f "${STATE}/server.pid" "${STATE}/server-info"
    echo "ERROR: pbg-server died during boot (PID ${SERVER_PID}). server.log tail:" >&2
    echo "${LOG_TAIL}" >&2
    exit 4
fi

echo "{\"port\":${PORT},\"url\":\"http://localhost:${PORT}\"}"
