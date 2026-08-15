"""Helpers shared by pbg-superpowers skills."""
__version__ = "0.22.0"

# Light, import-safe contract (no process_bigraph): eager.
from viva_superpowers.test_contract import (  # noqa: E402,F401
    Expected, value, band, predicate, check, TestBuilder, sanitize,
)
from viva_superpowers.test_diff import diff_reports  # noqa: E402,F401
from viva_superpowers import test_vocab  # noqa: E402,F401

# Heavy post_sim family (pulls process_bigraph): lazy, so a pure consumer
# (e.g. study_audit importing `check`) doesn't drag the simulation stack in.
_POST_SIM_NAMES = frozenset({
    "TestStep", "ReportCardStep", "ResultsStep", "ResultsHandle",
    "AnalysisStep", "Analysis", "VisualizationStep",
    "TEST_REGISTRY", "REPORT_CARD_REGISTRY", "POST_SIM_REGISTRY",
    "VISUALIZATION_REGISTRY", "ANALYSIS_REGISTRY", "ANALYSIS_SCALES", "KINDS",
    "StudyContext", "write_test", "write_card", "prune", "applicable",
    "iter_post_sim", "register_post_sim",
})


def __getattr__(name):
    if name in _POST_SIM_NAMES:
        from viva_superpowers import post_sim
        return getattr(post_sim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _POST_SIM_NAMES)
