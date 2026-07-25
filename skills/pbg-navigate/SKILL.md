---
name: pbg-navigate
description: Read-only navigation of the workspace knowledge graph (the SP4a linkage index) plus the SP5 "decisions needed" scan. Lead with `decisions <inv>` — the ranked list of what needs your decision (uncovered ACs, verdict divergence, open feedback, param drift, stale findings). Also surfaces the cheap reverse queries that today need grep — the AC→study gating matrix + unlinked-AC gaps, which studies cite a source, which findings measure an observable, and a study's prerequisite DAG. Pure deterministic query, no AI, no writes.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: decisions <inv> | ac-gaps <inv> | source <bib_key> | finding-by-observable <token> | dag <inv> | observable <token> | composite <id>
---

# pbg-navigate

Transversal, **read-only** skill. Queries the workspace **linkage index** — a
derived, ephemeral knowledge graph over the YAML (studies ↔ composites ↔
observables ↔ sources ↔ findings ↔ acceptance ↔ study-DAG). It NEVER writes to
YAML and adds NO AI judgment: it surfaces the deterministic index built by
`viva_superpowers.linkage_index` so you don't have to grep.

**Lead with `decisions <inv>`.** When you arrive at an investigation, the first
question is "what needs my decision?" — so run the **decisions-needed scan**
first. It aggregates the divergences/gaps SP1–SP4 already compute into one ranked
list (it makes no new judgment — it gathers + ranks existing signals). The other
subcommands answer the follow-up "where does this link?" questions.

There are two equivalent backends; prefer whichever is available:

- **Direct (no server):** call `viva_superpowers.linkage_index` /
  `viva_superpowers.needs_attention` via `.venv/bin/python`.
- **Via the dashboard:** `GET /api/linkage-index` / `GET /api/needs-attention`
  (when the dashboard server is running) — the same deterministic derive,
  TTL-cached.

## Subcommands

### `decisions <inv>`

**Lead with this.** Print the ranked **decisions-needed scan** for an
investigation: every divergence/gap SP1–SP4 computed, gathered + ranked by
severity (high → medium → low). One line per item:
`kind · study/ref · action_hint`. Pure deterministic aggregation, AI-free, no
writes — the output is ephemeral.

The signals: `uncovered_ac` (high), `verdict_divergence` (high), `param_drift`
(high), `phantom_observable` (high, **build-gated/optional** — only when an
`observables_for_ref` build callable is injected), `open_feedback` (medium),
`stale_finding` (low).

```bash
.venv/bin/python - "$INV" <<'PY'
import sys
from viva_superpowers.needs_attention import scan_investigation
res = scan_investigation(".", sys.argv[1])
order = {"high": 0, "medium": 1, "low": 2}
last = None
for it in res["items"]:
    if it["severity"] != last:
        last = it["severity"]
        print(f"\n[{last.upper()}]")
    ref = f"{it['study']}/{it['ref']}" if it["study"] else it["ref"]
    print(f"  {it['kind']} · {ref} · {it['action_hint']}")
s = res["summary"]["by_severity"]
print(f"\n{s['high']} high / {s['medium']} medium / {s['low']} low "
      f"({res['summary']['total']} total).")
PY
```

Or via the dashboard: `GET /api/needs-attention?investigation=<inv>` → the same
ranked `items` + `summary`. Signal 4 (phantom observable) is build-gated and off
by default; the dashboard supplies its cached build callable when enabled.

### `ac-gaps <inv>`

Print the **AC→study gating matrix** for an investigation: one row per
acceptance criterion with its linked `study`, computed `result`, and a **gap**
flag when the criterion has NO `study:` link. Unlinked criteria are the gaps —
they make the report claim coverage that nothing actually gates (e.g.
`chromosome-cycle-calibration` has 5 acceptance criteria with no `study:`).

```bash
.venv/bin/python - "$INV" <<'PY'
import sys, json
from viva_superpowers.linkage_index import ac_gating_matrix
m = ac_gating_matrix(".", sys.argv[1])
for r in m["criteria"]:
    flag = "  ⚠ GAP (no study linked)" if r["gap"] else ""
    print(f"- {r['behavior']:50s} study={r['study'] or '—'} result={r['result']}{flag}")
print(f"\n{len(m['gaps'])} unlinked acceptance criteria (gaps).")
PY
```

