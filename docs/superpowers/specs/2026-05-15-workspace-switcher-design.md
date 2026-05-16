# Workspace switcher — design

Date: 2026-05-15
Status: design (pre-implementation)
Affects: `vivarium-dashboard` (UI + server), `pbg-superpowers` (skills, `server/start-server.sh`, new helper module)

## 1. Problem

The Vivarium dashboard's left rail has a placeholder workspace switcher
(`vivarium-dashboard/vivarium_dashboard/templates/index.html.j2:121-123`) — a
non-interactive `<div>` with a tooltip "Other workspaces coming soon". The user
operates several workspaces concurrently (each its own `workspace.yaml` +
package, with its own dashboard server on its own port) and wants to switch
between them from the menu instead of by `cd`'ing and restarting servers.

Today there is no global record of which workspaces exist or which are running.
Each workspace's `start-server.sh` writes only workspace-local state under
`<workspace>/.pbg/server/`. Nothing in `~/.pbg/` is consulted.

## 2. Goals & non-goals

**Goals**

- One dropdown in the dashboard listing all known workspaces, with a clear
  indicator of which are currently running.
- Clicking a *running* workspace navigates the current tab to its dashboard.
- Clicking a *stopped* workspace shows a Start button that boots its dashboard
  in the background and redirects when it's healthy.
- Workspaces auto-register into the catalog when they are scaffolded
  (`/pbg-workspace`) and when their dashboard first starts (`/pbg-server start`).
- "Add existing workspace" and per-row "Forget" actions cover catalog
  management.

**Non-goals**

- Remote workspaces / SSH.
- A "Stop dashboard" button in the dropdown (`/pbg-server stop` in a terminal
  remains the way to stop a server).
- A first-class "Open in new tab" action (right-click works).
- Workspace renaming.
- Migrating existing workspaces into the catalog on first dashboard load
  (the next `/pbg-server start` will register them).
- Windows support (consistent with the rest of the plugin).

## 3. Architecture

Two new files under `~/.pbg/` form the registry:

```
~/.pbg/
├── workspaces.json              # the catalog (all known workspaces)
└── servers/
    ├── v2ecoli-workspace.json   # one per running dashboard server
    └── pbg-biomodels.a1b2c3.json  # hash-suffixed on name collision
```

**Single-writer per concern:**

- The **catalog** (`workspaces.json`) is written by `/pbg-workspace` (on
  scaffold) and `/pbg-server start` (on boot). Both go through
  `pbg_superpowers.workspace_catalog.add(...)` which takes a `flock` on the
  file before read-modify-write.
- The **running registry** (`servers/<name>.json`) is written by
  `start-server.sh` on boot and removed by the `/pbg-server stop` flow. Each
  server owns its own file → no inter-process locking needed.

**Render-time join (no fan-out):** the dashboard backend reads
`workspaces.json` and the contents of `~/.pbg/servers/`. For each catalog
entry it looks up a matching server entry by `path`; aliveness is a cheap
`kill -0 <pid>` (no HTTP probes). This keeps `/api/workspaces` O(reads of two
small directories) instead of fanning out into every workspace tree.

### 3.1 Catalog schema (`~/.pbg/workspaces.json`)

```json
{
  "version": 1,
  "workspaces": [
    {
      "name": "v2ecoli-workspace",
      "path": "/Users/eranagmon/code/v2ecoli-workspace",
      "package": "pbg_v2ecoli",
      "added_at": "2026-05-15T10:32:11Z"
    }
  ]
}
```

- Deduped by absolute `path`.
- `version` is forward-compat for future schema changes.
- `name` is informational (used as the dropdown label); `path` is the key.
- `package` is captured opportunistically from `workspace.yaml` at registration
  time; not required for the switcher to work.

### 3.2 Running-server schema (`~/.pbg/servers/<name>[.<hash>].json`)

```json
{
  "name": "v2ecoli-workspace",
  "path": "/Users/eranagmon/code/v2ecoli-workspace",
  "pid": 47192,
  "port": 8731,
  "url": "http://127.0.0.1:8731",
  "started_at": "2026-05-15T11:04:02Z"
}
```

