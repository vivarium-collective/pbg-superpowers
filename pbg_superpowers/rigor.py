"""Evidence & rigor scorecard — deterministic feedback on how well a study /
investigation defends its claims against a skeptical reader.

Motivation
----------
A skeptical reviewer of a simulation-based investigation repeatedly asks the
same questions: *Did you replicate across seeds? Where are the negative
controls? Have you separated observation from interpretation and excluded
alternative explanations? Are the acceptance criteria falsifiable, or tailored
to succeed? Is there an adversarial study that tries to break the framework?*

The framework already has rich structure (behavior_tests, gates, findings,
acceptance_criteria, simulation_set.seeds) but never *computes feedback* on
these dimensions, so authors omit them and reviewers can't see the gaps. This
module turns each rigor dimension into a deterministic signal computed from
declared (optional) fields. A missing field is not an error — it produces a
``gap`` signal, which IS the feedback that prompts the next investigation to do
better.

Everything here is pure and deterministic (no LLM/AI) so the AI-free dashboard
can call it directly. Mirrors :mod:`pbg_superpowers.study_verdict` in spirit:
pure ``spec -> dict`` functions.

Schema (all OPTIONAL, back-compatible)
--------------------------------------
study.yaml::

    kind: adversarial                 # or study_kind: adversarial (default: standard)
    robustness:                       # else derived from simulation_set.seeds / runs
      n_replicates: 3
      seeds: [0, 1, 2]
      parameter_sweep: true
    controls:                         # negative / discriminating / calibration controls
      - name: externally-maintained-membrane
        kind: negative                # negative | adversarial | positive | borderline
        hypothesis: "If the membrane is supplied externally, closure should FAIL."
        expected: fail-closure
        observed: fail-closure        # optional, after running
        result: PASS                  # PASS = control discriminated as expected
      # A positive/borderline control calibrates the metric across its range (C4).
    limitations: "What this result does NOT show: e.g. only one membrane function
      (a geometric boundary) is modelled, not transport/signalling/energetics."
      # or does_not_show: [...]
    alternative_hypotheses:           # competing explanations + how excluded
      - claim: "Survival gain is plain movement-to-resources, not sense-making."
        discriminated_by: "non-sensing motile control"
        status: not-excluded          # excluded | not-excluded | untested
    findings:                         # existing shape, extended with two opt fields
      - statement: "..."
        tier: interpretation          # observation | mechanism | interpretation
        mechanism_origin: engineered  # engineered | emergent (for tier=interpretation)
        evidence: {from_test: agency-advantage}
    falsifiability: "Closure would fail if the membrane were externally supplied."
      # or per behavior_test: could_fail_if: "..."

investigation.yaml::

    acceptance_criteria:
      - study: ...
        behavior: ...
        could_fail_if: "..."          # falsifiability note
        independent: false            # derived from theory-under-test vs independent perspective
    competing_frameworks:             # compared interpretive lenses (C13)
      - name: active inference
        relation: "predicts the same survival gain; distinguished by ..."
"""
from __future__ import annotations

from typing import Any

# Severity vocabulary, ordered worst→best for roll-ups.
GAP = "gap"
WARN = "warn"
OK = "ok"
_SEVERITY_RANK = {GAP: 0, WARN: 1, OK: 2}


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else ([] if v is None else [v])


def _nonempty(v: Any) -> bool:
    """True if a str/list field carries actual content."""
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(str(x).strip() for x in v)
    return bool(v)


def _findings(spec: dict) -> list[dict]:
    out = []
    for f in _as_list(spec.get("findings")):
        if isinstance(f, dict):
            out.append(f)
        elif isinstance(f, str):
            out.append({"statement": f})
    return out


def _replicate_count(spec: dict) -> tuple[int, bool]:
    """Return (n_replicates, parameter_sweep) from declared fields.

    Prefers an explicit ``robustness`` block; else counts ``simulation_set``
    seeds; else counts recorded ``runs``.
    """
    rob = spec.get("robustness") or {}
    if isinstance(rob, dict):
        n = rob.get("n_replicates")
        seeds = rob.get("seeds")
        sweep = bool(rob.get("parameter_sweep"))
        if isinstance(n, int):
            return n, sweep
        if isinstance(seeds, list):
            return len(seeds), sweep
    # Derive from simulation_set seeds.
    seeds_total = 0
    for sim in _as_list(spec.get("simulation_set")):
        if isinstance(sim, dict):
            seeds_total += len(_as_list(sim.get("seeds")))
    if seeds_total:
        return seeds_total, False
    # Fall back to count of recorded runs.
    return len(_as_list(spec.get("runs"))), False


