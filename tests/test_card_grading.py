"""Reference-driven card grading now lives in viva_superpowers (moved from
v2ecoli.library.card_criteria / report_card). These guard the shared home so the
report_card_verdict/v1 contract stays stable for every consumer (v2ecoli shims,
pbg_v2ecoli evaluators). Ported from v2ecoli tests/test_status_criterion.py,
test_report_card_verdict_json.py, test_render_verdict_html.py."""
from viva_superpowers import grade_axis, verdict_json, render_verdict_html
from viva_superpowers.card_grade import grade_card


# --- grade_axis: status (verdict carried by the measured node) -------------

def test_status_passes_through_verdict_and_fields():
    g = grade_axis(
        {"verdict": "within_tol", "value": 42.0, "meter": "ok", "detail": {"k": 1}},
        {"type": "status", "criterion_str": "in [35, 55]"},
    )
    assert g["verdict"] == "within_tol"
    assert g["value"] == 42.0
    assert g["criterion_str"] == "in [35, 55]"
    assert g["meter"] == "ok"
    assert g["detail"] == {"k": 1}


def test_status_unknown_verdict_is_ungraded():
    assert grade_axis({"verdict": "bogus"}, {"type": "status"})["verdict"] == "ungraded"


def test_status_missing_node_is_ungraded():
    g = grade_axis(None, {"type": "status"})
    assert g["verdict"] == "ungraded"
    assert g["value"] is None


# --- grade_axis: numeric criteria (banded verdicts) ------------------------

def test_rel_tol_bands_within_drift_mismatch():
    crit = {"type": "rel_tol", "reference": 100.0, "tol_rel": 0.05}
    assert grade_axis({"mean": 102.0}, crit)["verdict"] == "within_tol"   # 2% ≤ 5%
    assert grade_axis({"mean": 108.0}, crit)["verdict"] == "drift"        # 8% ≤ 10%
    assert grade_axis({"mean": 130.0}, crit)["verdict"] == "mismatch"     # 30% > 10%
    assert grade_axis({"mean": None}, crit)["verdict"] == "ungraded"


def test_boolean_criterion():
    assert grade_axis(True, {"type": "boolean"})["verdict"] == "within_tol"
    assert grade_axis(False, {"type": "boolean"})["verdict"] == "mismatch"
    assert grade_axis(None, {"type": "boolean"})["verdict"] == "ungraded"


def test_literature_flags_first_principles_violation():
    crit = {"type": "literature", "measured": [0.4, 0.5], "theoretical_max": 0.6,
            "tol_rel": 0.10}
    g = grade_axis({"mean": 0.9}, crit)   # above the ceiling
    assert g["verdict"] == "mismatch"
    assert g["detail"]["first_principles_violation"] is True


def test_unknown_criterion_is_ungraded():
    assert grade_axis({"mean": 1.0}, {"type": "nope"})["verdict"] == "ungraded"


# --- grade_card: rolls up the worst axis verdict ---------------------------

def test_grade_card_rolls_up_worst_verdict():
    card = {"a": {"mean": 100.0}, "b": {"mean": 150.0}}
    reference = {"axes": {
        "a": {"group": "G", "criterion": {"type": "rel_tol", "reference": 100.0, "tol_rel": 0.05}},
        "b": {"group": "G", "criterion": {"type": "rel_tol", "reference": 100.0, "tol_rel": 0.05}},
    }}
    report = grade_card(card, reference)
    assert report["axes"]["a"]["verdict"] == "within_tol"
    assert report["axes"]["b"]["verdict"] == "mismatch"
    assert report["overall"] == "mismatch"   # worst of the two


# --- verdict_json: report_card_verdict/v1 serialization --------------------

def _fake_report():
    return {
        "overall": "mismatch",
        "axes": {
            "physiology.doubling_time": {"group": "Physiology", "label": "Doubling time",
                "verdict": "within_tol", "value": 0.84, "meter": "Δ = -2.2%",
                "detail": {"p": 0.014, "cohens_d": -0.26, "delta_rel": -0.022}},
            "fluxes.o2": {"group": "Exchange fluxes", "label": "O2 exchange",
                "verdict": "mismatch", "value": -0.45, "meter": "Δ = -40.4%",
                "detail": {"p": 0.0, "cohens_d": 0.89, "delta_rel": -0.404}},
        },
    }


def test_verdict_json_group_verdict_is_worst_of_axes():
    report = {"overall": "drift", "axes": {
        "ribosomes.total": {"group": "Ribosomes", "label": "Total", "verdict": "drift",
            "value": 1.0, "meter": "", "detail": {}},
        "ribosomes.active_fraction": {"group": "Ribosomes", "label": "Active", "verdict": "within_tol",
            "value": 0.83, "meter": "", "detail": {}},
    }}
    vj = verdict_json(report)
    g = vj["groups"]["ribosomes"]
    assert g["verdict"] == "drift"          # worst of {drift, within_tol}
    assert len(g["axes"]) == 2


def test_verdict_json_groups_axes_and_slugs_group_names():
    vj = verdict_json(_fake_report(), model_ref="abc1234",
                      reference_model="vEcoli (v1)", generated="2026-06-13 00:00")
    assert vj["schema"] == "report_card_verdict/v1"
    assert vj["overall"] == "mismatch"
    assert set(vj["groups"]) == {"physiology", "exchange_fluxes"}
    phys = vj["groups"]["physiology"]
    assert phys["axes"][0]["id"] == "physiology.doubling_time"
    assert phys["axes"][0]["verdict"] == "within_tol"
    assert vj["groups"]["exchange_fluxes"]["verdict"] == "mismatch"
    assert vj["groups"]["physiology"]["verdict"] == "within_tol"


# --- render_verdict_html: self-contained HTML from a stored v1 verdict -----

def _vj():
    return {
        "schema": "report_card_verdict/v1", "overall": "drift",
        "reference_model": "vEcoli @ basal", "model_ref": "v2ecoli @ basal",
        "groups": {
            "standard": {"verdict": "drift", "axes": [
                {"id": "physiology.cell_mass", "label": "Cell mass",
                 "verdict": "within_tol", "value": 1.2, "meter": "Δ=+1%"},
                {"id": "physiology.growth_rate", "label": "Growth rate",
                 "verdict": "drift", "value": 0.9, "meter": "Δ=+7%"}]},
            "config": {"verdict": "within_tol", "axes": [
                {"id": "config.seeds", "label": "Seeds",
                 "verdict": "within_tol", "value": 4, "meter": ""}]},
        },
    }


def test_render_is_self_contained_with_groups_and_axes():
    html = render_verdict_html(_vj(), title="vEcoli ↔ v2ecoli (basal)")
    assert "<img" not in html and "src=" not in html        # no external assets
    assert "Cell mass" in html and "Growth rate" in html
    assert "Standard" in html and "Config" in html          # group headers, title-cased
    assert "vEcoli ↔ v2ecoli (basal)" in html               # title
    assert "overall" in html.lower()


def test_render_tolerates_missing_value_and_meter():
    vj = {"schema": "report_card_verdict/v1", "overall": "ungraded",
          "groups": {"tests": {"verdict": "ungraded", "axes": [
              {"id": "tests.t1", "label": "t1", "verdict": "ungraded"}]}}}
    html = render_verdict_html(vj)
    assert "t1" in html
