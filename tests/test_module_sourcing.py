import viva_superpowers.module_sourcing as MS

CATALOG = {
    "viva-munk":   ["physics_2d", "rigid_body", "collision", "force"],
    "spatio-flux": ["spatial", "fba", "diffusion"],
    "viva-cpm":    ["cpm", "cell_shape", "adhesion", "spatial"],
    "growth-proc": ["growth", "biomass"],
}

def _axes(rep):
    return {a["id"]: a for g in rep["groups"].values() for a in g["axes"]}


def test_match_and_covers():
    assert MS.match_modules(["physics_2d", "collision"], CATALOG) == ["viva-munk"]
    assert MS.covers(["growth", "physics_2d"], ["growth-proc", "viva-munk"], CATALOG)   # composition
    assert not MS.covers(["growth", "fba"], ["growth-proc"], CATALOG)
    assert MS.missing_capabilities(["growth", "fba"], ["growth-proc"], CATALOG) == ["fba"]


def test_reuse_fit_passes():
    spec = {"name": "cell-jostling", "requires": ["physics_2d", "rigid_body", "collision"],
            "sourcing": {"decision": "reuse", "modules": ["viva-munk"], "rationale": "pymunk covers it"}}
    rep = MS.build_sourcing_report(spec, CATALOG); ax = _axes(rep)
    assert ax["source_fit"]["verdict"] == "within_tol"
    assert ax["reinvention"]["verdict"] == "within_tol"
    assert ax["survey_recorded"]["verdict"] == "within_tol"
    assert MS.sourcing_gate(rep) == "pass"


def test_reuse_misfit_fails_hard():
    # chose viva-munk but the task needs a spatial capability it lacks
    spec = {"name": "trap", "requires": ["physics_2d", "spatial"],
            "sourcing": {"decision": "reuse", "modules": ["viva-munk"], "rationale": "looks right"}}
    rep = MS.build_sourcing_report(spec, CATALOG); ax = _axes(rep)
    assert ax["source_fit"]["verdict"] == "mismatch"
    assert "spatial" in ax["source_fit"]["detail"]["missing_capabilities"]
    assert MS.sourcing_gate(rep) == "fail"


def test_compose_covers():
    spec = {"name": "growth-and-push", "requires": ["growth", "physics_2d"],
            "sourcing": {"decision": "compose", "modules": ["growth-proc", "viva-munk"], "rationale": "x"}}
    ax = _axes(MS.build_sourcing_report(spec, CATALOG))
    assert ax["source_fit"]["verdict"] == "within_tol"


def test_build_new_when_a_module_already_fits_is_reinvention():
    spec = {"name": "shape", "requires": ["cpm", "cell_shape"],
            "sourcing": {"decision": "build-new", "modules": [], "rationale": "I'll write my own CPM"}}
    rep = MS.build_sourcing_report(spec, CATALOG); ax = _axes(rep)
    assert ax["reinvention"]["verdict"] == "mismatch"           # viva-cpm already fits → hard fail
    assert "viva-cpm" in ax["reinvention"]["detail"]["existing_fits"]
    assert ax["novelty_justified"]["verdict"] == "drift"
    assert MS.sourcing_gate(rep) == "fail"


def test_build_new_is_justified_when_nothing_fits():
    spec = {"name": "novel", "requires": ["quantum_transport", "exotic_mechanism"],
            "sourcing": {"decision": "build-new", "modules": [], "rationale": "no module covers this"}}
    rep = MS.build_sourcing_report(spec, CATALOG); ax = _axes(rep)
    assert ax["reinvention"]["verdict"] == "within_tol"
    assert ax["novelty_justified"]["verdict"] == "within_tol"
    assert MS.sourcing_gate(rep) == "pass"


def test_unsurveyed_build_drifts():
    spec = {"name": "blind", "requires": ["quantum_transport"],
            "sourcing": {"decision": "build-new", "modules": []}}   # no rationale
    ax = _axes(MS.build_sourcing_report(spec, CATALOG))
    assert ax["survey_recorded"]["verdict"] == "drift"
