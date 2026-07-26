from viva_superpowers.study_canonicalize import canonicalize_models, canonicalize_ordering

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
