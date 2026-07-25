"""Default Visualization classes shipped with pbg-superpowers.

All five inherit ``viva_superpowers.visualization.Visualization`` and implement
``render_final(results, *, config) -> str``. They are auto-discovered via
``bigraph_schema.package.discover`` so workspaces don't need to register them
manually.

Usage (from a composite or investigation spec):
    visualizations:
      - name: trajectory
        address: "local:TimeSeriesPlot"
        config: {observable: free_DnaA, sources: [baseline]}
"""
from viva_superpowers.visualizations.time_series import TimeSeriesPlot
from viva_superpowers.visualizations.timeseries_from_observables import (
    TimeSeriesFromObservables,
)
from viva_superpowers.visualizations.param_vs_observable import ParamVsObservable
from viva_superpowers.visualizations.distribution import Distribution
from viva_superpowers.visualizations.phase_space import PhaseSpace
from viva_superpowers.visualizations.heatmap import Heatmap

__all__ = [
    "TimeSeriesPlot",
    "TimeSeriesFromObservables",
    "ParamVsObservable",
    "Distribution",
    "PhaseSpace",
    "Heatmap",
]
