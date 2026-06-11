# Active Investigation Framework — Program Design

> **Status:** approved program design (2026-06-11). Decomposed into 5 sub-projects + a parallel hygiene track; each sub-project gets its own spec → plan → build cycle. This document is the program-level design and scope.

## Motivation

A six-agent audit of the pbg / Vivarium-2.0 framework (pbg-superpowers, vivarium-dashboard, v2ecoli) found a consistent pattern: **the framework is well-scaffolded but full of half-built loops and dead entry points.** The structure — the study/investigation spine, the `/pbg-*` skills, the ~55 assistance modules — is genuinely good. But again and again, one half of a loop is built and the other is missing, or a module exists and nothing calls it. Information is *captured but stranded*: it has nowhere to flow, so the agent reconstructs every cross-link by hand and the system feels passive rather than actively helpful.

Representative confirmed findings (zero production call-sites unless noted):
- **Schema features with no executor.** `simulation_set[].kind: sweep` and `kind: seeds` are schema-validated (`vivarium-dashboard/lib/investigations.py:757-778`) but no runner expands them — declared multi-run experiments execute a single point.
- **Orphaned guards.** `pbg_superpowers/readout_validation.py` (the author-time *never-fabricate* observable check) has no skill, endpoint, or caller. `param_enforcement.py`'s drift detector is fully wired to read/lint/render but the `enforced_params` field is authored nowhere, so it never fires. `roll_up.py` (verdict/acceptance persistence) is never triggered — verdicts exist only at render-time, so exports/snapshots lose them. `backfill_runs.py` never auto-registers on-disk runs into `study.yaml runs[]`.
- **Fragmented loops.** A finding's `next_action` (the natural "what next" signal) is display-only; the dashboard's "seed followup" reads a *different* field family (`follow_up_studies` / `followup_study_proposals`). Expert `inputs:` are collected at the investigation level but never flow into study design. Imported expert feedback is displayed but never fed back into findings/design — the loop is open.
- **No queryable cross-links.** No observable registry, no acceptance-criteria→study coverage matrix, no composite dependency graph, no "which studies use this source," no cross-study observable search. Every hop is reconstructed by grep or by building the composite and introspecting.
- **Vocabulary fragmentation.** Three incompatible readout dialects (`identifier`, `store_path`, `index_by`) with three independent tokenizers and no validation gate.
- **Bloat.** `server.py` is a 14.6K-LOC god-file; yaml-io, composite-discovery, and study-charts logic are duplicated across repos; `parent_studies` and `pipeline_gate.prerequisites` both live on.

## The frame: Propagate · Navigate · Guide

Three capabilities, in dependency order, turn the stranded structure into an active one:

1. **Propagate** — information flows automatically through every hop (Layer 1).
2. **Navigate** — the cross-links become queryable, not reconstructed (Layer 2).
3. **Guide** — the system surfaces the decisions the user needs to make (Layer 3).

## Architecture principles

- **Deterministic logic in pbg-superpowers; the dashboard stays AI-free.** Every new computation (a propagation step, a linkage index, a "needs attention" scan) is a pure, tested function in `pbg_superpowers/`. The dashboard renders and the `/pbg-*` skills call these functions; the AI assistance (judgment, prose, seeking input) lives only in the skills. (Per memory `feedback_dashboard_ai_free`.)
- **Extend the existing propagation orchestrator, don't replace it.** `study_outcomes.sync()` already chains `record_runs → compute_outcomes → populate_simulation_set → write_gate_evaluator → populate_finding_observations`. Layer 1 completes both ends of every hop and extends the chain upstream (design) and downstream (acceptance, feedback) rather than inventing a new engine.
- **Code-owned vs authored slots.** The established convention holds: code fills only absent code-owned fields, never clobbers authored values, via ruamel round-trip (comment-preserving). New propagation respects it.
- **The linkage index is a derived, cached artifact** — computed from the YAML + built composites, never a separate source of truth. It is regenerated on change; it makes the implicit "knowledge graph" explicit and queryable.
- **Never-guess / typed errors.** New resolvers/validators return typed "unresolved" results rather than guessing (the readout-resolver pattern), and surface them as decisions rather than silent failures.

---

## Sub-projects

### SP1 — Downstream persistence (run → verdict → acceptance, on disk)
**Closes:** verdicts/acceptance only exist at render-time; on-disk runs unregistered; `enforced_params` never fires.
- Auto-trigger `roll_up` (persist `gate_evaluator` + investigation `computed_acceptance`) inside `study_outcomes.sync()` / the post-run hook, so computed verdicts are written to disk — exports, the read-only snapshot, and `/pbg-report` carry real verdicts instead of recomputing.
- Auto-write investigation acceptance (`investigation_status.write_investigation_acceptance`) when a member study's verdict changes.
- Auto-register on-disk runs (`backfill_runs`) into `study.yaml runs[]` from the run-completion path (the SimulationsDB view already scans disk; study-level recording must too).
- Activate `enforced_params`: auto-derive the expected param set from `conditions.*.params` so the already-built drift detector (`param_enforcement.py`) fires; surface violations.
**Scope note:** these are mostly small "wire the missing trigger" changes to existing, tested modules.

