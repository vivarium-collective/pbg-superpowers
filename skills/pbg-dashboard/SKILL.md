---
name: pbg-dashboard
description: Start / stop / open the interactive vivarium-dashboard server (the side-rail-tabbed UI — Workspace, Registry, Composites, Investigations, Visualizations, GitHub Branches, Simulations DB). Distinct from /pbg-server (the report-mirror server). Subcommands start, stop, status, open, restart.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|open|restart [--port N] [--browser] [--investigation SLUG]
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

- **`/pbg-dashboard open [--investigation SLUG]`** — open the dashboard URL in the browser. Auto-starts the server first if it isn't already running. With `--investigation SLUG` (or implicitly, the slug inferred from the current branch — see below), focus or open the dashboard tab AND switch the SPA's view to that investigation's detail via injected JS — bypassing the SPA's default-to-alphabetically-first behavior.

- **`/pbg-dashboard restart`** — `stop` then `start`. Useful after a code change in an editable `vivarium-dashboard` install (Python reload isn't automatic; restart picks up changes).

Each subcommand prints a single JSON object describing the outcome.

## How to invoke

```bash
# default: prefers port 8765, leaves the browser alone (the URL is printed)
python -m pbg_superpowers.dashboard start

# open the browser too AND auto-pick the investigation matching this branch
python -m pbg_superpowers.dashboard start --browser

# force a specific investigation (implies --browser)
python -m pbg_superpowers.dashboard start --investigation dnaa-replication

# specific port (e.g. when 8765 is taken by another workspace)
python -m pbg_superpowers.dashboard start --port 9001

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

1. `<workspace>/.venv/bin/vivarium-dashboard` — the canonical, preferred path. Composites resolve from the workspace's own site-packages.
2. **Parent git-worktree's `.venv/bin/vivarium-dashboard`** — used when the current workspace is a secondary git worktree (its `.git` is a file pointing at `<main>/.git/worktrees/<name>`) and the local `.venv` is missing or doesn't have the binary. Safe because all worktrees of the same repo share source; the dashboard's `set_workspace_root()` + sys.path injection guarantees the **local** workspace's source wins for composite discovery. Avoids forcing a per-worktree `uv sync` (~5 min) just to spin up a server.

If neither path resolves, `start` raises an error and prints the install command. **Sibling-WORKSPACE venvs (different repos) are still off-limits** — those would silently load the wrong composites (mem3dg-readdy friction #13).

## Investigation auto-pick (one-branch-per-investigation convention)

The dashboard SPA auto-picks the alphabetically-first investigation when the current branch doesn't match the canonical `investigation/<slug>` pattern. This skill works around that by:

1. **Explicit `--investigation <slug>`** — wins. Implies `--browser`.
2. **Inferred from the current git branch** — when `--browser` is set (or implied) and `--investigation` isn't, the skill reads the branch name and matches it against `investigations/<slug>/investigation.yaml` directories. Match order:
   - Exact branch == slug (`colonies` ↔ `investigations/colonies/`)
   - `investigation/<slug>` prefix
   - Token-overlap scoring — `feat/dnaa-biology` → `dnaa-replication` (shared token `dnaa`)
   - Single-investigation workspace → unambiguous
3. **Falls back to alphabetical** — if no inference applies, the SPA's own default takes over.

When the slug is provided/inferred, the skill calls `_openInvestigationDetail(slug)` in the focused tab via AppleScript JS injection (Chrome family + Safari family on macOS). The JS polls for `_openInvestigationDetail` to be defined (up to 8 s) so it works whether the tab is already loaded or just opened.

## Safety

- Never modifies `workspace.yaml`, study yamls, or any persistent state — read-mostly.
- Binds to `127.0.0.1` only; never exposed externally.
- `stop` only kills the PID recorded in `.pbg/dashboard/dashboard.pid`. Won't touch other processes.
- Co-exists cleanly with `/pbg-server` (different state dir, different port).

## Compatibility with parallel worktrees

Each worktree gets its own `.pbg/dashboard/` state dir → its own port → its own server. Running `/pbg-dashboard start` from two worktrees concurrently is intentional and supported; the cross-worktree switcher in the dashboard sidebar finds the others via `~/.pbg/servers/*.json` (same convention as `/pbg-server`).

## When stage skills invoke this

Stage skills should NOT auto-start the dashboard — it's user-facing UI, not part of any stage's lifecycle. Invoke `/pbg-dashboard` only when the user wants to look at results, drive runs, or download reports.
