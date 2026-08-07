# Pressure scenarios — behavioral tests for the discipline skills

`tests/test_skill_conventions.py` is a *static* lint: it checks a skill's shape
(trigger description, H1, budgets), never its effect on an agent. This directory
is the *behavioral* layer, following obra/superpowers' `writing-skills` Iron Law:

> NO SKILL WITHOUT A FAILING TEST FIRST. If you didn't watch an agent fail
> without the skill, you don't know if the skill teaches the right thing.

Each `*.md` here is one scenario targeting one discipline rule (a `<HARD-GATE>` or
an Excuse|Reality table). A scenario is **not** run by `pytest` — it's a prompt you
dispatch to a fresh subagent, because the thing under test is *agent behavior under
pressure*, which a unit test can't observe.

## How to run one

1. **Control (no skill).** Dispatch a fresh subagent with the scenario's *Prompt*
   and no access to the target skill. Record what it does and, verbatim, the
   rationalizations it produces. This is the baseline failure the skill exists to
   prevent — it should reproduce the "Baseline failure" documented in the file.
2. **Treatment (with skill).** Dispatch a fresh subagent with the same prompt and
   the target skill available. It should refuse the shortcut and take the
   documented correct action.
3. **Compare.** If the treatment agent still fails, the skill's wording is too
   weak — tighten the gate / add the observed excuse to the table, and repeat.
   Run 3+ reps per side; obra treats variance as a metric.

## The rule this directory enforces

When you edit a discipline section of a skill — a `<HARD-GATE>`, an Excuse|Reality
table, an honesty rule — **re-run its scenario against a fresh subagent before
shipping.** The tables must contain *observed* excuses, not invented ones. See
[`docs/conventions/writing-viva-skills.md`](../../docs/conventions/writing-viva-skills.md#behavioral-testing-pressure-scenarios).

## The corpus

| Scenario | Target rule | Skill |
|---|---|---|
| [`mock-downgrade.md`](mock-downgrade.md) | never silently downgrade to mock/reproduction | `viva-expert` |
| [`fabricated-observable.md`](fabricated-observable.md) | never fabricate an observable / provided-mechanisms-only | `viva-study` (+ `check-observables`) |
| [`verdict-from-memory.md`](verdict-from-memory.md) | evidence-before-verdict gate | `viva-study` Decide |
| [`stale-tree-diagnosis.md`](stale-tree-diagnosis.md) | a `ran` status with uncommitted/unreproducible artifacts is not a result | `viva-harden-investigation` (rule 0, already validated in the wild) |
