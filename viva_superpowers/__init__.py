"""Helpers shared by pbg-superpowers skills."""
__version__ = "0.22.0"

# Light, import-safe contract (no process_bigraph): eager.
from viva_superpowers.test_contract import (  # noqa: E402,F401
    Expected, value, band, predicate, check, TestBuilder, sanitize,
)
from viva_superpowers.test_diff import diff_reports  # noqa: E402,F401
from viva_superpowers import test_vocab  # noqa: E402,F401
# Reference-driven card grading (typed criteria → report_card_verdict/v1).
# Light: stdlib + scipy-at-call-time only, no process_bigraph.
from viva_superpowers.card_criteria import grade_axis  # noqa: E402,F401
from viva_superpowers.card_grade import (  # noqa: E402,F401
    dig, grade_card, verdict_json, render_verdict_html,
)

# Heavy post_sim family (pulls process_bigraph): lazy, so a pure consumer
# (e.g. study_audit importing `check`) doesn't drag the simulation stack in.
_POST_SIM_NAMES = frozenset({
    "TestStep", "ReportCardStep", "ResultsStep", "ResultsHandle",
    "AnalysisStep", "Analysis", "VisualizationStep", "TestReportStep",
    "TEST_REGISTRY", "REPORT_CARD_REGISTRY", "POST_SIM_REGISTRY",
    "VISUALIZATION_REGISTRY", "ANALYSIS_REGISTRY", "ANALYSIS_SCALES", "KINDS",
    "StudyContext", "write_test", "write_card", "write_report", "build_report",
    "tests_dir", "history_dir", "prune", "applicable",
    "iter_post_sim", "register_post_sim",
})


def __getattr__(name):
    if name in _POST_SIM_NAMES:
        from viva_superpowers import post_sim
        return getattr(post_sim, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _POST_SIM_NAMES)
