"""Default Visualization classes shipped with pbg-superpowers.

All five inherit ``pbg_superpowers.visualization.Visualization`` and implement
``render_final(results, *, config) -> str``. They are auto-discovered via
``bigraph_schema.package.discover`` so workspaces don't need to register them
manually.

Usage (from a composite or investigation spec):
    visualizations:
      - name: trajectory
        address: "local:TimeSeriesPlot"
        config: {observable: free_DnaA, sources: [baseline]}
"""
from pbg_superpowers.visualizations.time_series import TimeSeriesPlot
from pbg_superpowers.visualizations.param_vs_observable import ParamVsObservable
from pbg_superpowers.visualizations.distribution import Distribution
from pbg_superpowers.visualizations.phase_space import PhaseSpace
from pbg_superpowers.visualizations.heatmap import Heatmap

__all__ = ["TimeSeriesPlot", "ParamVsObservable", "Distribution", "PhaseSpace", "Heatmap"]