def _dim(id_: str, label: str, severity: str, detail: str, comments: list[str]) -> dict:
    return {"id": id_, "label": label, "severity": severity,
            "detail": detail, "comments": comments}


def study_rigor(spec: dict) -> dict:
    """Compute the per-study rigor scorecard.

    Returns ``{dimensions: [...], score: {gap,warn,ok,total}, summary: str}``.
    Pure; tolerant of a minimal spec (every absent field yields a ``gap``).
    """
    spec = spec or {}
    findings = _findings(spec)
    interp = [f for f in findings if (f.get("tier") or "").lower() == "interpretation"]
    tiered = [f for f in findings if f.get("tier")]
    dims: list[dict] = []

    # 1. Replication [C4]
    n_rep, sweep = _replicate_count(spec)
    if sweep or n_rep >= 3:
        dims.append(_dim("replication", "Replication", OK,
                         f"{n_rep} replicate(s)" + (" + parameter sweep" if sweep else ""), ["C4"]))
    elif n_rep == 2:
        dims.append(_dim("replication", "Replication", WARN,
                         "only 2 replicates — add seeds for a robustness claim", ["C4"]))
    else:
        dims.append(_dim("replication", "Replication", GAP,
                         "single run — no replication across seeds declared "
                         "(add robustness.seeds or simulation_set.seeds)", ["C4"]))

    # 2. Controls & calibration [C1, C2, C4] — a system that SHOULD fail
    #    (discriminative power) AND a clearly-passing / borderline case so the
    #    metric is calibrated across its range, not merely asserted.
    controls = [c for c in _as_list(spec.get("controls")) if isinstance(c, dict)]
    negs = [c for c in controls if (c.get("kind") or "").lower() in ("negative", "adversarial")]
    pos = [c for c in controls if (c.get("kind") or "").lower() in ("positive", "borderline")]
    discriminating = [c for c in negs if str(c.get("result", "")).upper() == "PASS"]
    if not controls:
        dims.append(_dim("negative_control", "Controls & calibration", GAP,
                         "no controls — declare a system that SHOULD fail the criteria "
                         "(externally-maintained / -supplied) plus a clearly-passing / borderline "
                         "case so the metric is calibrated, not just asserted", ["C1", "C2", "C4"]))
    elif not negs:
        dims.append(_dim("negative_control", "Controls & calibration", WARN,
                         "controls declared but none negative/adversarial — add a system that SHOULD fail", ["C1", "C2"]))
    elif discriminating and pos:
        dims.append(_dim("negative_control", "Controls & calibration", OK,
                         f"{len(discriminating)} discriminating control(s) + a passing/borderline case "
                         "calibrate the metric across its range", ["C1", "C2", "C4"]))
    elif discriminating:
        dims.append(_dim("negative_control", "Controls & calibration", WARN,
                         "negative control discriminates, but no clearly-passing / borderline case to "
                         "calibrate the metric across its range", ["C2", "C4"]))
    else:
        dims.append(_dim("negative_control", "Controls & calibration", WARN,
                         f"{len(negs)} control(s) declared but none recorded a discriminating result", ["C1", "C2"]))

    # 3. Alternative hypotheses [C3, C6, C8]
    alts = [a for a in _as_list(spec.get("alternative_hypotheses")) if isinstance(a, dict)]
    excluded = [a for a in alts if (a.get("status") or "").lower() == "excluded"]
    if excluded:
        dims.append(_dim("alternatives", "Alternative hypotheses", OK,
                         f"{len(excluded)} of {len(alts)} competing explanation(s) excluded by evidence", ["C3", "C6", "C8"]))
    elif alts:
        dims.append(_dim("alternatives", "Alternative hypotheses", WARN,
                         f"{len(alts)} alternative(s) listed but none excluded yet", ["C3", "C6", "C8"]))
    elif interp:
        dims.append(_dim("alternatives", "Alternative hypotheses", GAP,
                         "interpretation-tier finding(s) present but no competing explanations "
                         "considered (add alternative_hypotheses + how the evidence discriminates)", ["C3", "C6", "C8"]))
    else:
        dims.append(_dim("alternatives", "Alternative hypotheses", GAP,
                         "no alternative hypotheses declared", ["C6"]))

    # 4. Claim discipline — observation vs mechanism vs interpretation [C3]
    if not findings:
        dims.append(_dim("claim_discipline", "Claim discipline", GAP,
                         "no findings recorded", ["C3"]))
    elif not tiered:
        dims.append(_dim("claim_discipline", "Claim discipline", WARN,
                         "findings not tiered — label each observation / mechanism / interpretation", ["C3"]))
    else:
        interp_no_evidence = [f for f in interp if not f.get("evidence")]
        if interp_no_evidence:
            dims.append(_dim("claim_discipline", "Claim discipline", GAP,
                             f"{len(interp_no_evidence)} interpretation finding(s) not linked to evidence", ["C3"]))
        else:
            dims.append(_dim("claim_discipline", "Claim discipline", OK,
                             "findings tiered; interpretation claims carry evidence", ["C3"]))

    # 5. Falsifiability of the bar [C5, C1]
    has_fals = bool(str(spec.get("falsifiability") or "").strip())
    if not has_fals:
        for t in _as_list(spec.get("behavior_tests")):
            if isinstance(t, dict) and str(t.get("could_fail_if") or "").strip():
                has_fals = True
                break
    if not has_fals:
        for c in _as_list(spec.get("acceptance_criteria")):  # study-embedded, if any
            if isinstance(c, dict) and str(c.get("could_fail_if") or "").strip():
                has_fals = True
                break
    dims.append(_dim("falsifiability", "Falsifiability", OK if has_fals else GAP,
                     "a 'how this could fail' note is declared" if has_fals
                     else "criteria read as tailored-to-succeed — add a falsifiability note "
                          "(study.falsifiability or behavior_test.could_fail_if)", ["C5", "C1"]))

    # 6. Engineered vs emergent [C7]
    interp_no_origin = [f for f in interp if not (f.get("mechanism_origin"))]
    if not interp:
        dims.append(_dim("mechanism_origin", "Engineered vs emergent", OK,
                         "no interpretation-tier claim that requires the distinction", ["C7"]))
    elif interp_no_origin:
        dims.append(_dim("mechanism_origin", "Engineered vs emergent", WARN,
                         f"{len(interp_no_origin)} interpretation claim(s) don't state whether the "
                         "mechanism is engineered or emergent", ["C7"]))
    else:
        dims.append(_dim("mechanism_origin", "Engineered vs emergent", OK,
                         "interpretation claims declare engineered vs emergent", ["C7"]))

    # 7. Limitations / "what this does not show" [C8, C11]
    has_lim = _nonempty(spec.get("limitations")) or _nonempty(spec.get("does_not_show"))
    dims.append(_dim("limitations", "Limitations stated", OK if has_lim else GAP,
                     "states what the result does not show" if has_lim
                     else "no limitations / 'what this does not show' — add a short bound on the claim "
                          "(scope/fidelity of the model, what is NOT demonstrated)", ["C8", "C11"]))

    score = {GAP: 0, WARN: 0, OK: 0}
    for d in dims:
        score[d["severity"]] = score.get(d["severity"], 0) + 1
    addressed = score[OK]
    total = len(dims)
    return {
        "dimensions": dims,
        "score": {"gap": score[GAP], "warn": score[WARN], "ok": score[OK], "total": total},
        "summary": f"{addressed}/{total} rigor dimensions addressed"
                   + (f" · {score[GAP]} gap(s)" if score[GAP] else ""),
    }


