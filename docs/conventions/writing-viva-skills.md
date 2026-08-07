# Writing viva-* skills

House conventions for authoring and editing the `/viva-*` skills. For the
underlying *method* — baseline-testing a skill against a fresh agent, capturing
rationalizations, tuning wording, token budgets — defer to
[`superpowers:writing-skills`](https://github.com/obra/superpowers) (invoke it
via the **Skill** tool). This file records only what is specific to this repo.

The house exemplar is [`skills/viva-harden-investigation/SKILL.md`](../../skills/viva-harden-investigation/SKILL.md):
a trigger description, a mode-classification table, red flags drawn from real
sessions, and a "real-world impact" section. When in doubt, match its shape.

## The conventions (enforced by `tests/test_skill_conventions.py`)

These are not style preferences — they are asserted in CI. A skill that violates
them fails the build.

1. **`description` is a trigger, not a summary.** It states *when to reach for the
   skill*, in the third person, starting with **"Use when …"**. It never
   summarizes the skill's workflow, steps, or deliverables — obra's testing shows
   an agent will follow a workflow-summarizing description *instead of reading the
   skill body*, and skip the real doctrine. Keep it **≤ 500 characters**.
   - ✅ `Use when wrapping any simulation tool as a process-bigraph Process, or composing wrapped simulators — including when the build looks hard or you are tempted to mock it.`
   - ❌ `Wraps a tool: clones the repo, builds it, writes a Process class, tests, a README, a showcase investigation, and publishes a read-only workbench…` (that is the deliverable spec — it belongs in the body).

2. **The H1 matches the command.** The first `# …` line is `# /viva-<name>`, and
   `<name>` equals the directory name and the frontmatter `name:`. No `pbg-`
   titles (the rebrand is finished).

3. **No `pbg-` in the description or H1.** Legitimate ecosystem repo names
   (`pbg-emitters`, `pbg-basic-processes`) may appear in the *body*, never the
   trigger or title.

4. **No internal program vocabulary in the description.** "spine stage #N",
   "SP4a", "stage #3b" are maintainer tags — keep them in the body if needed, not
   the user-facing trigger.

## Splitting heavy skills (SKILL.md + reference.md)

A skill's `SKILL.md` is loaded into context whenever the skill is relevant, so it
must stay lean: **doctrine, decision-making, and a compact workflow/subcommand
index**. Move long procedural detail — per-phase walkthroughs, full per-subcommand
specs, templates, mode step-by-steps — into a sibling **`reference.md`** the agent
reads on demand, and point at it from `SKILL.md`. `viva-expert` and `viva-study`
follow this pattern. Keep the split **behavior-neutral**: move content verbatim,
delete nothing. Content-contract tests read `SKILL.md` + `reference.md` together
(the documented contract is both files).

## Composition, not re-implementation

viva-superpowers is a *domain* plugin. When a general software-engineering
process applies — TDD, systematic debugging, git worktrees, writing skills —
**defer to the corresponding `superpowers:` skill by name** rather than
re-implementing it. `viva-harden-investigation` models this well
(`REQUIRED: superpowers:systematic-debugging`).

## The gateway

`viva-orient` is auto-injected at session start (see `hooks/session-start`). It is
the newcomer router: the Rule, the zero-state routing table, and the red-flags
table live there. Keep it lean (it loads every session) and keep its skill map in
sync when skills are added, removed, or merged.
