---
name: viva-navigate
description: Read-only navigation of the workspace knowledge graph (the SP4a linkage index) plus the SP5 "decisions needed" scan. Lead with `decisions <inv>` — the ranked list of what needs your decision (uncovered ACs, verdict divergence, open feedback, param drift, stale findings). Also surfaces the cheap reverse queries that today need grep — the AC→study gating matrix + unlinked-AC gaps, which studies cite a source, which findings measure an observable, and a study's prerequisite DAG. Pure deterministic query, no AI, no writes. Wraps GET /api/linkage-index (ac_gating_matrix, studies_for_source, findings_for_observable, study_dag, studies_for_observable, composite_emits) and GET /api/needs-attention (the decisions-needed scan).
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: decisions <inv> | ac-gaps <inv> | source <bib_key> | finding-by-observable <token> | dag <inv> | observable <token> | composite <id>
---

# viva-navigate

Transversal, **read-only** skill. Queries the workspace **linkage index** — a
derived, ephemeral knowledge graph over the YAML (studies ↔ composites ↔
observables ↔ sources ↔ findings ↔ acceptance ↔ study-DAG). It NEVER writes to
YAML and adds NO AI judgment: it surfaces the deterministic index the
dashboard computes server-side so you don't have to grep.

**Lead with `decisions <inv>`.** When you arrive at an investigation, the first
question is "what needs my decision?" — so run the **decisions-needed scan**
first. It aggregates the divergences/gaps SP1–SP4 already compute into one ranked
list (it makes no new judgment — it gathers + ranks existing signals). The other
subcommands answer the follow-up "where does this link?" questions.

Every subcommand calls the dashboard: `GET /api/linkage-index` (SP4a/SP4b
linkage + navigate queries, param-dispatched) or `GET /api/needs-attention`
(the SP5 decisions-needed scan) — the same deterministic derive the old
in-process helpers computed, now TTL-cached server-side. This requires the
dashboard server to be running (see preamble below).

## Subcommands

| Form | What it does |
|---|---|
| `/viva-navigate decisions <inv>` | Ranked decisions-needed scan. `GET /api/needs-attention?investigation=<inv>`. |
| `/viva-navigate ac-gaps <inv>` | AC→study gating matrix + unlinked-AC gaps. `GET /api/linkage-index?investigation=<inv>` → `ac_matrix`. |
| `/viva-navigate source <bib_key>` | Studies that cite a bibliography key. `GET /api/linkage-index?source=<bib_key>` → `studies`. |
| `/viva-navigate finding-by-observable <token>` | Findings that measure an observable token. `GET /api/linkage-index?observable=<token>` → `findings`. |
| `/viva-navigate dag <inv>` | Study prerequisite DAG for an investigation. `GET /api/linkage-index?investigation=<inv>` → `dag`. |
| `/viva-navigate observable <token>` | Cross-study observable registry (which composites emit it, which studies use them). `GET /api/linkage-index?observable_registry=<token>` → `studies`, `composites`. |
| `/viva-navigate composite <id>` | What a composite emits + which studies use it. `GET /api/linkage-index?composite=<id>` → `emits`, `used_by_studies`. |

## Common preamble (all subcommands)

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

## decisions

**Lead with this.** Print the ranked **decisions-needed scan** for an
investigation: every divergence/gap SP1–SP4 computed, gathered + ranked by
severity (high → medium → low). One line per item:
`kind · study/ref · action_hint`. Pure deterministic aggregation, AI-free, no
writes — the output is ephemeral.

The signals: `uncovered_ac` (high), `verdict_divergence` (high), `param_drift`
(high), `phantom_observable` (high, **build-gated/optional** — only when an
`observables_for_ref` build callable is injected; the server supplies its
cached one when enabled), `open_feedback` (medium), `stale_finding` (low).

```bash
INV="${1:?Usage: /viva-navigate decisions <inv>}"
curl -sf "$URL/api/needs-attention?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
order = {"high": 0, "medium": 1, "low": 2}
last = None
for it in d["items"]:
    if it["severity"] != last:
        last = it["severity"]
        print(f"\n[{last.upper()}]")
    ref = f"{it[\"study\"]}/{it[\"ref\"]}" if it["study"] else it["ref"]
    print(f"  {it[\"kind\"]} · {ref} · {it[\"action_hint\"]}")
s = d["summary"]["by_severity"]
print(f"\n{s[\"high\"]} high / {s[\"medium\"]} medium / {s[\"low\"]} low "
      f"({d[\"summary\"][\"total\"]} total).")
'
```

