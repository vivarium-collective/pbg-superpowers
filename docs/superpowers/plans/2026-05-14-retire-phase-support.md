# Retire Phase Support from pbg-superpowers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the phase-development feature (the `/pbg-phase` skill, the `phase_*` Python modules, the phase JSON schema, the model-template `phases/` dir, and every reference to phases in tests, schema, reports, skills, and docs) from pbg-superpowers, matching pbg-template's removal of its phase backend (pbg-template commit `49259a6`).

**Architecture:** Phases were the legacy unit of model-development work; the `tasks` array in `workspace.schema.json` (the active-branch workstream model) has superseded them. pbg-template already dropped its phase backend and `phases/` scaffold dir. This plan brings pbg-superpowers in line: delete the phase code surface, then scrub every consumer (schema, report renderer, model template, skills, README, tests). Removal order is "consumers first, then the thing they consume" so the test suite stays green after every task.

**Tech Stack:** Python 3.11+, pytest, hatchling, Jinja2, JSON Schema (draft-07). Decision context: this conversation chose option **B** — "phases are being retired everywhere."

**Out of scope (follow-ups, not this plan):**
- `tests/test_workspace_yaml_schema.py::test_migrate_v1_to_v2_lifts_first_model` and `::test_migrate_v2_is_idempotent` exercise pbg-template's `_migrate_v1_to_v2.py` helper, which still lifts `phases`. They do not validate against pbg-superpowers' schema, so they keep passing. Retiring phase-lifting from pbg-template's migration helper is a pbg-template change — leave these two tests untouched.
- `skills/pbg-expert/SKILL.md` mentions "Phase 1/2/3…" as its own internal procedure headings and "phase" as a cell-cycle enum example (`G1/S/G2/M`). Neither is the workflow-phase feature — do not touch pbg-expert.
- The `phase-space` value in the `visualization.type` enum (`workspace.schema.json`) is a *plot type*, not a workflow phase — keep it.
- Historical plan/spec docs under `docs/superpowers/` that mention phases are archived artifacts — leave them.

---

## File Structure

**Delete entirely:**
- `skills/pbg-phase/` — the skill directory (contains `SKILL.md`)
- `pbg_superpowers/phase_md.py` — phase frontmatter parser/renderer
- `pbg_superpowers/phase_gate.py` — phase gate evaluation + test-module generation
- `pbg_superpowers/phase_files.py` — `plan.md` / `phase-N.md` skeleton generation
- `pbg_superpowers/schemas/phase.schema.json` — phase frontmatter JSON schema
- `tests/test_phase_md.py`, `tests/test_phase_gate.py`, `tests/test_phase_files.py`, `tests/test_phase_frontmatter_schema.py` — dedicated phase unit tests
- `tests/fixtures/phases/` — phase markdown fixtures (`phase-1-planned.md`, `phase-2-in_progress.md`, `phase-3-gate_pending.md`)
- `templates/model/phases/` — model-template phases dir (`plan.md.j2`, `deliverables/.keep`)

**Modify:**
- `tests/test_failure_modes.py` — drop phase imports + 5 phase tests
- `tests/test_e2e_happy_path.py` — drop phase-plan/gate steps + phase assertions
- `tests/test_workspace_yaml_schema.py` — drop the "Top-level phases" test section + phase block in `test_full_workspace_validates`
- `tests/test_report_render.py` — drop `phases` fixture key + `"Phase tracker"` assertion
- `tests/test_model_scaffold.py` — drop `phases/plan.md` + `phases/deliverables/.keep` from `must_exist`
- `tests/test_skill_manifests.py` — drop `pbg-phase` from `EXPECTED_SKILLS` (done in Task 6, atomically with deleting the skill dir)
- `pbg_superpowers/schemas/workspace.schema.json` — remove top-level `phases` property, the `phase` definition, and the `phases` field in the `visualization` and `simulation` definitions
- `pbg_superpowers/report.py` — drop `phases=model.get("phases", [])` from `render_model_report`
- `templates/model/reports/index.html.j2` — remove the Phase tracker panel + per-phase deep-dive loop
- `plugin.yaml` — remove `pbg-phase` from `skills:`, reword the description
- `skills/pbg-report/SKILL.md`, `skills/pbg-server/SKILL.md`, `skills/pbg-viz/SKILL.md`, `skills/pbg-workspace/SKILL.md` — remove phase references
- `README.md` — remove the `/pbg-phase` row, the "Phases are first-class" bullet, and reword scope sentences

