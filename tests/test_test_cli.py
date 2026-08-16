"""viva-test CLI: reads the shipped test_report/v1 (viz/tests/report.json), applies
the severity gate, prints a pytest-style summary, exits 0/1 on the gate."""
import json

import viva_superpowers.test_cli as tc


def _ws(tmp_path, slug, *, report=None, verdicts=None):
    (tmp_path / "workspace.yaml").write_text("name: test-ws\n", encoding="utf-8")
    sd = tmp_path / "workspace" / "studies" / slug
    sd.mkdir(parents=True)
    (sd / "study.yaml").write_text(f"name: {slug}\n", encoding="utf-8")
    if report is not None:
        td = sd / "viz" / "tests"
        td.mkdir(parents=True)
        (td / "report.json").write_text(json.dumps(report), encoding="utf-8")
    for name, doc in (verdicts or {}).items():
        rc = sd / "viz" / "report_card"
        rc.mkdir(parents=True, exist_ok=True)
        (rc / f"{name}.verdict.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def _report(overall, axes_by_card, counts):
    cards = {}
    for card, axes in axes_by_card.items():
        cards[card] = {"overall": overall, "groups": {"phys": {
            "verdict": overall, "axes": axes}}}
    return {"schema": "test_report/v1", "study": "s", "overall": overall,
            "counts": counts, "cards": cards}


_FAIL_REPORT = _report("mismatch", {"growth": [
    {"id": "dt", "label": "Doubling time", "verdict": "within_tol", "meter": "Δ=-2%"},
    {"id": "gr", "label": "Growth rate", "verdict": "mismatch", "meter": "Δ=-40%",
     "severity": "hard", "citation": "Kurokawa 1999"},
]}, {"cards": 1, "axes": 2, "within_tol": 1, "drift": 0, "mismatch": 1,
     "ungraded": 0, "hard_mismatch": 1})

_PASS_REPORT = _report("within_tol", {"growth": [
    {"id": "dt", "label": "Doubling time", "verdict": "within_tol", "meter": "ok"}]},
    {"cards": 1, "axes": 1, "within_tol": 1, "drift": 0, "mismatch": 0,
     "ungraded": 0, "hard_mismatch": 0})


def test_fail_prints_summary_and_exits_1(tmp_path, capsys):
    ws = _ws(tmp_path, "s", report=_FAIL_REPORT)
    rc = tc.main(["s", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "study: s" in out and "growth" in out
    assert "SUITE: FAIL" in out and "gate: fail" in out
    assert "FAIL  growth::gr" in out          # failing axis named
    assert "Kurokawa 1999" in out             # citation surfaced
    assert "1 hard" in out


def test_pass_exits_0(tmp_path, capsys):
    ws = _ws(tmp_path, "s", report=_PASS_REPORT)
    rc = tc.main(["s", "--workspace", str(ws)])
    assert rc == 0
    assert "SUITE: PASS" in capsys.readouterr().out


def test_json_output(tmp_path, capsys):
    ws = _ws(tmp_path, "s", report=_FAIL_REPORT)
    rc = tc.main(["s", "--workspace", str(ws), "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    doc = json.loads(out)
    assert doc["schema"] == "test_report/v1"
    assert doc["gate"]["status"] == "fail"     # gate injected


def test_rebuild_from_report_cards(tmp_path, capsys):
    # No report.json — reassemble from viz/report_card/*.verdict.json.
    verdict_doc = {"overall": "mismatch", "groups": {"phys": {"verdict": "mismatch", "axes": [
        {"id": "gr", "label": "Growth rate", "verdict": "mismatch", "severity": "hard"}]}}}
    ws = _ws(tmp_path, "s", verdicts={"growth": verdict_doc})
    rc = tc.main(["s", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert rc == 1                              # rebuilt report gates fail
    assert "growth" in out and "SUITE: FAIL" in out


def test_missing_report_exits_2(tmp_path, capsys):
    ws = _ws(tmp_path, "s")                      # study exists, no tests at all
    rc = tc.main(["s", "--workspace", str(ws)])
    assert rc == 2
    assert "no test report" in capsys.readouterr().err
