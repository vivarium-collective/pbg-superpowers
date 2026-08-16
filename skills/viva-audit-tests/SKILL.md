---
name: viva-audit-tests
description: Use before locking a study's acceptance-criteria Tests for an autonomous model-building loop — audits whether the Tests are SUFFICIENT (discriminating, covering the question, independent, with a discriminating control) so a wrong model can't pass them. Gates the pre-registration lock.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit
argument-hint: <study-slug>
---

# /viva-audit-tests

Judge whether a study's `behavior_tests[]` are rigorous enough to VALIDATE a
model — not too weak, not gameable — BEFORE they are pre-registered/locked and
the model-iteration loop begins. This is the AUDIT gate of the agentic
model-building loop (spec: `docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md`).

## What it checks

Deterministic (from `viva_superpowers.test_audit.build_audit_report`):
- **discrimination** (hard) — no trivially-wide band a wrong model would also pass.
- **objective coverage** (hard) — every mechanism the `question`/`purpose.mechanism` names has a primary Test.
- **redundancy** (soft) — Tests key on distinct observables.
- **discriminating control** (soft) — a Test the correct model should FAIL absent the mechanism.
- **band provenance** (soft) — numeric bands carry `cites`/`provenance`.

AI reasoning you add on top (the deterministic scaffold can't):
- **null-model plausibility** — for each primary Test, reason whether a scrambled/knockout/null model (mechanism removed) would ALSO satisfy the band. If yes, the Test is insufficient even if its band is narrow — say so and downgrade `discrimination`.
- **semantic coverage** — the mechanism-token scaffold flags literal misses; confirm real coverage (a Test may cover a mechanism the tokenizer didn't match, or vice-versa).

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

Then apply the AI-reasoning dimensions (null-model, semantic coverage): if either
finds an insufficiency the deterministic pass missed, treat the audit as **fail**
and report which Tests to strengthen. On `fail`, the loop returns to AUTHOR; only a
`pass`/`warn` audit may proceed to the pre-registration lock.

## Gate contract

- `fail` → a hard dimension (discrimination / objective_coverage) is a mismatch, OR your null-model/semantic reasoning found one. Do NOT lock; strengthen the Tests.
- `warn` → only soft dimensions flagged (redundancy / control / provenance). Lockable, but note the gaps.
- `pass` → sufficient. Proceed to lock.
