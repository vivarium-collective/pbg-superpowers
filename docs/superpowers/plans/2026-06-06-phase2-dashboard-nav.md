# Phase 2: Dashboard Investigation-Centric Navigation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the vivarium-dashboard render the nested investigation structure: endpoints resolve studies under `investigations/<inv>/studies/`, the top-left becomes a **repo switcher**, the menu reads **Investigations**, the list→detail→studies-sync flow works, lifecycle badges show git state, and reports are per-investigation.

**Architecture:** Build on Phase 1's `WorkspacePaths.study_dir()` (already mirrored into the dashboard's `lib/workspace_paths.py`). Most UI (list/detail views, studies-sync, `/api/workspaces`) already exists — repoint study resolution, repurpose the switcher, add badges, relabel.

**Tech Stack:** Python 3.12 stdlib http.server, pytest; vanilla-JS SPA (`walkthrough.js`, `investigation-switcher.js`), Jinja template (`index.html.j2`).

**Spec:** `docs/superpowers/specs/2026-06-06-investigation-centric-restructure-design.md`. **Branch:** `vivarium-dashboard feat/dashboard-investigation-nav` (off `feat/nested-study-resolution`).

---

## Task 1: Nested study resolution in iset endpoints (TDD)

**Files:**
- Modify: `vivarium_dashboard/server.py` — `_read_study_status` (~1213), `_get_iset_detail` study loop (~7699)
- Test: `tests/test_iset_nested.py`

- [ ] **Step 1: Write failing test** — a nested workspace where the member study lives at `investigations/<inv>/studies/<slug>/study.yaml`; assert `_build_iset_summary_for_test` reports `n_studies==1` with the study's status (not "planning"/missing), and `_build_iset_detail_for_test` resolves the study (status != "missing").

```python
# tests/test_iset_nested.py
from pathlib import Path
import yaml
from vivarium_dashboard.server import _build_iset_summary_for_test, _build_iset_detail_for_test

def _nested_ws(tmp):
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp / "investigations" / "inv-a"; (inv / "studies" / "s1").mkdir(parents=True)
    (inv / "investigation.yaml").write_text("name: inv-a\ntitle: A\nstudies:\n  - s1\n", encoding="utf-8")
    (inv / "studies" / "s1" / "study.yaml").write_text(
        "name: s1\ninvestigation: inv-a\nstatus: complete\n", encoding="utf-8")
    return tmp

def test_summary_resolves_nested_study(tmp_path):
    ws = _nested_ws(tmp_path)
    out = {i["name"]: i for i in _build_iset_summary_for_test(ws)}
    assert out["inv-a"]["n_studies"] == 1

def test_detail_resolves_nested_study(tmp_path):
    ws = _nested_ws(tmp_path)
    d = _build_iset_detail_for_test(ws, "inv-a")
    s1 = {s["name"]: s for s in d["studies"]}["s1"]
    assert s1["status"] != "missing"
```

- [ ] **Step 2: Run — expect FAIL** (`_get_iset_detail` resolves flat `studies/s1` → "missing"; `_read_study_status` returns "planning"). Run: `.venv/bin/python -m pytest tests/test_iset_nested.py -v`

- [ ] **Step 3: Repoint resolution to the Phase 1 resolver.** In `_read_study_status` replace the hardcoded `candidates` with a nested-aware resolve:

```python
def _read_study_status(ws_root: Path, slug: str) -> tuple[str, bool]:
    from .lib.workspace_paths import WorkspacePaths
    wp = WorkspacePaths.load(ws_root)
    try:
        sp = wp.study_dir(slug) / "study.yaml"
    except FileNotFoundError:
        sp = ws_root / "investigations" / slug / "spec.yaml"  # legacy v2 spec fallback
    if not sp.is_file():
        return "planning", False
    try:
        spec = yaml.safe_load(sp.read_text(encoding="utf-8")) or {}
    except Exception:
        return "planning", False
    status = spec.get("status") or "planning"
    return status, _count_runs_for_study(slug, spec) > 0
```

In `_get_iset_detail` study loop, replace lines ~7700-7706 with:

```python
    for slug in (spec.get("studies") or []):
        try:
            sp = workspace_paths().study_dir(slug) / "study.yaml"
        except FileNotFoundError:
            sp = workspace_paths().investigations / slug / "spec.yaml"
        if not sp.is_file():
            studies_out.append({"name": slug, "status": "missing", "error": "study.yaml not found"})
            continue
```

- [ ] **Step 4: Run — expect PASS.** Also run the existing `tests/test_iset_endpoints.py` to confirm flat back-compat still passes.

- [ ] **Step 5: Commit** `feat(dashboard): resolve iset member studies nested-aware (Phase 1 study_dir) + flat back-compat`

---

## Task 2: Lifecycle badges in `/api/iset-list` (TDD)

**Files:** Modify `server.py` `_build_iset_summary_for_test`; Test `tests/test_iset_nested.py` (append).

- [ ] **Step 1: Failing test** — in a git workspace where `inv-a` exists on `main` and `inv-b` only on a feature branch, assert the summary marks `inv-a` lifecycle `merged` and `inv-b` `wip`.