---

## Task 1: Strip phase blocks from shared test files

Remove every phase reference from tests that ALSO cover non-phase behavior, so these files stop importing the phase modules. The dedicated `test_phase_*.py` files are deleted whole in Task 2; the phase modules themselves in Task 3.

**Files:**
- Modify: `tests/test_failure_modes.py`
- Modify: `tests/test_e2e_happy_path.py`
- Modify: `tests/test_workspace_yaml_schema.py`
- Modify: `tests/test_report_render.py`
- Modify: `tests/test_model_scaffold.py`

> **Note:** `tests/test_skill_manifests.py` is intentionally NOT touched here. `test_all_expected_skills_present` also rejects *extra* skills, so removing `pbg-phase` from `EXPECTED_SKILLS` while `skills/pbg-phase/` still exists breaks the suite. That edit moves to Task 6, atomic with deleting the skill directory.

- [ ] **Step 1: `tests/test_failure_modes.py` — remove phase imports**

Delete these two lines (currently lines 12–13):

```python
from pbg_superpowers.phase_md import parse_phase_md, PhaseValidationError
from pbg_superpowers.phase_gate import evaluate_gate
```

- [ ] **Step 2: `tests/test_failure_modes.py` — remove the 5 phase test functions**

Delete the five functions in full: `test_phase_md_rejects_no_frontmatter`, `test_phase_md_rejects_unclosed_frontmatter`, `test_phase_gate_pending_means_not_passed`, `test_phase_gate_no_tests_means_not_passed`, `test_phase_gate_failing_blocks_promotion` (currently lines 32–69, i.e. everything after `test_load_rejects_truncated_workspace_yaml` to end of file). After this edit the file ends with `test_load_rejects_truncated_workspace_yaml`.

- [ ] **Step 3: `tests/test_e2e_happy_path.py` — trim the docstring**

Replace the module docstring (lines 1–7):

```python
"""End-to-end happy path:
  scaffold workspace -> scaffold model -> install wrapper -> register process ->
  snapshot registry -> plan phase 1 -> generate phase tests -> mark passing ->
  gate passes -> render reports.

This synthesizes what every stage skill does in production, using the
programmatic helpers directly (no Agent dispatches, no walkthroughs)."""
```

with:

```python
"""End-to-end happy path:
  scaffold workspace -> scaffold model -> install wrapper -> register process ->
  snapshot registry -> render reports.

This synthesizes what every stage skill does in production, using the
programmatic helpers directly (no Agent dispatches, no walkthroughs)."""
```

- [ ] **Step 4: `tests/test_e2e_happy_path.py` — rename the test + drop phase keys from the model entry**

Rename the test function (line 41) from `test_full_flow_scaffold_to_phase_complete` to `test_full_flow_scaffold_to_reports`.

In the `wsdata["models"]` block (currently lines 60–74), remove the `phase_plan` stage line and the `phases` key so it reads:

```python
    wsdata["models"] = {
        "m": {
            "submodule_path": "models/m", "remote": "local",
            "pbg_processes": ["pbg-fake-tool"],
            "stages": {
                "add_model": {"status": "complete", "pr": 1},
                "pull_processes": {"status": "complete", "pr": 2},
                "data": {"status": "complete", "pr": 3},
                "expert_input": {"status": "complete", "pr": 4},
                "baseline": {"status": "complete", "pr": 5},
            },
        }
    }
```