- Filename keyed on workspace name.
- On name collision (two distinct paths sharing a name), append the first 6
  hex chars of `sha1(path)`: e.g. `pbg-biomodels.a1b2c3.json`.

## 4. UI

The placeholder div at `index.html.j2:121-123` becomes the interactive trigger.

**Closed (trigger):**

```
┌──────────────────────────────────────┐
│ ● v2ecoli-workspace            ▾    │
└──────────────────────────────────────┘
```

The status glyph reflects the current workspace's own status (always `●`
running, since the dashboard is by definition up).

**Open (panel, dismissed on outside-click / Esc):**

```
┌─ Workspaces ─────────────────────────┐
│ ● v2ecoli-workspace            (this)│
│   /Users/eranagmon/code/v2ecoli-…    │
├──────────────────────────────────────┤
│ ● pbg-biomodels                      │  → navigates same tab to its URL
│   /Users/eranagmon/code/pbg-biomod…  │
├──────────────────────────────────────┤
│ ○ chromosome-rep1     [Start ▸]      │
│   /Users/eranagmon/code/chromoso…    │
├──────────────────────────────────────┤
│ ⚠ test-workspace      [Clean up]     │
│   /Users/eranagmon/code/test-work…   │
├──────────────────────────────────────┤
│ ⊘ missing-thing       [Forget ×]     │
│   /old/path/that/is/gone             │
├──────────────────────────────────────┤
│ + Add existing workspace…            │
└──────────────────────────────────────┘
```

**Glyphs:** `●` running · `○` stopped · `⚠` stale · `⊘` missing path.

**Row behavior:**

- *Current workspace* — pinned at top, marked `(this)`, no click action.
- *Running* — whole row is `<a href="<url>">`; same-tab navigation.
- *Stopped* — `[Start ▸]` button. Clicking POSTs `/api/workspaces/start`; the
  button shows a spinner labeled "Starting…"; on success the page navigates to
  the new URL. On failure, inline error in the row.
- *Stale* — `[Clean up]` button POSTs `/api/workspaces/cleanup-stale`,
  which removes `~/.pbg/servers/<name>*.json` plus orphan
  `<path>/.pbg/server/server-info` and `server.pid`.
- *Missing* — `[Forget ×]` button POSTs `/api/workspaces/forget` (removes
  catalog entry only; nothing on disk is touched in the workspace tree).
- Right-click on any row → "Forget" and "Open in new tab".

**Sort order:** current first, then running (alphabetical by name), then
stopped (alphabetical), then stale/missing.

**Empty state:** if `workspaces.json` is missing or only contains the current
workspace, the panel shows the current row plus "Add existing workspace…".

**Refresh:** the panel fetches `/api/workspaces` each time it opens — no
polling, no websockets. After a successful Start, navigation handles the
implicit refresh.

**Add existing workspace modal:** single text input "Path to workspace
directory" + Cancel/Add. The backend validates `<path>/workspace.yaml` exists
and the path is absolute. Local-only server → text input is enough; no native
file picker.

## 5. API

All endpoints live on the dashboard server. All accept/return JSON. All
read/write only under `~/.pbg/` (and the orphan files explicitly named below).

### 5.1 `GET /api/workspaces`

Response:

```json
{
  "current": {
    "name": "v2ecoli-workspace",
    "path": "/Users/eranagmon/code/v2ecoli-workspace"
  },
  "workspaces": [
    { "name": "v2ecoli-workspace", "path": "/…/v2ecoli-workspace",
      "status": "current", "url": "http://127.0.0.1:8730", "pid": 47100 },
    { "name": "pbg-biomodels",     "path": "/…/pbg-biomodels",
      "status": "running", "url": "http://127.0.0.1:8731", "pid": 47192 },
    { "name": "chromosome-rep1",   "path": "/…/chromosome-rep1",
      "status": "stopped" },
    { "name": "test-workspace",    "path": "/…/test-workspace",
      "status": "stale", "pid": 41001 },
    { "name": "missing-thing",     "path": "/old/path/that/is/gone",
      "status": "missing" }
  ]
}
```

Server-side logic:

1. Load `~/.pbg/workspaces.json` (return empty list + current-only if absent
   or corrupt; log a warning).
