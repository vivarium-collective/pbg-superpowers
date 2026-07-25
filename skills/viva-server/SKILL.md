---
name: viva-server
description: Manage the local stage-skill mirror server that serves reports/index.html and proxies stage-skill guidance/click events through .pbg/server/. NOT the interactive dashboard — that's `vivarium-workbench serve` (workspace's `scripts/serve.sh`). Subcommands start, stop, status, cleanup.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|cleanup
---

# pbg-server

Transversal skill (no stage). Manages the workspace's stage-skill mirror server. State lives under `<workspace>/.pbg/server/`.

> **This is NOT the interactive dashboard.** The interactive dashboard
> (side-rail tabs: Workspace inputs, Registry, Composites, Investigations,
> Visualizations, GitHub Branches) is served by `vivarium-workbench serve`,
> launched from inside the workspace via `bash scripts/serve.sh`. If you
> want that, run `scripts/serve.sh`, not `/viva-server start`. The two
> servers are unrelated processes — they share neither port nor PID file.

## What this server actually does

- Serves the static `<workspace>/reports/index.html` on its picked port.
- Watches `.pbg/server/content/<step>.html` files written by stage skills (brainstorming, executing-plans, etc.) and renders them as a "guidance band" in the report page.
- Records click events from that band into `.pbg/server/state/events` so subsequent skill invocations can read the user's responses.

When no stage skill is mirroring prompts, the report page is the only thing it serves. Use this skill when running stage skills that want bi-directional UI; otherwise it's optional.

## Subcommands

- **`/viva-server start`** — runs `<plugin>/server/start-server.sh <workspace>`. Writes `.pbg/server/server-info` (port, URL, content/state dirs) and `.pbg/server/server.pid`. Prints the URL. The start script resolves Python from the workspace venv first; falls back to `$PATH` python3 if the venv isn't built yet. On stale state from a previous crashed boot, it cleans up automatically before retrying.

  **Cross-worktree dedup (Pass C).** Before starting, the skill queries `python -m viva_superpowers.workspace_catalog duplicates-for-path --path <workspace>`. If one or more records point at the SAME worktree path:
    - For each duplicate whose PID is dead → silently remove the record and continue.
    - For each duplicate whose PID is alive → prompt the user: `Server already running for this worktree at <url> (pid <pid>). Kill and restart? [y/N]`. On `y` send SIGTERM to the PID, wait briefly for it to exit, then remove the record via `python -m viva_superpowers.workspace_catalog cleanup-servers`. On `N` abort start with: `Aborted; existing server kept.`
    - Records pointing at DIFFERENT worktree paths are NEVER touched. Parallel worktrees each get their own dashboard server (intentional — that's how cross-worktree agent parallelism works).
- **`/viva-server stop`** — reads `.pbg/server/server.pid`, sends SIGTERM, removes both `server-info` and `server.pid` once the process exits.
- **`/viva-server status`** — prints `.pbg/server/server-info` if present and the server is alive; otherwise reports "not running" or "stale".
- **`/viva-server cleanup`** — scans `~/.pbg/servers/*.json` for orphans (PID dead OR worktree path no longer exists) and removes them. Delegates to `python -m viva_superpowers.workspace_catalog cleanup-servers`. Reports the count of removed and kept records. Live servers whose worktree path exists are NEVER removed. Safe to run anytime; runs no destructive git/shell operations.

## What "alive" means

A server is alive when:
1. `.pbg/server/server-info` exists, AND
2. `.pbg/server/server.pid` exists, AND
3. The PID is a running process (`kill -0 $PID` succeeds), AND
4. `GET http://localhost:<port>/api/state` returns 200.

If only some of these are true (e.g., stale PID file from a previously-crashed server), `status` reports "stale". `start` now self-heals stale state by clearing the dead files and retrying — but the underlying crash cause is still in `.pbg/server/server.log`, so investigate the tail before restarting if a server keeps dying.

## Safety

- Never kills processes outside `.pbg/server/server.pid`.
- Never modifies `workspace.yaml` or any persistent state — server is read-mostly (only writes to `.pbg/server/state/events`).
- The server binds to `127.0.0.1` only; it is NOT exposed externally.
- The server picks a free port on `start`; multiple workspaces can run servers concurrently without conflict.
- The interactive `vivarium-workbench serve` and this report-mirror server can run side-by-side; they don't share state.

## Compatibility with other skills

Every other skill works without `/viva-server`. When the server IS running, stage skills additionally mirror their interactive prompts to `.pbg/server/content/<step>.html` — the report page renders these as a top "guidance band". Click events flow back via `.pbg/server/state/events`. Stage skills read both terminal answers AND `state/events`; terminal wins on conflict.
