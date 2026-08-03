"""Import-parity tests for the Phase 1 substrate shims.

The composite generation/discovery/introspection, config-helper, and
visualization Step framework modules moved to ``process_bigraph`` in
process-bigraph 1.8.1 (vivarium-collective/process-bigraph#179). The
``viva_superpowers`` modules of the same name are now thin re-export shims
(see ``viva_superpowers/composite_spec.py`` for the established precedent).

These tests assert import-parity: every name re-exported by a shim module
must be the identical object (``is``, not just ``==``) as the one defined in
its ``process_bigraph`` counterpart. This guards against accidental copies,
re-implementations, or stale re-exports creeping back in.
"""
from __future__ import annotations

import importlib

import pytest

PAIRS = [
    ("viva_superpowers.composite_generator", "process_bigraph.composite_generator"),
    ("viva_superpowers.composite_discovery", "process_bigraph.composite_discovery"),
    ("viva_superpowers.core_introspection", "process_bigraph.core_introspection"),
    ("viva_superpowers.config_helpers", "process_bigraph.config_helpers"),
    ("viva_superpowers.visualization", "process_bigraph.visualization"),
    ("viva_superpowers.visualizations", "process_bigraph.visualizations"),
    ("viva_superpowers.visualizations.time_series", "process_bigraph.visualizations.time_series"),
    ("viva_superpowers.visualizations.heatmap", "process_bigraph.visualizations.heatmap"),
    ("viva_superpowers.visualizations.phase_space", "process_bigraph.visualizations.phase_space"),
    ("viva_superpowers.visualizations.distribution", "process_bigraph.visualizations.distribution"),
    ("viva_superpowers.visualizations.param_vs_observable", "process_bigraph.visualizations.param_vs_observable"),
    (
        "viva_superpowers.visualizations.timeseries_from_observables",
        "process_bigraph.visualizations.timeseries_from_observables",
    ),
]


@pytest.mark.parametrize("shim,real", PAIRS)
def test_shim_reexports_are_identical(shim, real):
    s, r = importlib.import_module(shim), importlib.import_module(real)
    names = getattr(r, "__all__", None) or [n for n in dir(r) if not n.startswith("__")]
    for name in names:
        assert getattr(s, name) is getattr(r, name), f"{shim}.{name} is not {real}.{name}"


def test_workbench_semiprivate_names_survive():
    """The workbench imports these semi-private names directly (not in __all__)."""
    from viva_superpowers.composite_generator import (  # noqa: F401
        _REGISTRY,
        emitter_defaults,
        install_default_emitters,
    )


def test_timeseries_from_observables_private_helpers_survive():
    """tests/test_timeseries_from_observables.py imports these directly."""
    from viva_superpowers.visualizations.timeseries_from_observables import (  # noqa: F401
        _build_traces,
        _label_for_run,
        _load_runs,
        _load_study_observable_meta,
        _render_html,
        _y_axis_label,
    )


def test_visualizations_package_and_submodule_imports_both_work():
    """Both `from viva_superpowers.visualizations import X` and
    `from viva_superpowers.visualizations.time_series import X` must work
    and refer to the identical class object."""
    from viva_superpowers.visualizations import TimeSeriesPlot as pkg_cls
    from viva_superpowers.visualizations.time_series import TimeSeriesPlot as mod_cls

    assert pkg_cls is mod_cls


def test_entry_point_group_dropped():
    """D1: the self-referential process_bigraph.spec_generators entry point
    is removed from pyproject.toml — process-bigraph discovers its own
    generators internally now."""
    import pathlib
    import tomllib

    pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    entry_points = data.get("project", {}).get("entry-points", {})
    assert "process_bigraph.spec_generators" not in entry_points