- [ ] **Step 5: `tests/test_e2e_happy_path.py` — delete phase steps 7–12**

Delete the entire block from the `# 7. Create initial phase plan` comment through the end of step 12 (currently lines 122–175 — the `create_initial_plan`, `generate_test_module`, `test_phases.py` run, frontmatter status edit, `evaluate_gate`, and the `wsdata["models"]["m"]["phases"] = [...]` update). Step 6 (registry snapshot, ending with `assert snap["processes"] == ["FakeProcess"]`) is immediately followed by step 13 (`# 13. Render reports ...`).

- [ ] **Step 6: `tests/test_e2e_happy_path.py` — drop the phase-tracker assertions**

In the report assertions block (currently lines 187–196), remove these two lines:

```python
    assert "p1" in model_html  # phase tracker shows phase 1
    assert "complete" in model_html  # status pill class
```

The block keeps `assert "FakeProcess" in model_html`.

- [ ] **Step 7: `tests/test_workspace_yaml_schema.py` — drop the phase block from `test_full_workspace_validates`**

Replace the function (currently lines 33–52):

```python
def test_full_workspace_validates(validator):
    """Full v2 workspace with phases/observables/visualizations at top-level."""
    ws = _minimal_workspace()
    ws["package_path"] = "pbg_chromosome_rep1"
    ws["pbg_processes"] = ["pbg-cobra", "pbg-smoldyn"]
    ws["phases"] = [
        {"n": 1, "name": "DnaA accumulation", "status": "complete", "gate_passed": True},
        {"n": 2, "name": "Replication extension", "status": "planned"},
    ]
    ws["observables"] = [
        {"name": "DnaA", "store_path": "chromosome.DnaA_count", "units": "molecules"},
        {"name": "cell_mass", "store_path": "cell.mass"},
    ]
    ws["visualizations"] = [
        {"name": "dnaA-trajectory", "type": "time-series", "observables": ["DnaA"]},
    ]
    ws["datasets"] = [{"name": "bremer-1996", "path": "datasets/bremer-1996/", "claims": ["phase-1.dnaA-accumulation"]}]
    ws["references_bib"] = "references/papers.bib"
    ws["server"] = {"enabled": False}
    validator.validate(ws)
```

with:

```python
def test_full_workspace_validates(validator):
    """Full v2 workspace with observables/visualizations at top-level."""
    ws = _minimal_workspace()
    ws["package_path"] = "pbg_chromosome_rep1"
    ws["pbg_processes"] = ["pbg-cobra", "pbg-smoldyn"]
    ws["observables"] = [
        {"name": "DnaA", "store_path": "chromosome.DnaA_count", "units": "molecules"},
        {"name": "cell_mass", "store_path": "cell.mass"},
    ]
    ws["visualizations"] = [
        {"name": "dnaA-trajectory", "type": "time-series", "observables": ["DnaA"]},
    ]
    ws["datasets"] = [{"name": "bremer-1996", "path": "datasets/bremer-1996/", "claims": ["dnaA-accumulation"]}]
    ws["references_bib"] = "references/papers.bib"
    ws["server"] = {"enabled": False}
    validator.validate(ws)
```

- [ ] **Step 8: `tests/test_workspace_yaml_schema.py` — delete the "Top-level phases" section**

Delete the whole section (currently lines 66–122): the `# ---- Top-level phases ----` comment banner and the five functions `test_phase_n_must_be_positive`, `test_phase_invalid_status_fails`, `test_source_artifact_in_phase_validates`, `test_source_artifact_invalid_kind_fails`, `test_phase_prereq_phases_validates`. The file goes directly from `test_no_models_field_in_v2` to the `# ---- Top-level observables ----` banner.

- [ ] **Step 9: `tests/test_report_render.py` — drop the `phases` fixture key**

