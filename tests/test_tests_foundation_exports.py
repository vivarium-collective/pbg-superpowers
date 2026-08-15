def test_foundation_reexports():
    import viva_superpowers as vsp
    for name in ("Expected", "value", "band", "predicate", "check",
                 "TestBuilder", "diff_reports"):
        assert hasattr(vsp, name), name
    # vocab still reachable via submodule
    from viva_superpowers import test_vocab
    assert test_vocab.CANONICAL[0] == "within_tol"

def test_foundation_has_no_heavy_imports():
    # the contract must be importable without process_bigraph / vivarium_workbench
    import sys, importlib
    for mod in ("viva_superpowers.test_vocab", "viva_superpowers.test_contract",
                "viva_superpowers.test_diff"):
        importlib.import_module(mod)
    # importing the pure modules must not have pulled workbench in
    assert "vivarium_workbench" not in sys.modules
