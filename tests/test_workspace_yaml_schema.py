"""Workspace schema tests — v2 (schema_version: 2, workspace = model)."""
import json
import pytest
from jsonschema import Draft7Validator, ValidationError


@pytest.fixture
def validator(schemas_dir):
    schema = json.loads((schemas_dir / "workspace.schema.json").read_text())
    return Draft7Validator(schema)


# ---------------------------------------------------------------------------
# Minimal v2 workspace
# ---------------------------------------------------------------------------

def _minimal_workspace():
    return {
        "schema_version": 2,
        "name": "test-ws",
        "created": "2026-05-09",
        "plugin_version": "0.1.0",
        "stages": {
            "workspace_bootstrap": {"status": "complete", "pr": 1, "completed": "2026-05-09"}
        },
    }


def test_minimal_workspace_validates(validator):
    validator.validate(_minimal_workspace())


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


# ---------------------------------------------------------------------------
# v2: no models field required (breaking from v1)
# ---------------------------------------------------------------------------

def test_no_models_field_in_v2(validator):
    """Schema v2 does not define models — workspace without models validates."""
    ws = _minimal_workspace()
    # No 'models' key — should validate cleanly.
    validator.validate(ws)


# ---------------------------------------------------------------------------
# Top-level phases
# ---------------------------------------------------------------------------

def test_phase_n_must_be_positive(validator):
    ws = _minimal_workspace()
    ws["phases"] = [{"n": 0, "name": "x", "status": "planned"}]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_phase_invalid_status_fails(validator):
    ws = _minimal_workspace()
    ws["phases"] = [{"n": 1, "name": "x", "status": "BOGUS"}]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_source_artifact_in_phase_validates(validator):
    """phase with optional source_artifact field validates."""
    ws = _minimal_workspace()
    ws["phases"] = [
        {
            "n": 1,
            "name": "DnaA accumulation",
            "status": "planned",
            "source_artifact": {
                "kind": "expert_doc",
                "ref": "replication-review-2025",
            },
        },
    ]
    validator.validate(ws)


def test_source_artifact_invalid_kind_fails(validator):
    ws = _minimal_workspace()
    ws["phases"] = [
        {
            "n": 1,
            "name": "DnaA accumulation",
            "status": "planned",
            "source_artifact": {"kind": "bogus-kind", "ref": "some-doc"},
        },
    ]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_phase_prereq_phases_validates(validator):
    ws = _minimal_workspace()
    ws["phases"] = [
        {"n": 1, "name": "Phase A", "status": "complete", "gate_passed": True},
        {"n": 2, "name": "Phase B", "status": "planned", "prereq_phases": [1]},
    ]
    validator.validate(ws)


# ---------------------------------------------------------------------------
# Top-level observables
# ---------------------------------------------------------------------------

def test_observable_validates(validator):
    ws = _minimal_workspace()
    ws["observables"] = [
        {
            "name": "DnaA",
            "store_path": "chromosome.DnaA_count",
            "units": "molecules",
            "description": "DnaA protein count",
        },
        {"name": "cell_mass", "store_path": "cell.mass"},  # units/description optional
    ]
    validator.validate(ws)


def test_observable_missing_store_path_fails(validator):
    ws = _minimal_workspace()
    ws["observables"] = [{"name": "DnaA"}]  # store_path missing — must fail
    with pytest.raises(ValidationError):
        validator.validate(ws)


# ---------------------------------------------------------------------------
# Top-level visualizations
# ---------------------------------------------------------------------------

def test_visualization_validates(validator):
    ws = _minimal_workspace()
    ws["observables"] = [{"name": "DnaA", "store_path": "chromosome.DnaA_count"}]
    ws["visualizations"] = [
        {
            "name": "dnaA-trajectory",
            "type": "time-series",
            "observables": ["DnaA"],
            "config": {"y_label": "DnaA (molecules)"},
        },
        {
            "name": "dnaA-histogram",
            "type": "histogram",
            "observables": ["DnaA"],
        },
    ]
    validator.validate(ws)


def test_visualization_invalid_type_fails(validator):
    ws = _minimal_workspace()
    ws["visualizations"] = [
        {"name": "bad-viz", "type": "scatter-plot", "observables": ["DnaA"]},
    ]
    with pytest.raises(ValidationError):
        validator.validate(ws)


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

def test_imports_validates(validator):
    ws = _minimal_workspace()
    ws["imports"] = {
        "v2ecoli": {
            "source": "https://github.com/eagmon/v2ecoli.git",
            "ref": "v0.5.2",
            "mode": "reference",
            "path": "external/v2ecoli",
            "description": "Whole-cell E. coli model",
        },
        "legacy-rep": {
            "source": "git@github.com:lab/replication-old.git",
            "ref": "main",
            "mode": "fork-source",
        },
    }
    validator.validate(ws)


