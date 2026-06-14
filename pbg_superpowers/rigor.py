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

# Above this coefficient of variation, per-measure spread across seeds is
# treated as cross-seed disagreement (item 14 — replication scores AGREEMENT,
# not merely count). Deterministic threshold; tolerant of missing sub-fields.
_HIGH_CV = 0.5


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


def _replication_agreement(spec: dict, n_rep: int) -> tuple[bool, str]:
    """Inspect ``robustness`` for cross-seed AGREEMENT (item 14).

    Returns ``(disagrees, reason)``. Two deterministic signals, both optional:

    * ``robustness.per_measure[*]`` — an explicit ``cv`` (coefficient of
      variation), else derived as ``|std / mean|``; a value above
      :data:`_HIGH_CV` means the measure is not stable across seeds.
    * ``robustness.seeds_with_advantage`` — count (int) or list of seeds, or a
      fraction in ``(0, 1]`` (float); no majority (``<= 0.5`` of replicates)
      means the seeds don't agree on the effect.

    When no agreement evidence is present, returns ``(False, "")`` — the
    replicate count alone stands. Tolerant of malformed sub-fields.
    """
    rob = spec.get("robustness")
    if not isinstance(rob, dict):
        return False, ""
    reasons: list[str] = []

    # 1. Per-measure coefficient of variation.
    for m in _as_list(rob.get("per_measure")):
        if not isinstance(m, dict):
            continue
        cv = m.get("cv")
        if cv is None:
            std = m.get("std")
            mean = m.get("mean")
            try:
                if std is not None and mean not in (None, 0):
                    cv = abs(float(std) / float(mean))
            except (TypeError, ValueError, ZeroDivisionError):
                cv = None
        try:
            if cv is not None and float(cv) > _HIGH_CV:
                reasons.append(f"{m.get('name') or 'a measure'} CoV={float(cv):.2f}")
        except (TypeError, ValueError):
            pass

    # 2. Majority agreement among seeds.
    swa = rob.get("seeds_with_advantage")
    frac = None
    if isinstance(swa, bool):
        frac = None
    elif isinstance(swa, list):
        frac = (len(swa) / n_rep) if n_rep else None
    elif isinstance(swa, int):
        frac = (swa / n_rep) if n_rep else None
    elif isinstance(swa, float):
        frac = swa if 0 < swa <= 1 else ((swa / n_rep) if n_rep else None)
    if frac is not None and frac <= 0.5:
        reasons.append("no majority of seeds shows the advantage")

    return (bool(reasons), "; ".join(reasons))


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

    # 1. Replication [C4] — score AGREEMENT, not just count (item 14): with
    #    enough replicates, also check that the seeds actually agree.
    n_rep, sweep = _replicate_count(spec)
    if sweep or n_rep >= 3:
        base = f"{n_rep} replicate(s)" + (" + parameter sweep" if sweep else "")
        disagrees, why = _replication_agreement(spec, n_rep)
        if disagrees:
            dims.append(_dim("replication", "Replication", WARN,
                             base + f" but seeds disagree ({why}) — "
                             "result is not robust across seeds", ["C4"]))
        else:
            dims.append(_dim("replication", "Replication", OK, base, ["C4"]))
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
    # A control only discriminates if it actually ran (non-empty `observed`)
    # AND recorded a PASS — a PASS with no observation earns no credit (item 15).
    discriminating = [c for c in negs
                      if str(c.get("result", "")).upper() == "PASS" and _nonempty(c.get("observed"))]
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

    # 3. Alternative hypotheses [C3, C6, C8] — also credit the Decide-phase
    #    synthesis (discovery_implications.alternate_hypotheses).
    # [C5] Single alternatives source: prefer the Decide-phase synthesis
    # (discovery_implications.alternate_hypotheses), fall back to the top-level
    # alternative_hypotheses so authored prose anywhere still counts.
    _di = spec.get("discovery_implications") or {}
    alts = []
    if isinstance(_di, dict):
        alts = [a for a in _as_list(_di.get("alternate_hypotheses")) if isinstance(a, dict)]
    if not alts:
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

    # 5. Falsifiability of the bar [C5, C1] — the one authored field is
    #    study.falsifiability (no producer ever writes a per-test could_fail_if).
    has_fals = bool(str(spec.get("falsifiability") or "").strip())
    dims.append(_dim("falsifiability", "Falsifiability", OK if has_fals else GAP,
                     "a 'how this could fail' note is declared" if has_fals
                     else "criteria read as tailored-to-succeed — add a falsifiability note "
                          "(study.falsifiability)", ["C5", "C1"]))

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

    # 7. Limitations / "what this does not show" [C8, C11] — also credit the
    #    Decide-phase remaining_uncertainties (the same "what's still open").
    _di_lim = spec.get("discovery_implications") or {}
    has_lim = (_nonempty(spec.get("limitations")) or _nonempty(spec.get("does_not_show"))
               or (isinstance(_di_lim, dict) and _nonempty(_di_lim.get("remaining_uncertainties"))))
    dims.append(_dim("limitations", "Limitations stated", OK if has_lim else GAP,
                     "states what the result does not show" if has_lim
                     else "no limitations / 'what this does not show' — add a short bound on the claim "
                          "(scope/fidelity of the model, what is NOT demonstrated)", ["C8", "C11"]))

    # 8. Next steps / discovery implications [Decide-phase completeness]
    di = spec.get("discovery_implications")
    if isinstance(di, dict):
        has_di = any(_nonempty(v) for v in di.values())
    else:
        has_di = _nonempty(di)
    has_next = has_di or _nonempty(spec.get("follow_up_studies"))
    dims.append(_dim("next_steps", "Next steps", OK if has_next else GAP,
                     "declares discovery implications / follow-up studies" if has_next
                     else "no discovery_implications or follow_up_studies — state what this study "
                          "changes and what to investigate next (the Decide phase)", ["next-steps"]))

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


