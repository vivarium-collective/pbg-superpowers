---
name: pbg-navigate
description: Read-only navigation of the workspace knowledge graph (the SP4a linkage index). Surfaces the cheap reverse queries that today need grep — the AC→study gating matrix + unlinked-AC gaps, which studies cite a source, which findings measure an observable, and a study's prerequisite DAG. Pure deterministic query, no AI, no writes.
user-invocable: true
allowed-tools: Bash(*) Read
argument-hint: ac-gaps <inv> | source <bib_key> | finding-by-observable <token> | dag <inv>
---

# pbg-navigate

Transversal, **read-only** skill. Queries the workspace **linkage index** — a
derived, ephemeral knowledge graph over the YAML (studies ↔ composites ↔
observables ↔ sources ↔ findings ↔ acceptance ↔ study-DAG). It NEVER writes to
YAML and adds NO AI judgment: it surfaces the deterministic index built by
`pbg_superpowers.linkage_index` so you don't have to grep.

There are two equivalent backends; prefer whichever is available:

- **Direct (no server):** call `pbg_superpowers.linkage_index` via
  `.venv/bin/python`.
- **Via the dashboard:** `GET /api/linkage-index` (when the dashboard server is
  running) — the same deterministic derive, TTL-cached.

## Subcommands

### `ac-gaps <inv>`

Print the **AC→study gating matrix** for an investigation: one row per
acceptance criterion with its linked `study`, computed `result`, and a **gap**
flag when the criterion has NO `study:` link. Unlinked criteria are the gaps —
they make the report claim coverage that nothing actually gates (e.g.
`chromosome-cycle-calibration` has 5 acceptance criteria with no `study:`).

```bash
.venv/bin/python - "$INV" <<'PY'
import sys, json
from pbg_superpowers.linkage_index import ac_gating_matrix
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
from pbg_superpowers.linkage_index import studies_for_source
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
from pbg_superpowers.linkage_index import findings_for_observable
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
from pbg_superpowers.linkage_index import study_dag
d = study_dag(".", sys.argv[1])
for e in d["edges"]:
    print(f"{e['from']} → {e['to']}")
PY
```

Or via the dashboard: `GET /api/linkage-index?investigation=<inv>` → `dag`.

## Notes

- **Pure query, AI-free.** Every subcommand calls `linkage_index` /
  `/api/linkage-index` and prints the deterministic result. No model judgment,
  no writes — the index is ephemeral and never persisted into YAML.
- Run from the workspace root (the first argument to the helpers is the
  workspace path, shown here as `.`).
