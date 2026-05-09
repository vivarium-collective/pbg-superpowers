import json
import pytest
from jsonschema import Draft7Validator, ValidationError


@pytest.fixture
def validator(schemas_dir):
    schema = json.loads((schemas_dir / "phase.schema.json").read_text())
    return Draft7Validator(schema)


def _minimal():
    return {
        "phase": 1, "name": "DnaA accumulation",
        "status": "planned", "prereq_phases": [],
        "gate_passed": False, "acceptance_tests": [],
    }


def test_minimal_validates(validator):
    validator.validate(_minimal())


def test_full_validates(validator):
    fm = _minimal()
    fm.update({
        "phase": 2, "name": "Initiation trigger",
        "status": "in_progress", "prereq_phases": [1], "gate_passed": False,
        "opened_pr": 9,
        "acceptance_tests": [
            {"id": "phase-2.t1", "desc": "DnaA > threshold => oriC fires", "status": "pending"},
        ],
        "parameters_added": [{"name": "oriC_threshold", "value": 80, "unit": "count"}],
        "deliverables": {
            "code_diff": "deliverables/phase-2-diff.md",
            "plots": ["deliverables/phase-2-traces.png"],
            "test_report": "deliverables/phase-2-tests.md",
        },
        "open_questions": ["phase-2.q1"],
    })
    validator.validate(fm)


def test_acceptance_test_id_pattern(validator):
    fm = _minimal()
    fm["acceptance_tests"] = [{"id": "wrongformat", "desc": "x", "status": "pending"}]
    with pytest.raises(ValidationError):
        validator.validate(fm)


def test_status_enum(validator):
    fm = _minimal()
    fm["status"] = "DONE"
    with pytest.raises(ValidationError):
        validator.validate(fm)
