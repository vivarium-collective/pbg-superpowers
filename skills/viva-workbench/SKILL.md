---
name: viva-workbench
description: Use when the interactive vivarium-workbench dashboard server needs to be started, stopped, checked, opened in a browser, or restarted — the server every dashboard-touching skill and the study reports depend on.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|open|restart [--port N] [--browser] [--investigation SLUG]
---

# /viva-workbench

Transversal skill (no stage). Manages the interactive **vivarium-workbench**
server: the UI you actually look at to drive a workspace — Investigations,
Studies, Simulations DB, Visualizations, Composites, GitHub Branches. Also
handles its session-per-tab model — one workspace per browser tab, opened
from the workspace switcher.

> **Serves reports too.** The workbench also serves the static
> `reports/index.html` (and mirrors stage-skill guidance into it). The old
> standalone report-mirror server (`/viva-server`) was retired — the workbench
> is now the single server. For a quick offline look without the workbench,
> open `reports/index.html` directly, or run `python -m http.server -d reports`.

## See also — viva-expert → investigation → study → run → publish

This skill is step 5 (final) of the showcase chain: [`/viva-expert`](../viva-expert/SKILL.md)
scaffolds a whole showcase investigation via `investigation-from-wrapper`, whose
member studies are managed via [`/viva-investigation`](../viva-investigation/SKILL.md)
(step 2) and [`/viva-study`](../viva-study/SKILL.md) (step 3), with individual
composites smoke-testable via [`/viva-run`](../viva-run/SKILL.md) (step 4). This
skill drives the *interactive* workbench, and the same workspace also builds the
**published read-only** flow: the publish scaffolder writes
`scripts/publish_dashboard.sh` + `.github/workflows/publish-dashboard.yml`, then
`vivarium-workbench-publish` renders a static snapshot deployed to gh-pages.

## Session-per-tab — one workspace per browser tab

The workbench multiplexes **many workspaces from one running server, one per
browser tab.** This is the model Jim (`jcschaff`) + Alex (`AlexPatrie`) built
(session-per-tab slices, vivarium-dashboard PRs #538–#550; design in the repo's
`docs/session-binding.md` + `docs/session-registry.md`).

How it works:

- **Each tab is its own session on its own workspace.** A per-tab id lives in
  `sessionStorage` and rides every request as an **`X-VW-Session`** header
  (server-minted via a response-header handshake, wired by a `window.fetch`
  override). The server's `SessionRegistry` routes each request to *that tab's*
  workspace — including resolving the workspace's **own `.venv` interpreter** for
  env-worker calls. Tabs are independent: v2ecoli in one, biomodels in another,
  side by side, no cross-talk.
- **Opening a workspace opens a NEW tab bound to it.** In the left-rail
  **workspace switcher** (backed by `/api/workspaces`), selecting a workspace (or
  a branch/source) opens it in a **new browser tab** rather than re-pointing the
  current one — so your current work is never disrupted. A managed/preparing
  workspace is born with an hourglass favicon and flips to ready when
  materialized.
- **Back-compatible.** Header-less clients (curl, the CLI, tests) carry no
  per-tab id → they resolve to the process **default** workspace (the one passed
  to `serve --workspace`), exactly as before.

**To use it:** run one workbench (`/viva-workbench start` from any workspace, or
just open the already-running one), then use the workspace switcher to open each
workspace you want in its own tab. You do **not** launch a server per workspace
for this — one server fans them out per tab.

> Legacy note: the switcher also still supports the older **port-per-workspace**
> mode (each running workspace as its own server process on its own port, opened
> as a peer URL in a new tab; visible as per-row `url`/`pid` in `/api/workspaces`).
> Both coexist; session-per-tab is the direction.

## What this skill actually does

Drives the `vwb` (vivarium-workbench) CLI's server-lifecycle verbs so the
workbench runs detached, survives terminal exits, has its state tracked at
`<workspace>/.pbg/server/`, and (with `--browser`) opens in your browser. This
launches the **default-workspace** server for a workspace/worktree; session-per-tab
multiplexing of *other* workspaces then happens in the browser via the switcher
(above).

State files (written by `vwb serve`, read by every dashboard-touching skill):

  `.pbg/server/server-info`  JSON: `{port, host, url, pid, ...}`
  `.pbg/server/server.pid`   text: PID of the running server
  `.pbg/server/server.log`   text: stdout/stderr of the detached server

## Subcommands

- **`/viva-workbench start`** → `vwb serve --detach` — picks a free port, launches
  the server detached, writes `.pbg/server/{server-info,server.pid,server.log}`,
  waits for the HTTP probe, and (with `--browser` → `--open`) opens the URL.
  Import crashes surface via the log tail. If already alive, adopts it.
