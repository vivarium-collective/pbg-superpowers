# Workspace Switcher v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 dropdown panel (which gets clipped by the 240px rail's `overflow: hidden`) with a centered modal overlay; add `POST /api/workspaces/stop` so running workspaces can be stopped from the UI.

**Architecture:** The v1 trigger button stays. Click → JS lazily mounts a modal into `document.body` (escapes the rail's clipping). The modal has 720px width, two-line rows (path on its own line, no horizontal scroll). The whole row is clickable for the status-default action; per-row right-aligned button for the secondary action (Stop on running non-current rows). New endpoint sends SIGTERM and polls for the child's atexit hook to remove its registry entry.

**Tech Stack:** Python 3.10+ (stdlib `signal`, `subprocess`, `os`), pytest, vanilla JS, plain CSS.

**Spec:** `docs/superpowers/specs/2026-05-15-workspace-switcher-v2.md`

**Repo:** All changes in `/Users/eranagmon/code/vivarium-dashboard` on branch `feat/workspace-switcher` (stacking on top of v1, which has not yet merged). No changes to `pbg-superpowers`.

---

## Task 1: `POST /api/workspaces/stop` endpoint

**Files:**
- Modify: `vivarium_dashboard/server.py` — add to `_POST_ROUTE_MAP` + handler method on `Handler`
- Modify: `tests/test_workspaces_api.py` — append 5 new tests

### Context for the implementer

- The route map at `server.py:232-236` already has entries for `/api/workspaces/{add,forget,cleanup-stale,start}` (added by v1's Task 6). You're adding one more: `/api/workspaces/stop`.
- The handler signature in this codebase is `def _post_workspaces_<name>(self, body: dict)`. The dispatching `do_POST` parses the JSON body and passes it. JSON response goes through `self._json(data, code)`.
- `WORKSPACE` is a module-level `Path` set by `serve()` in `server.py` to the dashboard's bound workspace, already resolved.
- `pbg_superpowers.workspace_catalog` exposes `list_workspaces()`, `find_running(path)`, `find_entry(path)`. `find_running` returns the entry only if `kill -0 pid` succeeds.
- Existing test pattern: a `server` fixture (defined at the top of `tests/test_workspaces_api.py`) boots `vivarium-dashboard serve` as a subprocess with `PBG_HOME=tmp_path/pbg-home`, polls for `server-info`, and yields a dict with `url` and `pbg_home`. Helper `_post_json(url, path, payload, timeout=...)` does the POST and returns parsed JSON on 2xx (raises `urllib.error.HTTPError` on non-2xx).
- The `server` fixture's bound workspace is something like `tmp_path/ws` with `name: ws` in its `workspace.yaml`. The fixture is per-test, so each test gets a fresh `PBG_HOME`.

- [ ] **Step 1: Add a failing test for the happy path**

Append to `tests/test_workspaces_api.py`:

```python
def test_post_workspaces_stop_happy_path(server, tmp_path):
    """Stopping a real running subprocess sends SIGTERM, the child's atexit
    removes the global entry, and the endpoint returns 200 within 3s."""
    import subprocess as _sp
    import signal as _signal
    # Spawn a real long-running process. We register IT as a fake dashboard
    # for a "victim" workspace; the test asserts the endpoint successfully
    # terminates it. We DON'T actually need a vivarium-dashboard child here
    # because find_running only checks `kill -0 pid` — any live PID works,
    # but we need atexit-like cleanup on SIGTERM. A child that handles SIGTERM
    # by removing the registry file mimics the real cleanup:
    pbg_home = server["pbg_home"]
    victim_ws = tmp_path / "victim-ws"
    victim_ws.mkdir()
    (victim_ws / "workspace.yaml").write_text("name: victim-ws\npackage: pbg_victim\n")

    # Add the victim workspace to the catalog (via the running dashboard
    # subprocess, which shares PBG_HOME).
    _post_json(server["url"], "/api/workspaces/add", {"path": str(victim_ws)})

    # Spawn a real subprocess that will:
    # - On SIGTERM, delete the registry entry then exit cleanly.
    # That mimics cmd_serve's atexit/SIGTERM behavior.
    helper = tmp_path / "fake_dashboard.py"
    helper.write_text(f"""
import os, signal, sys, time
ENTRY = {repr(str(pbg_home / "servers" / "victim-ws.json"))}
def cleanup(*_):
    try:
        os.unlink(ENTRY)
    except FileNotFoundError:
        pass
    sys.exit(0)
signal.signal(signal.SIGTERM, cleanup)
while True:
    time.sleep(60)
""")
    fake = _sp.Popen([sys.executable, str(helper)])
    try:
        # Wait for the child to be alive enough to handle signals.
        time.sleep(0.2)
        # Register a global running entry pointing at this child's PID.
        import json as _json
        (pbg_home / "servers").mkdir(exist_ok=True)
        entry = {
            "name": "victim-ws",
            "path": str(victim_ws.resolve()),
            "pid": fake.pid,
            "port": 9999,
            "url": "http://127.0.0.1:9999",
            "started_at": "2026-05-15T00:00:00Z",
        }
        (pbg_home / "servers" / "victim-ws.json").write_text(_json.dumps(entry))

        resp = _post_json(server["url"], "/api/workspaces/stop",
                          {"path": str(victim_ws)}, timeout=10)
        assert resp == {"ok": True}
        # Entry must be gone (child's cleanup unlinked it).
        assert not (pbg_home / "servers" / "victim-ws.json").exists()
    finally:
        # Belt-and-suspenders: ensure the helper is dead.
        try:
            fake.kill()
        except ProcessLookupError:
            pass
        fake.wait(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/eranagmon/code/vivarium-dashboard && pytest tests/test_workspaces_api.py::test_post_workspaces_stop_happy_path -v`
Expected: 404 (no route) → urllib.error.HTTPError → AssertionError, or some other failure indicating the endpoint doesn't exist.

- [ ] **Step 3: Register the new route in `_POST_ROUTE_MAP`**

In `vivarium_dashboard/server.py`, find `_POST_ROUTE_MAP` (around line 232 — the dict with the v1 workspace-switcher entries `/api/workspaces/add`, `/forget`, `/cleanup-stale`, `/start`). Add one more entry alongside them:

```python
    "/api/workspaces/stop":          "_post_workspaces_stop",
```

Place it right after `/api/workspaces/start`. Alignment-wise, match the existing leading whitespace (4 spaces inside the dict).

- [ ] **Step 4: Implement `_post_workspaces_stop` on `Handler`**

Add the new method directly below `_post_workspaces_start` in `vivarium_dashboard/server.py`. The exact code:

```python
    def _post_workspaces_stop(self, body: dict):
        """POST /api/workspaces/stop — SIGTERM a running workspace's dashboard
        and poll for the child's atexit hook to remove the global registry
        entry. Refuses self-stop and uncatalogued paths. Does NOT escalate
        to SIGKILL on timeout — returns 504 with the PID instead."""
        import signal as _signal
        import time as _time

        path = body.get("path") if isinstance(body, dict) else None
        if not path or not isinstance(path, str) or not path.startswith("/"):
            self._json({"error": "path must be an absolute string"}, 400)
            return

        target = Path(path).expanduser().resolve()

        from pbg_superpowers import workspace_catalog

        # Catalog membership guard (same as /start).
        if not any(Path(e.get("path") or "").resolve() == target
                   for e in workspace_catalog.list_workspaces()):
            self._json({"error": "workspace not in catalog"}, 400)
            return

        # Refuse self-stop: WORKSPACE is the dashboard's own bound workspace,
        # already resolved by serve(). Stopping it would kill the dashboard
        # the user is currently using.
        if target == WORKSPACE:
            entry_self = workspace_catalog.find_running(target)
            pid_self = entry_self["pid"] if entry_self else os.getpid()
            self._json({
                "error": f"refusing to stop self — use the terminal: kill {pid_self}"
            }, 400)
            return

        entry = workspace_catalog.find_running(target)
        if entry is None:
            self._json({"error": "not running"}, 400)
            return

        pid = int(entry["pid"])
        try:
            os.kill(pid, _signal.SIGTERM)
        except ProcessLookupError:
            # Already dead between find_running and os.kill — treat as success.
            self._json({"ok": True}, 200)
            return

        # Poll for the child's atexit to remove the global entry.
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline:
            if workspace_catalog.find_entry(target) is None:
                self._json({"ok": True}, 200)
                return
            _time.sleep(0.1)

        self._json({
            "error": "stop_timeout",
            "hint": f"PID {pid} still alive; SIGKILL it manually if stuck",
        }, 504)
```

(`signal` and `time` are imported inside the function rather than at module top: `time` IS already imported at module level — you may use `time.monotonic()` and `time.sleep(0.1)` directly without the alias. Same for `signal`: check `grep -n "^import signal" vivarium_dashboard/server.py` first; if already imported at top, drop the `import signal as _signal` line and use `signal.SIGTERM` directly. The defensive aliases above only matter if either name shadows.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/eranagmon/code/vivarium-dashboard && pytest tests/test_workspaces_api.py::test_post_workspaces_stop_happy_path -v`
Expected: PASS (~0.5–1.0 s, dominated by the helper subprocess startup).

- [ ] **Step 6: Add failing test for self-stop refusal**

Append to `tests/test_workspaces_api.py`:

```python
def test_post_workspaces_stop_refuses_self(server, tmp_path):
    """POSTing stop with the dashboard's own bound workspace path returns
    400 and a message pointing the user at the terminal."""
    # The server fixture's bound workspace is at server["workspace"].
    # (If the fixture exposes it under a different key, adapt.)
    self_path = server["workspace"]
    try:
        _post_json(server["url"], "/api/workspaces/stop", {"path": str(self_path)})
        assert False, "expected 400 for self-stop"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert "refusing to stop self" in body["error"]
        assert "kill " in body["error"]  # message includes a PID
```

If the `server` fixture in `tests/test_workspaces_api.py` doesn't expose `workspace` (the bound directory), look at how it sets up the subprocess (the `--workspace <path>` argument) and either add a `"workspace"` key to the yielded dict or read it from elsewhere. Don't invent a new fixture; reuse the existing one and minimally extend it.

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_workspaces_api.py::test_post_workspaces_stop_refuses_self -v`
Expected: FAIL (the test currently passes if the path isn't recognized as self — but the catalog-membership check will fire FIRST and return 400 with "workspace not in catalog", not "refusing to stop self". So you'll see a 400 but the message check fails).

This test reveals a subtle ordering issue: should we check self BEFORE catalog-membership, or AFTER? Self should be checked AFTER, because if the user's own workspace ISN'T in the catalog yet (first-run UX), the catalog-membership 400 is the more accurate response. Self-stop refusal is for the case where the user's own workspace IS in the catalog (which it will be once they've ever added it). So Step 4's code already has the correct order: catalog FIRST, self SECOND.

The test as written assumes the dashboard's own workspace IS in the catalog. So before calling stop, add it:

Update the test body:

```python
def test_post_workspaces_stop_refuses_self(server, tmp_path):
    """POSTing stop with the dashboard's own bound workspace path returns
    400 and a message pointing the user at the terminal."""
    self_path = server["workspace"]
    # Ensure the dashboard's own workspace is in the catalog (Add it).
    _post_json(server["url"], "/api/workspaces/add", {"path": str(self_path)})
    try:
        _post_json(server["url"], "/api/workspaces/stop", {"path": str(self_path)})
        assert False, "expected 400 for self-stop"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert "refusing to stop self" in body["error"]
        assert "kill " in body["error"]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_workspaces_api.py::test_post_workspaces_stop_refuses_self -v`
Expected: PASS.

- [ ] **Step 9: Add failing test for not-running refusal**

Append:

```python
def test_post_workspaces_stop_refuses_not_running(server, tmp_path):
    """If the workspace has no live entry, stop returns 400 'not running'."""
    pbg_home = server["pbg_home"]
    other_ws = tmp_path / "stopped-ws"
    other_ws.mkdir()
    (other_ws / "workspace.yaml").write_text("name: stopped-ws\npackage: pbg_stopped\n")
    _post_json(server["url"], "/api/workspaces/add", {"path": str(other_ws)})

    # No server entry exists for this workspace.
    try:
        _post_json(server["url"], "/api/workspaces/stop", {"path": str(other_ws)})
        assert False, "expected 400"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["error"] == "not running"
```

Also append the stale-entry variant (find_running returns None for dead PIDs too):

```python
def test_post_workspaces_stop_refuses_stale_entry(server, tmp_path):
    """If the server entry exists but the PID is dead, treat as 'not running'."""
    import subprocess as _sp
    pbg_home = server["pbg_home"]
    other_ws = tmp_path / "stale-ws"
    other_ws.mkdir()
    (other_ws / "workspace.yaml").write_text("name: stale-ws\npackage: pbg_stale\n")
    _post_json(server["url"], "/api/workspaces/add", {"path": str(other_ws)})

    # Get a confirmed-dead PID.
    proc = _sp.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    import json as _json
    (pbg_home / "servers").mkdir(exist_ok=True)
    (pbg_home / "servers" / "stale-ws.json").write_text(_json.dumps({
        "name": "stale-ws", "path": str(other_ws.resolve()),
        "pid": proc.pid, "port": 9998,
        "url": "http://127.0.0.1:9998",
        "started_at": "2026-05-15T00:00:00Z",
    }))

    try:
        _post_json(server["url"], "/api/workspaces/stop", {"path": str(other_ws)})
        assert False, "expected 400"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["error"] == "not running"
```

- [ ] **Step 10: Run tests, confirm pass**

Run: `pytest tests/test_workspaces_api.py -k "stop" -v`
Expected: 4 PASS (happy-path, self, not-running, stale-entry).

- [ ] **Step 11: Add failing test for uncatalogued path**

Append:

```python
def test_post_workspaces_stop_refuses_uncatalogued(server, tmp_path):
    """A real workspace dir that's NOT in the catalog can't be stopped — even
    if a server entry exists. (Safety: don't let the dashboard send SIGTERM
    to arbitrary PIDs.)"""
    other_ws = tmp_path / "ghost"
    other_ws.mkdir()
    (other_ws / "workspace.yaml").write_text("name: ghost\npackage: pbg_ghost\n")
    # Note: do NOT add to catalog.

    try:
        _post_json(server["url"], "/api/workspaces/stop", {"path": str(other_ws)})
        assert False, "expected 400"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        body = json.loads(exc.read())
        assert body["error"] == "workspace not in catalog"
```

- [ ] **Step 12: Run test, confirm pass**

Run: `pytest tests/test_workspaces_api.py::test_post_workspaces_stop_refuses_uncatalogued -v`
Expected: PASS.

- [ ] **Step 13: Add timeout test (child ignores SIGTERM)**

Append:

```python
def test_post_workspaces_stop_timeout(server, tmp_path):
    """If the child ignores SIGTERM, the endpoint returns 504 with the PID
    in the error message. The endpoint does NOT escalate to SIGKILL."""
    import subprocess as _sp
    pbg_home = server["pbg_home"]
    victim_ws = tmp_path / "stubborn-ws"
    victim_ws.mkdir()
    (victim_ws / "workspace.yaml").write_text("name: stubborn-ws\npackage: pbg_stubborn\n")
    _post_json(server["url"], "/api/workspaces/add", {"path": str(victim_ws)})

    # Spawn a child that explicitly ignores SIGTERM.
    helper = tmp_path / "stubborn.py"
    helper.write_text("""
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    time.sleep(60)
""")
    fake = _sp.Popen([sys.executable, str(helper)])
    try:
        time.sleep(0.2)
        import json as _json
        (pbg_home / "servers").mkdir(exist_ok=True)
        (pbg_home / "servers" / "stubborn-ws.json").write_text(_json.dumps({
            "name": "stubborn-ws", "path": str(victim_ws.resolve()),
            "pid": fake.pid, "port": 9997,
            "url": "http://127.0.0.1:9997",
            "started_at": "2026-05-15T00:00:00Z",
        }))

        # The endpoint has a 3s polling deadline; give urllib up to 10s to
        # be safe.
        try:
            _post_json(server["url"], "/api/workspaces/stop",
                       {"path": str(victim_ws)}, timeout=10)
            assert False, "expected 504"
        except urllib.error.HTTPError as exc:
            assert exc.code == 504
            body = json.loads(exc.read())
            assert body["error"] == "stop_timeout"
            assert str(fake.pid) in body["hint"]
    finally:
        # Important: SIG_IGN is reset on SIGKILL — this must succeed.
        fake.kill()
        fake.wait(timeout=5)
```

- [ ] **Step 14: Run test, confirm pass**

Run: `pytest tests/test_workspaces_api.py::test_post_workspaces_stop_timeout -v --timeout=15`
Expected: PASS in ~3.5s (the endpoint's 3s deadline + small overhead).

- [ ] **Step 15: Run the full test file**

Run: `pytest tests/test_workspaces_api.py -v --timeout=30`
Expected: 17 passed (12 existing v1 tests + 5 new v2 tests).

- [ ] **Step 16: Commit**

```bash
cd /Users/eranagmon/code/vivarium-dashboard
git add vivarium_dashboard/server.py tests/test_workspaces_api.py
git commit -m "feat(api): POST /api/workspaces/stop"
```

---

## Task 2: Rewrite `workspace-switcher.js` for the modal

**Files:**
- Modify: `vivarium_dashboard/static/workspace-switcher.js` (rewrite; same path, same `<script src="assets/workspace-switcher.js">` entry)

### Context for the implementer

- The v1 JS reads `#viv-workspace-switcher-trigger` (the rail button) and `#viv-workspace-switcher-panel` (the inline dropdown). For v2, we drop the panel and lazily create a modal in `document.body` on first open.
- Endpoints that the JS calls: `GET /api/workspaces`, `POST /api/workspaces/add`, `POST /api/workspaces/forget`, `POST /api/workspaces/cleanup-stale`, `POST /api/workspaces/start`, `POST /api/workspaces/stop` (Task 1 added the last one).
- v1's response shape from `GET /api/workspaces`:
  ```json
  {
    "current": { "name": "...", "path": "..." },
    "workspaces": [
      { "name": "...", "path": "...", "status": "current|running|stopped|stale|missing",
        "url": "...", "pid": 47192 }
    ]
  }
  ```
- The status sort order returned by the server: current → running → stopped → stale → missing.
- HTML escaping: v1's `escapeHtml` helper is kept verbatim.
- No JS test runner exists; verification is manual.

- [ ] **Step 1: Read v1's `workspace-switcher.js` to anchor your rewrite**

```bash
cat /Users/eranagmon/code/vivarium-dashboard/vivarium_dashboard/static/workspace-switcher.js
```

You're going to keep the action handlers (`doStart`, `doCleanup`, `doForget`, plus a new `doStop`) and the API call shape, but throw out everything related to the dropdown panel DOM. The new shell mounts to `document.body`.

- [ ] **Step 2: Write the new `workspace-switcher.js`**

Replace the entire contents of `vivarium_dashboard/static/workspace-switcher.js` with:

```javascript
// Workspace switcher v2: centered modal mounted to <body> on first open.
//
// The trigger button (#viv-workspace-switcher-trigger) lives in the rail
// from index.html.j2. Click → mount + open the modal. Reads GET
// /api/workspaces on each open. Per-row primary action = click anywhere
// except the right-side button. Secondary action = the button (Stop on
// running non-current, Forget on stopped, Clean up on stale, Forget on
// missing).

(function () {
  const trigger = document.getElementById('viv-workspace-switcher-trigger');
  if (!trigger) return;

  let modal = null;
  let card = null;
  let listEl = null;
  let escHandler = null;

  const GLYPH = {
    current: '●', running: '●', stopped: '○', stale: '⚠', missing: '⊘',
  };
  const GLYPH_CLASS = {
    current: 'viv-glyph-running', running: 'viv-glyph-running',
    stopped: 'viv-glyph-stopped', stale: 'viv-glyph-stale',
    missing: 'viv-glyph-missing',
  };

  function ensureMounted() {
    if (modal) return;
    modal = document.createElement('div');
    modal.className = 'viv-ws-modal';
    modal.innerHTML = `
      <div class="viv-ws-modal-card" role="dialog" aria-label="Workspaces">
        <div class="viv-ws-modal-header">
          <h2>Workspaces</h2>
          <button type="button" class="viv-ws-modal-close" aria-label="Close">✕</button>
        </div>
        <ul class="viv-ws-modal-list"></ul>
        <div class="viv-ws-modal-footer">
          <button type="button" class="viv-ws-modal-add">+ Add existing workspace…</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    card = modal.querySelector('.viv-ws-modal-card');
    listEl = modal.querySelector('.viv-ws-modal-list');

    modal.addEventListener('click', (e) => {
      // Click on the dim overlay (outside the card) closes the modal.
      if (e.target === modal) close();
    });
    modal.querySelector('.viv-ws-modal-close').addEventListener('click', close);
    modal.querySelector('.viv-ws-modal-add').addEventListener('click', doAdd);
  }

  function open() {
    ensureMounted();
    modal.classList.add('open');
    listEl.innerHTML = '<li class="viv-ws-loading">Loading…</li>';
    refresh();
    escHandler = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', escHandler);
  }

  function close() {
    if (!modal) return;
    modal.classList.remove('open');
    if (escHandler) {
      document.removeEventListener('keydown', escHandler);
      escHandler = null;
    }
  }

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    open();
  });

  async function refresh() {
    try {
      const resp = await fetch('/api/workspaces');
      const data = await resp.json();
      render(data);
    } catch (err) {
      listEl.innerHTML = `<li class="viv-ws-error">Failed to load: ${escapeHtml(String(err))}</li>`;
    }
  }

  function render(data) {
    listEl.innerHTML = '';
    data.workspaces.forEach((ws) => listEl.appendChild(renderRow(ws)));
  }

  function renderRow(ws) {
    const li = document.createElement('li');
    li.className = 'viv-ws-row';
    if (ws.status === 'current') li.classList.add('viv-ws-row-current');

    const line1 = document.createElement('div');
    line1.className = 'viv-ws-line1';

    const glyph = document.createElement('span');
    glyph.className = `viv-ws-glyph ${GLYPH_CLASS[ws.status] || ''}`;
    glyph.textContent = GLYPH[ws.status] || '?';
    line1.appendChild(glyph);

    const name = document.createElement('span');
    name.className = 'viv-ws-name';
    name.innerHTML = `<strong>${escapeHtml(ws.name)}</strong>${
      ws.status === 'current' ? ' <small>(this)</small>' : ''
    }`;
    line1.appendChild(name);

    const btn = renderActionButton(ws, li);
    if (btn) line1.appendChild(btn);

    const line2 = document.createElement('div');
    line2.className = 'viv-ws-path';
    line2.textContent = ws.path;

    li.appendChild(line1);
    li.appendChild(line2);

    // Row click = primary action (except clicks on the button).
    if (ws.status !== 'current') {
      li.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        doPrimary(ws, li);
      });
    }
    return li;
  }

  function renderActionButton(ws, li) {
    if (ws.status === 'current') return null;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'viv-ws-action';
    let label;
    if (ws.status === 'running') {
      label = 'Stop ■';
      btn.classList.add('viv-ws-action-danger');
      btn.addEventListener('click', () => doStop(ws, btn, li));
    } else if (ws.status === 'stopped') {
      label = 'Forget';
      btn.classList.add('viv-ws-action-muted');
      btn.addEventListener('click', () => doForget(ws, btn, li));
    } else if (ws.status === 'stale') {
      label = 'Clean up';
      btn.classList.add('viv-ws-action-warn');
      btn.addEventListener('click', () => doCleanup(ws, btn, li));
    } else if (ws.status === 'missing') {
      label = 'Forget ×';
      btn.classList.add('viv-ws-action-muted');
      btn.addEventListener('click', () => doForget(ws, btn, li));
    }
    btn.textContent = label;
    return btn;
  }

  function doPrimary(ws, li) {
    if (ws.status === 'running') {
      window.location.href = ws.url;
    } else if (ws.status === 'stopped') {
      doStart(ws, null, li);
    } else if (ws.status === 'stale') {
      doCleanup(ws, null, li);
    } else if (ws.status === 'missing') {
      doForget(ws, null, li);
    }
  }

  function busy(btn, label) {
    if (btn) { btn.disabled = true; btn.dataset.original = btn.textContent; btn.textContent = label; }
  }
  function unbusy(btn) {
    if (btn) { btn.disabled = false; if (btn.dataset.original) btn.textContent = btn.dataset.original; }
  }

  async function postJson(path, payload) {
    const resp = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw Object.assign(new Error(body.error || `HTTP ${resp.status}`), { body });
    return body;
  }

  function rowError(li, msg) {
    let err = li.querySelector('.viv-ws-error');
    if (!err) {
      err = document.createElement('div');
      err.className = 'viv-ws-error';
      li.appendChild(err);
    }
    err.textContent = msg;
  }

  async function doStart(ws, btn, li) {
    busy(btn, 'Starting…');
    try {
      const data = await postJson('/api/workspaces/start', { path: ws.path });
      window.location.href = data.url;
    } catch (err) {
      rowError(li, err.message + (err.body && err.body.log_path ? ` (log: ${err.body.log_path})` : ''));
      unbusy(btn);
    }
  }

  async function doStop(ws, btn, li) {
    busy(btn, 'Stopping…');
    try {
      await postJson('/api/workspaces/stop', { path: ws.path });
      refresh();
    } catch (err) {
      rowError(li, err.message + (err.body && err.body.hint ? ` — ${err.body.hint}` : ''));
      unbusy(btn);
    }
  }

  async function doCleanup(ws, btn, li) {
    busy(btn, 'Cleaning…');
    try {
      await postJson('/api/workspaces/cleanup-stale', { path: ws.path });
      refresh();
    } catch (err) {
      rowError(li, err.message);
      unbusy(btn);
    }
  }

  async function doForget(ws, btn, li) {
    busy(btn, 'Forgetting…');
    try {
      await postJson('/api/workspaces/forget', { path: ws.path });
      refresh();
    } catch (err) {
      rowError(li, err.message);
      unbusy(btn);
    }
  }

  async function doAdd() {
    const p = window.prompt('Path to workspace directory:');
    if (!p) return;
    try {
      await postJson('/api/workspaces/add', { path: p });
      refresh();
    } catch (err) {
      window.alert('Could not add: ' + err.message);
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
})();
```

- [ ] **Step 3: Verify the file parses (lint-by-eyeball + node check if available)**

```bash
cd /Users/eranagmon/code/vivarium-dashboard
node --check vivarium_dashboard/static/workspace-switcher.js
```

Expected: no output (success). If `node` isn't available, skip — `python3 -c "import ast"` won't work on JS; the next step's `curl` will catch parse errors at load time.

- [ ] **Step 4: Run the Python test suite for regressions**

Run: `pytest tests/test_workspaces_api.py tests/test_workspace_switcher_cli.py -v --timeout=30`
Expected: 19 passed (17 from Task 1's final state + 2 from `test_workspace_switcher_cli.py`).

Yes — the JS rewrite affects no Python tests. The check is just to confirm you didn't break the route-map ordering or anything else in `server.py`.

- [ ] **Step 5: Commit**

```bash
git add vivarium_dashboard/static/workspace-switcher.js
git commit -m "feat(ui): rewrite workspace switcher as a centered modal"
```

---

## Task 3: Replace the v1 dropdown markup + add modal CSS

**Files:**
- Modify: `vivarium_dashboard/templates/index.html.j2` — remove v1 dropdown `<div>`, keep the trigger, append modal CSS to the `<style>` block

### Context for the implementer

- v1's markup is at lines ~176-198 of `vivarium_dashboard/templates/index.html.j2`. It looks like:
  ```html
  <div class="viv-workspace-switcher" id="viv-workspace-switcher">
    <button class="viv-workspace-switcher-trigger" ... id="viv-workspace-switcher-trigger">
      <span class="viv-workspace-switcher-glyph">●</span>
      <strong>{{ workspace_name }}</strong>
      <span class="viv-arrow">▾</span>
    </button>
    <div class="viv-workspace-switcher-panel" id="viv-workspace-switcher-panel" hidden>
      <div class="viv-workspace-switcher-header">Workspaces</div>
      <ul class="viv-workspace-switcher-list" id="viv-workspace-switcher-list">
        <li class="viv-workspace-switcher-loading">Loading…</li>
      </ul>
      <div class="viv-workspace-switcher-footer">
        <button class="viv-workspace-switcher-add" type="button" id="viv-workspace-switcher-add">
          + Add existing workspace…
        </button>
      </div>
    </div>
  </div>
  ```
- v1's CSS is at lines ~106-156 of the same file (search for `.viv-workspace-switcher` to find the block in the inline `<style>`). It defines `.viv-workspace-switcher-panel`, `.viv-workspace-switcher-list`, `.viv-workspace-switcher-list li`, button styles, etc.
- The trigger button (`<button id="viv-workspace-switcher-trigger">`) must stay because Task 2's JS reads it.

- [ ] **Step 1: Remove the v1 dropdown inner div, keep the trigger**

In `vivarium_dashboard/templates/index.html.j2`, find the `<div class="viv-workspace-switcher" id="viv-workspace-switcher">` block. Replace ONLY the inner `<div class="viv-workspace-switcher-panel" ...> ... </div>` with nothing.

After your edit the wrapper looks like:

```html
    <div class="viv-workspace-switcher" id="viv-workspace-switcher">
      <button class="viv-workspace-switcher-trigger" type="button"
              aria-haspopup="true" aria-expanded="false"
              id="viv-workspace-switcher-trigger">
        <span class="viv-workspace-switcher-glyph">●</span>
        <strong>{{ workspace_name }}</strong>
        <span class="viv-arrow">▾</span>
      </button>
    </div>