Or via the dashboard: `GET /api/linkage-index?investigation=<inv>` → `ac_matrix`.

### `source <bib_key>`

Print which studies cite a bibliography key (study-level `cites[]` + per-band
cites on tests/readouts).

```bash
.venv/bin/python - "$KEY" <<'PY'
import sys
from viva_superpowers.linkage_index import studies_for_source
print("\n".join(studies_for_source(".", sys.argv[1])) or "(no studies cite this key)")
PY
```

Or via the dashboard: `GET /api/linkage-index?source=<bib_key>` → `studies`.

### `finding-by-observable <token>`

Print which findings measure an observable token (resolved through the
finding's `evidence.from_test` → the test's `measure.{path,field}`).

```bash
.venv/bin/python - "$TOKEN" <<'PY'
import sys
from viva_superpowers.linkage_index import findings_for_observable
for f in findings_for_observable(".", sys.argv[1]):
    print(f"- {f['finding']}  (study {f['study']})")
PY
```

Or via the dashboard: `GET /api/linkage-index?observable=<token>` → `findings`.

### `dag <inv>`

Print an investigation's study prerequisite DAG (nodes + prerequisite/enables
edges from each study's `pipeline_gate`).

```bash
.venv/bin/python - "$INV" <<'PY'
import sys
from viva_superpowers.linkage_index import study_dag
d = study_dag(".", sys.argv[1])
for e in d["edges"]:
    print(f"{e['from']} → {e['to']}")
PY
```

Or via the dashboard: `GET /api/linkage-index?investigation=<inv>` → `dag`.

### `observable <token>`

The **cross-study observable registry**: which composites *emit* an observable
`<token>` and which studies use those composites. Unlike `finding-by-observable`
(which resolves through finding evidence in the YAML), this answers "which
composites actually *emit* this observable, and which studies use those
composites" — so it needs the real composite build behind
`studies_for_observable`. Matching reconciles the bulk dialects (a query for
`bulk.ATP[c]` finds a composite leaf `bulk[ATP[c]]`).

> **Triggers a composite build.** The emit edges come from an injected
> `observables_for_ref` build callable, so the first call builds the composite
> (cached, ~3s first time); subsequent calls are cheap.

```bash
.venv/bin/python - "$TOKEN" <<'PY'
import sys
from viva_superpowers.linkage_index import studies_for_observable
# observables_for_ref is the dashboard's _observables_for_ref (the real build).
from vivarium_workbench.lib.observables_views import _observables_for_ref
res = studies_for_observable(".", sys.argv[1], observables_for_ref=_observables_for_ref)
print("studies:   ", ", ".join(res["studies"]) or "(none)")
print("composites:", ", ".join(res["composites"]) or "(none)")
PY
```

Or via the dashboard: `GET /api/linkage-index?observable_registry=<token>` → the
registry (studies + composites). The server supplies the build callable. (Note
the distinct `observable_registry=` param — `observable=` is the SP4a
finding-by-observable query above, which returns `findings`.)

### `composite <id>`

What a composite **emits** + which studies **use** it (via `composite_emits`).
Also triggers a composite build (cached).

```bash
.venv/bin/python - "$ID" <<'PY'
import sys
from viva_superpowers.linkage_index import composite_emits
from vivarium_workbench.lib.observables_views import _observables_for_ref
res = composite_emits(".", sys.argv[1], observables_for_ref=_observables_for_ref)
print("emits:", ", ".join(res["emits"]) or "(none)")
print("used by studies:", ", ".join(res["used_by_studies"]) or "(none)")
PY
```

Or via the dashboard: `GET /api/linkage-index?composite=<id>` → `emits` +
`used_by_studies`.

## Notes

- **Pure query, AI-free.** Every subcommand calls `linkage_index` /
  `/api/linkage-index` and prints the deterministic result. No model judgment,
  no writes — the index is ephemeral and never persisted into YAML.
- Run from the workspace root (the first argument to the helpers is the
  workspace path, shown here as `.`).
