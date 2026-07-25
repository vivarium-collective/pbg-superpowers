"""Sync test: pbg-superpowers' bundled workspace.schema.json must match
pbg-template's canonical copy.

Two on-disk copies of ``workspace.schema.json`` exist:

  - pbg-template/template/.pbg/schemas/workspace.schema.json  (CANONICAL —
    scaffolded into every workspace; what the workspace's own lint reads)
  - viva_superpowers/schemas/workspace.schema.json             (BUNDLED —
    used by pbg-superpowers' scaffold + imports helpers in contexts where
    no workspace is available, e.g. unit tests or pre-scaffold validation)

The bundled copy must track the canonical. This test fails CI when they
diverge so drift surfaces immediately instead of when a workspace
validates against one but not the other.

Skips cleanly when pbg-template isn't on disk (matches the convention in
test_workspace_scaffold_snapshot.py — both tests check pbg-template as a
sibling checkout via the $PBG_TEMPLATE env var).

To resync after an INTENTIONAL pbg-template change::

    cp ~/code/pbg-template/template/.pbg/schemas/workspace.schema.json \\
       viva_superpowers/schemas/workspace.schema.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


PBG_TEMPLATE = Path(os.environ.get("PBG_TEMPLATE", "~/code/pbg-template")).expanduser().resolve()
CANONICAL = PBG_TEMPLATE / "template" / ".pbg" / "schemas" / "workspace.schema.json"
BUNDLED = (
    Path(__file__).resolve().parent.parent
    / "viva_superpowers" / "schemas" / "workspace.schema.json"
)


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not CANONICAL.is_file():
        pytest.skip(f"pbg-template canonical schema not found at {CANONICAL}")


def test_workspace_schema_matches_pbg_template():
    """Byte-by-byte equality. Trailing whitespace and key ordering also
    have to match — JSON is line-noise without a stable serialization, and
    a `cp` from canonical is the only sanctioned migration path."""
    assert BUNDLED.read_text() == CANONICAL.read_text(), (
        "viva_superpowers/schemas/workspace.schema.json has drifted from "
        f"pbg-template's canonical copy at {CANONICAL}. "
        "Resync with:\n\n"
        f"    cp {CANONICAL} {BUNDLED}\n\n"
        "(or update pbg-template's copy first if the change should be canonical.)"
    )


def test_workspace_schema_parses_as_json():
    """Defensive — guards against a malformed sync where bytes match but
    the file isn't valid JSON. Trivial but cheap insurance."""
    json.loads(BUNDLED.read_text())
    json.loads(CANONICAL.read_text())


def test_workspace_schema_top_level_shape_is_validatable():
    """A jsonschema sanity check — the bundled schema itself must be a
    valid Draft-07 schema, otherwise pbg-superpowers' validators would
    crash at runtime when first applied to a workspace.yaml."""
    import jsonschema
    schema = json.loads(BUNDLED.read_text())
    # check_schema raises if the meta-schema rejects it.
    jsonschema.Draft7Validator.check_schema(schema)


def test_workspace_schema_accepts_v2_and_v3():
    """v2ecoli friction #18 (2026-05-19): bumping workspace.yaml to
    schema_version: 3 (for the new default_baseline: block) tripped the
    validator's `{"const": 2}` constraint, blocking Install. Permissive
    fix is `{"enum": [2, 3]}` — both versions valid, no migration needed."""
    import jsonschema
    schema = json.loads(BUNDLED.read_text())
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())

    base = {
        "name": "x", "created": "2026-01-15",
        "plugin_version": "0.8.1",
    }
    validator.validate({**base, "schema_version": 2})
    validator.validate({**base, "schema_version": 3})


def test_workspace_schema_default_baseline_v3_block_validates():
    """The new v3 default_baseline: block needs a permissive but typed
    shape — composite + params + duration knobs + stop_on signal."""
    import jsonschema
    schema = json.loads(BUNDLED.read_text())
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())

    ws = {
        "schema_version": 3,
        "name": "v2ecoli", "created": "2026-01-15",
        "plugin_version": "0.8.1",
        "package_path": "v2ecoli",
        "default_baseline": {
            "composite": "v2ecoli.composites.baseline.baseline",
            "params": {"n_steps": 3600, "seed": 0},
            "duration_s": 3600,
            "max_duration_s": 7200,
            "interval_s": 1.0,
            "stop_on": "division",
            "description": "Phase-2 default baseline.",
        },
    }
    validator.validate(ws)


def test_workspace_schema_default_baseline_rejects_unknown_fields():
    """additionalProperties: false on the default_baseline block so typos
    fail loudly rather than silently sliding through validation."""
    import jsonschema
    schema = json.loads(BUNDLED.read_text())
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())

    ws = {
        "schema_version": 3,
        "name": "x", "created": "2026-01-15", "plugin_version": "0.8.1",
        "default_baseline": {"composite": "foo", "typo_field": 1},
    }
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(ws)
