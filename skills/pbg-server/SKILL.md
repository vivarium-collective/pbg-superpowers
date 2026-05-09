---
name: pbg-server
description: Manage the local HTTP server that backs the live dashboard. Subcommands start, stop, status. The server is opt-in — every other skill works without it.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status
---

# pbg-server

Transversal skill (no stage). Operates on the workspace's `.pbg/server/` directory.

## Subcommands

- **`/pbg-server start`** — runs `<plugin>/server/start-server.sh <workspace>` (passes the workspace root). Writes `.pbg/server/server-info` (port, URL, content/state dirs) and `.pbg/server/server.pid`. Prints the URL.
- **`/pbg-server stop`** — reads `.pbg/server/server.pid`, sends SIGTERM, removes both `server-info` and `server.pid` once the process exits.
- **`/pbg-server status`** — prints `.pbg/server/server-info` if present (and the server is alive); otherwise reports "not running".

## What "alive" means

A server is alive when:
1. `.pbg/server/server-info` exists, AND
2. `.pbg/server/server.pid` exists, AND
3. The PID is a running process (`kill -0 $PID` succeeds), AND
4. `GET http://localhost:<port>/api/state` returns 200.

If only some of these are true (e.g., stale PID file from a crashed server), `status` reports "stale" and `start` refuses until the user runs `stop` or removes the stale state manually.

## Safety

- Never kills processes outside `.pbg/server/server.pid`.
- Never modifies `workspace.yaml` or any persistent state — server is read-mostly (only writes to `.pbg/server/state/events`).
- The server binds to `127.0.0.1` only; it is NOT exposed externally.
- The server picks a free port on `start`; multiple workspaces can run servers concurrently without conflict.

## Compatibility with other skills

Every other skill works without `/pbg-server`. When the server IS running, stage skills additionally mirror their interactive prompts to `.pbg/server/content/<step>.html` — the dashboard renders these as a top "guidance band". Click events flow back via `.pbg/server/state/events`. Stage skills read both terminal answers AND `state/events`; terminal wins on conflict.
