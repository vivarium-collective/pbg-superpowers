---
name: pbg-dashboard
description: Start / stop / open the interactive vivarium-dashboard server (the side-rail-tabbed UI — Workspace, Registry, Composites, Investigations, Visualizations, GitHub Branches, Simulations DB). Distinct from /pbg-server (the report-mirror server). Subcommands start, stop, status, open, restart.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|open|restart [--port N] [--no-browser]
---

# pbg-dashboard

Transversal skill (no stage). Manages the interactive **vivarium-dashboard** server: the UI you actually look at to drive a workspace — Investigations, Studies, Simulations DB, Visualizations, GitHub Branches.

> **This is NOT `pbg-server`.** `/pbg-server` manages the workspace's
> *report-mirror* server (renders stage-skill guidance into the static
> `reports/index.html`). `/pbg-dashboard` manages the *interactive*
> dashboard served by the `vivarium-dashboard` pip package. The two
> processes are unrelated — different ports, different state dirs,
> different purposes. Run both side-by-side if you want.

## What this skill actually does

Wraps the `vivarium-dashboard serve` CLI so the dashboard runs detached, survives terminal exits, has its state tracked at `<workspace>/.pbg/dashboard/`, and opens in your browser automatically.

State files:

  `.pbg/dashboard/dashboard-info`  JSON: `{port, host, url, pid, workspace, started_at, log_file}`
  `.pbg/dashboard/dashboard.pid`   text: PID of the running server
  `.pbg/dashboard/dashboard.log`   text: stdout/stderr of the server

## Subcommands

- **`/pbg-dashboard start`** — pick a free port (prefer 8765), launch `vivarium-dashboard serve --workspace . --port <P>` detached, write info+pid+log, wait briefly for the HTTP probe, and open the URL in the browser. Crashes-on-import are surfaced via the log tail. If the dashboard is already alive, just opens the browser.

- **`/pbg-dashboard stop`** — read the PID file, send SIGTERM, wait up to 5 s, escalate to SIGKILL if needed, clear the state files.

- **`/pbg-dashboard status`** — `alive` / `stale` / `not-running`. Probes both the PID (`kill -0`) and the HTTP endpoint to distinguish a wedged process from a healthy one.

- **`/pbg-dashboard open`** — open the dashboard URL in the browser. Auto-starts the server first if it isn't already running.

- **`/pbg-dashboard restart`** — `stop` then `start`. Useful after a code change in an editable `vivarium-dashboard` install (Python reload isn't automatic; restart picks up changes).

Each subcommand prints a single JSON object describing the outcome.

## How to invoke

```bash
# default: prefers port 8765, opens browser
python -m pbg_superpowers.dashboard start

# specific port (e.g. when 8765 is taken by another workspace)
python -m pbg_superpowers.dashboard start --port 9001

# headless (CI / scripts)
python -m pbg_superpowers.dashboard start --no-browser

# probe state
python -m pbg_superpowers.dashboard status

# graceful shutdown
python -m pbg_superpowers.dashboard stop

# reopen the existing one (or auto-start if dead)
python -m pbg_superpowers.dashboard open
```

The `--workspace <path>` flag is also available (default: cwd) for invoking from outside the workspace root.

## What "alive" means

A dashboard is alive when all three are true:

1. `.pbg/dashboard/dashboard.pid` exists and the PID is a running process (`kill -0 $PID` succeeds), AND
2. `.pbg/dashboard/dashboard-info` exists, AND
3. `GET <url>/` returns 200.

If 1+2 hold but 3 doesn't, status reports `stale` with a note — the process may be wedged on import or stuck in a slow startup. Inspect `.pbg/dashboard/dashboard.log` (the tail explains it). `start` self-heals stale state by clearing the dead files and retrying.

## Resolving the dashboard binary

Order of resolution:

1. `<workspace>/.venv/bin/vivarium-dashboard` (workspace venv — matches the pbg-template scaffold flow).
2. `$(which vivarium-dashboard)` (global install).
3. `python -m vivarium_dashboard.server` (if `vivarium_dashboard` is importable from the current interpreter).

If none resolve, `start` raises an error telling the user to install `vivarium-dashboard`.

## Safety

- Never modifies `workspace.yaml`, study yamls, or any persistent state — read-mostly.
- Binds to `127.0.0.1` only; never exposed externally.
- `stop` only kills the PID recorded in `.pbg/dashboard/dashboard.pid`. Won't touch other processes.
- Co-exists cleanly with `/pbg-server` (different state dir, different port).

## Compatibility with parallel worktrees

Each worktree gets its own `.pbg/dashboard/` state dir → its own port → its own server. Running `/pbg-dashboard start` from two worktrees concurrently is intentional and supported; the cross-worktree switcher in the dashboard sidebar finds the others via `~/.pbg/servers/*.json` (same convention as `/pbg-server`).

## When stage skills invoke this

Stage skills should NOT auto-start the dashboard — it's user-facing UI, not part of any stage's lifecycle. Invoke `/pbg-dashboard` only when the user wants to look at results, drive runs, or download reports.