2. For each entry: if `path` doesn't exist on disk → `missing`. Else look up
   `~/.pbg/servers/<name>*.json` matching by `path`. If found AND `kill -0 pid`
   succeeds → `running` (or `current` if `path` matches the dashboard's own
   workspace). If found but PID dead → `stale`. If no file → `stopped`.

### 5.2 `POST /api/workspaces/start`

Request: `{ "path": "/Users/eranagmon/code/chromosome-rep1" }`

Behavior:

1. Validate `path` is absolute, exists, contains `workspace.yaml`, and matches
   an entry in the catalog. (Refuse arbitrary paths so the dashboard cannot
   be tricked into launching processes against non-workspaces.)
2. If `~/.pbg/servers/` already has a live entry for this path (file present
   AND `kill -0 pid` succeeds) → return its URL immediately (idempotent).
3. Spawn `vivarium-dashboard serve --workspace <path>` detached
   (`start_new_session=True`, `stdout/stderr` → `<path>/.pbg/server/start.log`,
   `stdin=DEVNULL`, `close_fds=True`, `cwd=path`). Do not wait on the child.
   Use `sys.executable -m vivarium_dashboard.cli serve --workspace <path>` so
   the child inherits the same Python environment as the parent dashboard.
4. Poll `~/.pbg/servers/` every 100 ms, up to 8 s, for a new entry matching
   `path`. When it appears + PID alive → return `{ "url": "...", "pid": ... }`.
5. On timeout: return 504 with `{ "error": "start_timeout", "log_path": "…",
   "hint": "tail …" }`. The UI keeps the row in "Starting…" with a
   "View log" link.

Why 8 s: typical cold-start writes the server entry in 1–2 s. Cold uv installs
push past 8 s; those cases get the structured timeout response.

### 5.3 `POST /api/workspaces/add`

Request: `{ "path": "/Users/eranagmon/code/some-existing-workspace" }`

Behavior:

1. Validate absolute path + `<path>/workspace.yaml` exists + readable.
2. Parse `workspace.yaml` for `name` and `package`. Reject if `name` missing.
3. If catalog already has this `path` → return the existing entry
   (idempotent).
4. Append to `workspaces.json` under `flock`.
5. Return the new entry.

### 5.4 `POST /api/workspaces/forget`

Request: `{ "path": "/Users/eranagmon/code/old-thing" }`

Behavior: remove matching catalog entry under `flock`. If the workspace is
currently `running`, refuse with 409 (`"stop the server before forgetting"`).
Does NOT touch any file inside the workspace tree.

### 5.5 `POST /api/workspaces/cleanup-stale`

Request: `{ "path": "/Users/eranagmon/code/test-workspace" }`

Behavior: re-verify the PID in `~/.pbg/servers/<name>*.json` is dead
(`kill -0` fails). If so, delete that file plus orphaned
`<path>/.pbg/server/server-info` and `<path>/.pbg/server/server.pid`. If the
PID is alive after all → 409 (`"server is still running"`).

### 5.6 Safety constraints (all endpoints)

- Reject any path that is not absolute, not on the local filesystem, or
  contains a URL scheme.
- `start` only accepts paths present in the catalog — prevents the dashboard
  from being used to launch arbitrary processes.
- `forget` / `cleanup-stale` never delete files inside the workspace tree
  beyond the explicitly named `.pbg/server/server-info` and `server.pid`.

## 6. Start-dashboard subprocess flow

The current dashboard server has to spawn another dashboard server, then
redirect the browser once it's healthy.

```python
# Inside POST /api/workspaces/start
log_path = Path(target_path) / ".pbg" / "server" / "start.log"
log_path.parent.mkdir(parents=True, exist_ok=True)

with log_path.open("ab") as logf:
    subprocess.Popen(
        [sys.executable, "-m", "vivarium_dashboard.cli",
         "serve", "--workspace", target_path],
        stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        cwd=target_path,
    )

deadline = time.monotonic() + 8.0
target = Path(target_path).resolve()
while time.monotonic() < deadline:
    entry = _find_running_entry_by_path(target)
    if entry and _pid_alive(entry["pid"]):
        return 200, {"url": entry["url"], "pid": entry["pid"]}
    time.sleep(0.1)
return 504, {"error": "start_timeout", "log_path": str(log_path),
             "hint": f"tail {log_path}"}
```

