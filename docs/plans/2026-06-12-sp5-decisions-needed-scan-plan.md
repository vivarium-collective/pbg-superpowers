# SP5 — Guide layer: the "decisions needed" scan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, **Layer 3 (Guide)** — the capstone. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`. Builds on SP1–SP4 (all merged).

**Goal:** One pure, deterministic **"decisions needed" scan** that AGGREGATES the divergences/gaps SP1–SP4 already compute — it makes NO new judgment, it gathers + ranks existing signals — into a single per-investigation list, surfaced as a dashboard "needs attention" panel and led-with by the navigate skill. This is what makes the framework *actively* point the investigator at the next decision.

**The six signals (all reuse — see the grounding):**
| # | Signal | Source (reuse, do NOT reimplement) | Severity | Build? |
|---|---|---|---|---|
| 1 | Uncovered acceptance criterion (no `study:` link) | `linkage_index.ac_gating_matrix(ws, inv)["gaps"]` | high | no |
| 2 | Computed-vs-authored verdict divergence | per-study `pipeline_gate.gate_evaluator.diverges_from_authored` + per-test `computed_outcomes[t]["reconcile"]=="divergent"` (READ what `sync` persisted — do NOT recompute/write) | high | no |
| 3 | Unaddressed expert feedback | `feedback_actions.study_feedback_actions(ws, slug)["summary"]["open"]` / `items[].status=="open"` | medium | no |
| 4 | Phantom / not-in-structure observable | `readout_validation.validate_readouts(spec, …, available=…)` → `status=="not_in_structure"` | high | **opt-in** |
| 5 | Param drift (enforced param not honored by a run) | SP1's per-run resolver (`investigation_status`/`param_enforcement` — `resolve_run_expected` or equiv) → `param_enforcement.check_enforced_params(declared, applied)` violations | high | no |
| 6 | Stale finding (no `next_action`, or `next_action` set but never seeded) | **greenfield classifier** over `findings[].{next_action, seeded_study, status}` | low | no |

**Isolation invariant (SP4b lesson):** the scan is PURE/cheap by DEFAULT — signals 1,2,3,5,6 read YAML only. Signal 4 (phantom observable) needs a composite build, so it is **opt-in** behind an INJECTED `observables_for_ref` (the dashboard supplies its cached `_observables_for_ref`); `scan_investigation(...)` with no `observables_for_ref` runs build-free and simply omits signal 4.

**Tech:** Python + JS; pytest. Repos: pbg-superpowers (the aggregator + skill) + vivarium-workbench (endpoint + panel). `.venv/bin/python`. **AI-free** (the scan is deterministic aggregation; dashboard renders; no model judgment). The output is EPHEMERAL — never written back to YAML.

**Reuse anchors (confirmed by grounding):** `linkage_index.ac_gating_matrix`, `feedback_actions.study_feedback_actions`, `readout_validation.validate_readouts`/`available_observables`, `param_enforcement.check_enforced_params`, `investigation_status.roll_up_acceptance` (the canonical investigation-level entry point) + `WorkspacePaths`/`study_io` + `linkage_index._iter_studies` for member iteration.

---

## Task 1: `needs_attention.scan_investigation` — the pure aggregator (signals 1,2,3,5,6)

**Files:** Create `viva_superpowers/needs_attention.py`; Test `tests/test_needs_attention.py`.

**The item shape (one normalized dict per finding-of-attention):**
```python
{
  "kind": "uncovered_ac" | "verdict_divergence" | "open_feedback" | "param_drift" | "stale_finding" | "phantom_observable",
  "severity": "high" | "medium" | "low",
  "study": str | None,          # the member study slug, when study-scoped
  "ref": str,                   # the specific thing (AC behavior / test name / item_id / param / finding id / readout)
  "title": str,                 # one-line human summary
  "detail": str,                # the specifics (expected vs actual, the open feedback text, etc.)
  "action_hint": str,           # the suggested next move, e.g. "link or author a study", "reconcile verdict", "apply or dismiss feedback", "re-run / update enforcement", "draft next_action / seed", "fix the readout"
}
```

