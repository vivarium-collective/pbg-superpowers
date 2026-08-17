---
name: viva-audit-tests
description: Use when a study's acceptance-criteria Tests must be audited for SUFFICIENCY before they are locked for an autonomous model-building loop — checks that the Tests are discriminating, cover the question, are independent, and include a discriminating control so a wrong model can't pass them, and (when the study carries a sourcing decision) audits that decision with an LLM near-miss judgment for capability tokens the manifest tags miss. Gates the pre-registration lock.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <study-slug>
---

# /viva-audit-tests

Judge whether a study's `behavior_tests[]` are rigorous enough to VALIDATE a
model — not too weak, not gameable — BEFORE they are pre-registered/locked and
the model-iteration loop begins. This is the AUDIT gate of the agentic
model-building loop (spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`).

The sufficiency report + gate this skill produces surfaces in the study's
Assurance › Audit tab (alongside the rigor scorecard and L0–L5 reproducibility).

## What it checks

Deterministic (from `viva_superpowers.test_audit.build_audit_report`):
- **discrimination** (hard) — no trivially-wide band a wrong model would also pass.
- **objective coverage** (hard) — every mechanism the `question`/`purpose.mechanism` names has a primary Test.
- **redundancy** (soft) — Tests key on distinct observables.
- **discriminating control** (soft) — a Test the correct model should FAIL absent the mechanism.
- **band provenance** (soft) — numeric bands carry `cites`/`provenance`.

Deterministic sourcing audit (only when the study carries a `sourcing:` decision,
i.e. it went through the loop's SELECT phase — from
`viva_superpowers.module_sourcing.build_sourcing_report` + `sourcing_gate`):
- **source_fit** (hard) — the chosen module(s)' declared capabilities cover the task's `requires` tokens.
- **reinvention** (hard) — didn't build-new where a catalogued module already fits.
- **novelty_justified** (soft) — build-new only when nothing catalogued fits.
- **survey_recorded** (soft) — a rationale / candidates were recorded (the catalog was surveyed).

AI reasoning you add on top (the deterministic scaffold can't):
- **null-model plausibility** — for each primary Test, reason whether a scrambled/knockout/null model (mechanism removed) would ALSO satisfy the band. If yes, the Test is insufficient even if its band is narrow — say so and downgrade `discrimination`.
- **semantic coverage** — the mechanism-token scaffold flags literal misses; confirm real coverage (a Test may cover a mechanism the tokenizer didn't match, or vice-versa).
- **sourcing near-miss (semantic capability fit)** — `source_fit` matches capability TOKENS exactly, so it can be wrong two ways the tokens can't see. For each `missing_capabilities` token a `source_fit` mismatch reports, reason whether the chosen module *semantically* provides it under a differently-named token (task needs `diffusion`; the module declares `pde_transport`). A true near-miss means the manifest **tags** are incomplete, not the sourcing wrong — recommend adding the token to the module's declared capabilities and treat the hard mismatch as a `warn`, not a `fail`. Conversely, flag an exact-token match that is semantically hollow (the module lists `spatial` but only 1-D; the task needs 3-D) — **downgrade source_fit to a mismatch even though the deterministic pass matched.**

## Run

```bash
STUDY="${1:?usage: /viva-audit-tests <study-slug>}"
python - "$STUDY" <<'PY'
import sys, json, yaml
from pathlib import Path
from viva_superpowers import paths, test_audit
ws = paths.workspace_root()
sf = paths.workspace_dir("studies", root=ws) / sys.argv[1] / "study.yaml"
spec = yaml.safe_load(sf.read_text()) if sf.is_file() else {}
rep = test_audit.build_audit_report(spec)
gate = test_audit.audit_gate(rep)
print("audit gate:", gate)
for g in rep["groups"].values():
    for ax in g["axes"]:
        if ax["verdict"] != "within_tol":
            print(f"  {ax['verdict']:9} {ax['id']}  {json.dumps(ax.get('detail') or {})}")
print(json.dumps(rep))  # for the caller / to write test-audit.verdict.json
PY
```

When the study carries a `sourcing:` decision, also run the deterministic sourcing
audit (skips cleanly when absent — most studies have no `sourcing:` block):

```bash
python - "$STUDY" <<'PY'
import sys, json, yaml
from viva_superpowers import paths, module_sourcing as ms
ws = paths.workspace_root()
spec = yaml.safe_load((paths.workspace_dir("studies", root=ws) / sys.argv[1] / "study.yaml").read_text())
if not spec.get("sourcing"):
    print("no sourcing decision — sourcing audit skipped"); raise SystemExit
catalog = spec.get("catalog") or {}          # {module: [capability tokens]} from the SELECT survey
rep = ms.build_sourcing_report(spec, catalog)
gate = ms.sourcing_gate(rep)
print("sourcing gate:", gate)
for g in rep["groups"].values():
    for ax in g["axes"]:
        if ax["verdict"] != "within_tol":
            print(f"  {ax['verdict']:9} {ax['id']}  {json.dumps(ax.get('detail') or {})}")
print(json.dumps(rep))   # near-miss judgment reasons over detail.missing_capabilities
PY
```

Then apply the AI-reasoning dimensions (null-model, semantic coverage, **sourcing
near-miss**): if any finds an insufficiency the deterministic pass missed, treat the
audit as **fail** and report which Tests to strengthen — EXCEPT a sourcing hard
mismatch your near-miss judgment attributes to incomplete manifest tags (a real
semantic fit under a different token), which is a `warn` + a recommendation to fix
the module's declared capabilities, not a `fail`. On `fail`, the loop returns to
AUTHOR (Tests) or SELECT (sourcing); only a `pass`/`warn` audit may proceed to the
pre-registration lock.

## Gate contract

- `fail` → a hard dimension (discrimination / objective_coverage; or sourcing source_fit / reinvention) is a mismatch, OR your null-model / semantic / sourcing-near-miss reasoning found one. Do NOT lock; strengthen the Tests (return to AUTHOR) or revise the sourcing decision (return to SELECT).
- `warn` → only soft dimensions flagged (redundancy / control / provenance; or sourcing novelty_justified / survey_recorded), OR a sourcing source_fit mismatch your near-miss judgment attributes to a manifest tagging gap (fix the module's declared capabilities). Lockable, but note the gaps.
- `pass` → sufficient. Proceed to lock.

The overall gate is the worse of the test-sufficiency gate and (when present) the
sourcing gate, after your near-miss reasoning has adjusted either.
