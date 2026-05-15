# Workspace switcher v2 — design

Date: 2026-05-15
Status: design (pre-implementation)
Affects: `vivarium-dashboard` (UI + one new API endpoint), `pbg-superpowers` (no code changes; this spec lives here for continuity with v1)

Supersedes: parts of [`2026-05-15-workspace-switcher-design.md`](2026-05-15-workspace-switcher-design.md) §4 (UI). v1's backend (registry files, GET/POST add/forget/cleanup-stale/start) is unchanged.

## 1. Problem

The v1 switcher ships a dropdown panel anchored inside the 240px left rail. Because `.viv-rail` is `overflow:hidden`, the absolutely-positioned panel gets clipped — long workspace paths force horizontal scrolling, which is awkward and obscures information. Two additional UX gaps surfaced during use:

- No way to stop a running workspace's dashboard from the UI. The v1 spec excluded this deliberately ("don't let dashboards kill siblings"); in practice the alternative is dropping to a terminal to send SIGTERM, which is heavier friction than the protection is worth.
- Forget / Clean-up / Add affordances are visible but cramped because the rail constrains everything to ~216px usable width.

## 2. Goals & non-goals

**Goals**

- Replace the dropdown panel with a centered modal that has room for path + name + action buttons on every row, with no horizontal scrolling.
- Make the primary action (switch / start / clean-up / forget) a single click anywhere on the row, with secondary actions on a per-row button on the right.
- Add a `Stop` action for running non-current workspaces, backed by a new `POST /api/workspaces/stop` endpoint.

**Non-goals**