## ac-gaps

Print the **AC→study gating matrix** for an investigation: one row per
acceptance criterion with its linked `study`, computed `result`, and a **gap**
flag when the criterion has NO `study:` link. Unlinked criteria are the gaps —
they make the report claim coverage that nothing actually gates (e.g.
`chromosome-cycle-calibration` has 5 acceptance criteria with no `study:`).

```bash
INV="${1:?Usage: /viva-navigate ac-gaps <inv>}"
curl -sf "$URL/api/linkage-index?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
m = d["ac_matrix"]
for r in m["criteria"]:
    flag = "  ⚠ GAP (no study linked)" if r["gap"] else ""
    print(f"- {r[\"behavior\"]:50s} study={r[\"study\"] or \"—\"} result={r[\"result\"]}{flag}")
print(f"\n{len(m[\"gaps\"])} unlinked acceptance criteria (gaps).")
'
```

## source

Print which studies cite a bibliography key (study-level `cites[]` + per-band
cites on tests/readouts).

```bash
KEY="${1:?Usage: /viva-navigate source <bib_key>}"
curl -sf "$URL/api/linkage-index?source=$KEY" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("\n".join(d["studies"]) or "(no studies cite this key)")
'
```

## finding-by-observable

Print which findings measure an observable token (resolved through the
finding's `evidence.from_test` → the test's `measure.{path,field}`).

```bash
TOKEN="${1:?Usage: /viva-navigate finding-by-observable <token>}"
curl -sf "$URL/api/linkage-index?observable=$TOKEN" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for f in d["findings"]:
    print(f"- {f[\"finding\"]}  (study {f[\"study\"]})")
'
```

## dag

Print an investigation's study prerequisite DAG (nodes + prerequisite/enables
edges from each study's `pipeline_gate`).

```bash
INV="${1:?Usage: /viva-navigate dag <inv>}"
curl -sf "$URL/api/linkage-index?investigation=$INV" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for e in d["dag"]["edges"]:
    print(f"{e[\"from\"]} → {e[\"to\"]}")
'
```

## observable

The **cross-study observable registry**: which composites *emit* an observable
`<token>` and which studies use those composites. Unlike `finding-by-observable`
(which resolves through finding evidence in the YAML), this answers "which
composites actually *emit* this observable, and which studies use those
composites" — so it needs the real composite build behind the server's
`observables_for_ref` callable. Matching reconciles the bulk dialects (a query
for `bulk.ATP[c]` finds a composite leaf `bulk[ATP[c]]`).

> **Triggers a composite build** the first time (cached, ~3s); subsequent
> calls are cheap. The server supplies the build callable — there is no
> client-side equivalent.

```bash
TOKEN="${1:?Usage: /viva-navigate observable <token>}"
curl -sf "$URL/api/linkage-index?observable_registry=$TOKEN" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("studies:   ", ", ".join(d["studies"]) or "(none)")
print("composites:", ", ".join(d["composites"]) or "(none)")
'
```

(Note the distinct `observable_registry=` param — `observable=` is the SP4a
finding-by-observable query above, which returns `findings`.)

## composite

What a composite **emits** + which studies **use** it. Also triggers a
composite build (cached).

```bash
ID="${1:?Usage: /viva-navigate composite <id>}"
curl -sf "$URL/api/linkage-index?composite=$ID" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("emits:", ", ".join(d["emits"]) or "(none)")
print("used by studies:", ", ".join(d["used_by_studies"]) or "(none)")
'
```

## Examples

```text
/viva-navigate decisions chromosome-cycle-calibration
/viva-navigate ac-gaps chromosome-cycle-calibration
/viva-navigate source agmon-2022
/viva-navigate finding-by-observable bulk.ATP[c]
/viva-navigate dag chromosome-cycle-calibration
/viva-navigate observable bulk.ATP[c]
/viva-navigate composite pbg_chromosome_rep1.composites.dnaa-binding
```

## Notes

- **Pure query, AI-free.** Every subcommand hits `/api/linkage-index` or
  `/api/needs-attention` and prints the deterministic result. No model
  judgment, no writes — the index is ephemeral and never persisted into YAML.
- **Requires the dashboard server.** This skill has no in-process fallback —
  if `.pbg/server/server-info` is missing, run `/viva-workbench start` first.
- Run from the workspace root (the preamble walks up to find it).
