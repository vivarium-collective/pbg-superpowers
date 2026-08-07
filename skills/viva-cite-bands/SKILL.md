---
name: viva-cite-bands
description: Use when a study's acceptance bands lack provenance — uncited numeric thresholds a reviewer would question, or expert PDFs whose values should back the bands.
user-invocable: true
allowed-tools: Bash(*) Read Edit
argument-hint: "<study-slug>"
---

# /viva-cite-bands

Guided band-provenance extraction: guides the agent through sourcing the
acceptance bands in a study's `behavior_tests[]` / `tests[]` that lack a
`cites` bib_key.  The AI does the reading and judgment; the vivarium-workbench
API surfaces candidates, writes the provenance, and validates.

**Dashboard-AI-free rule:** the AI reasoning stays entirely in this skill
(viva-superpowers).  The workbench only serves deterministic reads/writes —
no judgment happens server-side.  All writes go through `POST
/api/band-provenance` (never hand-edited YAML, never a client-side
reimplementation of the write).

**Thin client (Phase 2.1e):** this skill does no compute of its own — every
step is a `curl` call against the running dashboard server.  If a step below
looks like it needs local Python beyond parsing JSON, that's a sign the
workbench API under-covers the op — STOP and report it (the fix is a
workbench-side endpoint enhancement, not a bash reimplementation here).

---

## Preconditions

1. A pbg workspace with the named study exists (study directory at
   `studies/<study-slug>/study.yaml`).
2. `references/papers.bib` exists at the workspace root (the bib source the
   linter checks against).  If a citation source is not yet in `papers.bib`,
   add the BibTeX entry there **first** before recording it on the band.
3. The dashboard server is running (`.pbg/server/server-info` exists) — the
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
python3 -m viva_superpowers.server_preflight --url "$URL" || true  # version-skew preflight (warns; never fails)
```

---

## Step 1 — Find uncited bands

Call `GET /api/band-provenance?study=<study-slug>` to get the list of
band-bearing entries that lack a `cites` field:

```bash
curl -sf "$URL/api/band-provenance?study=<study-slug>" | python3 -m json.tool
```

Response shape:
```json
{
  "study": "<study-slug>",
  "missing": [
    {
      "name": "<test-name>",
      "kind": "behavior_test" | "test" | "readout",
      "band": { "low": 0.2, "high": 0.5 },
      "field_path": "behavior_tests[0]"
    }
  ]
}
```

If `missing` is `[]`, all bands are already cited — nothing to do.

---

## Step 1b — Pull the investigation's references as candidates

When the study belongs to an **investigation**, the investigation usually
already declares a curated pool of supporting references in its
`investigation.yaml` `inputs.references` block (workspace bib_keys that resolve
in `references/papers.bib`). These are first-class candidates for the uncited
bands — surface them via `GET /api/citation-gaps?investigation=<inv-slug>`:

```bash
curl -sf "$URL/api/citation-gaps?investigation=<investigation-slug>" | python3 -m json.tool
```

Response shape, keyed by member study slug:
```json
{
  "investigation": "<investigation-slug>",
  "gaps": {
    "<study-slug>": {
      "uncited_bands": [{ "test": "<test-name>", "observable": "<optional>" }],
      "available_references": ["dnaa-abundance-jb-1991", "dnaa-stability-jb-1999"]
    }
  }
}
```

For each uncited band in the study you are citing, the agent PROPOSES the most
**topically-relevant** reference(s) from `available_references` — matching the
reference's subject to the band's observable/test. **This match is the agent's
judgment.** Then:

1. Confirm the proposed pairing(s) with the user.
2. Apply via `POST /api/band-provenance` with `cites=[bib_key]`
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

For each uncited band, call `GET /api/expert-search` to find relevant
passages in the workspace's expert PDFs. `q` is a comma-separated list of
search terms:

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

Call `POST /api/band-provenance` to record the citation.  This is the ONLY
sanctioned write path — the workbench forwards it to a ruamel
comment-preserving round-trip so no comments or unrelated keys are disturbed:

```bash
BODY=$(python3 -c '
import json, sys
print(json.dumps({
    "study": sys.argv[1],
    "test_name": sys.argv[2],
    "cites": [sys.argv[3]],
    # include calibration_anchor only when the band has a literature midpoint
    "calibration_anchor": {
        "literature_target": float(sys.argv[4]),
        "cites": [sys.argv[3]],
    } if len(sys.argv) > 4 else None,
}))
' "<study-slug>" "<test-name>" "<bib_key>" "<midpoint-value>")

curl -sf -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/band-provenance" | python3 -m json.tool
```

Response shape: `{"study": ..., "test_name": ..., "written": bool}`
- `written: true` — file was updated (cite was missing or changed).
- `written: false` — entry not found (never fabricates) OR already identical (idempotent).

---

## Step 5 — Validate

Re-call `GET /api/band-provenance?study=<study-slug>` to confirm the band is
no longer listed:

```bash
curl -sf "$URL/api/band-provenance?study=<study-slug>" | python3 -m json.tool
```

Then call the report linter to confirm the band checks are clean:
- `band_test_missing_cites` does NOT fire for the updated band.
- `band_cites_unknown_bib_key` does NOT fire (the bib_key is known).

```bash
curl -sf "$URL/api/report-lint" | python3 -c '
import json, sys
findings = json.load(sys.stdin).get("findings", [])
band_checks = [f for f in findings if "band" in f.get("check", "")]
print(json.dumps(band_checks, indent=2))
'
```

---

## Guardrails summary

| Rule | Enforcement |
|---|---|
| Never fabricate a citation | `POST /api/band-provenance` returns `written:false` for non-existent names — no entry is created |
| Never hand-edit YAML | All writes via `POST /api/band-provenance` (comment-preserving) |
| Unknown bib_key → linter error | `band_cites_unknown_bib_key` check, surfaced via `GET /api/report-lint` |
| Uncertain source → `proposed_inputs` | Park pending in `investigation.yaml`, not on the band |
| Idempotent writes | Calling again with same args returns `written:false`, no write |
| No client-side compute | Every read/write is an API call; the skill never imports `viva_superpowers.*` directly |

---

## Full workflow example

```bash
# 0. Preamble (walk to workspace root, resolve $URL) — see "Common preamble" above.

# 1. Find uncited bands
curl -sf "$URL/api/band-provenance?study=dnaa-2" | python3 -m json.tool

# 2. Surface candidates
curl -sf --get "$URL/api/expert-search" \
  --data-urlencode "q=DnaA-ATP,0.2,0.5,fraction" \
  --data-urlencode "max_hits=5" | python3 -m json.tool

# 3. Agent reads snippets, picks source (Boesen2024, page 4)

# 4. Write provenance
BODY='{"study":"dnaa-2","test_name":"frac-test","cites":["Boesen2024"],"calibration_anchor":{"literature_target":0.35,"cites":["Boesen2024"]}}'
curl -sf -X POST -H "Content-Type: application/json" -d "$BODY" \
  "$URL/api/band-provenance" | python3 -m json.tool

# 5. Validate
curl -sf "$URL/api/band-provenance?study=dnaa-2" | python3 -m json.tool
```
