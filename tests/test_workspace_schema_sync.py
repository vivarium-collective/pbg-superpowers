"""Sync test: pbg-superpowers' bundled workspace.schema.json must match
pbg-template's canonical copy.

Two on-disk copies of ``workspace.schema.json`` exist:

  - pbg-template/template/.pbg/schemas/workspace.schema.json  (CANONICAL —
    scaffolded into every workspace; what the workspace's own lint reads)
  - pbg_superpowers/schemas/workspace.schema.json             (BUNDLED —
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
       pbg_superpowers/schemas/workspace.schema.json
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
    / "pbg_superpowers" / "schemas" / "workspace.schema.json"
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
        "pbg_superpowers/schemas/workspace.schema.json has drifted from "
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