def investigation_rigor(inv_spec: dict, study_specs: list[dict]) -> dict:
    """Roll study rigor up to the investigation, plus investigation-level
    dimensions (adversarial coverage, methodology strength).

    ``study_specs`` is the list of member study specs (any order). Returns
    ``{per_study: {slug: scorecard}, dimensions: [...], score: {...}, summary}``.
    """
    inv_spec = inv_spec or {}
    study_specs = study_specs or []

    per_study: dict[str, dict] = {}
    for s in study_specs:
        slug = (s or {}).get("name") or (s or {}).get("slug") or f"study-{len(per_study)}"
        per_study[slug] = study_rigor(s or {})

    dims: list[dict] = []

    # Adversarial coverage [C10]
    def _is_adversarial(s):
        return (str((s or {}).get("kind") or (s or {}).get("study_kind") or "").lower()
                == "adversarial")
    adversarial = [s for s in study_specs if _is_adversarial(s)]
    if adversarial:
        dims.append(_dim("adversarial_coverage", "Adversarial testing", OK,
                         f"{len(adversarial)} adversarial study(ies) designed to break the framework", ["C10", "C12", "C15"]))
    else:
        dims.append(_dim("adversarial_coverage", "Adversarial testing", GAP,
                         "no adversarial study — add one that tries to BREAK the criteria: "
                         "mimic / parasitic-or-dependent / externally-maintained / random-cyclic "
                         "systems that should NOT qualify", ["C10", "C12", "C15"]))

    # Methodology strength [C9, C2, C14] — informational positive headline; the
    # reusable methodological contribution the reviewers single out.
    has_dag = any("pipeline_gate" in (s or {}) for s in study_specs)
    has_ac = bool(_as_list(inv_spec.get("acceptance_criteria")))
    if has_dag and has_ac:
        dims.append(_dim("methodology", "Traceable methodology", OK,
                         "capability ladder (study DAG) + explicit acceptance criteria + pass/fail "
                         "gates + traceable findings — the reusable methodological contribution", ["C9", "C2", "C14"]))

    # Falsification exposure [C1] — has the framework ever been seen to reject
    # something? All-pass with no failing control reads as confirmation-only.
    def _passed(s):
        pg = (s or {}).get("pipeline_gate") or {}
        ge = (pg.get("gate_evaluator") or {}) if isinstance(pg, dict) else {}
        res = str(ge.get("result") or (s or {}).get("gate_status") or "").lower()
        return res in ("passed", "pass")

    def _has_discriminating_negative(s):
        for c in _as_list((s or {}).get("controls")):
            if (isinstance(c, dict)
                    and (c.get("kind") or "").lower() in ("negative", "adversarial")
                    and str(c.get("result", "")).upper() == "PASS"):
                return True
        return False

    all_passed = bool(study_specs) and all(_passed(s) for s in study_specs)
    visible_failure = (bool(adversarial)
                       or any(_has_discriminating_negative(s) for s in study_specs)
                       or (bool(study_specs) and not all_passed))
    if visible_failure:
        dims.append(_dim("falsification_exposure", "Falsification exposure", OK,
                         "the framework has been shown to reject at least one system (a discriminating "
                         "negative control, an adversarial study, or a non-passing result)", ["C1"]))
    else:
        dims.append(_dim("falsification_exposure", "Falsification exposure", GAP,
                         "every study passes and nothing was shown to fail — the framework was not "
                         "visibly exposed to falsification (add a control that fails, an adversarial "
                         "study, or report a non-passing result)", ["C1"]))

    # Competing theoretical frameworks [C13]
    cf = _as_list(inv_spec.get("competing_frameworks"))
    if cf:
        dims.append(_dim("comparative_framing", "Comparative framing", OK,
                         f"{len(cf)} competing theoretical framework(s) compared", ["C13"]))
    else:
        dims.append(_dim("comparative_framing", "Comparative framing", GAP,
                         "no competing theoretical frameworks compared (viability theory, organizational / "
                         "constraint closure, active inference) — show the findings uniquely support this lens", ["C13"]))

    # Aggregate the worst per-study gap count as an investigation signal.
    study_gaps = sum(sc["score"]["gap"] for sc in per_study.values())
    if study_gaps:
        dims.append(_dim("study_rigor_gaps", "Per-study rigor gaps", WARN if study_gaps < 4 else GAP,
                         f"{study_gaps} rigor gap(s) across {len(per_study)} member study(ies)", ["C2", "C4", "C6"]))
    elif per_study:
        dims.append(_dim("study_rigor_gaps", "Per-study rigor gaps", OK,
                         "member studies have no rigor gaps", []))

    score = {GAP: 0, WARN: 0, OK: 0}
    for d in dims:
        score[d["severity"]] = score.get(d["severity"], 0) + 1
    return {
        "per_study": per_study,
        "dimensions": dims,
        "score": {"gap": score[GAP], "warn": score[WARN], "ok": score[OK], "total": len(dims)},
        "summary": f"{score[OK]}/{len(dims)} investigation rigor dimensions addressed"
                   + (f" · {score[GAP]} gap(s)" if score[GAP] else ""),
    }