```python
import subprocess
def test_lifecycle_badge_main_vs_branch(tmp_path):
    ws = _nested_ws(tmp_path)
    for c in (["init","-q"],["add","-A"],["commit","-qm","init"]): subprocess.run(["git",*c],cwd=ws,check=True)
    subprocess.run(["git","checkout","-qb","feat/x"],cwd=ws,check=True)
    invb = ws/"investigations"/"inv-b"; (invb/"studies").mkdir(parents=True)
    (invb/"investigation.yaml").write_text("name: inv-b\nstudies: []\n",encoding="utf-8")
    out = {i["name"]: i for i in _build_iset_summary_for_test(ws)}
    assert out["inv-a"]["lifecycle"] == "merged"
    assert out["inv-b"]["lifecycle"] == "wip"
```

- [ ] **Step 2: Run — expect FAIL** (no `lifecycle` key).

- [ ] **Step 3: Implement** a helper `_iset_lifecycle(ws_root, slug)` that runs `git cat-file -e $(git merge-base HEAD main 2>/dev/null||echo HEAD):investigations/<slug>/investigation.yaml` → `"merged"` if present in the merge-base tree, else `"wip"`; default `"wip"` when not a git repo / no main. Add `"lifecycle": _iset_lifecycle(ws_root, name)` to the summary dict. (Wrap subprocess in try/except → `"wip"`.)

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit** `feat(dashboard): iset-list lifecycle badge (merged vs wip via merge-base)`

---

## Task 3: Menu label + page heading "Investigation" → "Investigations"

**Files:** Modify `vivarium_dashboard/templates/index.html.j2:372` (menu label) + the page `<h..>`/lead at ~970.

- [ ] **Step 1:** Change line 372 `<span class="viv-rail-link-label">Investigation</span>` → `Investigations`. Update the page-investigations heading/lead text to plural ("All investigations in this repo …").
- [ ] **Step 2: Verify render** — `grep -n 'rail-link-label">Investigations<' index.html.j2` returns the line; load the template via the existing template test if present.
- [ ] **Step 3: Commit** `feat(dashboard): rename menu Investigation -> Investigations (plural list)`

---

## Task 4: Top-left repo switcher (repurpose the switcher to `/api/workspaces`)

**Files:** Modify `vivarium_dashboard/static/investigation-switcher.js` (or add `repo-switcher.js` + swap the include in `index.html.j2`); trigger label at template ~304.

- [ ] **Step 1:** Add a `refreshRepos()` path that fetches `/api/workspaces` and renders rows: `current` (no-op), `running` (→ `window.location.assign(row.url)`), `stopped`/`stale`/`missing` (→ show "start with `/pbg-dashboard open`" hint). Keep the existing investigation registry as a secondary section OR move it behind the Branch menu.
- [ ] **Step 2:** Trigger label (template ~304) → show repo name only (drop `:investigation`). Keep `publishCurrentSlug` for studies-sync (now driven by the investigations list selection, not the top-left).
- [ ] **Step 3: Manual verify** — start two repos' dashboards; the switcher lists both; clicking the other navigates. (No unit test — SPA navigation; verify live.)
- [ ] **Step 4: Commit** `feat(dashboard): top-left switches repos (workspaces) instead of investigations`

---

## Task 5: Per-investigation report serving (TDD)

**Files:** Modify `server.py` report route (~4587); Test `tests/test_iset_nested.py` (append).

- [ ] **Step 1: Failing test** — request the per-investigation report path; assert it serves `investigations/<slug>/reports/index.html` when present (write a stub file), 404 otherwise.
- [ ] **Step 2: Run — expect FAIL** (route serves repo-level `reports/index.html`).
- [ ] **Step 3: Implement** a `GET /api/iset/<slug>/report` (or `/reports/<slug>/`) route that serves `workspace_paths().investigations / slug / "reports" / "index.html"`. Add a `report_dir(inv_slug)` helper to `WorkspacePaths` (both copies) returning `investigations/<slug>/reports`.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** `feat(dashboard): per-investigation report route (investigations/<slug>/reports/)`

---

## Task 6: List-first UX + studies-sidebar sync verification

**Files:** `walkthrough.js` (`_switchPage('investigations')` shows list; selection → `_openInvestigationDetail` + `publishCurrentSlug`).

- [ ] **Step 1:** Ensure entering the Investigations page shows the LIST (`#investigations-list` visible, detail hidden) until a card is clicked; clicking a card calls `_openInvestigationDetail(name)` AND `window._currentIsetSlug = name; _renderRailInvestigationGroups()` so the Studies sidebar syncs. (Most exists; wire the `_currentIsetSlug` set on card-click.)
- [ ] **Step 2: Manual verify** — list → click → detail + sidebar shows that investigation's nested studies. Empty sidebar before selection.
- [ ] **Step 3: Commit** `feat(dashboard): list-first Investigations UX + studies sidebar sync on select`

---

## Task 7: Green + push (no merge)

- [ ] **Step 1:** `.venv/bin/python -m pytest tests/test_iset_nested.py tests/test_iset_endpoints.py tests/test_investigation_registry.py -q` → PASS. Note any pre-existing failures (polars/build) unchanged.
- [ ] **Step 2:** `git push origin feat/dashboard-investigation-nav`
- [ ] **Step 3:** Open draft PR (base `feat/nested-study-resolution`, stacked) referencing the spec; summarize nested resolution + repo switcher + badges + labels + per-investigation reports.

---

## Self-Review
- Spec coverage: nested resolution (T1), badges (T2), label (T3), repo switcher (T4), per-investigation reports (T5), list+sync (T6). ✓
- Placeholders: T1/T2/T5 carry test+impl code; T3/T4/T6 are template/SPA edits specified against exact anchors (manual-verify where unit tests don't fit vanilla-JS navigation).
- Type consistency: `study_dir`/`report_dir` match Phase 1; `lifecycle` field used consistently (T2).
