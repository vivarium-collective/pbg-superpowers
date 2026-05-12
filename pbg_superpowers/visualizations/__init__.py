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

__all__ = ["TimeSeriesPlot"]
