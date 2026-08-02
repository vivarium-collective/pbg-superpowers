---
name: viva-workbench
description: Start / stop / open the interactive vivarium-workbench server (the side-rail-tabbed UI — Workspace, Registry, Composites, Investigations, Visualizations, GitHub Branches, Simulations DB) and use its session-per-tab model — one workspace per browser tab, opened from the workspace switcher. This is the server every dashboard-touching skill depends on, and it also serves the study reports. Subcommands start, stop, status, open, restart. (Formerly /pbg-dashboard.)
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|open|restart [--port N] [--browser] [--investigation SLUG]
---

# pbg-workbench

Transversal skill (no stage). Manages the interactive **vivarium-workbench**
server: the UI you actually look at to drive a workspace — Investigations,
Studies, Simulations DB, Visualizations, Composites, GitHub Branches.

> **Renamed from `/pbg-dashboard`.** The product is the **workbench**
> (`vivarium-workbench` pip package); "dashboard" is the legacy name. The old
> `/pbg-dashboard` alias has been removed — use `/viva-workbench`.

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
**published read-only** flow: `viva_superpowers.publish_assets.emit(...)` writes
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

Wraps the `vivarium-workbench serve` CLI so the workbench runs detached, survives
terminal exits, has its state tracked at `<workspace>/.pbg/dashboard/`, and (with
`--browser`) opens in your browser. This launches the **default-workspace** server
for a workspace/worktree; session-per-tab multiplexing of *other* workspaces then
happens in the browser via the switcher (above).

State files (dir name kept as `dashboard/` for back-compat):

  `.pbg/dashboard/dashboard-info`  JSON: `{port, host, url, pid, workspace, started_at, log_file}`
  `.pbg/dashboard/dashboard.pid`   text: PID of the running server
  `.pbg/dashboard/dashboard.log`   text: stdout/stderr of the server

## Subcommands

- **`/viva-workbench start`** — pick a free port (prefer 8765), launch
  `vivarium-workbench serve --workspace . --port <P>` detached, write
  info+pid+log, wait for the HTTP probe, and (with `--browser`) open the URL.
  Import crashes are surfaced via the log tail. If already alive, just opens the
  browser.
- **`/viva-workbench stop`** — read the PID file, SIGTERM, wait up to 5 s, escalate
  to SIGKILL if needed, clear state files.
- **`/viva-workbench status`** — `alive` / `stale` / `not-running`. Probes both the
  PID (`kill -0`) and the HTTP endpoint to distinguish a wedged process from a
  healthy one.
- **`/viva-workbench open [--investigation SLUG]`** — open the workbench URL in the
  browser. Auto-starts first if needed. With `--investigation SLUG` (or the slug
  inferred from the current branch), focus/open the tab AND switch the SPA to that
  investigation's detail via injected JS.
- **`/viva-workbench restart`** — `stop` then `start`. Useful after a code change in
  an editable `vivarium-workbench` install (Python reload isn't automatic).

Each subcommand prints a single JSON object describing the outcome.

## How to invoke

```bash
# default: prefers port 8765, leaves the browser alone (the URL is printed)
python -m viva_superpowers.workbench start

# open the browser too AND auto-pick the investigation matching this branch
python -m viva_superpowers.workbench start --browser

# force a specific investigation (implies --browser)
python -m viva_superpowers.workbench start --investigation dnaa-replication

# specific port (e.g. when 8765 is taken by another workspace)
python -m viva_superpowers.workbench start --port 9001

# probe state
python -m viva_superpowers.workbench status

# graceful shutdown
python -m viva_superpowers.workbench stop

# reopen the existing one (or auto-start if dead)
python -m viva_superpowers.workbench open
```

The `--workspace <path>` flag is also available (default: cwd) for invoking from
outside the workspace root. (`python -m viva_superpowers.dashboard …` remains a
working back-compat alias for the same CLI.)

## What "alive" means

A workbench is alive when all three hold:

1. `.pbg/dashboard/dashboard.pid` exists and the PID is running (`kill -0 $PID`), AND
2. `.pbg/dashboard/dashboard-info` exists, AND
3. `GET <url>/` returns 200.

If 1+2 hold but 3 doesn't, status reports `stale` — the process may be wedged on
import or in a slow startup. Inspect `.pbg/dashboard/dashboard.log` (the tail
explains it). `start` self-heals stale state by clearing dead files and retrying.

## Resolving the workbench binary

Order of resolution:

1. `<workspace>/.venv/bin/vivarium-workbench` — the canonical, preferred path.
   Composites resolve from the workspace's own site-packages.
2. **Parent git-worktree's `.venv/bin/vivarium-workbench`** — used when the current
   workspace is a secondary git worktree (its `.git` is a file pointing at
   `<main>/.git/worktrees/<name>`) and the local `.venv` is missing/incomplete.
   Safe because worktrees share source; the workbench's per-request workspace
   routing + sys.path handling guarantees the **local** workspace's source wins
   for composite discovery. Avoids forcing a per-worktree `uv sync` (~5 min).

If neither resolves, `start` raises and prints the install command.
**Sibling-WORKSPACE venvs (different repos) are still off-limits** — those would
silently load the wrong composites (mem3dg-readdy friction #13).

## Investigation auto-pick (one-branch-per-investigation convention)

The SPA auto-picks the alphabetically-first investigation when the current branch
doesn't match `investigation/<slug>`. This skill works around that by:

1. **Explicit `--investigation <slug>`** — wins. Implies `--browser`.
2. **Inferred from the current git branch** (when `--browser` is set/implied):
   exact `branch == slug`, then `investigation/<slug>` prefix, then token-overlap
   scoring (`feat/dnaa-biology` → `dnaa-replication`), then single-investigation
   workspace.
3. **Falls back to alphabetical** if nothing infers.

When a slug is provided/inferred, the skill calls `_openInvestigationDetail(slug)`
in the focused tab via AppleScript JS injection (Chrome + Safari families on
macOS), polling up to 8 s for the function to be defined.

## Safety

- Never modifies `workspace.yaml`, study yamls, or persistent state — read-mostly.
- Binds to `127.0.0.1` only; never exposed externally.
- `stop` only kills the PID in `.pbg/dashboard/dashboard.pid`. Won't touch other
  processes.
- Registers in `~/.pbg/servers/*.json` so the cross-worktree switcher can find it; parallel worktrees each get their own port/state dir.

## Compatibility with parallel worktrees

Each worktree gets its own `.pbg/dashboard/` state dir → its own port → its own
server. Running `/viva-workbench start` from two worktrees concurrently is
intentional and supported; the workspace switcher finds the others (and lets you
open each in a new tab). With session-per-tab you can also open several worktrees'
workspaces as tabs off a single running workbench.

## When stage skills invoke this

Stage skills should NOT auto-start the workbench — it's user-facing UI, not part of
any stage's lifecycle. Invoke `/viva-workbench` only when the user wants to look at
results, drive runs, or download reports.
