import json
import pytest
from jsonschema import Draft7Validator, ValidationError


@pytest.fixture
def validator(schemas_dir):
    schema = json.loads((schemas_dir / "workspace.schema.json").read_text())
    return Draft7Validator(schema)


def _minimal_workspace():
    return {
        "schema_version": 1,
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
    ws = _minimal_workspace()
    ws["models"] = {
        "ecoli-replication": {
            "submodule_path": "models/ecoli-replication",
            "remote": "git@github.com:eagmon/ecoli-replication.git",
            "pbg_processes": ["pbg-cobra", "pbg-smoldyn"],
            "stages": {"add_model": {"status": "complete", "pr": 2}},
            "phases": [
                {"n": 1, "name": "DnaA accumulation", "status": "complete", "pr": 8, "gate_passed": True},
            ],
        }
    }
    ws["datasets"] = [{"name": "bremer-1996", "path": "datasets/bremer-1996/", "claims": ["phase-1.dnaA-accumulation"]}]
    ws["references_bib"] = "references/papers.bib"
    ws["server"] = {"enabled": False}
    validator.validate(ws)


def test_expert_doc_sha256_optional(validator):
    """expertDoc accepts optional sha256 field (v0.1.9)."""
    ws = _minimal_workspace()
    ws["expert_docs"] = [
        {"name": "review-2025", "path": "references/expert/review-2025.pdf", "sha256": "abc123def456"},
        {"name": "notes", "path": "references/expert/notes.md"},  # no sha256 — still valid
    ]
    validator.validate(ws)


def test_references_pdfs_validates(validator):
    """references_pdfs array with required fields (v0.1.9)."""
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
    """referencePdf requires sha256 (v0.1.9)."""
    ws = _minimal_workspace()
    ws["references_pdfs"] = [
        {"bib_key": "Bremer1996", "path": "references/papers/Bremer1996.pdf"}
        # sha256 missing — should fail
    ]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_missing_schema_version_fails(validator):
    ws = _minimal_workspace()
    del ws["schema_version"]
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_invalid_status_fails(validator):
    ws = _minimal_workspace()
    ws["stages"]["workspace_bootstrap"]["status"] = "bogus"
    with pytest.raises(ValidationError):
        validator.validate(ws)


def test_phase_n_must_be_positive(validator):
    ws = _minimal_workspace()
    ws["models"] = {
        "m": {
            "submodule_path": "models/m", "remote": "x", "pbg_processes": [],
            "stages": {},
            "phases": [{"n": 0, "name": "x", "status": "planned"}],
        }
    }
    with pytest.raises(ValidationError):
        validator.validate(ws)


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


def test_external_model_validates(validator):
    ws = _minimal_workspace()
    ws["models"] = {
        "v2ecoli-mirror": {
            "submodule_path": "models/v2ecoli-mirror",
            "remote": "https://github.com/eagmon/v2ecoli.git",
            "pbg_processes": [],
            "stages": {"add_model": {"status": "complete", "pr": None}},
            "external": True,
        }
    }
    validator.validate(ws)
