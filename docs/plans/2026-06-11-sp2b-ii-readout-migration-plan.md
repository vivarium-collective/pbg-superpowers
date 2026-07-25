# SP2b-ii — Auto-migrate + flag readouts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Program:** Active Investigation Framework, Layer 1 / SP2b (readout vocabulary), piece ii. Program spec: `docs/specs/2026-06-11-active-investigation-framework-design.md`.

**Goal:** Wire the manual-only `readout_migration` into the workflow: surface (always) each study's readout migration status (canonical / migratable / `needs_human`), auto-canonicalize the safe `migratable` ones when `/pbg-report` or an explicit `/pbg-study migrate-readouts` runs, and drive the `needs_human` queue to re-authoring against SP2b-i's `/api/observables`. Real-workspace target: the **37 `unresolved`** readouts SP2b-i surfaced.

**Trigger decision (user):** auto-canonicalize on `/pbg-report` + an explicit `/pbg-study migrate-readouts` step (the agent, via the skills) — NOT silent-on-sync. The deterministic STATUS is computed/rendered always; the WRITE happens only via those skill steps. The dashboard never writes (AI-free).

**Verified:** `readout_migration.migrate_readouts(spec) -> (new_readouts, report)` is pure; `report` carries `needs_human: [{name, reason}]` (the unresolved, never-guessed). `migrate_study_file(study_dir, write=False)` is the ruamel rewrite of just the `readouts:` block (write=False = dry-run); `pbg-migrate-readouts` CLI exists. Reuse all of it. SP2b-i (merged) gives `/api/observables` + `/pbg-study check-observables` for the re-authoring.

**Tech:** Python, pytest. Repo: pbg-superpowers only. `.venv/bin/python`.

---

## Task 1: `readout_migration_status` (pure classify)

**Files:** `viva_superpowers/readout_migration.py`; Test `tests/test_readout_migration.py`.

- [ ] **Step 1: Failing tests.**
```python
from viva_superpowers.readout_migration import readout_migration_status

def test_status_classifies_canonical_migratable_needs_human(tmp_study_mixed_readouts):
    # study has: 1 already-canonical (index_by), 1 migratable (clean identifier/store_path), 1 prose needs_human
    s = readout_migration_status(tmp_study_mixed_readouts)
    assert {r["name"] for r in s["needs_human"]}    # the prose one
    assert {r["name"] for r in s["migratable"]}     # the clean legacy-dialect one
    # canonical = unchanged by a dry-run migrate
    assert isinstance(s["canonical"], list)

def test_status_pure_read(tmp_study_mixed_readouts):
    before = (tmp_study_mixed_readouts / "study.yaml").read_bytes()
    readout_migration_status(tmp_study_mixed_readouts)
    assert (tmp_study_mixed_readouts / "study.yaml").read_bytes() == before  # dry-run, no write
```
- [ ] **Step 2: fail. Step 3: implement** `readout_migration_status(study_dir) -> {"canonical":[...], "migratable":[...], "needs_human":[{name,reason}]}`: load the study spec (`study_io`), call `migrate_readouts(spec)` (dry-run, pure), and classify from its report: `needs_human` = the report's `needs_human`; `migratable` = readouts whose canonical form DIFFERS from the original (the ones a write would change); `canonical` = resolvable + already canonical (unchanged). PURE read — no write.
- [ ] **Step 4: pass. Step 5: commit** — `feat(readout-migration): readout_migration_status — classify canonical/migratable/needs_human (pure)`

## Task 2: report_linter surface

**Files:** `viva_superpowers/report_linter.py`; Test `tests/test_report_linter.py`.

