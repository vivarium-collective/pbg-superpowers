---
name: pbg-server
description: Manage the local HTTP server that backs the 5-tab dashboard (Workspace inputs, Registry, Simulation Setup, Visualizations, Build Model). Subcommands start, stop, status. The server is opt-in — every other skill works without it.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status
---

# pbg-server

Transversal skill (no stage). Operates on the workspace's `.pbg/server/` directory.

The dashboard exposes five tabs:

- **Workspace inputs** — datasets, references (PDFs auto-extract metadata), expert docs.
- **Registry** — browse the curated pbg-* module catalog (`scripts/_catalog/modules.json`); Install adds a submodule, pip-installs into `.venv`, appends to `pyproject.toml` deps, and refreshes the Discovered Processes/Types tables.
- **Simulation Setup** — observables to track and simulation run configurations.
- **Visualizations** — name + natural-language description; Create writes a request file and prompts the user to run `/pbg-viz <name>`; Add to project stages the generated file; Commit lands it on the active workstream branch.
- **Build Model** — workstream management strip (active branch, Push, Create PR, End).

## Subcommands

- **`/pbg-server start`** — runs `vivarium-dashboard serve --workspace <workspace>` (the dashboard CLI from the `vivarium-dashboard` package). The dashboard writes `.pbg/server/server-info` (port, URL, content/state dirs) and `.pbg/server/server.pid` on boot, plus a global running-registry entry at `~/.pbg/servers/<name>.json`. Prints the URL.
- **`/pbg-server stop`** — reads `.pbg/server/server.pid`, sends SIGTERM. The dashboard's exit handler removes `server-info`, `server.pid`, and the global registry entry; the skill verifies the PID is gone before returning.
- **`/pbg-server status`** — prints `.pbg/server/server-info` if present (and the server is alive); otherwise reports "not running". Also reports the global registry entry under `~/.pbg/servers/` if present.

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
