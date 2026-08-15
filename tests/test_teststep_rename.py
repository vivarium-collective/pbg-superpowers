import warnings
import viva_superpowers as vsp
from viva_superpowers import post_sim


def test_teststep_and_aliases_exist():
    assert vsp.TestStep is post_sim.TestStep
    assert vsp.ReportCardStep is vsp.TestStep            # alias
    assert vsp.REPORT_CARD_REGISTRY is vsp.TEST_REGISTRY  # same dict object


def test_subclassing_either_name_registers_in_test_registry():
    class _MyCardViaAlias(vsp.ReportCardStep):
        name = "unit_alias_card"
        def build(self, study): return ({"overall": "within_tol"}, "<html></html>")
    class _MyTestViaNew(vsp.TestStep):
        name = "unit_new_test"
        def build(self, study): return ({"overall": "within_tol"}, "<html></html>")
    assert vsp.TEST_REGISTRY["unit_alias_card"] is _MyCardViaAlias
    assert vsp.TEST_REGISTRY["unit_new_test"] is _MyTestViaNew
    # kind-tagged as "test" in the unified registry
    kinds = {nm: e["kind"] for nm, e in vsp.POST_SIM_REGISTRY.items()}
    assert kinds["unit_alias_card"] == "test"


def test_iter_post_sim_accepts_legacy_kind():
    names_new = {nm for nm, _ in vsp.iter_post_sim("test")}
    names_legacy = {nm for nm, _ in vsp.iter_post_sim("report_card")}
    assert names_new == names_legacy
    assert "unit_new_test" in names_new


def test_write_card_deprecated_but_works(tmp_path):
    ctx = post_sim.StudyContext(study_name="s", study_dir=tmp_path, spec={}, ws_root=tmp_path)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        p = vsp.write_card(ctx, "c1", {"overall": "within_tol"}, "<html>ok</html>")
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert p.exists()
    assert (p.parent / "c1.verdict.json").exists()
    # write_test writes identically, no warning
    p2 = vsp.write_test(ctx, "c2", {"overall": "mismatch"}, "<html>x</html>")
    assert p2.exists() and (p2.parent / "c2.verdict.json").exists()


def test_legacy_tuple_build_still_yields_view_data():
    class _T(vsp.TestStep):
        name = "unit_legacy_tuple"
        def applies(self, study): return True
        def build(self, study): return ({"overall": "drift"}, "<html>h</html>")
    step = _T({}, None) if False else _T.__new__(_T)   # construct minimally
    step.config = {}
    out = step.update({"study": {"any": 1}})
    assert out == {"view": "<html>h</html>", "data": {"overall": "drift"}}