- [ ] **Step 1: Failing test** — a study with migratable + needs_human readouts produces a lint finding naming both counts.
```python
def test_linter_surfaces_readout_migration_status(tmp_workspace_with_legacy_readouts):
    findings = report_linter.lint_workspace(ws)   # or the existing entry point
    msgs = " ".join(f["message"] for f in findings)
    assert "needs_human" in msgs or "re-author" in msgs   # the 37-unresolved surface
    assert "migratable" in msgs or "canonicaliz" in msgs
```
- [ ] **Step 2: fail. Step 3: implement** a `_check_*` in `report_linter.py` (matching the existing check pattern + `_LintContext`) that calls `readout_migration_status` per study and emits a finding when `migratable` or `needs_human` is non-empty: migratable → an INFO/suggestion ("N readouts can be canonicalized — run /pbg-study migrate-readouts"); needs_human → a higher-severity finding ("M readouts can't be parsed — re-author against /api/observables"). Surfaces in `/pbg-report` + the dashboard report render.
- [ ] **Step 4: pass. Step 5: commit** — `feat(report-linter): surface readout migration status (migratable + needs_human)`

## Task 3: skill steps — `/pbg-study migrate-readouts` + `/pbg-report` canonicalize

**Files:** `skills/pbg-study/SKILL.md`, `skills/pbg-report/SKILL.md`; Test: structural guard.

- [ ] **Step 1:** Add a `migrate-readouts <slug>` subcommand to `skills/pbg-study/SKILL.md`: run `readout_migration_status`; **auto-canonicalize** the `migratable` set via `migrate_study_file(study_dir, write=True)` (meaning-preserving, idempotent, leaves `needs_human` untouched — confirm with the user before writing); then for each `needs_human` readout, drive RE-AUTHORING using `/pbg-study check-observables` + `GET /api/observables` (the real emittable set from SP2b-i) — propose a canonical selector for the intended quantity, confirm, write. Never guess a selector. In `skills/pbg-report/SKILL.md`, add a step: before rendering, run `migrate_study_file(write=True)` on each member study to canonicalize the migratable readouts (the report trigger), and report the `needs_human` count as a blocking-ish finding.
- [ ] **Step 2:** Add `tests/test_migrate_readouts_skill.py` asserting `skills/pbg-study/SKILL.md` names `migrate-readouts` + `readout_migration_status` + `migrate_study_file` + `check-observables`, and `skills/pbg-report/SKILL.md` names `migrate_study_file`.
- [ ] **Step 3: pass. Commit** — `feat(skills): /pbg-study migrate-readouts + /pbg-report canonicalize-readouts step`

## Task 4: Golden + suite

**Files:** Test `tests/test_readout_migration.py` (skipif v2e-invest absent).

- [ ] **Step 1 (skipif `/Users/eranagmon/code/v2e-invest` absent, READ-ONLY):** `readout_migration_status` on a real v2e-invest study returns the three buckets with the prose/`derived` readouts in `needs_human` (matching SP2b-i's `unresolved` set) and any clean legacy-dialect ones in `migratable`; PURE read (study.yaml byte-identical before/after). No writes to v2e-invest.
- [ ] **Step 2:** `tests/test_readout_migration.py tests/test_report_linter.py tests/test_migrate_readouts_skill.py` green; full suite no new failures (pre-existing: `test_expert_search` cache, `test_study_evaluator_golden`). **Commit** — `test(readout-migration): v2e-invest status golden + suite`

---

## Self-Review
- Coverage: status classify (T1), report surface (T2), the migrate skill + report canonicalize step (T3), golden (T4). Matches SP2b-ii scope + the trigger decision.
- AI-free: the status + classify are deterministic (dashboard renders); the WRITE (canonicalize) + re-authoring happen only via the skills (the agent), never the dashboard. needs_human is never auto-guessed.
- Reuse: `migrate_readouts`/`migrate_study_file`/`study_io`; SP2b-i's `check-observables`/`/api/observables` for re-authoring. No reimplementation.
- Deferred: SP2b-iii (evaluator unification).

## Notes for the executor
- `.venv/bin/python -m pytest`. REUSE `migrate_readouts` (dry-run for status) + `migrate_study_file(write=True)` (the canonicalize) — do not reimplement migration. `migrate_study_file` already leaves `needs_human` untouched.
- The status fn is PURE (dry-run). The only writes are `migrate_study_file(write=True)`, invoked solely from the skill steps (confirm-with-user), never the dashboard.
- Match the existing `report_linter` `_check_*`/`_LintContext` pattern for Task 2.
- Don't modify the real v2e-invest; the golden is read-only.