- **`/viva-workbench stop`** → `vwb server-stop` — SIGTERM the recorded PID, wait,
  clear state files.
- **`/viva-workbench status`** → `vwb server-status` — `running` / `stale` /
  `stopped`. Probes both the PID (`kill -0`) and the HTTP endpoint to distinguish
  a wedged process from a healthy one.
- **`/viva-workbench open [--investigation SLUG]`** → `vwb server-open
  [--investigation SLUG]` — open the workbench URL in the browser (auto-start via
  `vwb serve --detach` first if not running). `--investigation SLUG` opens the
  dashboard at that investigation's route.
- **`/viva-workbench restart`** → `vwb server-restart` — `stop` then `serve
  --detach`. Useful after a code change in an editable `vivarium-workbench`
  install (Python reload isn't automatic).

Each verb prints a single line / JSON object describing the outcome.

## How to invoke

```bash
# default: pick a free port, leave the browser alone (the URL is printed)
vwb serve --detach

# open the browser too AND auto-pick the investigation matching this branch
vwb serve --detach --open

# force a specific investigation
vwb serve --detach --open --investigation dnaa-replication

# specific port
vwb serve --detach --port 9001

# probe state
vwb server-status

# graceful shutdown
vwb server-stop

# reopen the existing one (or auto-start if dead)
vwb server-open
```

The `--workspace <path>` flag is available on every verb (default: cwd) for
invoking from outside the workspace root. Prefer the workspace's own
`.venv/bin/vwb` so composites resolve from its site-packages.

## What "alive" means

A workbench is alive when all three hold:

1. `.pbg/server/server.pid` exists and the PID is running (`kill -0 $PID`), AND
2. `.pbg/server/server-info` exists, AND
3. `GET <url>/` returns 200.

If 1+2 hold but 3 doesn't, `vwb server-status` reports `stale` — the process may be
wedged on import or in a slow startup. Inspect `.pbg/server/server.log` (the tail
explains it). `vwb serve --detach` self-heals stale state by clearing dead files
and retrying.

## Resolving the workbench binary

Run `vwb` from the workspace's own environment:

1. `<workspace>/.venv/bin/vwb` — the canonical, preferred path. Composites resolve
   from the workspace's own site-packages.
2. **Parent git-worktree's `.venv/bin/vwb`** — used when the current workspace is a
   secondary git worktree (its `.git` is a file pointing at
   `<main>/.git/worktrees/<name>`) and the local `.venv` is missing/incomplete.
   Safe because worktrees share source; the workbench's per-request workspace
   routing + sys.path handling guarantees the **local** workspace's source wins
   for composite discovery. Avoids forcing a per-worktree `uv sync` (~5 min).

If neither resolves, install `vivarium-workbench` into the workspace `.venv`.
**Sibling-WORKSPACE venvs (different repos) are still off-limits** — those would
silently load the wrong composites (mem3dg-readdy friction #13).

## Investigation auto-pick (one-branch-per-investigation convention)

The SPA auto-picks the alphabetically-first investigation when the current branch
doesn't match `investigation/<slug>`. To land on a specific one, pass
`--investigation <slug>` to `vwb serve --detach --open` or `vwb server-open` — the
browser opens the dashboard directly at that investigation's route
(`/investigations/<slug>`). When no slug is given, the SPA falls back to
alphabetical. (To infer the slug from the current git branch — exact `branch ==
slug`, then an `investigation/<slug>` prefix, then token-overlap scoring like
`feat/dnaa-biology` → `dnaa-replication` — resolve it in the skill first, then
pass it explicitly.)

## Safety

- Never modifies `workspace.yaml`, study yamls, or persistent state — read-mostly.
- Binds to `127.0.0.1` only; never exposed externally.
- `vwb server-stop` only kills the PID in `.pbg/server/server.pid`. Won't touch
  other processes.
- `vwb serve` registers in `~/.pbg/servers/*.json` so the cross-worktree switcher can find it; parallel worktrees each get their own port/state dir.

## Compatibility with parallel worktrees

Each worktree gets its own `.pbg/server/` state dir → its own port → its own
server. Running `/viva-workbench start` from two worktrees concurrently is
intentional and supported; the workspace switcher finds the others (and lets you
open each in a new tab). With session-per-tab you can also open several worktrees'
workspaces as tabs off a single running workbench.

## When stage skills invoke this

Stage skills should NOT auto-start the workbench — it's user-facing UI, not part of
any stage's lifecycle. Invoke `/viva-workbench` only when the user wants to look at
results, drive runs, or download reports.
