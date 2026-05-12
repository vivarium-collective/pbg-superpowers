"""Unit tests for the default Visualization classes shipped with pbg-superpowers."""
from pbg_superpowers.visualizations import TimeSeriesPlot


def _fixture_results():
    """Minimal results dict: 1 sim, 2 runs, observable 'level' over 4 steps."""
    return {
        "baseline": {
            "runs": [
                {
                    "run_id": "r1",
                    "params": {"rate": 1.0},
                    "trajectory": [
                        {"step": i, "time": float(i), "state": {"level": 1.0 * (i + 1)}}
                        for i in range(4)
                    ],
                },
                {
                    "run_id": "r2",
                    "params": {"rate": 2.0},
                    "trajectory": [
                        {"step": i, "time": float(i), "state": {"level": 2.0 * (i + 1)}}
                        for i in range(4)
                    ],
                },
            ]
        }
    }


def test_time_series_plot_render_returns_html():
    inst = TimeSeriesPlot.__new__(TimeSeriesPlot)
    inst.config = {}
    html = inst.render_final(
        _fixture_results(),
        config={"observable": "level", "sources": ["baseline"], "title": "Test"},
    )
    assert isinstance(html, str)
    assert "Plotly.newPlot" in html
    assert "Test" in html  # title appears in HTML


def test_time_series_plot_two_lines_for_two_runs():
    inst = TimeSeriesPlot.__new__(TimeSeriesPlot)
    inst.config = {}
    html = inst.render_final(
        _fixture_results(),
        config={"observable": "level", "sources": ["baseline"], "title": ""},
    )
    # Each run becomes one Plotly trace. Look for the run_ids in the HTML.
    assert "r1" in html or "rate=1.0" in html
    assert "r2" in html or "rate=2.0" in html


def test_time_series_plot_reference_range_overlay():
    inst = TimeSeriesPlot.__new__(TimeSeriesPlot)
    inst.config = {}
    html = inst.render_final(
        _fixture_results(),
        config={
            "observable": "level", "sources": ["baseline"], "title": "",
            "_overlays": [
                {"kind": "reference-range", "y_min": 1.5, "y_max": 5.0,
                 "label": "phys-range"},
            ],
        },
    )
    # Reference range becomes a shaded band — look for the band's marker.
    assert "phys-range" in html


def test_time_series_plot_missing_observable_in_state():
    """Some trajectory points may lack the observable (sparse emission).
    The plot should silently skip those points without crashing."""
    results = {
        "baseline": {
            "runs": [{
                "run_id": "r1", "params": {},
                "trajectory": [
                    {"step": 0, "time": 0.0, "state": {"level": 1.0}},
                    {"step": 1, "time": 1.0, "state": {}},  # missing
                    {"step": 2, "time": 2.0, "state": {"level": 3.0}},
                ],
            }],
        }
    }
    inst = TimeSeriesPlot.__new__(TimeSeriesPlot)
    inst.config = {}
    html = inst.render_final(
        results,
        config={"observable": "level", "sources": ["baseline"], "title": ""},
    )
    assert "Plotly.newPlot" in html


from pbg_superpowers.visualizations import ParamVsObservable


def _sweep_fixture_results():
    """Sweep over rate=[0.1, 0.5, 1.0]; observable 'level' rises monotonically.
    Final values: 1.5, 7.5, 15.0."""
    runs = []
    for rate in [0.1, 0.5, 1.0]:
        traj = [{"step": i, "time": float(i),
                  "state": {"level": rate * (i + 1) * 3}}
                for i in range(5)]
        runs.append({"run_id": f"r-{rate}", "params": {"rate": rate},
                     "trajectory": traj})
    return {"rate-sweep": {"runs": runs}}


def test_param_vs_observable_final_reduce():
    inst = ParamVsObservable.__new__(ParamVsObservable)
    inst.config = {}
    html = inst.render_final(
        _sweep_fixture_results(),
        config={"sweep": "rate-sweep", "sweep_param": "rate",
                "observable": "level", "reduce": "final", "title": ""},
    )
    assert "Plotly.newPlot" in html
    # The y values for the three rates should appear (1.5, 7.5, 15.0)
    assert "1.5" in html
    assert "15" in html


def test_param_vs_observable_mean_reduce():
    inst = ParamVsObservable.__new__(ParamVsObservable)
    inst.config = {}
    html = inst.render_final(
        _sweep_fixture_results(),
        config={"sweep": "rate-sweep", "sweep_param": "rate",
                "observable": "level", "reduce": "mean", "title": ""},
    )
    assert "Plotly.newPlot" in html
