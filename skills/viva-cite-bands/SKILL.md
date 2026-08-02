---
name: viva-cite-bands
description: Guided band-provenance extraction — surface candidate evidence from expert PDFs for uncited acceptance bands and write structured cites/calibration_anchor provenance into study.yaml (spine stage #3b). The agent reads and judges; deterministic helpers do the writing and validation.
user-invocable: true
allowed-tools: Bash(*) Read Edit
argument-hint: "<study-slug>"
---

# /viva-cite-bands

Guides the agent through sourcing the acceptance bands in a study's
`behavior_tests[]` / `tests[]` that lack a `cites` bib_key.  The AI does
the reading and judgment; deterministic Python helpers surface candidates,
write the provenance, and validate.

**Dashboard-AI-free rule:** this skill lives entirely in pbg-superpowers.
The dashboard has no part here.  All writes go through `set_band_provenance`
(never hand-edited YAML).

---

## Preconditions

1. A pbg workspace with the named study exists (study directory at
   `studies/<study-slug>/study.yaml`).
2. `references/papers.bib` exists at the workspace root (the bib source the
   linter checks against).  If a citation source is not yet in `papers.bib`,
   add the BibTeX entry there **first** before recording it on the band.

---

## Step 1 — Find uncited bands

Run `bands_missing_provenance` to get the list of band-bearing entries that
lack a `cites` field:

```bash
STUDY_DIR="<workspace-root>/studies/<study-slug>"
.venv/bin/python -c "
import json
from viva_superpowers.band_provenance import bands_missing_provenance
from viva_superpowers.study_io import load_yaml_mapping
spec = load_yaml_mapping('$STUDY_DIR/study.yaml')
print(json.dumps(bands_missing_provenance(spec), indent=2))
"
```

Each entry in the output has the shape:
```json
{
  "name": "<test-name>",
  "kind": "behavior_test" | "test" | "readout",
  "band": { "low": 0.2, "high": 0.5 },
  "field_path": "behavior_tests[0]"
}
```

If the output is `[]`, all bands are already cited — nothing to do.

---

## Step 1b — Pull the investigation's references as candidates

When the study belongs to an **investigation**, the investigation usually
already declares a curated pool of supporting references in its
`investigation.yaml` `inputs.references` block (workspace bib_keys that resolve
in `references/papers.bib`). These are first-class candidates for the uncited
bands — surface them deterministically with `investigation_citation_gaps`
(or the `viva-citation-gaps` console script):

```bash
WS_ROOT="<workspace-root>"
INV_SLUG="<investigation-slug>"   # the owning investigation of the study
.venv/bin/python -c "
import json
from viva_superpowers.citation_gaps import investigation_citation_gaps
print(json.dumps(investigation_citation_gaps('$WS_ROOT', '$INV_SLUG'), indent=2))
"
# equivalently:
.venv/bin/python -m viva_superpowers.citation_gaps --workspace "$WS_ROOT" --investigation "$INV_SLUG"
# or the console script: viva-citation-gaps --workspace "$WS_ROOT" --investigation "$INV_SLUG"
```

The output is keyed by member study slug:
```json
{
  "<study-slug>": {
    "uncited_bands": [{ "test": "<test-name>", "observable": "<optional>" }],
    "available_references": ["dnaa-abundance-jb-1991", "dnaa-stability-jb-1999"]
  }
}
```

For each uncited band in the study you are citing, the agent PROPOSES the most
**topically-relevant** reference(s) from `available_references` — matching the
reference's subject to the band's observable/test. **This match is the agent's
judgment.** Then:

1. Confirm the proposed pairing(s) with the user.
2. Apply via `set_band_provenance(study_dir, test_name, cites=[bib_key])`
   (Step 4 below) — the references already resolve as bib_keys, so no
   cite-resolution work is needed.

**Never fabricate.** Only link references the investigation has already declared
in `inputs.references` (or another key already in `references/papers.bib`). If
none of the investigation's references topically fits a band, fall through to
the expert-PDF search (Step 2) or park it in `proposed_inputs` (Step 3) — do not
invent a bib_key.

This investigation-inputs pool is an **additional** candidate source; the
expert-PDF path below still applies for bands it does not cover.

---

## Step 2 — Surface candidate evidence per band

For each uncited band, call `search_expert_docs` to find relevant passages
in the workspace's expert PDFs:

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

`terms` should include: the test name or readout name, the numeric bounds
(e.g. `'0.2'`, `'0.5'`), and any domain keywords (e.g. `'DnaA-ATP'`,
`'fraction'`).

Each hit has shape:
```json
{
  "doc": "<filename>.pdf",
  "page": 3,
  "snippet": "…±100 chars around match…",
  "term": "<matched-term>"
}
```

Show the snippets to the user so they can review the evidence.

---

## Step 3 — Agent judgment (the only AI step)

Read the candidate snippets.  If needed, open the cited PDF page with the
`Read` tool for fuller context.

**Choose the source** — pick:
- `bib_key`: the BibTeX key in `references/papers.bib` that establishes the band
- verbatim quote: the sentence or phrase that states the numeric range

**If the source is NOT in `papers.bib`:**
Add the BibTeX entry to `references/papers.bib` before proceeding.  The
`band_cites_unknown_bib_key` linter will error on any key not in that file.

**If you are UNCERTAIN, or the expert did not provide a source:**
Record the band as a pending item in `investigation.yaml` under
`proposed_inputs` (see below) rather than asserting an unverified citation.
NEVER fabricate a citation — a made-up bib_key will cause a linter error
and silently corrupt the provenance record.

```yaml
# investigation.yaml — add under proposed_inputs:
proposed_inputs:
  - kind: band_provenance_pending
    study: <study-slug>
    test_name: <test-name>
    note: "Band [0.2, 0.5] — source not confirmed; awaiting expert input"
```

---

## Step 4 — Write provenance

Call `set_band_provenance` to record the citation.  This is the ONLY
sanctioned write path — it uses a ruamel comment-preserving round-trip so
no comments or unrelated keys are disturbed:

```bash
.venv/bin/python -c "
from pathlib import Path
from viva_superpowers.band_provenance import set_band_provenance
changed = set_band_provenance(
    Path('$STUDY_DIR'),
    test_name='<test-name>',
    cites=['<bib_key>'],
    calibration_anchor={          # include only when the band has a literature midpoint
        'literature_target': <midpoint-value>,
        'cites': ['<bib_key>'],
    },
)
print('written' if changed else 'no-op (already cited)')
"
```

`set_band_provenance` returns:
- `True` — file was updated (cite was missing or changed).
- `False` — entry not found (never fabricates) OR already identical (idempotent).

---

## Step 5 — Validate

Re-run `bands_missing_provenance` to confirm the band is no longer listed:

```bash
.venv/bin/python -c "
import json
from viva_superpowers.band_provenance import bands_missing_provenance
from viva_superpowers.study_io import load_yaml_mapping
spec = load_yaml_mapping('$STUDY_DIR/study.yaml')
remaining = bands_missing_provenance(spec)
print(json.dumps(remaining, indent=2))
"
```

Then run the band→cites linter to confirm:
- `band_test_missing_cites` does NOT fire for the updated band.
- `band_cites_unknown_bib_key` does NOT fire (the bib_key is known).

```bash
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.report_linter import lint_workspace_report
ws = Path('$WS_ROOT')
findings = lint_workspace_report(ws)
band_checks = [f.__dict__ for f in findings if 'band' in f.check]
print(json.dumps(band_checks, indent=2))
"
```

---

## Guardrails summary

| Rule | Enforcement |
|---|---|
| Never fabricate a citation | `set_band_provenance` returns `False` for non-existent names — no entry is created |
| Never hand-edit YAML | All writes via `set_band_provenance` (comment-preserving) |
| Unknown bib_key → linter error | `band_cites_unknown_bib_key` check in `report_linter` |
| Uncertain source → `proposed_inputs` | Park pending in `investigation.yaml`, not on the band |
| Idempotent writes | Calling again with same args returns `False`, no write |

---

## Full workflow example

```bash
# 1. Find uncited bands
.venv/bin/python -c "
import json
from viva_superpowers.band_provenance import bands_missing_provenance
from viva_superpowers.study_io import load_yaml_mapping
spec = load_yaml_mapping('studies/dnaa-2/study.yaml')
print(json.dumps(bands_missing_provenance(spec), indent=2))
"

# 2. Surface candidates
.venv/bin/python -c "
import json
from pathlib import Path
from viva_superpowers.expert_search import search_expert_docs
hits = search_expert_docs(Path('.'), terms=['DnaA-ATP', '0.2', '0.5', 'fraction'], max_hits=5)
print(json.dumps(hits, indent=2))
"

# 3. Agent reads snippets, picks source (Boesen2024, page 4)

# 4. Write provenance
.venv/bin/python -c "
from pathlib import Path
from viva_superpowers.band_provenance import set_band_provenance
set_band_provenance(
    Path('studies/dnaa-2'),
    test_name='frac-test',
    cites=['Boesen2024'],
    calibration_anchor={'literature_target': 0.35, 'cites': ['Boesen2024']},
)
"

# 5. Validate
.venv/bin/python -c "
import json
from viva_superpowers.band_provenance import bands_missing_provenance
from viva_superpowers.study_io import load_yaml_mapping
print(json.dumps(bands_missing_provenance(load_yaml_mapping('studies/dnaa-2/study.yaml')), indent=2))
"
```
