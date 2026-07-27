# Phase 3 PR A — L0–L5 Study-Reproducibility Audit Module Implementation Plan

> **For agentic workers:** implement task-by-task with TDD. Steps use checkbox (`- [ ]`).

**Goal:** A self-contained `viva_superpowers/study_audit.py` that evaluates a workspace against the L0–L5 reproducibility contract and returns a structured, JSON-serializable report, plus a CLI with a `--gate` mode (non-zero exit on any HARD-tier failure) for CI. This is the enforcement core of the "formalized audit system."

**Architecture:** Pure, workbench-free (`viva_superpowers` must NOT import `vivarium_workbench` — reverse of the real dependency). Reuses existing `viva_superpowers` building blocks: `workspace_paths.WorkspacePaths` (enumeration), `study_io.load_yaml` (loading), `composite_generator.discover_generators` + `_REGISTRY` (L1 composite resolution — native to this package), `study_canonicalize.canonicalize_models`/`canonicalize_ordering` (L0 schema / inputs.from DAG logic), `investigation_canonicalize.canonicalize_investigation` (members). The DAG acyclicity check uses stdlib `graphlib`. All checks are static (no simulation, per the CI decision).

**Tech Stack:** Python 3.11, dataclasses, stdlib `graphlib`, pytest.

## Global Constraints