In `test_render_model_report_with_registry`, replace the `wsdata["models"]` block (currently lines 49–57):

```python
    wsdata["models"] = {
        "ecoli-rep": {
            "submodule_path": "models/ecoli-rep", "remote": "x",
            "pbg_processes": ["pbg-cobra"],
            "stages": {"add_model": {"status": "complete", "pr": 2}},
            "phases": [{"n": 1, "name": "DnaA accumulation",
                        "status": "complete", "pr": 8, "gate_passed": True}],
        }
    }
```

with:

```python
    wsdata["models"] = {
        "ecoli-rep": {
            "submodule_path": "models/ecoli-rep", "remote": "x",
            "pbg_processes": ["pbg-cobra"],
            "stages": {"add_model": {"status": "complete", "pr": 2}},
        }
    }
```

- [ ] **Step 10: `tests/test_report_render.py` — drop the `"Phase tracker"` assertion**

In the same test, remove this line (currently line 75):

```python
    assert "Phase tracker" in html
```

- [ ] **Step 11: `tests/test_model_scaffold.py` — drop phase paths from `must_exist`**

Remove these two entries from the `must_exist` list (currently lines 37–38):

```python
        "phases/plan.md",
        "phases/deliverables/.keep",
```

- [ ] **Step 12: Run the suite — phase modules still present, so this must stay green**

Run: `cd ~/code/pbg-superpowers && source .venv/bin/activate && pytest -q`
Expected: PASS (the `test_phase_*.py` files and phase modules still exist; we only removed *references* from shared tests, plus phase test functions). The count drops by the 5 deleted `test_failure_modes` tests + 5 deleted `test_workspace_yaml_schema` tests.

- [ ] **Step 13: Commit**

```bash
git add tests/test_failure_modes.py tests/test_e2e_happy_path.py tests/test_workspace_yaml_schema.py tests/test_report_render.py tests/test_model_scaffold.py
git commit -m "test: drop phase references from shared test files"
```

---

## Task 2: Delete dedicated phase test files + fixtures

**Files:**
- Delete: `tests/test_phase_md.py`
- Delete: `tests/test_phase_gate.py`
- Delete: `tests/test_phase_files.py`
- Delete: `tests/test_phase_frontmatter_schema.py`
- Delete: `tests/fixtures/phases/` (directory: `phase-1-planned.md`, `phase-2-in_progress.md`, `phase-3-gate_pending.md`)

- [ ] **Step 1: Confirm nothing else references these fixtures**

Run: `grep -rn "fixtures/phases\|test_phase" --include="*.py" tests/`
Expected: no matches outside the four files being deleted (Task 1 already scrubbed the shared tests).

- [ ] **Step 2: Delete the files and the fixtures directory**

```bash
git rm tests/test_phase_md.py tests/test_phase_gate.py tests/test_phase_files.py tests/test_phase_frontmatter_schema.py
git rm -r tests/fixtures/phases
```

- [ ] **Step 3: Run the suite**

Run: `pytest -q`
Expected: PASS. The phase modules in `pbg_superpowers/` still exist but now have no test importers; nothing should error on collection.

- [ ] **Step 4: Commit**

```bash
git commit -m "test: delete dedicated phase test files and fixtures"
```

---

## Task 3: Delete the phase Python modules + phase JSON schema

**Files:**
- Delete: `pbg_superpowers/phase_md.py`
- Delete: `pbg_superpowers/phase_gate.py`
- Delete: `pbg_superpowers/phase_files.py`
- Delete: `pbg_superpowers/schemas/phase.schema.json`

- [ ] **Step 1: Confirm no remaining importers**

Run: `grep -rn "phase_md\|phase_gate\|phase_files\|phase.schema" --include="*.py" --include="*.json" pbg_superpowers/ tests/ scripts/ server/`
Expected: the only matches are `phase_files.py` importing `phase_md` internally (those files are about to be deleted). No external importer. If anything else matches, stop and resolve it before deleting.