```

The aria-haspopup and aria-expanded attributes can stay (they still describe the trigger's relationship to the modal even though JS will mount the modal later). Leave them.

- [ ] **Step 2: Remove v1 dropdown CSS**

In the inline `<style>` block, delete the lines covering ONLY these v1 rules (the trigger and arrow styles stay, since the trigger still uses them):

Lines to delete (search the file for these selectors and delete the block of CSS for each):
- `.viv-workspace-switcher-panel { ... }`
- `.viv-workspace-switcher-header { ... }`
- `.viv-workspace-switcher-list { ... }`
- `.viv-workspace-switcher-list li { ... }`
- `.viv-workspace-switcher-list li:last-child { ... }`
- `.viv-workspace-switcher-list a { ... }`
- `.viv-workspace-switcher-list a:hover { ... }`
- `.viv-workspace-switcher-list .viv-ws-path { ... }`
- `.viv-workspace-switcher-list .viv-ws-glyph { ... }`
- `.viv-workspace-switcher-list .viv-ws-row-current { ... }`
- `.viv-workspace-switcher-list button { ... }`
- `.viv-workspace-switcher-list button:hover { ... }`
- `.viv-workspace-switcher-footer { ... }`
- `.viv-workspace-switcher-add { ... }`
- `.viv-glyph-running`, `.viv-glyph-stopped`, `.viv-glyph-stale`, `.viv-glyph-missing` — **KEEP** these; they're reused by the modal.
- `.viv-ws-error` — **KEEP**; reused by the modal.

The trigger styles (`.viv-workspace-switcher`, `.viv-workspace-switcher-trigger`, `.viv-workspace-switcher-trigger:hover`, `.viv-workspace-switcher-glyph`) stay.

- [ ] **Step 3: Append the v2 modal CSS to the same `<style>` block**

Right before `</style>`, append:

```css
/* Workspace switcher v2 — centered modal mounted to body. */
.viv-ws-modal {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.32);
  display: none;
  align-items: center; justify-content: center;
  z-index: 2000;
  opacity: 0;
  transition: opacity 0.14s ease-out;
}
.viv-ws-modal.open {
  display: flex;
  opacity: 1;
}
.viv-ws-modal-card {
  width: min(720px, 90vw);
  max-height: 80vh;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.18);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.viv-ws-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid #eee;
}
.viv-ws-modal-header h2 {
  margin: 0; font-size: 15px; font-weight: 600; color: #333;
}
.viv-ws-modal-close {
  background: none; border: none; cursor: pointer;
  font-size: 18px; color: #666; padding: 0 4px;
}
.viv-ws-modal-close:hover { color: #000; }
.viv-ws-modal-list {
  list-style: none; margin: 0; padding: 0;
  overflow-y: auto; flex: 1;
}
.viv-ws-modal-footer {
  padding: 10px 18px; border-top: 1px solid #eee;
}
.viv-ws-modal-add {
  background: none; border: none; color: #0366d6;
  cursor: pointer; font-size: 13px; padding: 0;
}
.viv-ws-modal-add:hover { text-decoration: underline; }

/* Rows */
.viv-ws-row {
  padding: 10px 18px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
}
.viv-ws-row:last-child { border-bottom: none; }
.viv-ws-row:hover { background: #f6f8fa; }
.viv-ws-row-current { cursor: default; background: #f8f9fb; }
.viv-ws-row-current:hover { background: #f8f9fb; }
.viv-ws-line1 {
  display: flex; align-items: center; gap: 10px;
}
.viv-ws-row .viv-ws-glyph { width: 18px; text-align: center; font-size: 14px; }
.viv-ws-name { flex: 1; font-size: 13px; }
.viv-ws-name small { color: #777; font-weight: normal; }
.viv-ws-path {
  font-size: 11px; color: #888;
  margin-top: 3px; margin-left: 28px;
  word-break: break-all;
}
.viv-ws-action {
  font-size: 11px; padding: 4px 10px; cursor: pointer;
  border: 1px solid #ccc; background: #fff; border-radius: 3px;
}
.viv-ws-action:hover { background: #f0f0f0; }
.viv-ws-action:disabled { opacity: 0.6; cursor: progress; }
.viv-ws-action-danger { color: #cf222e; border-color: #f6c4c9; }
.viv-ws-action-danger:hover { background: #fdecef; }
.viv-ws-action-warn { color: #b3700d; border-color: #f0d8a7; }
.viv-ws-action-warn:hover { background: #fff5e1; }
.viv-ws-action-muted { color: #666; }
.viv-ws-loading {
  padding: 16px 18px; color: #999; font-size: 12px;
}
/* .viv-ws-error reused from v1; no rule change needed. */
```

- [ ] **Step 4: Visual sanity check via curl**

```bash
cd /Users/eranagmon/code/v2ecoli-workspace
# Kill any running dashboards
pgrep -f "vivarium_dashboard.cli serve" | xargs kill -TERM 2>/dev/null
sleep 1
nohup python3 -m vivarium_dashboard.cli serve --workspace . --port 0 > /tmp/v2-smoke.log 2>&1 &
disown
sleep 2
PORT=$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['port'])")
URL="http://127.0.0.1:$PORT"

echo "=== old dropdown panel HTML must be GONE ==="
curl -sf "$URL/" | grep -c "viv-workspace-switcher-panel" | xargs -I{} echo "  occurrences of 'viv-workspace-switcher-panel': {} (expect 0)"

echo "=== new modal CSS must be present ==="
curl -sf "$URL/" | grep -c "viv-ws-modal" | xargs -I{} echo "  occurrences of 'viv-ws-modal': {} (expect >= 2 — one in CSS, presence depends on JS lazy-mount)"

echo "=== new modal CSS rule visible ==="
curl -sf "$URL/" | grep -c "\.viv-ws-modal-card" | xargs -I{} echo "  occurrences of '.viv-ws-modal-card' CSS rule: {} (expect >= 1)"

echo "=== JS file is served + has new modal code ==="
curl -sf "$URL/assets/workspace-switcher.js" | grep -c "viv-ws-modal" | xargs -I{} echo "  occurrences of 'viv-ws-modal' in JS: {} (expect >= 1)"

# Shut down
pgrep -f "vivarium_dashboard.cli serve --workspace $(pwd)" | xargs kill -TERM 2>/dev/null
```

Expected: panel = 0, modal CSS = ≥2, modal CSS rule = ≥1, JS modal references = ≥1.

- [ ] **Step 5: Run the test suite to confirm no Python regressions**

```bash
cd /Users/eranagmon/code/vivarium-dashboard
pytest tests/test_workspaces_api.py tests/test_workspace_switcher_cli.py -v --timeout=30
```

Expected: 19 passed.

- [ ] **Step 6: Commit**

```bash
git add vivarium_dashboard/templates/index.html.j2
git commit -m "feat(ui): swap v1 dropdown markup for v2 modal CSS + lazy-mount target"
```

---

## Task 4: Manual end-to-end verification

This task is run by a human (or by you driving a browser); there is no test code.

- [ ] **Step 1: Reset state**

```bash
rm -rf ~/.pbg/workspaces.json ~/.pbg/servers ~/.pbg/workspaces.json.lock ~/.pbg/servers.lock
pgrep -f "vivarium_dashboard.cli serve" | xargs kill -TERM 2>/dev/null
sleep 1
```

- [ ] **Step 2: Pre-seed the catalog with a second workspace**

```bash
python3 -m pbg_superpowers.workspace_catalog add --path /Users/eranagmon/code/pbg-biomodels
```

- [ ] **Step 3: Boot dashboard A**

```bash
cd /Users/eranagmon/code/v2ecoli-workspace
nohup python3 -m vivarium_dashboard.cli serve --workspace . --port 0 > /tmp/v2-e2e-A.log 2>&1 &
disown
sleep 2
PORT=$(python3 -c "import json; print(json.load(open('.pbg/server/server-info'))['port'])")
echo "Open in browser: http://127.0.0.1:$PORT"
```

- [ ] **Step 4: In the browser, verify the modal**

1. Click the workspace name (`● v2ecoli ▾`) in the rail.
2. Modal opens centered, with a dim background.
3. Two rows: `● v2ecoli (this)` and `○ biomodels [Forget]`.
4. Long paths display in full on the second line; no horizontal scroll.
5. Hover on the biomodels row → bg tint, cursor changes to pointer.
6. Click the biomodels row body → starts the dashboard, navigates the tab to it.

- [ ] **Step 5: In dashboard B, verify Stop**

1. In the new dashboard's modal, locate the v2ecoli row (`● v2ecoli` with `[Stop ■]`).
2. Click `Stop ■`. Button shows "Stopping…", row re-renders within ~1s as `○ v2ecoli [Forget]` (stopped).
3. Confirm dashboard A's process is actually dead: `pgrep -f "vivarium_dashboard.cli serve --workspace /Users/eranagmon/code/v2ecoli-workspace"` returns nothing.

- [ ] **Step 6: Verify self-stop is blocked**

There is no Stop button on the current row. (Confirm visually.) The button is hidden by the row-type → button-renderer logic; you don't even get the chance to click it. The API guard is belt-and-suspenders for direct curl access.

- [ ] **Step 7: Verify Esc / outside-click close**

1. Open the modal again.
2. Press Esc → modal closes.
3. Open it again. Click on the dim area outside the white card → modal closes.

- [ ] **Step 8: Final cleanup**

```bash
pgrep -f "vivarium_dashboard.cli serve" | xargs kill -TERM 2>/dev/null
```

If all 8 steps pass, the feature is done.

---

## Notes for the implementing engineer

- **All commits on `feat/workspace-switcher`** (the branch from v1). When v1's PR lands, v2's commits will already be on the same branch and will appear in the same PR (or you can rebase / split if review prefers two PRs).
- **No changes to `pbg-superpowers`.** Everything in this plan is in `/Users/eranagmon/code/vivarium-dashboard`.
- **Pre-existing 16 test failures in the dashboard** are unrelated to this work. Don't try to fix them. Only watch that you don't add new failures.
- **The JS file is loaded via `<script src="assets/workspace-switcher.js">`** — this path mapping is established in v1 Task 10 and works because the dashboard's static handler maps `assets/` to `STATIC_DIR`.
- **`Path(e.get("path") or "")` defensive idiom** for catalog access already used in `/start` and is the pattern in the Stop handler too. Don't change it.
- **CSS classes prefixed with `viv-ws-`** are the v2 namespace. Don't reuse v1's `viv-workspace-switcher-*` prefixes for new rules — they're being removed by Task 3.
