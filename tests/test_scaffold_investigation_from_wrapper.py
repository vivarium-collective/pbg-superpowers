"""Task 14: `investigation-from-wrapper` scaffolder.

Generates an investigation + one skeleton study per composite generator so
the viva-expert skill's showcase-investigation step becomes near a
one-liner. Mirrors the canonical shapes hand-authored in the viva-fenics
build (investigation.yaml schema_version 2, study.yaml schema_version 4).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from viva_superpowers.scaffold import scaffold_investigation_from_wrapper


def _ws(tmp_path: Path, name: str = "demo-ws") -> Path:
    (tmp_path / "workspace.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    return tmp_path


FAKE_GENERATORS = [
    "pkg_demo.composites.alpha.alpha_baseline",
    "pkg_demo.composites.beta.beta_baseline",
    "gamma_baseline",  # bare short name (no dots)
]


def test_investigation_lists_all_study_slugs(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)

    inv_path = Path(result["investigation_path"])
    assert inv_path.is_file()
    inv = yaml.safe_load(inv_path.read_text())
    assert inv["schema_version"] == 2
    assert inv["studies"] == ["alpha-baseline", "beta-baseline", "gamma-baseline"]


def test_each_study_written_with_expected_shape(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)

    assert len(result["studies"]) == 3
    for entry, generator in zip(result["studies"], FAKE_GENERATORS):
        study_path = Path(entry["path"])
        assert study_path.is_file()
        study = yaml.safe_load(study_path.read_text())
        assert study["schema_version"] == 4
        assert study["baseline"][0]["composite"] == generator
        # script: is resolved relative to the WORKSPACE ROOT (not the study
        # dir) by /viva-study run-script — matches every hand-authored
        # viva-fenics reference study (e.g. studies/poisson-validation/
        # study.yaml -> script: studies/poisson-validation/sims/run.py).
        assert study["canonical_runs"][0]["script"] == f"studies/{entry['slug']}/sims/run.py"
        assert study["canonical_runs"][0]["default"] is True


def test_inputs_from_is_a_linear_chain(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)

    slugs = ["alpha-baseline", "beta-baseline", "gamma-baseline"]
    studies_by_slug = {}
    for entry in result["studies"]:
        study = yaml.safe_load(Path(entry["path"]).read_text())
        studies_by_slug[entry["slug"]] = study

    # The canonical DAG edge is inputs.from — no legacy pipeline_gate.prerequisites.
    for study in studies_by_slug.values():
        assert "prerequisites" not in study["pipeline_gate"]
        assert "parent_studies" not in study

    # First study has no inputs edge.
    first = studies_by_slug[slugs[0]]
    assert first["inputs"] == []

    # Each subsequent study's edge is the previous slug, via inputs.from.
    for prev_slug, slug in zip(slugs, slugs[1:]):
        assert studies_by_slug[slug]["inputs"] == [
            {"artifact": prev_slug, "from": prev_slug}
        ]


def test_acceptance_criteria_matches_study_behavior_names(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)

    inv = yaml.safe_load(Path(result["investigation_path"]).read_text())
    studies_by_slug = {
        entry["slug"]: yaml.safe_load(Path(entry["path"]).read_text())
        for entry in result["studies"]
    }

    assert len(inv["acceptance_criteria"]) == len(result["studies"])
    for crit in inv["acceptance_criteria"]:
        study = studies_by_slug[crit["study"]]
        assert crit["behavior"] == study["expected_behavior"][0]["name"]
        # And the behavior_tests stub references the same name.
        assert study["behavior_tests"][0]["name"] == crit["behavior"]


def test_default_investigation_slug_is_kebab_cased_name(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(ws, "Demo Showcase!!", FAKE_GENERATORS)
    inv_path = Path(result["investigation_path"])
    assert inv_path.parent.name == "demo-showcase"


def test_explicit_investigation_slug_overrides_name(tmp_path):
    ws = _ws(tmp_path)
    result = scaffold_investigation_from_wrapper(
        ws, "Demo Showcase", FAKE_GENERATORS, investigation_slug="custom-slug",
    )
    inv_path = Path(result["investigation_path"])
    assert inv_path.parent.name == "custom-slug"


def test_rerun_without_force_skips_existing_files(tmp_path):
    ws = _ws(tmp_path)
    first = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)
    assert first["investigation_written"] is True
    assert all(s["written"] for s in first["studies"])

    # Mutate one study.yaml so we can prove a no-force rerun leaves it alone.
    study_path = Path(first["studies"][0]["path"])
    original_text = study_path.read_text()
    study_path.write_text(original_text.replace("planned", "CUSTOM-EDIT"))

    second = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)
    assert second["investigation_written"] is False
    assert all(not s["written"] for s in second["studies"])
    # File content untouched.
    assert "CUSTOM-EDIT" in study_path.read_text()


def test_rerun_with_force_overwrites(tmp_path):
    ws = _ws(tmp_path)
    first = scaffold_investigation_from_wrapper(ws, "demo-showcase", FAKE_GENERATORS)
    study_path = Path(first["studies"][0]["path"])
    study_path.write_text(study_path.read_text().replace("planned", "CUSTOM-EDIT"))

    second = scaffold_investigation_from_wrapper(
        ws, "demo-showcase", FAKE_GENERATORS, force=True,
    )
    assert second["investigation_written"] is True
    assert all(s["written"] for s in second["studies"])
    assert "CUSTOM-EDIT" not in study_path.read_text()


def test_collision_disambiguates_slugs(tmp_path):
    ws = _ws(tmp_path)
    generators = [
        "pkg_one.composites.x.shared_name",
        "pkg_two.composites.y.shared_name",
    ]
    result = scaffold_investigation_from_wrapper(ws, "collide", generators)
    slugs = [s["slug"] for s in result["studies"]]
    assert slugs == ["shared-name", "shared-name-2"]
    assert len(set(slugs)) == 2


def test_requires_at_least_one_generator(tmp_path):
    import click

    ws = _ws(tmp_path)
    with pytest.raises(click.ClickException):
        scaffold_investigation_from_wrapper(ws, "empty", [])


def test_cli_subcommand_smoke(tmp_path, plugin_root):
    """End-to-end via `python -m viva_superpowers.scaffold investigation-from-wrapper`."""
    ws = _ws(tmp_path)
    subprocess.run(
        [
            sys.executable, "-m", "viva_superpowers.scaffold",
            "investigation-from-wrapper",
            "--name", "cli-demo",
            "--studies", ",".join(FAKE_GENERATORS),
            "--workspace", str(ws),
        ],
        check=True,
        cwd=plugin_root,
    )
    inv_path = ws / "investigations" / "cli-demo" / "investigation.yaml"
    assert inv_path.is_file()
    inv = yaml.safe_load(inv_path.read_text())
    assert inv["studies"] == ["alpha-baseline", "beta-baseline", "gamma-baseline"]
    for slug in inv["studies"]:
        assert (ws / "studies" / slug / "study.yaml").is_file()