# ---------------------------------------------------------------------------
# Per-finding evidential weight (item 8) — a strong/moderate/weak chip per
# finding, computed by REUSING the study-level rigor predicates restricted to
# the one finding (degrading to study-level signals when it can't be matched).
# ---------------------------------------------------------------------------

def _finding_match_tokens(finding: dict) -> set[str]:
    """Lower-cased identifiers a finding can be matched on — keyed primarily by
    ``evidence.from_test`` (per the contract), plus the finding's measure/name."""
    toks: set[str] = set()
    ev = finding.get("evidence")
    if isinstance(ev, dict):
        for k in ("from_test", "measure", "observable"):
            v = ev.get(k)
            if isinstance(v, str) and v.strip():
                toks.add(v.strip().lower())
    for k in ("measure", "id", "name", "test"):
        v = finding.get(k)
        if isinstance(v, str) and v.strip():
            toks.add(v.strip().lower())
    return toks


def _finding_divergence_present(finding: dict) -> bool:
    """Effect-size signal: ``calibration_anchor.divergence_factor`` (or the
    mirrored ``evidence.divergence_factor``) is present and meaningfully > 0.
    No recompute — reads the value the finding-observations pass already wrote."""
    for src in (finding.get("calibration_anchor"), finding.get("evidence")):
        if isinstance(src, dict):
            df = src.get("divergence_factor")
            try:
                if df is not None and abs(float(df)) > 0:
                    return True
            except (TypeError, ValueError):
                pass
    return False


def _control_matches(control: dict, tokens: set[str]) -> bool:
    if not tokens:
        return False
    hay = " ".join(str(control.get(k) or "") for k in
                   ("name", "test", "for_test", "discriminates", "hypothesis", "measure")).lower()
    return any(t in hay for t in tokens)