- [ ] **Step 2: Delete the modules and schema**

```bash
git rm pbg_superpowers/phase_md.py pbg_superpowers/phase_gate.py pbg_superpowers/phase_files.py pbg_superpowers/schemas/phase.schema.json
```

- [ ] **Step 3: Run the suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: remove phase_md / phase_gate / phase_files modules + phase schema"
```

---

## Task 4: Remove phases from `workspace.schema.json`

**Files:**
- Modify: `pbg_superpowers/schemas/workspace.schema.json`

- [ ] **Step 1: Remove the top-level `phases` property**

Delete this block from `properties` (currently lines 23–26):

```json
    "phases": {
      "type": "array",
      "items": {"$ref": "#/definitions/phase"}
    },
```

- [ ] **Step 2: Remove the `phase` definition**

Delete this block from `definitions` (currently lines 94–113):

```json
    "phase": {
      "type": "object",
      "required": ["n", "name", "status"],
      "properties": {
        "n": {"type": "integer", "minimum": 1},
        "name": {"type": "string"},
        "status": {"enum": ["planned", "in_progress", "gate_pending", "complete"]},
        "pr": {"type": ["integer", "null"]},
        "gate_passed": {"type": "boolean"},
        "opened_pr": {"type": ["integer", "null"]},
        "prereq_phases": {"type": "array", "items": {"type": "integer"}},
        "source_artifact": {
          "type": "object",
          "properties": {
            "kind": {"enum": ["expert_doc", "dataset", "reference", "claim"]},
            "ref": {"type": "string"}
          }
        }
      }
    },
```

- [ ] **Step 3: Remove the `phases` field from the `visualization` definition**

In `definitions.visualization.properties`, delete this line (currently line 133):

```json
        "phases": {"type": "array", "items": {"type": "integer", "minimum": 1}},
```

Note: `visualization` has `"additionalProperties": false`, so the field must be removed, not just left unreferenced.

- [ ] **Step 4: Remove the `phases` field from the `simulation` definition**

In `definitions.simulation.properties`, delete this line (currently line 150):

```json
        "phases": {"type": "array", "items": {"type": "integer", "minimum": 1}, "description": "Phase numbers this simulation belongs to (empty = global)"},
```

Note: `simulation` also has `"additionalProperties": false`.

- [ ] **Step 5: Verify the JSON still parses and has no dangling phase references**

Run:
```bash
python -c "import json; json.load(open('pbg_superpowers/schemas/workspace.schema.json')); print('parses OK')"
grep -n '"phases"\|#/definitions/phase\|"phase":' pbg_superpowers/schemas/workspace.schema.json
```
Expected: `parses OK`, and the `grep` returns **no matches** (exit code 1). The `phase-space` *plot-type* enum value in `definitions.visualization` is intentionally preserved and is not matched by these patterns.

- [ ] **Step 6: Run the suite**

Run: `pytest -q`
Expected: PASS — `test_workspace_yaml_schema.py` no longer references phases (Task 1).

- [ ] **Step 7: Commit**

```bash
git add pbg_superpowers/schemas/workspace.schema.json
git commit -m "feat: drop phases from workspace.schema.json"
```

---

## Task 5: Update the report renderer + model template

**Files:**
- Modify: `pbg_superpowers/report.py:77`
- Modify: `templates/model/reports/index.html.j2`
- Delete: `templates/model/phases/` (directory: `plan.md.j2`, `deliverables/.keep`)

- [ ] **Step 1: `pbg_superpowers/report.py` — drop the `phases` kwarg**

In `render_model_report`, remove this line from the `tpl.render(...)` call (currently line 77):

```python
        phases=model.get("phases", []),
```

The `tpl.render(...)` call keeps `model_name`, `generated_at`, `registry`, and `pbg_doc_json`.

- [ ] **Step 2: `templates/model/reports/index.html.j2` — remove the Phase tracker panel**

Delete this block (currently lines 11–17, including the trailing blank line after `</div>`):

```html