- Force-stop (SIGKILL) from the UI.
- Stop-self (stopping the dashboard you're currently looking at).
- Confirm dialogs / undo before destructive actions (Stop, Forget).
- "Create new workspace" scaffolding from the UI. Stays as `/pbg-workspace <name>` in Claude Code; user runs it in the terminal, then the new workspace appears in the catalog automatically (Task 2 from v1 already wired this).
- Renaming a workspace, editing its package, or any other catalog mutation beyond add/forget.
- Changes to the v1 backend other than the new `/stop` endpoint.

## 3. UI

### 3.1 Trigger

The trigger button in the left rail does not change. It still displays:

```
[● <workspace-name>  ▾]
```

The only behavioral change is what happens on click: instead of expanding a dropdown panel below the trigger, the click opens a centered modal overlay (see 3.2).

### 3.2 Modal shell

- Click trigger → fade in a full-viewport dim overlay (`rgba(0,0,0,0.32)`) + a centered modal card.
- Card: 720px wide (clamped to `min(720px, 90vw)`), `max-height: 80vh`, centered both axes via flex.
- Card header: `<h2>Workspaces</h2>` on the left, a `✕` close button on the right.
- Card body: scrollable `<ul>` of rows (see 3.3).
- Card footer: a single link-style button `+ Add existing workspace…` that opens the same add prompt v1 has.
- Close triggers: Esc key, click on overlay (outside the card), click on the `✕` button. Re-opening always refetches `/api/workspaces`.

### 3.3 Row layout (two lines)

Each row spans the full card width as two stacked lines:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ●  v2ecoli  (this)                                                  │
│    /Users/eranagmon/code/v2ecoli-workspace                          │
├─────────────────────────────────────────────────────────────────────┤
│ ●  biomodels                                            [ Stop ■ ]  │
│    /Users/eranagmon/code/pbg-biomodels                              │
├─────────────────────────────────────────────────────────────────────┤
│ ○  test-workspace                                       [ Forget ]  │
│    /Users/eranagmon/code/test-workspace                             │
├─────────────────────────────────────────────────────────────────────┤
│ ⚠  zombie-ws                                          [ Clean up ]  │
│    /Users/eranagmon/code/zombie-ws                                  │
├─────────────────────────────────────────────────────────────────────┤
│ ⊘  missing-thing                                      [ Forget × ]  │
│    /old/path/that/is/gone                                           │
└─────────────────────────────────────────────────────────────────────┘
```

**Structure of one row:**
- Outer `<li>` with `display: flex; flex-direction: column;` and a horizontal "first line" container.
- First line: `<span class="viv-ws-glyph">●/○/⚠/⊘</span>` + `<span class="viv-ws-name">name</span>` (left-aligned, `flex: 1`) + optional `<button class="viv-ws-action">` (right-aligned).
- Second line: `<div class="viv-ws-path">/absolute/path</div>` — full width, muted gray, slightly smaller. CSS `word-break: break-all;` so long paths wrap rather than scroll.

### 3.4 Interactions

**Primary action = click anywhere on the row except the button.** Status-dependent:

| Status   | Primary action                                                |
|----------|---------------------------------------------------------------|
| current  | no-op (cursor stays default, no hover affordance)             |
| running  | navigate same tab to `row.url`                                |
| stopped  | POST `/api/workspaces/start`, then navigate to returned URL   |
| stale    | POST `/api/workspaces/cleanup-stale`, then re-render          |
| missing  | POST `/api/workspaces/forget`, then re-render                 |

**Secondary action = the per-row right-side button.** One button per row, status-specific:

| Status   | Button label   | Color      | What it does                                          |
|----------|----------------|------------|-------------------------------------------------------|
| current  | _(none)_       |            |                                                       |
| running  | `Stop ■`       | red text   | POST `/api/workspaces/stop`, then re-render           |
| stopped  | `Forget`       | subtle     | POST `/api/workspaces/forget`, then re-render         |
| stale    | `Clean up`     | amber text | POST `/api/workspaces/cleanup-stale`, then re-render  |
| missing  | `Forget ×`     | subtle     | POST `/api/workspaces/forget`, then re-render         |

Note that the stale and missing rows have the same primary action and secondary action (the button just makes the affordance explicit when the user's mouse is over the button rather than the row body).

**Hover and pointer state:**
- Non-current rows: `cursor: pointer`, hover sets row background to `#f6f8fa`.
- Current row: `cursor: default`, no hover effect.
- Buttons stop event propagation so clicking them does not trigger the row's primary action.

**Keyboard accessibility:**
- Tab focuses rows in display order; Enter activates the row's primary action.
- Tab then focuses the row's button (if present); Enter activates the button.
- Esc closes the modal.

### 3.5 Action-in-flight state

When any per-row action POST is in flight (Start, Stop, Forget, Clean up), the row's button is disabled and its label changes to a present-progressive form (`Starting…`, `Stopping…`, `Forgetting…`, `Cleaning…`). The rest of the modal stays interactive.

### 3.6 Error display

If an action POST returns 4xx/5xx, the row inline-shows the error as a small red line below the path (still inside the same `<li>`). The button re-enables so the user can retry. There is no toast / global error surface — this matches v1's per-row error pattern (`viv-ws-error` class).

## 4. New API endpoint: `POST /api/workspaces/stop`

Request body:

```json
{ "path": "/Users/eranagmon/code/biomodels" }
```

Server-side logic:

1. **Validation.** If `path` missing / not a string / not absolute → 400 `{ "error": "path must be an absolute string" }`.
2. **Catalog membership.** Resolve `path` and confirm it appears in the catalog. If not → 400 `{ "error": "workspace not in catalog" }`. (Mirrors the safety guard on `/start`. The dashboard should not be a generic "send signal to PID" surface.)
3. **Refuse self-stop.** If the resolved `path` equals the dashboard's own bound workspace path (`WORKSPACE` in `server.py`) → 400 `{ "error": "refusing to stop self — use the terminal: kill <pid>" }`. Stopping yourself would kill the dashboard the user is using.
4. **Look up the running entry.** Call `workspace_catalog.find_running(path)`. If `None` (no entry, or PID dead) → 400 `{ "error": "not running" }`.
5. **Send SIGTERM.** `os.kill(entry["pid"], signal.SIGTERM)`. Wrap in `try/except ProcessLookupError`; if the process already died between the look-up and the kill, treat as success.
6. **Poll for cleanup.** Poll `workspace_catalog.find_entry(path)` every 100 ms for up to 3 s, waiting for the entry file to disappear (the child's `_unregister` hook removes it on SIGTERM). When gone → 200 `{ "ok": true }`.
7. **Timeout.** If the entry is still present after 3 s → 504 `{ "error": "stop_timeout", "hint": "PID <n> still alive; SIGKILL it manually if stuck" }`. The dashboard does NOT escalate to SIGKILL itself.

**Why SIGTERM and not SIGKILL:** SIGTERM lets the child's atexit / signal handler run, which removes both the global `~/.pbg/servers/<name>.json` and the workspace-local `server.pid`. SIGKILL bypasses all cleanup and leaves both files, which the user would then have to clean up via `cleanup-stale`. The 3-second budget is generous: the cleanup hook is sub-second in normal operation.

**Why no SIGKILL fallback:** force-killing a process is a deliberate decision, not an automatic one. If a dashboard is wedged enough to ignore SIGTERM, the user should know about it and choose the recovery path (kill -9, debug, restart). The 504 response gives them the PID; the terminal is one shell command away.

## 5. Frontend implementation outline

A rewrite of `vivarium_dashboard/static/workspace-switcher.js` (the v1 file). Same external contract: reads element IDs `viv-workspace-switcher-trigger` (the existing rail button) and creates the modal DOM on first open (lazy mount, not in the template).

```
init():
  trigger = #viv-workspace-switcher-trigger
  trigger.addEventListener('click', openModal)
  // No modal in the DOM until openModal() runs

openModal():
  ensureModalMounted()         // idempotent
  fetchAndRender()             // GET /api/workspaces
  document.addEventListener('keydown', escHandler)
  modal.classList.add('open')  // CSS controls visibility + opacity transition

closeModal():
  modal.classList.remove('open')
  document.removeEventListener('keydown', escHandler)

renderRows(payload):
  body.innerHTML = ''
  for each row in payload.workspaces:
    body.appendChild(renderRow(row, payload.current.path))

renderRow(row, currentPath):
  li = <li>
  line1 = <div class="viv-ws-line1">
    <span class="viv-ws-glyph">{glyph}</span>
    <span class="viv-ws-name">{escape(name)} {is current ? "(this)" : ""}</span>
    {button by status}
  line2 = <div class="viv-ws-path">{escape(path)}</div>
  li.append(line1, line2)
  li.addEventListener('click', e => if (!e.target.closest('button')) doPrimary(row))
  return li

doPrimary(row): // status-dispatched: start / cleanup / forget / navigate / nop
doSecondary(row, kind): // stop / forget / cleanup / forget
```

The modal DOM is built once and reused; on each open we just refetch and re-render the body. CSS uses `opacity` + `pointer-events` for transitions; no JS animation library.

Old CSS classes (`.viv-workspace-switcher-panel`, `.viv-workspace-switcher-list`, etc.) are removed — they only existed for the dropdown shape. New classes are `.viv-ws-modal`, `.viv-ws-modal-card`, `.viv-ws-row`, `.viv-ws-line1`, `.viv-ws-name`, `.viv-ws-path`, `.viv-ws-action`, `.viv-ws-glyph`, plus the existing color classes `.viv-glyph-running/stopped/stale/missing`.

In `index.html.j2`, the trigger `<button id="viv-workspace-switcher-trigger">` stays exactly as v1 built it. The inner `<div id="viv-workspace-switcher-panel" hidden>` (the v1 dropdown panel with header / `<ul>` / footer) is removed — the modal now mounts lazily from JS into `document.body` on first open.

## 6. Edge cases

| Case | Behavior |
|---|---|
| User clicks Stop on the only running non-current workspace, then clicks its row to switch | The row is gone by the time they read; click hits empty space. No crash. (Hover state hints "this row is being stopped"; not an MVP feature, just don't bind the row's primary handler while the action is in flight.) |
| User clicks Stop, then closes the modal before the request returns | Request still completes in the background. Next open of the modal re-fetches and shows the result. |
| Two browser tabs open the modal, one clicks Stop, the other still shows the row as running | Until the second tab re-opens the modal (or refreshes), it will show a stale row. Clicking the row will hit the same idempotency logic on `/start` (returns the existing url if the entry is already gone — actually `find_running` will return None at that point and it'll try to start again). Edge case; acceptable. |
| Self-stop attempt | 400 with terminal instruction. The button for the current row is hidden anyway, but the API surface is still hardened. |
| SIGTERM ignored by the child | 504 after 3 s with the PID in the error message. User must kill -9 manually. |
| Modal open during a long Start that times out (8 s upstream) | The Start button stays in "Starting…" until the 8 s upstream timeout returns 504, then the row shows the error and re-enables the button. Already v1 behavior. |
| Workspace path on disk has changed (e.g. user moved the directory) between modal open and Stop click | `find_running` returns None (the catalog `path` no longer matches anything live) → 400 "not running". Modal re-renders and shows the row as missing or stopped on next open. |

## 7. Testing

**Backend (vivarium-dashboard `tests/test_workspaces_api.py`):**
- `test_post_workspaces_stop_happy_path` — register a real subprocess as a running entry (`subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`), POST stop, assert 200, assert the entry file is gone within 3 s. Clean up the child in a `finally`.
- `test_post_workspaces_stop_refuses_self` — POST stop with `path` set to the dashboard's own workspace → 400 + the "refusing to stop self" error message.
- `test_post_workspaces_stop_refuses_not_running` — register a stale entry (dead PID), POST stop → 400 + "not running".
- `test_post_workspaces_stop_refuses_uncatalogued` — POST stop with a real workspace dir that isn't in the catalog → 400 + "not in catalog".
- `test_post_workspaces_stop_timeout` — register an entry whose PID belongs to a subprocess that ignores SIGTERM (`signal.signal(signal.SIGTERM, signal.SIG_IGN)` then `sleep(30)`), POST stop → 504 + entry still present.

**Frontend:** manual smoke test (same as v1 — no JS test runner in the dashboard repo).

## 8. Implementation order (preview for writing-plans)

Each step is one commit on `feat/workspace-switcher-v2`.

1. `POST /api/workspaces/stop` endpoint + 5 tests.
2. Rewrite `vivarium_dashboard/static/workspace-switcher.js` for the modal shape.
3. Replace the v1 dropdown CSS + `<div>` placeholder in `index.html.j2` with the v2 trigger + modal-mount.
4. Manual end-to-end run across two real workspaces.

The branch can be merged directly into the still-open PR for v1 (since v1 hasn't landed yet), or stacked on `feat/workspace-switcher` if v1 is already merged. Decision depends on PR review timing.