def test_import_invalid_mode_fails(validator):
    ws = _minimal_workspace()
    ws["imports"] = {"x": {"source": "u", "ref": "r", "mode": "BOGUS"}}
    with pytest.raises(ValidationError):
        validator.validate(ws)


# ---------------------------------------------------------------------------
# Expert docs, references PDFs, datasets
# ---------------------------------------------------------------------------

def test_expert_doc_sha256_optional(validator):
    ws = _minimal_workspace()
    ws["expert_docs"] = [
        {"name": "review-2025", "path": "references/expert/review-2025.pdf", "sha256": "abc123def456"},
        {"name": "notes", "path": "references/expert/notes.md"},  # no sha256 — valid
    ]
    validator.validate(ws)


def test_references_pdfs_validates(validator):
    ws = _minimal_workspace()
    ws["references_pdfs"] = [
        {
            "bib_key": "Bremer1996",
            "path": "references/papers/Bremer1996.pdf",
            "sha256": "deadbeefcafe1234deadbeefcafe1234deadbeefcafe1234deadbeefcafe1234",
        }
    ]
    validator.validate(ws)


def test_references_pdfs_missing_sha256_fails(validator):
    ws = _minimal_workspace()
    ws["references_pdfs"] = [
        {"bib_key": "Bremer1996", "path": "references/papers/Bremer1996.pdf"}
        # sha256 missing — should fail
    ]
    with pytest.raises(ValidationError):
        validator.validate(ws)


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

def test_missing_schema_version_fails(validator):
    ws = _minimal_workspace()
    del ws["schema_version"]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_schema_version_1_fails(validator):
    """v2 schema rejects schema_version: 1."""
    ws = _minimal_workspace()
    ws["schema_version"] = 1
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_invalid_stage_status_fails(validator):
    ws = _minimal_workspace()
    ws["stages"]["workspace_bootstrap"]["status"] = "bogus"
    with pytest.raises(ValidationError):
        validator.validate(ws)


# ---------------------------------------------------------------------------
# Migration helper tests (v1 -> v2 logic)
# ---------------------------------------------------------------------------

def test_migrate_v1_to_v2_lifts_first_model():
    """_migrate_v1_to_v2 lifts phases/observables/visualizations from first model."""
    import sys
    from pathlib import Path
    # Import migration helper from pbg-template scripts.
    template_dir = Path.home() / "code" / "pbg-template"
    if not template_dir.exists():
        pytest.skip("pbg-template not found")
    scripts_dir = str(template_dir / "template")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from scripts._migrate_v1_to_v2 import migrate_v1_to_v2

    v1_ws = {
        "schema_version": 1,
        "name": "test-ws",
        "created": "2026-01-01",
        "plugin_version": "0.1.0",
        "stages": {"workspace_bootstrap": {"status": "complete"}},
        "models": {
            "my-model": {
                "submodule_path": "models/my-model",
                "remote": "https://github.com/org/my-model.git",
                "pbg_processes": ["pbg-cobra"],
                "stages": {},
                "phases": [{"n": 1, "name": "Phase A", "status": "planned"}],
                "observables": [{"name": "X", "store_path": "cell.X"}],
                "visualizations": [{"name": "X-viz", "type": "time-series", "observables": ["X"]}],
            }
        },
    }
    v2 = migrate_v1_to_v2(v1_ws)
    assert v2["schema_version"] == 2
    assert "models" not in v2
    assert v2["package_path"] == "pbg_my_model"
    assert len(v2["phases"]) == 1
    assert v2["phases"][0]["name"] == "Phase A"
    assert len(v2["observables"]) == 1
    assert v2["observables"][0]["name"] == "X"
    assert len(v2["visualizations"]) == 1
    assert v2["visualizations"][0]["name"] == "X-viz"
    assert v2["pbg_processes"] == ["pbg-cobra"]


def test_migrate_v2_is_idempotent():
    """Migrating a v2 workspace is a no-op."""
    import sys
    from pathlib import Path
    template_dir = Path.home() / "code" / "pbg-template"
    if not template_dir.exists():
        pytest.skip("pbg-template not found")
    scripts_dir = str(template_dir / "template")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from scripts._migrate_v1_to_v2 import migrate_v1_to_v2

    v2_ws = {
        "schema_version": 2,
        "name": "test-ws",
        "created": "2026-01-01",
        "plugin_version": "0.1.0",
        "stages": {"workspace_bootstrap": {"status": "complete"}},
        "phases": [{"n": 1, "name": "Phase A", "status": "planned"}],
        "observables": [{"name": "X", "store_path": "cell.X"}],
        "visualizations": [],
    }
    result = migrate_v1_to_v2(v2_ws)
    assert result["schema_version"] == 2
    assert result["phases"] == v2_ws["phases"]
    assert result["observables"] == v2_ws["observables"]
