import subprocess, sys, textwrap


def test_importing_package_does_not_eager_import_post_sim():
    # Fresh interpreter: importing viva_superpowers must NOT import post_sim.
    code = textwrap.dedent("""
        import sys, viva_superpowers
        assert "viva_superpowers.post_sim" not in sys.modules, "post_sim eagerly imported"
        # pure contract is available eagerly
        from viva_superpowers import check, band, diff_reports, TestBuilder  # noqa
        assert "viva_superpowers.post_sim" not in sys.modules
        # accessing a heavy name triggers the lazy import
        _ = viva_superpowers.TestStep
        assert "viva_superpowers.post_sim" in sys.modules
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_from_import_heavy_name_still_works():
    from viva_superpowers import ReportCardStep, ResultsStep  # triggers __getattr__
    assert ReportCardStep is not None and ResultsStep is not None
