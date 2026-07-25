# Unified Readout schema + resolver (Readout-coord #3) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A `readout_resolver` that normalizes a study's readouts (any of the 3 dialects) into a **canonical selector** the evaluator (#6) + `RunReader` (#2) can consume, plus the canonical readout schema for new studies. Normalize-on-read so existing studies work WITHOUT rewriting the user's investigation data; prose-laden/ambiguous readouts are flagged unresolved (never-guess).

**Architecture:** `viva_superpowers/readout_resolver.py`. `resolve_readout(readout: dict) -> ResolvedReadout | UnresolvedReadout`. It parses, in priority order: canonical `index_by`/`aggregate` → used directly; else the `identifier`/`store_path` string into a canonical selector. The canonical selector aligns with B2's existing `study_evaluator` expression/observable handling and #2's `RunReader.select`/`aggregate_series` (`index_by={type,value}`, expressions over observable ids). Schema formalized additively in pbg-template (keep `identifier`/`store_path` tolerated for back-compat).

**Tech:** Python 3.11+, pytest. Spec: `docs/specs/2026-06-09-readout-coordination-design.md` (#3). No pbg-emitters/RunReader dependency (that's #6 — this only produces the normalized selector).

---

## Real dialects to normalize (from v2e-invest dnaa studies)
- `identifier: listeners.monomer_counts[3861]` → literal index into a listener vector.
- `identifier: listeners.replication_data.number_of_oric` → scalar listener path.
- `identifier: listeners.rnap_data.rna_init_event_per_cistron (dnaA cistron)` → path + prose qualifier.
- `identifier: bulk MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])` → arithmetic **expression** over bulk ids.
- `identifier: bulk PD03831[c] (apo) · MONOMER0-160[c] (DnaA-ATP) · MONOMER0-4565[c] (DnaA-ADP)` → multiple bulk ids + prose (ambiguous group).
- `store_path: bulk.ATP[c]` / `store_path: listeners.mass.cell_mass` / `store_path: derived` (legacy).
- canonical `index_by: {type: bulk_id|monomer_id|literal_index, value: ...}`.

## Canonical selector (output)
```python
@dataclass
class ResolvedReadout:
    name: str
    kind: str            # "scalar" | "element" | "expression"
    observable: str | None        # for scalar/element (e.g. "listeners.mass.cell_mass", "bulk")
    index_by: dict | None         # {type, value} for element
    expression: str | None        # for expression kind (e.g. "a / (b + c)")
    operand_ids: list[dict] | None  # for expression: [{token, index_by}], so #6 can select each
    aggregate: dict | None        # {op, over:[ids]} when authored (not inferable from old dialects)
    units: str | None
    source_dialect: str           # "index_by" | "identifier" | "store_path"
@dataclass
class UnresolvedReadout:
    name: str
    raw: str
    reason: str          # why it couldn't be normalized (prose, multi-id group, "derived", ...)
```

## File map
- Create: `viva_superpowers/readout_resolver.py`.
- Modify: `pbg-template/template/.pbg/schemas/study.schema.json` (formalize canonical readout — additive).
- Test: `tests/test_readout_resolver.py`.

---

## Task 1: Parse the structured single-target dialects
- [ ] **Step 1: Failing tests** with the REAL readout dicts: `listeners.monomer_counts[3861]` → `kind=element, observable="listeners.monomer_counts", index_by={type:literal_index, value:3861}`; `listeners.replication_data.number_of_oric` → `kind=scalar, observable="listeners.replication_data.number_of_oric"`; `bulk MONOMER0-160[c]` / `store_path: bulk.ATP[c]` → `kind=element, observable="bulk", index_by={type:bulk_id, value:"MONOMER0-160[c]"}`; canonical `index_by` passed through. `store_path: derived` → UnresolvedReadout(reason="derived").
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the parser for: `<path>[<int>]` → literal_index; bare dotted path → scalar; `bulk <id>` / `bulk.<id>` → bulk_id; canonical `index_by` → passthrough; recognized non-resolvable tokens (`derived`, empty) → Unresolved. Strip a trailing `(prose)` qualifier when the head is a clean path (record it in a note), but if the prose is load-bearing/ambiguous, Unresolved.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(readout_resolver): parse literal-index/scalar/bulk-id dialects`

## Task 2: Parse arithmetic expressions over observable ids
- [ ] **Step 1: Failing test** — `bulk MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])` → `kind=expression, expression="MONOMER0-160[c] / (PD03831[c] + MONOMER0-160[c] + MONOMER0-4565[c])", operand_ids=[{token, index_by:{type:bulk_id, value:...}} for each distinct id]`. Reuse/align with B2 `study_evaluator`'s expression tokenizer (read it; share a helper if clean) so #6 evaluates identically. A malformed/prose-mixed expression → Unresolved.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — detect an arithmetic expression (contains `+-*/()` over id tokens), tokenize the operand ids (same id grammar as B2: dotted paths and `NAME[c]`-style), tag each as `bulk_id` (when prefixed `bulk`) or by path. Strip a leading `bulk ` marker.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(readout_resolver): expression dialect over observable ids`