**Why `start_new_session=True`:** the child must survive its parent. If the
dashboard that spawned this child is later stopped, the child keeps running.

**Polling source of truth:** `~/.pbg/servers/<name>*.json`, not the
workspace-local `.pbg/server/server-info`. `start-server.sh` writes both; the
global file is the canonical signal for this flow.

**No SSE / WebSocket:** an 8 s blocking HTTP request is fine for this rare
action. Avoids introducing a new transport pattern.

**Concurrency:** two browser tabs clicking Start on the same workspace within
the 8 s window both find the same fresh entry on poll and return the same
URL. A second `start-server.sh` invocation notices the existing alive PID and
exits early (the existing "alive" check from the `pbg-server` skill).

**Crash path:** if the spawned child dies before writing
`~/.pbg/servers/<name>*.json`, the poll just times out — no orphan global
entry, workspace stays `stopped` in the dropdown. The user sees the timeout
with the log path and can rerun.

## 7. Skill changes

### 7.1 `pbg_superpowers/workspace_catalog.py` (new module)

The only writer surface to the registry. Functions:

- `add(path, name=None, package=None)` — append-or-noop with `flock` on
  `~/.pbg/workspaces.json`. Parses `workspace.yaml` if `name`/`package` are
  omitted.
- `list()` — return parsed catalog. Falls back to `[]` on corrupt/missing.
- `forget(path)` — remove catalog entry under `flock`.
- `register_server(name, path, pid, port, url)` — write
  `~/.pbg/servers/<name>[.<hash>].json`.
- `unregister_server(path)` — delete the matching server file.
- `find_running(path)` — scan `~/.pbg/servers/`, return entry if PID alive.
- `find_running_entry_by_path(path)` — same, used by the start poll.

The module honors a `PBG_HOME` env override (defaulting to `~/.pbg/`) so the
test suite can isolate state.

All path comparisons resolve symlinks and normalize via `Path.resolve()`
before comparing, so two catalog/server entries that reference the same
workspace via different symlink paths are treated as one.

The module is also a CLI: `python -m pbg_superpowers.workspace_catalog
<subcommand> [flags]`, with subcommands `add`, `forget`, `list`,
`register-server`, `unregister-server`. The skill shims and shell scripts
invoke these subcommands; the Python API is what the dashboard backend uses
directly.

### 7.2 `/pbg-workspace` shim

At the end of step 4 of its lifecycle, after the bootstrap commit:

```bash
python -m pbg_superpowers.workspace_catalog add \
  --path "$TARGET" --name "$NAME" --package "$PKG"
```

Idempotent.

### 7.3 `/pbg-server start` shim

At the top of the boot path, before launching the server, call the same
helper against the auto-detected workspace root. Picks up workspaces that
pre-date this feature or were created outside `/pbg-workspace`.

### 7.4 `vivarium-dashboard/vivarium_dashboard/cli.py:cmd_serve`

The dashboard's `cmd_serve` is the canonical launcher (not pbg-superpowers'
`start-server.sh`, which serves a separate report-mirror role and is left
alone by this feature). `cmd_serve` already writes
`<workspace>/.pbg/server/server-info`; this feature extends it to also:

1. Write `<workspace>/.pbg/server/server.pid` (containing `os.getpid()`) on
   boot. The dashboard CLI currently runs in the foreground and has no PID
   file; we add one because the Start-from-stopped flow detaches the child
   and the parent process needs a stable handle to it.
2. Register a global running entry by calling
   `pbg_superpowers.workspace_catalog.register_server(...)` with the
   workspace name (parsed from `workspace.yaml`), absolute path, current
   PID, port, and URL.
3. Install a `signal` handler (SIGTERM, SIGINT) and an `atexit` hook that
   calls `unregister_server(path)` and removes the local `server.pid` on
   exit.

The detached-child case (spawned by `/api/workspaces/start`) and the
foreground case (user runs `vivarium-dashboard serve` directly) use the
same code path — the only difference is who is sending the eventual
SIGTERM.

## 8. Edge cases