- **Worktree:** `~/code/viva-sp-audit`, branch `feat/study-audit-l0-l5` (off `origin/main` @ `0050f85`). Verify `git branch --show-current` + HEAD before commits.
- **Tests:** run with `~/code/pbg-superpowers/.venv/bin/python -m pytest` from the worktree root (cwd-first import → the worktree's `viva_superpowers` is used; verified). `read_text(encoding="utf-8")` everywhere.
- **No `vivarium_workbench` import** anywhere in `study_audit.py` — the module ships in the package v2ecoli CI imports; a workbench dep would break that and invert the dependency graph.
- **Tiered contract (from the design doc §3):** L0 Structure + L1 Resolvability are **hard** tier; L2 Executability, L3 Outputs, L4 Evidence, L5 Ordering(execution) are **soft** (warn/ratchet). L5 graph-validity (acyclic / no dangling) is **hard**. `--gate` exits non-zero iff any `status=="fail"` check with `tier=="hard"` exists.
- **Injectable dependencies for testability:** the composite-resolution check takes `known_composites: set[str] | None = None` (default: names from `discover_generators()`); tests pass a fake set so they need no real workspace package. Same idea for any registry-backed check.
- **Never raise on a bad workspace:** a malformed study.yaml becomes an L0 `fail` CheckResult, not a traceback. The whole audit is best-effort and total.

---

### Task 1: Data model + workspace enumeration + empty-report skeleton

**Files:** Create `viva_superpowers/study_audit.py`; Create `tests/test_study_audit.py`.

**Interfaces (Produces):**
```python
@dataclass(frozen=True)
class CheckResult:
    level: str      # "L0".."L5"
    name: str       # short slug, e.g. "no-nested-study", "composite-resolves"
    status: str     # "pass" | "warn" | "fail"
    tier: str       # "hard" | "soft"
    detail: str = "" # human reason; "" when pass

@dataclass
class StudyAudit:
    slug: str
    checks: list[CheckResult]
    def worst(self) -> str:  # "fail" if any fail else "warn" if any warn else "pass"

@dataclass
class AuditReport:
    studies: list[StudyAudit]
    investigations: list[StudyAudit]   # reuse StudyAudit shape, slug = inv slug (L5 checks)
    def hard_failures(self) -> list[tuple[str, CheckResult]]:  # (slug, check) for tier==hard & status==fail
    def as_dict(self) -> dict          # fully JSON-serializable (for CLI --json and PR C)

def audit_workspace(ws_root, *, known_composites: set[str] | None = None) -> AuditReport
```

- [ ] **Step 1: Failing test** — `audit_workspace(tmp_path)` on an empty dir (just `workspace.yaml: "name: t\n"`, empty `studies/`) returns an `AuditReport` with `studies == []`, `investigations == []`, `hard_failures() == []`, and `as_dict()` returns `{"studies": [], "investigations": [], ...}` (json.dumps round-trips).
- [ ] **Step 2:** Run → FAIL (module missing).
- [ ] **Step 3:** Implement the dataclasses + `worst`/`hard_failures`/`as_dict` + an `audit_workspace` that enumerates `WorkspacePaths.load(ws_root).studies` dirs (each `studies/<slug>/study.yaml`) and `.investigations` dirs but runs no checks yet (empty `checks`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit: `feat(audit): study_audit data model + workspace enumeration`.

---

### Task 2: L0 Structure + L1 Resolvability checks (HARD tier)

**Files:** Modify `viva_superpowers/study_audit.py`; extend `tests/test_study_audit.py`.

**L0 checks (per study unless noted, all `tier="hard"`):**
- `no-nested-study` (workspace-level, emitted once): FAIL if any `investigations/**/study.yaml` exists.
- `slug-matches-dir`: FAIL if `study.yaml` `name`/`slug` (if present) != dir name.
- `canonical-model-schema`: FAIL unless `conditions.baseline` exists with a `composite`, and every `conditions.variants[]` entry is a mapping with a `composite`. (Load a deep copy, run `study_canonicalize.canonicalize_models` on it; if it reports a structural change that isn't a no-op, FAIL with the reason.)
- `investigation-members-only` (per investigation): FAIL if `investigation.yaml` has neither `members` nor is empty-but-valid; WARN if it still carries a legacy `studies:` key.

**L1 checks (per study, `tier="hard"`):**
- `composite-resolves`: for baseline + each variant `composite`, FAIL if the name is not in `known_composites` (default `discover_generators()` names; also treat file-discovered `*.composite.yaml` / `…millard2017_metabolism` as resolvable — mirror the #393 guard's skip list).
- `params-are-generator-accepted`: FAIL if a model's `params` keys ⊄ (generator params ∪ `{"n_steps"}` run-control). Skip when the composite is unresolved (already caught above).
- `inputs-from-resolves`: FAIL if any `inputs[].from` names a study not present in the workspace (dangling edge).

- [ ] **Step 1: Failing tests** — fixture workspaces:
  - good study (baseline+variant, resolvable composites via a fake `known_composites={"pkg.good"}`, params ⊆ a fake generator-params map) → all L0/L1 `pass`.
  - `investigations/inv/study.yaml` present → `no-nested-study` FAIL.
  - study dir `s1` whose `study.yaml` `name: other` → `slug-matches-dir` FAIL.
  - study with `composite: pkg.missing` (not in `known_composites`) → `composite-resolves` FAIL.
  - study with `params: {bogus: 1}` on a resolvable composite → `params-are-generator-accepted` FAIL.
  - study with `inputs: [{artifact: x, from: nope}]` → `inputs-from-resolves` FAIL.
  (Inject `known_composites` and a fake generator-params lookup — add a `generator_params: dict[str,set] | None = None` param to `audit_workspace`, default derived from `_REGISTRY`.)
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement the L0/L1 checks, appending `CheckResult`s to each `StudyAudit.checks`. Best-effort per study (malformed yaml → single L0 `fail`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit: `feat(audit): L0 structure + L1 resolvability checks`.

---

### Task 3: L2/L3/L4 (SOFT) + L5 Ordering (per-investigation) checks

**Files:** Modify `viva_superpowers/study_audit.py`; extend `tests/test_study_audit.py`.

**Checks:**
- **L2 `node-keyable`** (`soft`, per study): WARN unless the study is content-addressable — composite resolves AND every `inputs[].from` producer resolves (so an `artifact_id = H(composite, config, sorted(input_ids), commit)` could be formed). Reuses L1 results; WARN (not fail) so it ratchets.
- **L3 `outputs-present`** (`soft`, per study): WARN if the study declares observables/report cards but `studies/<slug>/viz/` has no HTML and `viz/report_card/` has no cards on disk. (A fresh checkout legitimately has none → WARN, never FAIL.)
- **L4 `report-card-verdict`** (`soft`, per study): for each `viz/report_card/<card>.html`, WARN if the sibling `<card>.verdict.json` is missing or lacks a valid `overall` (the Phase 2c computed-verdict artifact). `pass` when every card has a computed verdict; no cards → `pass` (nothing to check).
- **L5 per investigation** (`investigations` list): build the `inputs[].from` DAG over the investigation's `members` (+ implicit upstream producers), then:
  - `dag-acyclic` (`hard`): FAIL on a cycle (`graphlib.CycleError`).
  - `no-dangling-edges` (`hard`): FAIL if any member's `inputs[].from` names a non-existent study.
  - `topological-executable` (`soft`): WARN placeholder that the order is derivable (always pass unless the DAG is invalid) — records the resolved `graphlib` order in `detail`.

- [ ] **Step 1: Failing tests** —
  - study with resolvable composite + resolvable inputs → L2 `pass`; with a dangling input → L2 `warn`.
  - study declaring a report card but empty `viz/` → L3 `warn`; study with `viz/report_card/x.html` + `x.verdict.json` → L3 `pass`, L4 `pass`; card html without verdict.json → L4 `warn`.
  - investigation `members:[a,b]` where `b.inputs=[{from:a}]` → L5 `dag-acyclic` pass + order `[a,b]`; a↔b cycle → `dag-acyclic` FAIL (hard); `b.inputs=[{from:ghost}]` → `no-dangling-edges` FAIL (hard).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Use `graphlib.TopologicalSorter`; catch `graphlib.CycleError` → hard fail. Investigation members normalization: entries may be bare slugs or `{study|slug|name: ...}` dicts (mirror `investigation_member_slugs`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit: `feat(audit): L2/L3/L4 richness + L5 ordering checks`.

---

### Task 4: CLI + `--gate` + `--json`

**Files:** Modify `viva_superpowers/study_audit.py` (add `main(argv)`, `render_report(report) -> str`); extend `tests/test_study_audit.py`.

- `python -m viva_superpowers.study_audit --workspace <path>` → prints a human table (per study: level, check, status glyph ✓/⚠/✗, detail), then a summary line.
- `--json` → prints `json.dumps(report.as_dict())` instead.
- `--gate` → after printing, `return 1` iff `report.hard_failures()` is non-empty, else `0` (for CI). Without `--gate`, always `return 0`.

- [ ] **Step 1: Failing tests** — `main(["--workspace", str(good_ws), "--gate"]) == 0`; `main(["--workspace", str(nested_ws), "--gate"]) == 1` (has an L0 hard fail); `main(["--workspace", str(good_ws), "--json"]) == 0` and captured stdout `json.loads` round-trips to a dict with `"studies"`. (Use `capsys`.)
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `render_report` + `main` (argparse). Add the `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))` guard.
- [ ] **Step 4:** Run → PASS; run the WHOLE `tests/test_study_audit.py` green; run `~/code/pbg-superpowers/.venv/bin/python -m pytest tests/test_rigor.py tests/test_study_audit.py -q` to confirm no import regressions.
- [ ] **Step 5:** Commit: `feat(audit): CLI with --gate (CI exit code) and --json`.

---

## Self-Review

- **Contract coverage:** L0 (no-nested/slug/schema/members), L1 (composite/params/inputs-resolve), L2 (keyable), L3 (outputs-present), L4 (report-card computed verdict), L5 (acyclic/dangling/order) — every row of the design's §3 table. Tiers match: L0/L1 + L5-graph-validity hard, rest soft.
- **Type consistency:** `CheckResult`/`StudyAudit`/`AuditReport` used verbatim across all tasks; `audit_workspace(ws_root, *, known_composites=None, generator_params=None)` signature stable; `as_dict()` JSON-serializable for PR C.
- **No workbench import; injectable registry** → unit-testable without a v2ecoli workspace.
- **Out of scope:** PR B (v2ecoli CI workflow calling `--gate`) and PR C (read-only workbench Audit view reading `as_dict()`), each their own PR.

## Notes

- `discover_generators` is at `composite_generator.py:573`; `_REGISTRY` at `:174`. Deriving `generator_params` from `_REGISTRY`: mirror how the #393 guard read each entry's declared `parameters` keys.
- Keep every check total: wrap per-study work in try/except → a single L0 `fail("unreadable: <err>")`, never a traceback that aborts the whole audit.
