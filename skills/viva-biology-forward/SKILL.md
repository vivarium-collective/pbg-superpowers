---
name: viva-biology-forward
description: Use when a study has computed outcomes but its findings lack biological interpretation — empty or placeholder statement/summary/explanation fields, numbers without mechanism, or a reviewer asking "what does this mean biologically?"
user-invocable: true
allowed-tools: Bash(*) Read Edit
argument-hint: "<study-slug>"
---

# /viva-biology-forward

Brings the quantitative biology forward into the structured finding slots the
report renderer already draws, then guides the agent to author the mechanism
prose using the auto-filled numbers as a scaffold. Fills the quantitative
slots (`evidence.observed`, `expected.range`, `divergence_factor`) via the
workbench API, then guides the agent to write the biological interpretation
(statement/summary/explanation/status) over that scaffold.

**Architecture:**
- **Deterministic part** (code-owned, never hand-edit): the workbench's
  `POST /api/study-findings-populate-observations` fills `evidence.observed`,
  `evidence.units`, `expected.range`/`cites`, `provenance.run_ids`,
  `evidence.divergence_factor`, and the measured side of `calibration_anchor` —
  all from `computed_outcomes` + band + readouts.
- **Authored part** (AI only): the agent writes `statement`, `summary`,
  `explanation`, `status`, and `expected.summary` (+ selects
  `expert_reference.quote` from `GET /api/expert-search` candidates).

**Dashboard-AI-free rule:** the AI reasoning stays entirely in this skill
(viva-superpowers). The workbench only serves deterministic reads/writes — no
judgment happens server-side. All number-writes go through
`POST /api/study-findings-populate-observations` (never hand-edited YAML).

**Thin client (Phase 2.1f):** this skill does no compute of its own — every
deterministic step is a `curl` call against the running dashboard server. If a
step below looks like it needs local Python beyond parsing JSON, that's a sign
the workbench API under-covers the op — STOP and report it (the fix is a
workbench-side endpoint enhancement, not a bash reimplementation here).

---

## Preconditions

1. A pbg workspace with the named study exists (`studies/<study-slug>/study.yaml`).
2. The study has `findings[]` with at least one entry carrying `evidence.from_test`.
3. The canonical run has been evaluated: `computed_outcomes[T].measured_value` must
   exist for the linked test. Run `/viva-study run-baseline` + sync if not present.
4. The dashboard server is running (`.pbg/server/server-info` exists) — the
   preamble below errors out with a fix-it hint if not.

## Common preamble

```bash
# Walk up to workspace root.
DIR="$PWD"
while [ "$DIR" != "/" ] && [ ! -f "$DIR/workspace.yaml" ]; do
  DIR="$(dirname "$DIR")"
done
[ -f "$DIR/workspace.yaml" ] || { echo "ERROR: not inside a pbg workspace"; exit 1; }
cd "$DIR"

INFO=".pbg/server/server-info"
[ -f "$INFO" ] || { echo "ERROR: dashboard server not running. Run /viva-workbench start"; exit 1; }
URL="$(python3 -c "import json; print(json.load(open('$INFO'))['url'])")"
```

---

## Step 0 — Prerequisite: sync the canonical run

If the canonical run's `computed_outcomes` may be stale (a fresh run just
completed), reconcile `runs.db` → `study.yaml` first so `measured_value` is
present for the linked tests:

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-sync-runs" | python3 -m json.tool
```

---

## Step 1 — Fill the quantitative slots (deterministic)

Call `POST /api/study-findings-populate-observations` to fill all absent
code-owned slots:

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```

The response reports `{study, filled, skipped}`.
- `filled` — findings that received at least one new code-owned field.
- `skipped` — findings with no `evidence.from_test` link or no `measured_value`.

If `filled == 0` and you expected fills, check:
- Does the finding have `evidence.from_test: <test-name>`?
- Does the canonical run's `computed_outcomes` have a `measured_value` for that test?
  Re-run Step 0 (`POST /api/study-sync-runs`) or `/viva-sync-runs` to refresh.

---

## Step 2 — Show the observed-vs-band scaffold

After populate, `Read` the study's `study.yaml` (the `Read` tool) and look at
each `findings[]` entry that now carries `evidence.observed`. For each, note:

- `evidence.observed` (+ `evidence.units`)
- `expected.range` (or `expected.threshold`)
- `evidence.divergence_factor`
- `provenance.run_ids`

These filled numbers are the scaffold you author the prose over in Step 4.
(Reading the YAML is a native file read — no local compute.)

---

## Step 3 — Surface expert-doc candidates (optional but recommended)

For each finding that needs an `expert_reference.quote`, call
`GET /api/expert-search` to find relevant passages in the workspace's expert
PDFs. `q` is a comma-separated list of search terms:

```bash
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=<test-name>,<numeric-bound>,<domain-term>" \
  --data-urlencode "max_hits=5" | python3 -m json.tool
```

`q` should include: the test name or readout name, the numeric bounds
(e.g. `0.2`, `0.5`), and any domain keywords (e.g. `DnaA-ATP`, `fraction`).

Response shape:
```json
{
  "terms": ["<test-name>", "0.2", "0.5", "<domain-term>"],
  "hits": [
    { "doc": "<filename>.pdf", "page": 3, "snippet": "…±100 chars around match…", "term": "<matched-term>" }
  ]
}
```

Present the snippets and let the agent select a verbatim quote for
`expert_reference.quote`. If needed, open the cited PDF page with the `Read`
tool for fuller context.

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
If the numbers change (e.g. after a new run), re-run Step 1
(`POST /api/study-findings-populate-observations`) to refresh them.

---

## Step 5 — Validate (idempotency check)

Re-call `POST /api/study-findings-populate-observations` to confirm it's
idempotent (returns `filled=0`):

```bash
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "<study-slug>"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```

Expected output: `{"study": ..., "filled": 0, "skipped": N}` — nothing changed
because all code-owned slots are already present.

---

## Guardrails

| Rule | Enforcement |
|---|---|
| Numbers are code-owned | `POST /api/study-findings-populate-observations` fills only absent slots; never hand-edit `evidence.observed`, `expected.range`, `divergence_factor`, `provenance.run_ids` |
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
# (preamble above sets $URL)

# 0. Prerequisite: reconcile the canonical run's outcomes
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' "$URL/api/study-sync-runs" | python3 -m json.tool

# 1. Fill the numbers
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool

# 2. Read studies/dnaa-2/study.yaml (Read tool); note observed / range /
#    divergence_factor for each finding with evidence.observed.

# 3. Search expert PDFs for a quote
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=DnaA-ATP,0.2,0.5,fraction" \
  --data-urlencode "max_hits=5" | python3 -m json.tool

# 4. Agent authors the prose with Edit tool (statement/summary/status/expert_reference)

# 5. Validate idempotency (expect filled=0)
curl -sf -X POST -H "Content-Type: application/json" \
  -d '{"study": "dnaa-2"}' \
  "$URL/api/study-findings-populate-observations" | python3 -m json.tool
```
