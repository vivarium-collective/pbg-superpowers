from viva_superpowers.study_canonicalize import canonicalize_models, canonicalize_ordering, migrate_study_file, backfill_question

STYLE_B_WITH_COMMENTS = """\
# Hand-authored research log — MUST survive migration.
schema_version: 4
name: colonies-x
title: Device run
baseline:
- name: mother-machine-simple
  composite: v2ecoli.composites.ecoli_colony.ecoli_colony
  params:
    seed: 0            # canonical seed
  note: |
    Nominal composite for the workbench catalog.
pipeline_gate:
  prerequisites:
  - colonies-prev
# trailing comment
status: ran
"""

def test_migrate_writes_and_preserves_comments(tmp_path):
    d = tmp_path / "colonies-x"; d.mkdir()
    (d / "study.yaml").write_text(STYLE_B_WITH_COMMENTS)
    report = migrate_study_file(d, known_slugs={"colonies-x", "colonies-prev"}, write=True)
    assert report["written"] is True
    text = (d / "study.yaml").read_text()
    assert text.count("MUST survive migration") == 1   # preserved exactly once (catches duplication)
    assert "Nominal composite for the workbench" in text  # note prose survives
    assert "conditions:" in text and "\nbaseline:" not in text  # moved into conditions
    assert "from: colonies-prev" in text             # ordering -> inputs.from
    assert "pipeline_gate:" not in text              # removed (no dangling)

def test_dry_run_does_not_write(tmp_path):
    d = tmp_path / "colonies-x"; d.mkdir()
    (d / "study.yaml").write_text(STYLE_B_WITH_COMMENTS)
    before = (d / "study.yaml").read_text()
    migrate_study_file(d, known_slugs={"colonies-x", "colonies-prev"}, write=False)
    assert (d / "study.yaml").read_text() == before   # byte-identical

def test_already_canonical_is_noop(tmp_path):
    d = tmp_path / "s"; d.mkdir()
    (d / "study.yaml").write_text(
        "schema_version: 4\nname: s\nconditions:\n  baseline:\n    composite: c.b\n"
        "    params: {}\n  model_settings: []\n")
    before = (d / "study.yaml").read_text()
    migrate_study_file(d, known_slugs={"s"}, write=True)
    assert (d / "study.yaml").read_text() == before   # byte-identical no-op


def test_style_A_already_canonical_inherits_variant_composite():
    spec = {"conditions": {
        "baseline": {"composite": "c.base", "params": {"seed": 0}},
        "variants": [{"name": "ko", "params": {"knockouts": ["EG10526"]}}],
    }}
    report = canonicalize_models(spec)
    assert spec["conditions"]["variants"][0]["composite"] == "c.base"  # inherited
    assert "conditions" in spec and "baseline" not in spec  # no top-level baseline
    assert report["changed"] is True and "ko" in report["inherited_composites"]

def test_style_B_toplevel_baseline_list_moves_into_conditions():
    spec = {"baseline": [{"name": "m", "composite": "c.x", "params": {"seed": 0}}]}
    report = canonicalize_models(spec)
    assert "baseline" not in spec  # top-level removed
    assert spec["conditions"]["baseline"]["composite"] == "c.x"
    assert report["style"] == "B" and report["changed"] is True

def test_both_keeps_conditions_drops_toplevel():
    spec = {"baseline": [{"name": "d", "composite": "c.dupe", "params": {}}],
            "conditions": {"baseline": {"composite": "c.real", "params": {"seed": 1}}}}
    report = canonicalize_models(spec)
    assert "baseline" not in spec
    assert spec["conditions"]["baseline"]["composite"] == "c.real"  # conditions wins
    assert "both_dropped_toplevel" in report["flags"]

def test_multi_baseline_is_flagged_not_migrated():
    spec = {"baseline": [{"name": "a", "composite": "c.a"}, {"name": "b", "composite": "c.b"}]}
    report = canonicalize_models(spec)
    assert "multi_baseline_needs_human" in report["flags"]
    assert "baseline" in spec and report["changed"] is False  # untouched

def test_variant_parameter_overrides_renamed_to_params():
    spec = {"conditions": {"baseline": {"composite": "c.b"},
            "variants": [{"name": "v", "parameter_overrides": {"media": "rich"}}]}}
    canonicalize_models(spec)
    v = spec["conditions"]["variants"][0]
    assert v["params"] == {"media": "rich"} and "parameter_overrides" not in v

def test_idempotent():
    spec = {"conditions": {"baseline": {"composite": "c.b", "params": {}},
            "variants": [{"name": "v", "composite": "c.b", "params": {}}],
            "model_settings": []}}
    r1 = canonicalize_models(spec); r2 = canonicalize_models(spec)
    assert r2["changed"] is False


