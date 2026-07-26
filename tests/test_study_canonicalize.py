from viva_superpowers.study_canonicalize import canonicalize_models

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