### SP2 — Upstream + executor, incl. the readout vocabulary
**Closes:** dead sweep/seeds contracts; orphaned readout validation; dialect fragmentation; expert-inputs→design break.
- **Sweep/seeds executor:** expand `kind: sweep` (over `sweep_over`) and `kind: seeds` (over `n_seeds`) into N runs in the run path (`lib/run_runner.py` + the run endpoint), recording each — the schema's declared experiments finally execute.
- **Readout vocabulary unification (theme D):** make `readout_resolver` the single tokenizer for every code path (emitter config, evaluator, viz); auto-migrate the three legacy dialects → canonical `index_by`; wire `readout_validation` as the author-time *never-fabricate* guard, exposed as `GET /api/observables` + a `/pbg-study check-observables` step ("does my composite actually emit this?").
- **Expert-inputs → study design:** a step that reads investigation `inputs:` and proposes edits into member studies (citations on bands, `conditions` references), with accept/decline.

### SP3 — Reflexive loops (result → next, feedback → design)
**Closes:** fragmented followup seeding; open feedback loop.
- Unify the followup path so a finding's `next_action` is actionable end-to-end (reconcile `finding.next_action` with `follow_up_studies` / `followup_study_proposals` into one mechanism the UI and `seed_from_followup` share).
- Close the feedback loop: imported feedback items become actionable — suggested `finding.next_action` / finding drafts / design edits — and are tracked open→addressed, so a reviewer's comment provably drives follow-up.

### SP4 — The linkage index + navigation surfaces (Navigate)
**Closes:** no queryable cross-links; reverse navigation is grep/build.
- A derived, cached **linkage index**: the explicit knowledge graph connecting studies ↔ composites ↔ processes ↔ observables ↔ sources ↔ findings ↔ acceptance, computed from the YAML + built composites and keyed on SP2's canonical observable vocabulary.
- Reverse-index query surfaces (endpoints + skill steps): observable registry ("what emits X / what does this composite emit"), **acceptance-criteria→study gating matrix** (which member study covers which AC, with gaps flagged), composite dependency graph (what feeds/consumes a store), source↔study ("which studies use this dataset/reference"), cross-study observable/finding search.

### SP5 — The "decisions needed" surface (Guide)
**Closes:** the system never proactively asks; gates are correct but passive.
- One pure computation that scans the now-flowing, now-indexed investigation and surfaces *what needs attention*: computed-vs-authored verdict divergence, uncovered acceptance criteria, unaddressed feedback, phantom observables (from SP2's validator), param drift (SP1), stale findings.
- Surfaced both as a dashboard **"needs attention" panel** and led-with by the skills, so the agent opens with "here are the N decisions for you" instead of waiting to be told.

### Hygiene track (parallel, theme E — not a gate)
- Split `server.py` (14.6K LOC) into API-domain modules (overlaps read-only-dashboard #4 / the P1/P2 backlog bucket E).
- Consolidate duplicated yaml-io (a dashboard `yaml_io.py` mirroring `study_io.py`), composite-discovery (one library, not vendored-and-diverging), study-charts, and atomic-write.
- Retire `parent_studies` in favor of `pipeline_gate.prerequisites`; delete confirmed-dead code only after its loop is wired (SP1–SP3 first).

---

## Order and dependencies
`SP1 → SP2 → SP3` (propagation must flow before navigation and guidance have signals to work with) `→ SP4` (indexes the now-flowing data) `→ SP5` (reads the indexed signals). Each sub-project ships independently and adds value on its own. The hygiene track runs opportunistically alongside; the dead-code deletions in it must wait until SP1–SP3 confirm what is truly unused vs merely unwired.

## Non-goals (YAGNI)
- No new propagation engine — extend `sync()`.
- No central database for the knowledge graph — it stays a derived, cached artifact over the YAML + composites.
- No AI logic in the dashboard — all new computation is deterministic in pbg-superpowers.
- No frontend framework rewrite.
- No speculative auto-actions: the system proposes and seeks input at decision points; it does not unilaterally rewrite study design, fabricate findings, or merge.

## Success criteria
- Every propagation hop is automated or has an explicit, intentional human gate — no silent breaks where info must be hand-carried (verified against the audit's hop table).
- The agent can answer "what emits X," "which study covers this acceptance criterion," "which studies use this source," and "what needs my attention" via a query, not a manual reconstruction.
- The confirmed-dead modules (`readout_validation`, `param_enforcement`'s field, `roll_up` trigger, `backfill` trigger, the sweep/seeds executor) are either wired into a live path or deleted — none left as orphaned placeholders.
- The dashboard imports no AI/skills/requirements dependency (enforced by a repo-wide gate added in the hygiene track).
