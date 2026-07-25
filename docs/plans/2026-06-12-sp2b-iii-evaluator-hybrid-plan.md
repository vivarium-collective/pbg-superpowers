# SP2b-iii — Evaluator/Resolver Hybrid (verdict-safe) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 1 / SP2b (readout vocabulary), piece iii — the verdict-safe slice. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** Fold the duplicated literal-index regex into the canonical `readout_resolver` by routing **element-kind** readouts through it in `study_evaluator._resolve_series`, while keeping scalar/expression/bare-bulk/prose on the existing body — a **fallback-hybrid** with **ZERO verdict change**.

**Why narrow (grounding verdict):** full unification is NOT verdict-safe — the resolver gives up on bare bracket bulk ids (`MONOMER0-160[c]`, which the evaluator resolves) and strips trailing prose to scalar (which the evaluator correctly rejects); both would flip verdicts. The tokenizer PRIMITIVES are already single-sourced (the resolver imports the evaluator's `_BRACKET_ID`/`_DOTTED_IDENT`/`_extract_observable_tokens`). The only safe remaining win is the literal-index regex dedup. Do NOT route scalar/expression through the resolver (its `to_select_dict()` is `None` for those; the evaluator's series-reading + `_eval_expression` must stay).

**THE SAFETY NET (hard gate):** the evaluator suite must stay **byte-identical** — `1 failed, 99 passed` across `tests/test_study_evaluator.py test_study_evaluator_golden.py test_study_evaluator_readouts_golden.py test_study_evaluator_via_readouts.py test_readout_resolver.py`. The 1 failure (`test_golden_study_tests_all_agent_bucketed`) is a pre-existing STALE golden unrelated to SP2b-iii — leave it in that same failing state (do not "fix" or further change it). ANY movement in the 99/1 count = verdict drift = stop.

**Tech:** Python, pytest. Repo: pbg-superpowers only. `.venv/bin/python`.

**Anchors:** `_LITERAL_INDEX_PATH_RE` (study_evaluator.py:235, duplicates the resolver's `_LITERAL_INDEX_RE`); `_resolve_series` :240; the literal-index fast path :270-281 (the ONLY block to change); `resolve_readout` + `ResolvedReadout.to_select_dict` in `readout_resolver.py`.

---

## Task 1: Route element-kind through `resolve_readout`; dedup the literal-index regex

**Files:** Modify `viva_superpowers/study_evaluator.py`; Test `tests/test_study_evaluator_via_readouts.py` (+ the goldens as the net).

- [ ] **Step 1: Failing/characterizing test.** Confirm a literal-index path resolves via the resolver path and produces the SAME selector:
```python
def test_literal_index_routes_through_resolver(real_run_reader):
    # path "listeners.monomer_counts[3]" → resolve_readout element → reader.select(to_select_dict())
    df = se._resolve_series("listeners.monomer_counts[3]", real_run_reader)
    # same series the old literal-index fast path produced (compare to a select({type:literal_index,value:3,observable:...}))
    assert df is not None and len(df)  # element resolved + read
def test_bare_bulk_id_still_resolves_via_fallback(real_run_reader):
    # the resolver gives up on a bare bracket bulk id; the evaluator body must still resolve it (no regression)
    df = se._resolve_series("MONOMER0-160[c]", real_run_reader)
    assert df is not None  # branch C fallback, unchanged
```
- [ ] **Step 2: Run** (the literal-index one may pass already via the old path; the point is it goes through the resolver after Step 3 and stays equivalent).
- [ ] **Step 3: Implement.** At `_resolve_series` :270-281, replace the `_LITERAL_INDEX_PATH_RE.match` fast path with: `r = resolve_readout({'identifier': path.strip()})`; if `isinstance(r, ResolvedReadout) and r.kind == "element"` → `return _normalize(reader.select(r.to_select_dict()))` (matching whatever the old block returned — same select dict, same post-processing). Otherwise FALL THROUGH to the existing tokenize/series/expression body (:283-310) UNCHANGED. Delete `_LITERAL_INDEX_PATH_RE` (:235) if now unused (grep first); import `resolve_readout`/`ResolvedReadout` from `readout_resolver`. Do NOT touch the scalar/series/`_try_select_fallback`/`_eval_expression` paths.
- [ ] **Step 4: Run the literal-index + bare-bulk tests → pass.**
- [ ] **Step 5: THE GATE — run the full evaluator net** and confirm EXACTLY `1 failed, 99 passed` (same set), the 1 being the stale `test_golden_study_tests_all_agent_bucketed`. If the count moves → revert and stop (verdict drift).
- [ ] **Step 6: Commit** — `feat(study-evaluator): route element-kind readouts through readout_resolver (dedup literal-index regex); scalar/expr/bulk/prose unchanged — verdict-safe`

## Task 2: Confirm zero verdict change + the dialect note

**Files:** docstring in `study_evaluator.py`; Test: the net.

- [ ] **Step 1:** Add a short docstring/comment at `_resolve_series` documenting the hybrid: element-kind via the canonical resolver; scalar/expression/bare-bulk/prose deliberately on the local body because the resolver (a) returns `Unresolved` for bare bracket bulk ids and (b) strips prose — routing them would change verdicts. Reference the SP2b-iii grounding.
- [ ] **Step 2: Full pbg-superpowers suite** — no new failures beyond the pre-existing 2 (`test_expert_search` cache + the stale `test_golden_study_tests_all_agent_bucketed`). The ATP-fraction readouts golden (`test_study_evaluator_readouts_golden`) MUST stay green (the canary). **Commit** — `docs(study-evaluator): document the verdict-safe element-only resolver hybrid`

---

## Self-Review
- Coverage: element-kind routed through the resolver + literal-index regex deduped (T1); zero-verdict-change confirmed + documented (T2). Matches the chosen narrow scope.
- Safety: the goldens (esp. the ATP-fraction canary) stay byte-identical; scalar/expression/bulk/prose paths untouched. Any 99/1 movement stops the build.
- No placeholders: grounded anchors. The full-unification path is intentionally NOT taken (it changes verdicts).

## Notes for the executor
- `.venv/bin/python -m pytest`. The element-kind routing must produce the SAME select dict the old literal-index block did (verified equivalent: same regex, same `{type:literal_index,value,observable}`). If they differ for any input, keep the old block.
- The 1 pre-existing golden failure (`test_golden_study_tests_all_agent_bucketed`) is STALE/unrelated — leave it failing in the same way; do not let this change touch it.
- Don't modify the real v2e-invest.
