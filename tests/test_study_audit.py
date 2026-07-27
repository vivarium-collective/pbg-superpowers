"""Tests for the L0-L5 study-reproducibility audit (viva_superpowers.study_audit)."""
import json

from viva_superpowers.study_audit import (
    CheckResult,
    StudyAudit,
    AuditReport,
    audit_workspace,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _ws(tmp_path, name="t"):
    (tmp_path / "workspace.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    (tmp_path / "studies").mkdir(exist_ok=True)
    return tmp_path


def _study(tmp_path, slug, text):
    d = tmp_path / "studies" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "study.yaml").write_text(text, encoding="utf-8")
    return d


def _find(audit, name):
    return next((c for c in audit.checks if c.name == name), None)


def _all_checks(report):
    out = []
    for a in list(report.studies) + list(report.investigations):
        out.extend(a.checks)
    return out


def _find_any(report, name):
    return next((c for c in _all_checks(report) if c.name == name), None)


# ---------------------------------------------------------------------------
# Task 1 — data model + enumeration + empty report
# ---------------------------------------------------------------------------

def test_empty_workspace_returns_empty_report(tmp_path):
    _ws(tmp_path)
    report = audit_workspace(tmp_path)
    assert report.studies == []
    assert report.investigations == []
    assert report.hard_failures() == []
    d = report.as_dict()
    assert d["studies"] == []
    assert d["investigations"] == []
    # fully JSON-serializable
    assert json.loads(json.dumps(d)) == d


def test_worst_semantics():
    a = StudyAudit(slug="s", checks=[])
    assert a.worst() == "pass"
    a.checks.append(CheckResult("L0", "x", "pass", "hard"))
    assert a.worst() == "pass"
    a.checks.append(CheckResult("L2", "y", "warn", "soft"))
    assert a.worst() == "warn"
    a.checks.append(CheckResult("L0", "z", "fail", "hard"))
    assert a.worst() == "fail"


def test_enumeration_produces_one_studyaudit_per_study(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1", "name: s1\n")
    _study(tmp_path, "s2", "name: s2\n")
    report = audit_workspace(tmp_path)
    slugs = {a.slug for a in report.studies}
    assert {"s1", "s2"} <= slugs


# ---------------------------------------------------------------------------
# Task 2 — L0 Structure + L1 Resolvability (HARD tier)
# ---------------------------------------------------------------------------

_KNOWN = {"pkg.good"}
_GENPARAMS = {"pkg.good": {"rate"}}

_GOOD_STUDY = """\
name: s1
conditions:
  baseline:
    name: base
    composite: pkg.good
  variants:
    - name: v1
      composite: pkg.good
      params:
        rate: 2
  model_settings: []
"""


def _audit(tmp_path):
    return audit_workspace(tmp_path, known_composites=_KNOWN, generator_params=_GENPARAMS)


def test_good_study_passes_all_l0_l1(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1", _GOOD_STUDY)
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    for name in ("slug-matches-dir", "canonical-model-schema",
                 "composite-resolves", "params-are-generator-accepted",
                 "inputs-from-resolves"):
        c = _find(a, name)
        assert c is not None, f"{name} missing"
        assert c.status == "pass", f"{name} -> {c.status}: {c.detail}"
    assert report.hard_failures() == []


def test_nested_study_fails_no_nested(tmp_path):
    _ws(tmp_path)
    nested = tmp_path / "investigations" / "inv" / "study.yaml"
    nested.parent.mkdir(parents=True)
    nested.write_text("name: nested\n", encoding="utf-8")
    report = _audit(tmp_path)
    c = _find_any(report, "no-nested-study")
    assert c is not None and c.status == "fail" and c.tier == "hard"


def test_slug_mismatch_fails(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1", "name: other\n")
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    c = _find(a, "slug-matches-dir")
    assert c.status == "fail" and c.tier == "hard"


def test_missing_composite_fails_resolution(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1",
           "name: s1\nconditions:\n  baseline:\n    composite: pkg.missing\n  model_settings: []\n")
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    c = _find(a, "composite-resolves")
    assert c.status == "fail" and c.tier == "hard"


def test_bogus_params_fail(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1",
           "name: s1\nconditions:\n  baseline:\n    composite: pkg.good\n    params:\n      bogus: 1\n  model_settings: []\n")
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    c = _find(a, "params-are-generator-accepted")
    assert c.status == "fail" and c.tier == "hard"


def test_n_steps_param_is_accepted(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1",
           "name: s1\nconditions:\n  baseline:\n    composite: pkg.good\n    params:\n      rate: 1\n      n_steps: 10\n  model_settings: []\n")
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    assert _find(a, "params-are-generator-accepted").status == "pass"


def test_dangling_input_from_fails(tmp_path):
    _ws(tmp_path)
    _study(tmp_path, "s1",
           "name: s1\nconditions:\n  baseline:\n    composite: pkg.good\n  model_settings: []\n"
           "inputs:\n  - artifact: x\n    from: nope\n")
    report = _audit(tmp_path)
    (a,) = [x for x in report.studies if x.slug == "s1"]
    c = _find(a, "inputs-from-resolves")
    assert c.status == "fail" and c.tier == "hard"


def test_malformed_study_is_single_l0_fail(tmp_path):
    _ws(tmp_path)
    d = tmp_path / "studies" / "bad"
    d.mkdir(parents=True)
    (d / "study.yaml").write_text("name: [unterminated\n", encoding="utf-8")
    report = _audit(tmp_path)  # must not raise
    (a,) = [x for x in report.studies if x.slug == "bad"]
    assert a.worst() == "fail"
    assert any(c.level == "L0" and c.status == "fail" for c in a.checks)


def test_legacy_studies_key_warns(tmp_path):
    _ws(tmp_path)
    inv = tmp_path / "investigations" / "inv"
    inv.mkdir(parents=True)
    (inv / "investigation.yaml").write_text("name: inv\nstudies:\n  - s1\n", encoding="utf-8")
    report = _audit(tmp_path)
    (a,) = [x for x in report.investigations if x.slug == "inv"]
    c = _find(a, "investigation-members-only")
    assert c.status == "warn"
