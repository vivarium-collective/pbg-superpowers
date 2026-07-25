# SP3b — feedback → design (close the loop) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 1 / SP3 (reflexive loops), piece b — closes the OPEN feedback loop. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`. Joins SP3a (merged) at `findings[].next_action`.

**Goal:** Make imported expert feedback ACTIONABLE — a feedback item becomes a tracked proposed action (write a finding's `next_action`, draft a finding, propose a design edit, or seed a study) that can be applied and tracked open→applied. Today feedback is imported + displayed but dead-ends at a free-text status string.

**The open half (grounding):** `feedback_import.py` imports `investigations/<inv>/feedback/<ts>.yaml` (`{meta, annotations:{section:[{author,text,ts}]}, responses:{section:{status,by,at,response}}}`); `feedback_tracking.study_feedback_tracked` (:43) aggregates + derives status from `responses` (`_derive_status` :31). NOTHING writes `responses` or links feedback→finding/next_action — the loop dead-ends. SP3b adds a deterministic, tracked `actions:` surface parallel to `responses`, with apply primitives.

**Tech:** Python + JS; pytest. Repos: pbg-superpowers (the mechanism + skill) + vivarium-workbench (the panel + apply API). `.venv/bin/python`.

**AI-free split:** deterministic `feedback_item_id` + `study_feedback_actions` aggregation + `apply_feedback_action` primitives in pbg-superpowers (dashboard renders + an Apply button POSTs); the AI judgment (which action kind, the proposed_text) is in the `/pbg-study feedback-respond` skill.

---

## Task 1: `feedback_item_id` + `study_feedback_actions` aggregator (pbg-superpowers, pure)

**Files:** Create `viva_superpowers/feedback_actions.py`; Test `tests/test_feedback_actions.py`.

- [ ] **Step 1: Failing tests.**
```python
from viva_superpowers.feedback_actions import feedback_item_id, study_feedback_actions

def test_feedback_item_id_stable():
    a = feedback_item_id("study-s1", "2026-06-10T00:00", "alice")
    assert a == feedback_item_id("study-s1", "2026-06-10T00:00", "alice")  # stable hash
    assert a != feedback_item_id("study-s1", "2026-06-10T00:00", "bob")

def test_study_feedback_actions_joins_annotation_and_action(tmp_inv_with_feedback_and_action):
    # feedback yaml: annotations for study-s1 + an actions: block keyed by item_id
    res = study_feedback_actions(ws, "s1")
    it = res["items"][0]
    assert it["item_id"] and it["text"] and it["status"] in ("open","applied","dismissed")
    assert it["action"]["kind"] in ("next_action","finding","design-edit","study-seed")  # when present
    assert "open" in res["summary"]
```
- [ ] **Step 2: fail. Step 3: implement** `feedback_item_id(section, ts, author) -> str` (stable hash) and `study_feedback_actions(ws_root, slug) -> {items:[{item_id, section, ts, author, text, action?:{kind,target_finding?,proposed_text,by,at}, status}], summary:{open,applied,dismissed,total}}` — mirror `study_feedback_tracked`: read the feedback files, match `study-<slug>` annotations, join each with its `actions[item_id]` entry (a NEW block in the feedback yaml), derive status (open if no action / action.status). PURE read — no writes. Reuse `feedback_import._feedback_files`.
- [ ] **Step 4: pass. Step 5: commit** — `feat(feedback-actions): feedback_item_id + study_feedback_actions aggregator (pure)`

## Task 2: `apply_feedback_action` primitives (pbg-superpowers)

**Files:** `viva_superpowers/feedback_actions.py`; Test `tests/test_feedback_actions.py`.

- [ ] **Step 1: Failing test** — applying a `kind: next_action` action writes the finding's `next_action` (the SP3a join) + flips the action to `applied`:
```python
def test_apply_next_action_writes_finding_next_action(tmp_inv_with_action):
    # action = {item_id, kind: next_action, target_study: s1, target_finding: F-01, proposed_text: "test X"}
    from viva_superpowers.feedback_actions import apply_feedback_action
    res = apply_feedback_action(ws, item_id)
    spec = _read_study_yaml(ws, "s1")
    f = next(f for f in spec["findings"] if f["id"] == "F-01")
    assert f["next_action"] == "test X"              # written → now seedable via SP3a
    assert _action_status(ws, item_id) == "applied"  # tracked
    # idempotent: re-apply is a no-op
    assert apply_feedback_action(ws, item_id)["already_applied"] is True
```
- [ ] **Step 2: fail. Step 3: implement** `apply_feedback_action(ws_root, item_id) -> dict`: look up the action; dispatch by kind — `next_action` → write `findings[<target_finding>].next_action = proposed_text` via the atomic `study_io` ruamel writer (fill-absent / overwrite-with-confirm? — fill the finding's next_action; this is the SP3a join point); `study-seed` → call `seed_from_followup.resolve_seed_source`+`write_child_study` (SP3a); `finding` → draft a new finding stub; `design-edit` → record the proposed edit as a tracked note (no silent design mutation). Flip the action's `status: applied` (by/at) in the feedback yaml. IDEMPOTENT (re-apply → no-op). Best-effort + clear errors.
- [ ] **Step 4: pass. Step 5: commit** — `feat(feedback-actions): apply_feedback_action — next_action/finding/design-edit/study-seed primitives (joins SP3a)`

## Task 3: `/pbg-study feedback-respond` skill (the AI judgment)

**Files:** `skills/pbg-study/SKILL.md`; Test: structural guard.

- [ ] **Step 1:** Add a `feedback-respond <slug>` subcommand to `skills/pbg-study/SKILL.md`: read the tracked-OPEN feedback items (`study_feedback_actions`); for each, the agent PROPOSES the `kind` (which action best addresses it) + the `proposed_text` (which finding's next_action it becomes / what edit / whether to seed) — the judgment — and writes the `actions[item_id]` entry to the feedback yaml (a deterministic `record_feedback_action` helper, or via the existing feedback writer). Then optionally `apply_feedback_action`. Never silently mutate design — propose + (user/agent) apply. Reference `docs/conventions/handling-investigation-feedback.md` (the "map each point to an action" step, now persisted as a tracked artifact).
- [ ] **Step 2:** Add `tests/test_feedback_respond_skill.py` asserting `skills/pbg-study/SKILL.md` names `feedback-respond` + `study_feedback_actions` + `apply_feedback_action`.
- [ ] **Step 3: pass. Commit** — `feat(pbg-study): feedback-respond subcommand — turn open feedback into tracked actions`

## Task 4: Dashboard — feedback→action panel + Apply (vivarium-workbench)

**Files:** (vivarium-workbench, branch `feat/sp3b-feedback-dashboard` off origin/main) `server.py` (a new `/api/feedback-apply-action` + surface `study_feedback_actions` on the spec), `static/study-detail.js` (`_renderFeedbackTrackedPanel` ~:981), `static/walkthrough.js` (report table). Use its `.venv`.

- [ ] **Step 1: Failing test** — `/api/feedback-apply-action` applies an action via the pbg primitive.
```python
def test_feedback_apply_action_endpoint(tmp_inv_with_action):
    body, code = server.Handler._feedback_apply_action_test({"workspace": ws, "item_id": item_id})
    assert code == 200 and json.loads(body).get("applied")
```
- [ ] **Step 2: fail. Step 3: implement.** Surface `study_feedback_actions` on `_study_detail_spec` (read-only, beside `feedback_tracked`). Add `POST /api/feedback-apply-action` → `apply_feedback_action` (lazy import, tolerant). Extend `_renderFeedbackTrackedPanel` (study-detail.js) to show each item's proposed action (kind + proposed_text) + an open/applied badge + an **Apply** button POSTing the item_id. The dashboard NEVER computes the action — it renders the pbg data + applies via the primitive (AI-free). Report (walkthrough.js): a per-study feedback→action table.
- [ ] **Step 4: pass. `node -c` clean. Step 5: commit** — `feat(server): /api/feedback-apply-action + feedback->action panel/badge/Apply button`

## Task 5: Golden + manual

- [ ] **Step 1 (golden, skipif v2e-invest absent, READ-ONLY → tmp copy):** a feedback item with a `kind: next_action` action → `apply_feedback_action` on a TMP copy writes the finding's next_action + flips the action applied; the real v2e-invest untouched. `study_feedback_actions` on a real investigation returns the items+summary.
- [ ] **Step 2:** new tests green; suites no new failures (pre-existing via base). **MANUAL VERIFY (pending):** serve v2e-invest; an open feedback item shows its proposed action + Apply; applying a `next_action` writes the finding's next_action (then SP3a's Seed-from-finding button can originate a study — the closed loop).
- [ ] **Step 3: commit** — `test(feedback-actions): golden + suite`

---

## Self-Review
- Coverage: aggregator (T1), apply primitives joining SP3a (T2), responder skill (T3), dashboard panel+apply (T4), golden+manual (T5). Matches SP3b.
- AI-free: the tracking + apply are deterministic in pbg-superpowers; the dashboard renders + applies via the primitive; the judgment (kind/proposed_text) is in the skill.
- The closed loop: feedback → action (kind:next_action) → `findings[].next_action` → SP3a seeds a study. The reflexive loop is complete.
- Rendering structural-tested + manual.

## Notes for the executor
- `.venv/bin/python -m pytest`. REUSE `feedback_import._feedback_files`, the `study_io` atomic writer, and SP3a's `seed_from_followup` (for kind:study-seed). Mirror `study_feedback_tracked` for the aggregator. The `actions:` block is a NEW top-level key in the feedback yaml (parallel to `responses`), keyed by `feedback_item_id`.
- The apply writes are code-owned + idempotent + ruamel comment-preserving; never silently mutate design beyond the action's explicit target.
- Don't modify the real v2e-invest; goldens use a tmp copy.
