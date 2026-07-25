# Feedback-YAML track + surface (spine stage #3c) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Consolidate the scattered report-feedback YAMLs into a **tracked, status-bearing index per study** and surface it on the study-detail page. Today `load_investigation_feedback` merges the `annotations` across the ~12 `investigations/<inv>/feedback-*/feedback.yaml` files but **ignores the `responses` block** (which carries `status: done` + the answer) — so an addressed item looks identical to an open one. 3c derives per-item status (open / addressed / dismissed) and renders it. (Per the dashboard-AI-free principle: the consolidation is plain Python in pbg-superpowers; the dashboard only renders it.)

**Architecture:** (a) pbg-superpowers `feedback_tracking.py`: `study_feedback_tracked(workspace, study_slug)` reads BOTH `annotations` and `responses` across all feedback files (reuse `feedback_import._feedback_files`), matches the study's sections (`study-<slug>` prefix, like `feedback_for_study`), and returns a tracked list + summary. (b) vivarium-workbench: surface the tracked index on study-detail (status badges + open/addressed/dismissed counts), reading the new function. Pure render.

**Feedback YAML shape (real):** `meta{investigation, report_id, generated_at}`, `annotations{<section_id>: [{ts, author, text}]}`, `responses{<section_id>: {status, by, at, response}}`.

**Status derivation:** for each annotation item, status = `addressed` if its section has a `responses[section]` with `status` in {done, addressed, resolved}; `dismissed` if the section response `status` is `dismissed`/`wontfix`; else `open`. Attach the section's response (text/by/at) to addressed items.

**Tech:** Python 3.11+, pytest. `.venv/bin/python`.

---

## File map
- Create: `viva_superpowers/feedback_tracking.py`.
- Test: `tests/test_feedback_tracking.py`.
- Modify (dashboard): `vivarium_workbench/server.py` (`_collect_study_feedback` → tracked, or a new study-detail field) + `static/study-detail.js` (+/or `templates/study-detail.html`) for the render. Test: `tests/` mirror.

---

## Task 1: `study_feedback_tracked` (pbg-superpowers)
- [ ] **Step 1: Failing tests** (`tests/test_feedback_tracking.py`) — build a tmp workspace with `investigations/<inv>/feedback-<ts>/feedback.yaml` files containing `annotations` for sections `study-foo`, `study-foo-charts`, `study-bar`, and a `responses: {study-foo-charts: {status: done, by: claude, at: ..., response: ...}}`. `study_feedback_tracked(ws, "foo")` returns `{items: [...], summary: {open, addressed, dismissed, total}}` where each item = `{section, ts, author, text, status, response?, responded_by?, responded_at?, report_id}`, newest-first; the `study-foo-charts` items are `addressed` with the response attached, `study-foo` items are `open`, `study-bar` excluded. A `dismissed` section response → `dismissed`. Summary counts correct.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — reuse `feedback_import._feedback_files(inv_dir)` to enumerate files; per file read `annotations` + `responses`; aggregate by section (newest-first by ts); match `study-<slug>` sections; derive status per the rules above; build items + summary. Iterate over ALL investigations in the workspace (a study's feedback could be under its investigation — match by section prefix like `_collect_study_feedback` does). Pure, tolerant (skip malformed files, like the existing reader).
- [ ] **Step 4: Run → pass.** **Step 5: Golden (skipif absent):** run against the real `/Users/eranagmon/code/v2e-invest` workspace for a dnaa study with real feedback (e.g. `dnaa-3-box-binding`); assert it returns tracked items with a mix of statuses (the real feedback has `responses` with `status: done`) and a sane summary. READ-ONLY — never modify v2e-invest. **Commit** — `feat(feedback_tracking): study_feedback_tracked with per-item status`

## Task 2: Surface on study-detail (vivarium-workbench, render only)
- [ ] **Step 1:** Branch `feat/feedback-tracking-render` off origin/main. Find where feedback is currently surfaced: `server.py:_collect_study_feedback` (~1473) attaches `spec["expert_feedback"]`; find where the study-detail page renders it (study-detail.js / study-detail.html / or it isn't rendered there yet). 
- [ ] **Step 2: Failing test** (Python, mirror `test_study_detail_page.py`) — the study-detail data/spec now carries the tracked feedback (`study_feedback_tracked` output) with `status` + `summary`; assert the served data includes it.
- [ ] **Step 3: Implement** — `_collect_study_feedback` (or a new field, e.g. `spec["feedback_tracked"]`) calls `viva_superpowers.feedback_tracking.study_feedback_tracked` (defensive import). In `study-detail.js` (or the template), render a **Feedback** panel: a summary line (`<O> open / <A> addressed / <D> dismissed`) + the items with a status badge each (open=highlight, addressed=muted + show the response, dismissed=muted-strike). Escape all text. Render nothing when there's no feedback. NO AI — pure render of the tracked data.
- [ ] **Step 4:** Run the touched dashboard tests green. **Step 5: Commit** — `feat(study-detail): render tracked feedback with status`

---

## Self-Review
- Goal: consolidate scattered feedback + per-item status (T1) + surface on study-detail (T2). User chose "track + surface with status" (no auto-mutation of study content).
- Constraint: consolidation is plain pbg-superpowers Python; dashboard only renders (no AI). The existing `load_investigation_feedback` (annotations-only) is left intact for back-compat; this is additive.
- Status derivation is conservative (open unless a section response marks it done/dismissed); never fabricates a response.
- Types: `study_feedback_tracked(workspace, study_slug) -> {"items": list[dict], "summary": {open,addressed,dismissed,total}}`.

## Notes for executor
- `.venv/bin/python -m pytest`. Reuse `feedback_import._feedback_files` + the `study-<slug>` matching from `feedback_for_study`/`_collect_study_feedback`.
- Real v2e-invest READ-ONLY (golden + dashboard tests use it read-only or tmp fixtures).
- Dashboard `main` may be checked out in a worktree (`vivarium-workbench-pdmp`); create the branch off `origin/main` in the main `vivarium-workbench` checkout (a new branch != main, so it won't conflict with the worktree).
- Render mirrors the recently-added computed-outcomes panel in `study-detail.js` (idempotent sibling node, escaped, only-when-present).