| Case | Behavior |
|---|---|
| Two workspaces share a `name` | `~/.pbg/servers/<name>.<hash6>.json` disambiguates on disk; UI shows path on hover. |
| Workspace deleted from disk | Status `missing`; only action is `Forget`. |
| Server crash leaves global entry | Status `stale`; `Clean up` removes the global entry + orphan workspace-local server-info/pid. |
| User cleans up while server alive | `cleanup-stale` re-checks `kill -0`; 409 if PID alive. |
| Corrupt `workspaces.json` | `/api/workspaces` falls back to current-only and logs a warning. Dashboard never hard-fails. |
| Concurrent catalog writers | `flock` on `workspaces.json` during read-modify-write. Per-server files are single-writer → no locking. |
| Forget current workspace | 409 — refuse. |
| Browser navigates away mid-Start | Child server keeps coming up; visible in dropdown next time. |
| Spawned child dies pre-registration | Poll times out (504); no orphan global entry. |
| Cross-platform | Linux + macOS. Windows is out of scope. |

## 9. Error responses (user-visible)

| Code | Where surfaced | Message |
|---|---|---|
| `start_timeout` | Stopped row | "Couldn't confirm the server started in 8 s — View log." (link to `start.log`) |
| `validation_failed` | Add modal | "Not a workspace (no `workspace.yaml`)." |
| `pid_alive` | Stale row | "Server is still running — use `/pbg-server stop`." |
| `running` | Missing/normal row | "Stop the server before forgetting." |

## 10. Testing

`pbg_superpowers/workspace_catalog.py` is the only new Python module; covered
by `pytest` in `tests/`:

- Catalog round-trip (add/list/forget).
- Dedup-by-path.
- Name-collision hash suffix.
- `flock` under concurrent writers (spawn N threads, all append, expect
  exactly N entries).
- `missing` / `stale` / `running` / `stopped` detection from synthetic
  state.

API endpoints: a fixture creates `~/.pbg/` under `tmp_path` via `PBG_HOME` so
tests never touch the real home dir.

- `GET /api/workspaces` — join logic against synthetic catalog + server
  entries covers each status.
- `POST /api/workspaces/start` happy path — fake `start-server.sh` writes a
  fresh server entry and exits; verify polling + 200 response.
- `POST /api/workspaces/start` timeout — fake `start-server.sh` that sleeps
  past 8 s; verify 504 + `log_path`.
- `POST /api/workspaces/add` — accept valid `workspace.yaml`, reject missing.
- `POST /api/workspaces/forget` — accept stopped, reject running.
- `POST /api/workspaces/cleanup-stale` — accept dead PID, reject live PID.

Frontend: covered by manual verification — render the dropdown against a
curated mock response and visually check that the right glyph, buttons, and
links appear per row. If the dashboard repo gains a JS test runner later, a
DOM-level test of the panel renderer is a natural follow-up. No
headless-browser test for the navigation itself is planned.

## 11. Implementation order (preview for writing-plans)

1. `pbg_superpowers/workspace_catalog.py` + unit tests (pbg-superpowers repo).
2. `vivarium-dashboard/vivarium_dashboard/cli.py:cmd_serve` — write
   `server.pid`, register on boot, unregister on exit + tests.
3. `GET /api/workspaces` endpoint + tests (vivarium-dashboard).
4. `POST /api/workspaces/add` + tests.
5. `POST /api/workspaces/forget` + tests.
6. `POST /api/workspaces/cleanup-stale` + tests.
7. `POST /api/workspaces/start` + tests.
8. `index.html.j2` dropdown markup, CSS, JS panel.
9. `/pbg-workspace` registration shim (pbg-superpowers repo).
10. `/pbg-server` SKILL.md update — the skill's description currently mentions
    that `start` writes `.pbg/server/server.pid`, but with the dashboard CLI
    now writing the PID file itself, the skill text needs to be updated.
    (No code change in pbg-superpowers' `start-server.sh`.)
11. Manual end-to-end run across two real workspaces.

Each step is its own commit so the diff stays cohesive. Steps 1, 9, 10 live
in the `pbg-superpowers` repo; steps 2–8 live in the `vivarium-dashboard`
repo.