<div class="panel"><h2>Phase tracker</h2>
{% if phases %}<div class="tracker">
{% for p in phases %}<div class="pill {{ p.status }}"><strong>{{ p.n }} · {{ p.name }}</strong><br>{{ p.status }}</div>{% endfor %}
</div>
{% else %}<p>No phases yet. <code>/pbg-phase-plan {{ model_name }}</code></p>{% endif %}
</div>
```

After this edit, `<div id="guidance" ...></div>` is followed directly by the `<div class="panel"><h2>Process registry</h2>` panel.

- [ ] **Step 3: `templates/model/reports/index.html.j2` — remove the per-phase deep-dive loop**

Delete this block (currently lines 33–42, including the surrounding blank lines):

```html

{% for p in phases if p.status == 'complete' %}
<div class="panel"><h3>Phase {{ p.n }} · {{ p.name }} — deep dive</h3>
{% if p.deliverables and p.deliverables.plots %}{% for plot in p.deliverables.plots %}<img src="../phases/{{ plot }}" alt="">{% endfor %}{% endif %}
<h4>Acceptance tests</h4>
<table><thead><tr><th>ID</th><th>Description</th><th>Status</th></tr></thead><tbody>
{% for t in (p.acceptance_tests or []) %}<tr><td><code>{{ t.id }}</code></td><td>{{ t.desc }}</td><td>{{ t.status }}</td></tr>{% endfor %}
</tbody></table>
</div>
{% endfor %}
```

After this edit, the `<div class="panel"><h2>Type registry</h2>` panel is followed directly by the `<div class="panel"><h2>Composite document</h2>` panel.

- [ ] **Step 4: Delete the model-template `phases/` directory**

```bash
git rm -r templates/model/phases
```

- [ ] **Step 5: Run the report + model-scaffold tests**

Run: `pytest -q tests/test_report_render.py tests/test_model_scaffold.py tests/test_e2e_happy_path.py`
Expected: PASS. The model report renders without a Phase tracker; the scaffolded model tree no longer contains `phases/`.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pbg_superpowers/report.py templates/model/reports/index.html.j2
git commit -m "feat: drop phase tracker from model report + template"
```

---

## Task 6: Remove the `/pbg-phase` skill + scrub other skills

**Files:**
- Delete: `skills/pbg-phase/` (directory)
- Modify: `tests/test_skill_manifests.py`
- Modify: `plugin.yaml`
- Modify: `skills/pbg-report/SKILL.md`
- Modify: `skills/pbg-server/SKILL.md`
- Modify: `skills/pbg-viz/SKILL.md`
- Modify: `skills/pbg-workspace/SKILL.md`

- [ ] **Step 1: Delete the skill directory and drop it from `EXPECTED_SKILLS`**

These two changes are atomic — `test_skill_manifests.py::test_all_expected_skills_present` rejects both missing AND extra skills, so the directory deletion and the `EXPECTED_SKILLS` edit must land together.

Delete the directory:
```bash
git rm -r skills/pbg-phase
```

Then in `tests/test_skill_manifests.py`, replace the `EXPECTED_SKILLS` set (currently lines 11–15):
```python
EXPECTED_SKILLS = {
    "pbg-workspace", "pbg-server", "pbg-report", "pbg-phase",
    "pbg-viz", "pbg-package", "pbg-expert", "pbg-composer", "pbg-wrapper",
    "pbg-suggest", "pbg-explore",
}
```
with:
```python
EXPECTED_SKILLS = {
    "pbg-workspace", "pbg-server", "pbg-report",
    "pbg-viz", "pbg-package", "pbg-expert", "pbg-composer", "pbg-wrapper",
    "pbg-suggest", "pbg-explore",
}
```

- [ ] **Step 2: `plugin.yaml` — remove `pbg-phase` from the skills list**

