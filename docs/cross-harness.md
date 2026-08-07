# Cross-harness support (spike)

viva-superpowers was built as a Claude Code plugin, but its substance is not
Claude-specific. This page describes running it from other coding agents (Codex,
Cursor, Gemini CLI). **Status: spike** — the Codex first-loop is the proven path;
broader support is incremental.

## What's portable vs. what each harness needs

| Layer | Portable? | Notes |
|---|---|---|
| `viva_superpowers` Python CLI | ✅ fully | `pip install viva-superpowers`; 9 console entry points |
| vivarium-workbench HTTP API | ✅ fully | any agent that runs a shell + makes HTTP calls can drive it |
| Skill **bodies** (`skills/*/SKILL.md`) | ✅ mostly | portable prose + shell/curl; a few Claude idioms — see [`references/codex-tools.md`](../references/codex-tools.md) |
| Skill **delivery** (marketplace, Skill tool, session-start hook) | ❌ Claude-only | replaced per harness by an entry file + the idiom map |
| Gateway auto-injection | ❌ Claude-only | `hooks/session-start` injects `viva-orient` on Claude; elsewhere `AGENTS.md` is the gateway (loaded by the harness, not auto-injected) |

## Quick start — Codex

1. `pip install viva-superpowers`
2. Point Codex at this repo so it reads **`AGENTS.md`** (the gateway) and can open
   `skills/<name>/SKILL.md` on demand.
3. Describe what you want to model. The gateway routes you: `/viva-workspace` →
   `/viva-workbench start` → `/viva-expert` or `/viva-study`. Follow the referenced
   `SKILL.md`, using [`references/codex-tools.md`](../references/codex-tools.md) to
   translate any Claude idioms.

## Limitations (honest)

- **The gateway is softer off Claude.** Claude's `session-start` hook *guarantees*
  the gateway loads every session; `AGENTS.md` loads only if the harness reads it,
  so the "invoke before acting" discipline is less enforced.
- **No subagent fan-out in the spike.** The 7 dispatch-using skills run inline on
  Codex (see the idiom map) — correct but slower, more context.
- **`superpowers:` composition is optional.** Use it if obra's plugin is installed
  for your harness; otherwise apply the principle inline.
- **Verified loop only.** The spike proves `/viva-workspace` → `/viva-workbench` →
  `/viva-run` from Codex (see `tests/pressure-scenarios/codex-first-loop.md`).
  Everything else is expected to work but is not yet exercised per-harness.

## Keeping harnesses in sync

`AGENTS.md`'s Rule + routing table are single-sourced against
`skills/viva-orient/SKILL.md` by `tests/test_cross_harness.py`, so the Claude
gateway and the `AGENTS.md` gateway can't drift apart. Adding a harness = a new
entry file + (if its tool vocabulary differs) a new `references/<harness>-tools.md`
— never a copy of the skills.