## Task 3: Never-guess on prose/ambiguous + study-level resolve
- [ ] **Step 1: Failing tests** — the multi-id-with-`·` prose form (`bulk A (apo) · B (DnaA-ATP) · C`) → Unresolved(reason mentions multi-id/prose); a `resolve_study_readouts(spec) -> {name: ResolvedReadout|UnresolvedReadout}` over a real dnaa-2 readouts block returns the right mix (the DnaA-ATP-fraction expression resolved; the `·`-group unresolved; oriC scalar resolved).
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `resolve_study_readouts` + the ambiguity guards (multiple top-level ids without an operator, parentheticals that aren't a single trailing qualifier, `·`/`;` separators → Unresolved with a clear reason). NEVER fabricate an index/selector.
- [ ] **Step 4: Run → pass.** **Step 5: Commit** — `feat(readout_resolver): resolve_study_readouts + never-guess on prose/ambiguous`

## Task 4: Canonical schema (pbg-template, additive)
- [ ] **Step 1:** In `pbg-template/template/.pbg/schemas/study.schema.json`, formalize the canonical readout item: `name`, `description`, `index_by:{type (enum bulk_id|monomer_id|listener_id|literal_index), value}`, `aggregate:{op (enum sum|mean|max|min), over:[string]}`, `units`, `status`. Keep `additionalProperties: true` and document `identifier`/`store_path` as deprecated-but-tolerated (so existing studies still validate). Add/keep a schema test if pbg-template has one.
- [ ] **Step 2:** Run pbg-template tests (`python -m pytest -q`) — green. **Step 3: Commit** (separate, in pbg-template) — `feat(schema): formalize canonical readout (index_by + aggregate)`

---

## Self-Review
- Spec #3: unified schema (T4) + resolver normalizing the 3 dialects (T1-3) + the type→observable mapping (in the resolver). Migration of user studies = NOT forced (resolver normalizes on read; explicit rewrite is a later, user-supervised step). #6 consumes `ResolvedReadout`.
- No placeholders: real dialect strings drive every test; the canonical selector shape is defined.
- Types: `resolve_readout -> ResolvedReadout|UnresolvedReadout`; aligns with B2 expression tokens + #2 `index_by` shape.

## Notes for executor
- `.venv/bin/python -m pytest`.
- Read `viva_superpowers/study_evaluator.py`'s expression resolver and REUSE its id-tokenizer (don't fork the grammar) so #6 evaluates the readout expression the same way.
- Do NOT modify any real study under v2e-invest; tests use copied/inline readout dicts.
- The pbg-template schema change is a SEPARATE commit in a different repo (note it; the orchestrator may PR it separately).
