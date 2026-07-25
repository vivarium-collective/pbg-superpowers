---
name: viva-biology-forward
description: Author the mechanism prose for study findings — runs populate_finding_observations to fill quantitative slots (evidence.observed, expected.range, divergence_factor) then guides the agent to write the biological interpretation (statement/summary/explanation/status) over that scaffold (spine stage #5).
user-invocable: true
allowed-tools: Bash(*) Read Edit
argument-hint: "<study-slug>"
---

# /viva-biology-forward

Brings the quantitative biology forward into the structured finding slots the
report renderer already draws, then guides the agent to author the mechanism
prose using the auto-filled numbers as a scaffold.

**Architecture:**
- **Deterministic part** (code-owned, never hand-edit): `populate_finding_observations`
  fills `evidence.observed`, `evidence.units`, `expected.range`/`cites`,
  `provenance.run_ids`, `evidence.divergence_factor`, and the measured side of
  `calibration_anchor` — all from `computed_outcomes` + band + readouts.
- **Authored part** (AI only): the agent writes `statement`, `summary`,
  `explanation`, `status`, and `expected.summary` (+ selects `expert_reference.quote`
  from `search_expert_docs` candidates).

**Dashboard-AI-free rule:** this skill lives entirely in pbg-superpowers.
The dashboard has no part here. All number-writes go through
`populate_finding_observations` (never hand-edited YAML).

---

## Preconditions

1. A pbg workspace with the named study exists (`studies/<study-slug>/study.yaml`).
2. The study has `findings[]` with at least one entry carrying `evidence.from_test`.
3. The canonical run has been evaluated: `computed_outcomes[T].measured_value` must
   exist for the linked test. Run `/viva-study run-baseline` + sync if not present.

---

## Step 1 — Fill the quantitative slots (deterministic)

Run `populate_finding_observations` to fill all absent code-owned slots:

```bash
STUDY_DIR="<workspace-root>/studies/<study-slug>"
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.finding_observations import populate_finding_observations
result = populate_finding_observations(Path('$STUDY_DIR'))
print(json.dumps(result, indent=2))
"
```

The output reports `{filled: N, skipped: N}`.
- `filled` — findings that received at least one new code-owned field.
- `skipped` — findings with no `evidence.from_test` link or no `measured_value`.

If `filled == 0` and you expected fills, check:
- Does the finding have `evidence.from_test: <test-name>`?
- Does the canonical run's `computed_outcomes` have a `measured_value` for that test?
  Run `study_outcomes.sync` or `pbg-sync-runs` to refresh.

---

## Step 2 — Show the observed-vs-band scaffold

After populate, show the agent the filled scaffold for each filled finding:

```bash
.venv/bin/python -c "
import yaml
from pathlib import Path
spec = yaml.safe_load(Path('$STUDY_DIR/study.yaml').read_text())
for f in (spec.get('findings') or []):
    ev = f.get('evidence', {})
    ex = f.get('expected', {})
    if 'observed' in ev:
        print(f'--- {f[\"id\"]} ({f.get(\"status\", \"?\")})')
        print(f'  observed = {ev[\"observed\"]} {ev.get(\"units\",\"\")}')
        print(f'  expected.range = {ex.get(\"range\")}')
        print(f'  divergence_factor = {ev.get(\"divergence_factor\")}')
        print(f'  run_ids = {f.get(\"provenance\",{}).get(\"run_ids\")}')
        print()
"
```

---

## Step 3 — Surface expert-doc candidates (optional but recommended)

For each finding that needs a `expert_reference.quote`, search the workspace's
expert PDFs for relevant passages:

```bash
WS_ROOT="<workspace-root>"
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.expert_search import search_expert_docs
hits = search_expert_docs(
    Path('$WS_ROOT'),
    terms=['<test-name>', '<numeric-bound>', '<domain-term>'],
    max_hits=5,
)
print(json.dumps(hits, indent=2))
"
```

Each hit has `{doc, page, snippet, term}`. Present the snippets and let the agent
select a verbatim quote for `expert_reference.quote`.

---

## Step 4 — Author the mechanism prose (the only AI step)

For each finding whose numbers are filled, the agent writes ONLY the irreducible
authored slots. Use the scaffold from Step 2 as a guide:

| Slot | What to write |
|---|---|
| `statement` | One-sentence biological claim ("The DnaA-ATP fraction lands in the [0.2,0.5] band…") |
| `summary` | Mechanism explanation — what the number means and why the model produces it |
| `explanation` | Optional deeper mechanistic rationale |
| `status` | `confirms` / `partial` / `contradicts` / `novel` — based on divergence_factor |
| `expected.summary` | The literature claim the test is checking against (one sentence) |
| `expert_reference.quote` | Verbatim sentence from the expert PDF (selected in Step 3) |

Write the prose to `study.yaml` using the `Edit` tool. The numbers (`observed`,
`range`, `divergence_factor`, `run_ids`) are code-owned — never hand-edit them.
If the numbers change (e.g. after a new run), re-run `populate_finding_observations`
to refresh them.

---

## Step 5 — Validate (idempotency check)

Re-run `populate_finding_observations` to confirm it's idempotent (returns `filled=0`):

```bash
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.finding_observations import populate_finding_observations
print(json.dumps(populate_finding_observations(Path('$STUDY_DIR')), indent=2))
"
```

Expected output: `{"filled": 0, "skipped": N}` — nothing changed because all
code-owned slots are already present.

---

## Guardrails

| Rule | Enforcement |
|---|---|
| Numbers are code-owned | `populate_finding_observations` fills only absent slots; never hand-edit `evidence.observed`, `expected.range`, `divergence_factor`, `provenance.run_ids` |
| Never overstate beyond divergence | If `divergence_factor > 0`, the finding `status` must be `partial` or `contradicts`, never `confirms` |
| Uncertain mechanism → mark novel | If you cannot find a literature match, set `status: novel` and do not fabricate `expert_reference` |
| No from_test → skip | A finding with only `from_run` is never auto-filled (never-fabricate rule); document it as an authored finding |
| Idempotent | Re-running populate on an already-filled study is always safe |

---

## Quick-reference: divergence_factor arithmetic

```
With expected.range [low, high]:
  inside [low, high]  → divergence_factor = 0.0  (status: confirms)
  below low           → (low - measured) / low   (positive; status: partial/contradicts)
  above high          → (measured - high) / high (positive; status: partial/contradicts)

With calibration_anchor.literature_target L:
  divergence_factor = (measured - L) / L   (signed; positive = above target)

With threshold T only:
  divergence_factor = (measured - T) / T   (signed)
```

---

## Full workflow example

```bash
# 0. Prerequisites: run is complete and synced
.venv/bin/python -m viva_superpowers.study_outcomes --study dnaa-2 --workspace .

# 1. Fill the numbers
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.finding_observations import populate_finding_observations
print(json.dumps(populate_finding_observations(Path('studies/dnaa-2')), indent=2))
"

# 2. Show the scaffold
.venv/bin/python -c "
import yaml
from pathlib import Path
spec = yaml.safe_load(Path('studies/dnaa-2/study.yaml').read_text())
for f in (spec.get('findings') or []):
    ev = f.get('evidence', {})
    if 'observed' in ev:
        print(f'{f[\"id\"]}: observed={ev[\"observed\"]} range={f.get(\"expected\",{}).get(\"range\")} div={ev.get(\"divergence_factor\")}')
"

# 3. Search expert PDFs for a quote
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.expert_search import search_expert_docs
hits = search_expert_docs(Path('.'), terms=['DnaA-ATP', '0.2', '0.5', 'fraction'], max_hits=5)
print(json.dumps(hits, indent=2))
"

# 4. Agent authors the prose with Edit tool (statement/summary/status/expert_reference)

# 5. Validate idempotency
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.finding_observations import populate_finding_observations
print(json.dumps(populate_finding_observations(Path('studies/dnaa-2')), indent=2))
"
# Expected: {"filled": 0, "skipped": N}
```