Delete this line from the `skills:` list (currently line 47):

```yaml
  - pbg-phase
```

- [ ] **Step 3: `plugin.yaml` — reword the in-development description**

Replace this line (currently line 12):

```yaml
  dashboard, multi-phase model development, and visualization codegen.
```

with:

```yaml
  dashboard, model development, and visualization codegen.
```

- [ ] **Step 4: `skills/pbg-report/SKILL.md` — remove phase references**

Three edits:

(a) In the frontmatter `description:` field, replace:
```
Pulls workspace.yaml, phase frontmatters, decisions log, and (per model) the live process-bigraph registry;
```
with:
```
Pulls workspace.yaml, decisions log, and (per model) the live process-bigraph registry;
```

(b) Replace the bullet:
```
- `<workspace>/reports/index.html` — workspace dashboard: phase tracker, process registry, type registry, recent decisions, browsable composite document
```
with:
```
- `<workspace>/reports/index.html` — workspace dashboard: process registry, type registry, recent decisions, browsable composite document
```

(c) Replace the bullet:
```
- Never modifies `workspace.yaml`, `phases/*.md`, `decisions.yaml`, or any other persistent state — read-only consumer.
```
with:
```
- Never modifies `workspace.yaml`, `decisions.yaml`, or any other persistent state — read-only consumer.
```

- [ ] **Step 5: `skills/pbg-server/SKILL.md` — remove the phase reference**

Replace the bullet:
```
- **Build Model** — workstream management strip (active branch, Push, Create PR, End), phase list with Start phase / Evaluate gate buttons.
```
with:
```
- **Build Model** — workstream management strip (active branch, Push, Create PR, End).
```

- [ ] **Step 6: `skills/pbg-viz/SKILL.md` — remove the phase reference**

Replace:
```
1. Read `.pbg/viz-requests/<visualization-name>.md` from the current workspace. It contains the user's natural-language description plus workspace context (observables, simulations, phases). If the file doesn't exist, abort and tell the user to click **Create** in the dashboard first.
```
with:
```
1. Read `.pbg/viz-requests/<visualization-name>.md` from the current workspace. It contains the user's natural-language description plus workspace context (observables, simulations). If the file doesn't exist, abort and tell the user to click **Create** in the dashboard first.
```

- [ ] **Step 7: `skills/pbg-workspace/SKILL.md` — remove the phase reference**

Replace:
```
7. **Next steps** — print a brief summary: workspace is ready; open the dashboard with `bash scripts/serve.sh`. From the dashboard, use the **Registry** tab to install pbg-* modules, **Simulation Setup** to configure observables, and **Build Model** to start a workstream branch and drive phases.
```
with:
```
7. **Next steps** — print a brief summary: workspace is ready; open the dashboard with `bash scripts/serve.sh`. From the dashboard, use the **Registry** tab to install pbg-* modules, **Simulation Setup** to configure observables, and **Build Model** to start a workstream branch.
```

- [ ] **Step 8: Confirm no workflow-phase references remain in skills**

Run: `grep -rn -i "phase" skills/`
Expected: matches only in `skills/pbg-expert/SKILL.md` — the internal procedure headings (`### Phase 1: Study the Tool` …) and the cell-cycle enum example (`'phase': 'enum[string,"G1"...`). Those are intentionally kept. Any other match is a miss — fix it.

- [ ] **Step 9: Run the suite**

Run: `pytest -q`
Expected: PASS — `test_skill_manifests.py::test_all_expected_skills_present` now passes with `pbg-phase` gone from both `EXPECTED_SKILLS` (Task 1) and the `skills/` directory.

- [ ] **Step 10: Commit**

```bash
git add plugin.yaml skills/ tests/test_skill_manifests.py
git commit -m "feat: remove /pbg-phase skill + scrub phase refs from other skills"
```

---

## Task 7: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Reword the opening scope sentence**

Replace (currently lines 4–6):

```
and organizes that work into multi-phase research workspaces with an interactive
dashboard and HTML reports.
```

with:

```
and organizes that work into research workspaces with an interactive
dashboard and HTML reports.
```

- [ ] **Step 2: Reword the value-proposition sentence**

Replace (currently lines 8–10):

```
Use it to go from "I have a simulator" to "I have a reviewable, reproducible,
multi-phase model project" — without writing the registry, packaging, and report
boilerplate by hand.
```

with:

```
Use it to go from "I have a simulator" to "I have a reviewable, reproducible
model project" — without writing the registry, packaging, and report
boilerplate by hand.
```

- [ ] **Step 3: Remove the `/pbg-phase` row from the skills table**

Delete this row (currently line 42):

```
| `/pbg-phase <n>` | In dev | current workspace | Drive phase _n_ of model development — code, tests, and the phase gate. |
```

- [ ] **Step 4: Reword the "Workspace IS the model" bullet**

In the Concepts section, replace (currently lines 49–51):

```
- **Workspace IS the model.** A workspace root contains `pbg_<slug>/`, `tests/`,
  `phases/`, and `workspace.yaml` directly. It owns the datasets, references,
  decision log, and dashboard for one model.
```

with:

```
- **Workspace IS the model.** A workspace root contains `pbg_<slug>/`, `tests/`,
  and `workspace.yaml` directly. It owns the datasets, references, decision log,
  and dashboard for one model.
```

- [ ] **Step 5: Remove the "Phases are first-class" bullet**

Delete this bullet in full (currently lines 72–74):

```
- **Phases are first-class.** Each phase is a `phases/phase-N.md` file with YAML
  frontmatter (`status`, `prereq_phases`, `gate_passed`, `acceptance_tests`, …).
  The Build Model tab renders each with Start phase / Evaluate gate actions.
```

- [ ] **Step 6: Reword the L3 tests bullet**

Replace (currently lines 90–91):

```
- **L3 (workspace tests)** — `pytest tests/` from a workspace root, including registry
  checks, a drift detector, and `test_phases.py` auto-generated from phase frontmatter.
```

with:

```
- **L3 (workspace tests)** — `pytest tests/` from a workspace root, including registry
  checks and a drift detector.
```

- [ ] **Step 7: Confirm no workflow-phase references remain in README**

Run: `grep -n -i "phase" README.md`
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: remove phase support from README"
```

---

## Task 8: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full suite green**

Run: `cd ~/code/pbg-superpowers && source .venv/bin/activate && pytest -q`
Expected: PASS, zero failures.

- [ ] **Step 2: No stray workflow-phase references in the live surface**

Run:
```bash
grep -rn -i "phase" \
  --include="*.py" --include="*.json" --include="*.yaml" --include="*.yml" \
  --include="*.md" --include="*.j2" \
  pbg_superpowers/ tests/ skills/ templates/ server/ scripts/ plugin.yaml README.md
```
Expected — only these acceptable matches remain:
- `skills/pbg-expert/SKILL.md` — internal procedure headings + cell-cycle enum example
- `pbg_superpowers/schemas/workspace.schema.json` — the `phase-space` plot-type enum value
- `pbg_superpowers/visualizations/phase_space.py` (if present) — a plot-type visualization, unrelated to workflow phases

Anything else is a miss — open the file and remove it.

- [ ] **Step 3: Confirm the deleted surface is gone**

Run:
```bash
ls skills/pbg-phase pbg_superpowers/phase_md.py pbg_superpowers/phase_gate.py \
   pbg_superpowers/phase_files.py pbg_superpowers/schemas/phase.schema.json \
   templates/model/phases tests/fixtures/phases 2>&1
```
Expected: every path reports "No such file or directory".

- [ ] **Step 4: Confirm git status is clean**

Run: `git status`
Expected: working tree clean, all task commits present.
