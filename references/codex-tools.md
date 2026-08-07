# Idiom map: driving viva-superpowers from Codex (and other non-Claude harnesses)

The `/viva-*` skill bodies were written for Claude Code and use a few Claude-only
idioms. The *substance* is portable; this file maps the idioms so a Codex (or
Cursor / Gemini CLI) agent can follow any `skills/<name>/SKILL.md` unchanged. Read
[`AGENTS.md`](../AGENTS.md) first — it's the gateway.

## The mappings

| A skill says… | On Claude Code | On Codex / here |
|---|---|---|
| "use the **Skill** tool" / "invoke `/viva-x`" | the Skill tool runs the skill | **open `skills/viva-x/SKILL.md` and follow it** — there is no slash runner |
| `allowed-tools: Bash(*) …` (frontmatter) | Claude's permission model | **ignore it** — you already have a shell; frontmatter is Claude-only metadata |
| `argument-hint:` (frontmatter) | Claude arg hinting | ignore; the args are documented in the skill body |
| a `<HARD-GATE>` block | a hard behavioral gate | **same force** — it's a rule, not a Claude feature; obey it |
| an Excuse\|Reality table | rationalization guard | same — read it before taking the shortcut it names |

## Subagent dispatch → run inline

Seven skills assume Claude/obra subagent fan-out (the **Agent tool**,
`superpowers:dispatching-parallel-agents`, `superpowers:subagent-driven-development`).
Codex has no native subagent fan-out in this spike. Where these skills say
"dispatch subagents" / "in parallel", **run the steps inline / sequentially** in the
current session instead — slower and more context, but correct.

Affected skills:

- **`viva-expert`** (heavy mode) — do the clone → build → wrap → test → publish
  phases inline; keep the `.build-progress.md` ledger (it matters *more* without
  subagents, since one long session is doing everything).
- **`viva-report`** — run Pass A inline for each investigation (skip the
  `audit-reviewer-prompt.md` parallel dispatch).
- **`viva-investigation`** — `scaffold-from-plan` builds member studies
  sequentially instead of via `subagent-driven-development`.
- **`viva-study`**, **`viva-harden-investigation`**, **`viva-navigate`**,
  **`viva-orient`** — any "dispatch"/"subagent" phrasing → inline.

## `superpowers:` composition

Skills defer to obra's `superpowers:*` skills by name (systematic-debugging,
receiving-code-review, writing-skills, test-driven-development, using-git-worktrees).
obra ships a Codex plugin, so **if `superpowers` is installed for your harness, use
it**. If not, apply the principle inline (e.g. "verify before implementing feedback"
for `receiving-code-review`) — the skill body states enough to act on.

## What needs no adaptation

The backend is identical on every harness:

- **`viva_superpowers` CLI** — `viva-scaffold`, `viva-compute-outcomes`,
  `viva-sync-runs`, etc. (`pip install viva-superpowers`, then run them).
- **The vivarium-workbench HTTP API** — start it (`/viva-workbench start` →
  `vivarium-workbench serve`), read `.pbg/server/server-info` for the URL, and make
  the same HTTP calls the skills document. No Claude anywhere in this path.