def _excluded_alternatives(spec: dict) -> list[dict]:
    """The excluded competing explanations — same source preference as the
    ``alternatives`` rigor dimension (DI-synthesis preferred, top-level fallback)."""
    _di = spec.get("discovery_implications") or {}
    alts: list[dict] = []
    if isinstance(_di, dict):
        alts = [a for a in _as_list(_di.get("alternate_hypotheses")) if isinstance(a, dict)]
    if not alts:
        alts = [a for a in _as_list(spec.get("alternative_hypotheses")) if isinstance(a, dict)]
    return [a for a in alts if (a.get("status") or "").lower() == "excluded"]


def _alt_matches(alt: dict, tokens: set[str]) -> bool:
    if not tokens:
        return False
    hay = " ".join(str(alt.get(k) or "") for k in
                   ("discriminated_by", "discriminator", "discriminates", "claim")).lower()
    return any(t in hay for t in tokens)


def finding_evidential_weight(spec: dict, finding: dict) -> dict:
    """Per-finding evidential weight (item 8).

    Returns ``{"weight": "strong"|"moderate"|"weak", "dims": {...}, "n_supporting": int}``
    where ``dims`` carries the five booleans ``replication, effect_size,
    control_strength, independence, alternatives``.

    Pure and tolerant. Every dimension REUSES an existing study-level predicate,
    restricted to the finding via a TOLERANT matcher keyed on
    ``finding['evidence']['from_test']``; when a finding can't be matched to
    per-finding inputs it degrades to the study-level signal (never mislabels).
    """
    spec = spec or {}
    finding = finding or {}
    tokens = _finding_match_tokens(finding)

    # replication — _replication_agreement restricted to the finding's measure;
    # degrade to the full study robustness block when no per-measure matches.
    n_rep, sweep = _replicate_count(spec)
    rob = spec.get("robustness")
    rep_spec = spec
    if isinstance(rob, dict) and tokens:
        per = [m for m in _as_list(rob.get("per_measure"))
               if isinstance(m, dict) and str(m.get("name") or "").lower() in tokens]
        if per:
            rep_spec = {**spec, "robustness": {**rob, "per_measure": per}}
    disagrees, _ = _replication_agreement(rep_spec, n_rep)
    replication = (sweep or n_rep >= 3) and not disagrees

    # effect_size — the finding's recorded divergence_factor (no recompute).
    effect_size = _finding_divergence_present(finding)

    # control_strength — reuse the discriminating-control filter (PASS + non-empty
    # observed), matched to this finding's test; degrade to "any discriminating
    # control in the study" when none names this test.
    controls = [c for c in _as_list(spec.get("controls")) if isinstance(c, dict)]
    negs = [c for c in controls if (c.get("kind") or "").lower() in ("negative", "adversarial")]
    discriminating = [c for c in negs
                      if str(c.get("result", "")).upper() == "PASS" and _nonempty(c.get("observed"))]
    matched_controls = [c for c in discriminating if _control_matches(c, tokens)]
    control_strength = bool(matched_controls) if matched_controls else bool(discriminating)

    # independence — emergent (not engineered) interpretation.
    independence = (finding.get("mechanism_origin") or "").lower() == "emergent"

    # alternatives — an excluded competing explanation whose discriminator names
    # this finding's test; degrade to "any excluded alternative in the study".
    excluded = _excluded_alternatives(spec)
    matched_alts = [a for a in excluded if _alt_matches(a, tokens)]
    alternatives = bool(matched_alts) if matched_alts else bool(excluded)

    dims = {
        "replication": bool(replication),
        "effect_size": bool(effect_size),
        "control_strength": bool(control_strength),
        "independence": bool(independence),
        "alternatives": bool(alternatives),
    }
    n_supporting = sum(1 for v in dims.values() if v)
    if n_supporting >= 4:
        weight = "strong"
    elif n_supporting >= 2:
        weight = "moderate"
    else:
        weight = "weak"
    return {"weight": weight, "dims": dims, "n_supporting": n_supporting}


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
                    and str(c.get("result", "")).upper() == "PASS"
                    and _nonempty(c.get("observed"))):  # item 15: must have run
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
