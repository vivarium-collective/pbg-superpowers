import json
import pytest
import yaml
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