def test_valid_prereq_becomes_inputs_from():
    spec = {"name": "b", "pipeline_gate": {"prerequisites": ["a"], "enables": ["c"]}}
    report = canonicalize_ordering(spec, known_slugs={"a", "b", "c"})
    assert {"artifact": "a", "from": "a"} in spec["inputs"]
    assert "pipeline_gate" not in spec           # deleted (no dangling)
    assert report["changed"] is True and "a" in report["added_inputs"]

def test_mapping_prereq_shape():
    spec = {"name": "b", "pipeline_gate": {"prerequisites": [{"study": "a"}]}}
    canonicalize_ordering(spec, known_slugs={"a", "b"})
    assert {"artifact": "a", "from": "a"} in spec["inputs"]

def test_dangling_prereq_is_flagged_and_retained():
    # a prereq referencing an unknown slug is flagged, no edge added, pipeline_gate retained
    spec = {"name": "x", "pipeline_gate": {"prerequisites": ["ghost"]}}
    report = canonicalize_ordering(spec, known_slugs={"x"})
    assert "dangling_prereq:ghost" in report["flags"]
    assert "pipeline_gate" in spec  # retained for human fix
    assert "pipeline_gate_retained" in report["flags"]

def test_existing_inputs_not_duplicated():
    spec = {"name": "b", "inputs": [{"artifact": "a", "from": "a"}],
            "pipeline_gate": {"prerequisites": ["a"]}}
    canonicalize_ordering(spec, known_slugs={"a", "b"})
    assert spec["inputs"].count({"artifact": "a", "from": "a"}) == 1

def test_parca_dependency_preserved():
    spec = {"name": "s", "inputs": [{"artifact": "sim_data", "from": "parca"}],
            "pipeline_gate": {"prerequisites": ["parca"]}}
    canonicalize_ordering(spec, known_slugs={"parca", "s"})
    # parca edge already present as sim_data; adding {parca,parca} is allowed but dedup keeps sim_data
    assert {"artifact": "sim_data", "from": "parca"} in spec["inputs"]

def test_parent_studies_becomes_inputs_and_is_deleted():
    spec = {"name": "b", "parent_studies": ["a"]}
    report = canonicalize_ordering(spec, known_slugs={"a", "b"})
    assert {"artifact": "a", "from": "a"} in spec["inputs"]
    assert "parent_studies" not in spec
    assert report["changed"] is True

def test_mixed_valid_and_dangling_prereq():
    spec = {"name": "b", "pipeline_gate": {"prerequisites": ["a", "ghost"]}}
    report = canonicalize_ordering(spec, known_slugs={"a", "b"})
    assert {"artifact": "a", "from": "a"} in spec["inputs"]     # valid edge added
    assert "dangling_prereq:ghost" in report["flags"]
    assert "pipeline_gate" in spec                              # retained (has a dangling)
    assert "pipeline_gate_retained" in report["flags"]


def test_backfill_from_purpose_question():
    spec = {"conditions": {"baseline": {"composite": "c"}}, "purpose": {"question": "Does X?"}}
    r = backfill_question(spec)
    assert spec["question"] == "Does X?" and r["source"] == "purpose.question" and r["changed"] is True

def test_backfill_prefers_existing_question():
    spec = {"conditions": {"baseline": {"composite": "c"}}, "question": "Already here",
            "purpose": {"question": "other"}}
    r = backfill_question(spec)
    assert spec["question"] == "Already here" and r["changed"] is False

def test_backfill_falls_back_to_description_then_title():
    spec = {"conditions": {"baseline": {"composite": "c"}}, "description": "Desc prose"}
    r = backfill_question(spec)
    assert spec["question"] == "Desc prose" and r["source"] == "description"
    spec2 = {"conditions": {"baseline": {"composite": "c"}}, "title": "T"}
    r2 = backfill_question(spec2)
    assert spec2["question"] == "T" and r2["source"] == "title"

def test_no_backfill_without_conditions():
    spec = {"baseline": [{"name": "b", "composite": "c"}], "purpose": {"question": "Q"}}
    r = backfill_question(spec)
    assert "question" not in spec and r["changed"] is False

def test_no_source_flags_not_fabricates():
    spec = {"conditions": {"baseline": {"composite": "c"}}}
    r = backfill_question(spec)
    assert "question" not in spec and "no_question_source" in r["flags"]

def test_migrate_study_file_backfills_question_only(tmp_path):
    d = tmp_path / "s"; d.mkdir()
    (d / "study.yaml").write_text(
        "schema_version: 4\nname: s\nconditions:\n  baseline:\n    composite: c.b\n"
        "    params: {}\n  model_settings: []\npurpose:\n  question: Does it work?\n")
    rep = migrate_study_file(d, known_slugs={"s"}, write=True)
    assert rep["written"] is True                      # question backfill alone triggers the write
    assert "question: Does it work?" in (d / "study.yaml").read_text()