- [ ] **Step 1: Failing tests** (build small tmp workspaces with `study_io`; reuse the fixture style in `tests/test_linkage_index.py`):
```python
from viva_superpowers.needs_attention import scan_investigation, _stale_findings

def test_uncovered_ac_surfaces_high(tmp_inv_with_unlinked_ac):
    res = scan_investigation(ws, "inv")
    acs = [i for i in res["items"] if i["kind"] == "uncovered_ac"]
    assert acs and acs[0]["severity"] == "high"

def test_open_feedback_surfaces_medium(tmp_inv_with_open_feedback):
    res = scan_investigation(ws, "inv")
    assert any(i["kind"] == "open_feedback" and i["severity"] == "medium" for i in res["items"])

def test_verdict_divergence_read_from_persisted_flag(tmp_inv_study_diverges):
    # study has pipeline_gate.gate_evaluator.diverges_from_authored: true (already persisted by sync)
    res = scan_investigation(ws, "inv")
    assert any(i["kind"] == "verdict_divergence" and i["study"] == "s1" for i in res["items"])

def test_stale_finding_classifier(tmp_study_findings):
    # F-01 has next_action but no seeded_study → stale; F-02 has neither → stale; F-03 next_action+seeded_study → NOT stale
    stale = {f["id"] for f in _stale_findings(spec)}
    assert stale == {"F-01", "F-02"}

def test_param_drift_surfaces_when_run_violates(tmp_inv_run_param_drift):
    res = scan_investigation(ws, "inv")
    assert any(i["kind"] == "param_drift" and i["severity"] == "high" for i in res["items"])

def test_scan_is_pure_no_writes(tmp_inv_with_unlinked_ac):
    before = _snapshot(ws); scan_investigation(ws, "inv"); assert _snapshot(ws) == before

def test_scan_build_free_by_default_omits_phantom(tmp_inv_with_phantom_readout):
    res = scan_investigation(ws, "inv")  # no observables_for_ref → no build, no phantom items
    assert not any(i["kind"] == "phantom_observable" for i in res["items"])

def test_summary_ranks_by_severity(tmp_inv_mixed):
    res = scan_investigation(ws, "inv")
    sev = [i["severity"] for i in res["items"]]
    assert sev == sorted(sev, key=lambda s: {"high":0,"medium":1,"low":2}[s])  # high first
    assert res["summary"]["by_severity"]["high"] >= 1 and res["summary"]["total"] == len(res["items"])
```
- [ ] **Step 2: fail. Step 3: implement** `scan_investigation(ws_root, inv_slug, *, observables_for_ref=None) -> {"investigation": slug, "items": [...], "summary": {"by_severity": {...}, "by_kind": {...}, "total": int}}`:
  - Resolve member studies from the investigation spec (`investigation.yaml` `studies:`), iterate via `linkage_index._iter_studies` filtered to members (or `WorkspacePaths`).
  - **Signal 1:** `ac_gating_matrix(ws, inv)["gaps"]` → one `uncovered_ac` item per gap (`ref`=behavior, `study`=None, high).
  - **Signal 2:** per member study, READ `spec["pipeline_gate"]["gate_evaluator"]["diverges_from_authored"]` (if truthy → one `verdict_divergence` item, `ref`=study) AND scan persisted `computed_outcomes[*][test]["reconcile"]=="divergent"` if present (one item per divergent test, `ref`=test name). READ ONLY — never call `write_gate_evaluator` / recompute.
  - **Signal 3:** `study_feedback_actions(ws, slug)` → for each `items[]` with `status=="open"`, one `open_feedback` item (`ref`=item_id, `detail`=text, medium). Tolerant if the study has no feedback.
  - **Signal 5:** for each run with a declared baseline/variant, reuse SP1's per-run param resolver (find it: `investigation_status`/`param_enforcement` — `resolve_run_expected` or the function `populate_enforced_params` builds on) to get declared vs applied, then `check_enforced_params(declared, applied)` → one `param_drift` item per `ParamViolation` (`ref`=param, `detail`=expected/actual, high). BEST-EFFORT: if declared/applied can't be assembled for a study, skip it (no crash) — param drift is the most fragile signal.
  - **Signal 6:** `_stale_findings(spec)` (greenfield) → a finding is stale when `next_action` absent/empty AND no `seeded_study`, OR `next_action` present but `seeded_study` absent. Skip findings whose `status` marks them terminal/accepted if such a status exists. One `stale_finding` item per stale finding (`ref`=finding id, low).
  - Each signal wrapped so one failing source never sinks the whole scan (best-effort per signal, like `linkage_index`'s per-study tolerance).
  - Sort items by severity (high→medium→low) then kind then ref (stable/deterministic). Build `summary`.
- [ ] **Step 4: pass. Step 5: commit** — `feat(needs-attention): pure decisions-needed scan aggregating SP1-4 signals (build-free)`

## Task 2: opt-in phantom-observable signal (the only build-requiring source)

**Files:** `viva_superpowers/needs_attention.py`; Test `tests/test_needs_attention.py`.

- [ ] **Step 1: Failing test** (inject a STUB `observables_for_ref` — no real build):
```python
def _stub_obs(ref):  # composite emits only cell_mass; a study readout references a phantom
    return {"leaves": ["agents.0.listeners.mass.cell_mass"], "catalogs": {}}

def test_phantom_observable_opt_in(tmp_inv_with_phantom_readout):
    res = scan_investigation(ws, "inv", observables_for_ref=_stub_obs)
    assert any(i["kind"] == "phantom_observable" and i["severity"] == "high" for i in res["items"])
```
- [ ] **Step 2: fail. Step 3: implement.** When `observables_for_ref` is provided, for each member study: resolve its composite ref (reuse `linkage_index._composites_of_study`), call `observables_for_ref(ref)` → `{leaves, catalogs}`, pass as `available=` to `readout_validation.validate_readouts(spec, available=...)`, and emit a `phantom_observable` item for each result with `status=="not_in_structure"` (`ref`=readout name, high). Tolerant: a build that raises skips that study (the SP4b isolation pattern — match `enrich_observable_edges`'s try/except). NOTE the lineage-prefix lesson is already handled inside `validate_readouts`/`available_observables` per SP2b-i — do not re-normalize.
- [ ] **Step 4: pass. Step 5: commit** — `feat(needs-attention): opt-in phantom-observable signal behind injected build`

## Task 3: `/pbg-navigate decisions <inv>` subcommand (lead-with-it)

**Files:** Modify `skills/pbg-navigate/SKILL.md`; Test `tests/test_navigate_skill.py`.

- [ ] **Step 1:** Add a `decisions <inv>` (alias the framing — "needs attention") subcommand to `skills/pbg-navigate/SKILL.md`: prints the ranked decisions-needed scan (`scan_investigation`), grouped by severity, each line `kind · study/ref · action_hint`. CLI form via `needs_attention.scan_investigation(".", inv)`; dashboard form `GET /api/needs-attention?investigation=<inv>`. AI-free pure query. Note signal 4 is build-gated/optional. The skill's intro should say a navigator should LEAD with this scan (it's the "what needs my decision" entry point).
- [ ] **Step 2:** Extend `tests/test_navigate_skill.py` to assert `decisions` + `scan_investigation` + `/api/needs-attention` are named.
- [ ] **Step 3: pass. Commit** — `feat(pbg-navigate): decisions subcommand — lead with the needs-attention scan`

## Task 4: Dashboard — `/api/needs-attention` + the "needs attention" panel (vivarium-workbench)

**Files:** (vivarium-workbench, branch `feat/sp5-needs-attention-dashboard` off origin/main) `server.py` (a new `_needs_attention` worker + dispatch + `_needs_attention_test` seam, modeled on SP4b's `_linkage_index`), the investigation-detail JS (find where the investigation page renders — grep `investigation` in `static/`), `static/walkthrough.js` (report). Use its `.venv`.

- [ ] **Step 1: Failing test** — `/api/needs-attention?investigation=<inv>` returns the ranked scan (pure path; monkeypatch any build away).
```python
def test_needs_attention_endpoint(tmp_v2ecoli_inv):
    body, code = server.Handler._needs_attention_test(ws, investigation="inv")
    d = json.loads(body); assert code == 200
    assert "items" in d and "summary" in d
```
- [ ] **Step 2: fail. Step 3: implement.** `_needs_attention(ws_root, *, investigation)` → `needs_attention.scan_investigation(ws_root, investigation)` (lazy import, tolerant → empty-typed payload at 200, never 500). DEFAULT build-free; if you choose to include phantom observables, inject the cached `_observables_for_ref` adapter exactly like SP4b's `_obs_for_ref` (reuse that pattern — `_observables_for_ref` returns `(bytes,status)`, normalize to dict) — but default the endpoint to build-free unless `?observables=1` is passed (cheap by default). Render a **"Needs attention"** panel on the investigation-detail page: a severity-ranked list (high items first, color-coded), each row `kind · study/ref · action_hint`, collapsible like the readiness panel (`<details>` with the high-severity count on top — follow the readiness-panel dropdown pattern). Empty scan → a quiet "✓ nothing needs attention" state. The dashboard NEVER computes the signals — it renders `scan_investigation`'s output (AI-free). Report (walkthrough.js): a compact decisions-needed section.
- [ ] **Step 4: pass. `node -c` clean on touched JS. Step 5: commit** — `feat(server): /api/needs-attention + investigation needs-attention panel`

## Task 5: Golden + manual

- [ ] **Step 1 (golden, skipif v2e-invest absent, READ-ONLY):** `scan_investigation("/Users/eranagmon/code/v2e-invest", "<a real investigation slug>")` returns a ranked items list + summary over the real dnaa investigation WITHOUT writing (snapshot before/after byte-identical); assert the chromosome-cycle-calibration uncovered-AC gap (the known SP4a live gap — 5 unlinked ACs) shows up as `uncovered_ac` high items. v2e-invest untouched.
- [ ] **Step 2:** new tests green; suites no new failures (record the pre-existing baseline first). **MANUAL VERIFY (pending):** serve v2e-invest; the investigation page shows the Needs-attention panel led by the uncovered-AC gap; `/pbg-navigate decisions <inv>` prints the same ranked list.
- [ ] **Step 3: commit** — `test(needs-attention): decisions-scan golden + suite`

---

## Self-Review
- Coverage: the pure 5-signal aggregator (T1), the opt-in phantom signal (T2), the navigate subcommand (T3), the dashboard endpoint+panel (T4), golden+manual (T5). Matches SP5 (Guide), completes the Active Investigation Framework.
- AI-free: deterministic aggregation in pbg-superpowers; the dashboard renders; the skill leads-with-it. No new judgment — every signal is an EXISTING SP1–4 computation, gathered + ranked.
- Isolation: build-free by default (signals 1,2,3,5,6); signal 4 is opt-in behind the injected build (SP4b pattern). Output EPHEMERAL.
- Reuse: ac_gating_matrix (SP4a), study_feedback_actions (SP3b), validate_readouts (SP2b), check_enforced_params (SP1), persisted divergence flags (spine). Only the stale-finding classifier is new.

## Notes for the executor
- `.venv/bin/python -m pytest`. REUSE the named functions — do NOT recompute verdicts (read the persisted `diverges_from_authored` flag / `reconcile` field), do NOT reimplement AC roll-up, feedback aggregation, readout validation, or param checking.
- Best-effort PER SIGNAL: one source raising must not sink the scan (mirror `linkage_index`'s per-study tolerance). Param drift (signal 5) is the most fragile — skip a study whose declared/applied can't be assembled rather than failing.
- Signal 2 reads what `study_outcomes.sync` already persisted; if neither the flag nor `computed_outcomes` is present (un-synced study), simply emit nothing for that study — do NOT trigger a sync.
- Build-free by default; phantom observables only when `observables_for_ref` is injected. Match `enrich_observable_edges`'s tolerant try/except for the build.
- Don't modify the real v2e-invest; golden read-only.
