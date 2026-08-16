# viva-superpowers — agent gateway (harness-neutral)

This file is the entry point for coding agents that read `AGENTS.md` (Codex,
Cursor, and others). It plays the same role as the `viva-orient` skill, which
Claude Code auto-injects at session start via `hooks/session-start` — on harnesses
without that hook, **this file is the gateway.**

viva-superpowers builds **process-bigraph research workspaces** — wrapping
simulators as typed Processes, composing them, and running studies through the
**vivarium-workbench** dashboard. The capabilities are documented as skills in
`skills/<name>/SKILL.md`; the backend is the `viva_superpowers` Python CLI plus the
workbench HTTP API. **The workbench is the backend — most skills do nothing useful
without it.**

## How to use a skill on this harness

There is no `/plugin` marketplace, no "Skill tool", and no slash-command runner
here — those are Claude Code mechanisms. Instead: **when a `/viva-*` skill fits the
task, open its `skills/<name>/SKILL.md` and follow it before acting.** A `/viva-x`
name in this file or in a skill body names the file `skills/viva-x/SKILL.md`; read
it. Ignore Claude-only frontmatter (`allowed-tools`, `argument-hint`). For the full
idiom map — subagent dispatch, `superpowers:` composition, tool names — see
[`references/codex-tools.md`](references/codex-tools.md).

## The Rule

**If there is even a 1% chance a `/viva-*` skill fits what you are about to do,
open its `SKILL.md` and follow it BEFORE acting** — before reading YAML, exploring
the workspace, writing a script, or calling the API by hand. The skills encode this
workspace's conventions (canonical `study.yaml`, the AI-free/dashboard split,
provenance); hand-rolling around them silently drifts the workspace. This is not
negotiable; you cannot rationalize your way out of it. If a skill turns out wrong
for the situation you don't have to use it — but you must check first. When you do,
announce **"Using /viva-X to …"**.

## Where are you? Route by observable state (check top to bottom)

| State you can observe | Route to |
|---|---|
| No `workspace.yaml` in cwd/ancestors, and the user wants to model something | `/viva-workspace <name>` **first** — never wrap tools or write models into a bare directory |
| Workspace exists, but `.pbg/server/` is missing/stale (no dashboard) | `/viva-workbench start` |
| "wrap X" / "use simulator X" / "add a solver" | `/viva-expert` (default bridges the REAL tool; `--lightweight` for in-workspace) |
| "is X true?" / "compare A vs B" / any research question | `/viva-study new` (group several under `/viva-investigation`) |
| "run this composite" / "what does it emit?" | `/viva-run` |
| "what's here?" / lost / just arrived | `/viva-status`, then `/viva-catalog` |

**First session, from nothing:** `/viva-workspace my-model` → `/viva-workbench start`
→ then wrap a tool (`/viva-expert`) or design a study (`/viva-study`). "Model X"
always means **workspace first**.

## Skill map

| Group | Skills |
|---|---|
| **Wrap & compose** | `/viva-expert` (wrap a simulator as a Process, or compose several) |
| **Workspace lifecycle** | `/viva-workspace` (scaffold), `/viva-workbench` (dashboard server), `/viva-init` (machine setup) |
| **Studies & runs** | `/viva-study` (design→build→simulate→evaluate→decide), `/viva-tests` (author/enrich/run graded tests → margin + diff feedback), `/viva-audit-tests` (audit Tests are sufficient before pre-registration lock), `/viva-model-build` (autonomous loop: question → author Tests → audit → lock → build/run/evaluate → iterate model until pass), `/viva-benchmark` (run a suite through the loop → process-quality rubric → report diff-able across framework variants), `/viva-run`, `/viva-investigation`, `/viva-report`, `/viva-viz` |
| **Navigate & status** | `/viva-catalog`, `/viva-navigate` (read-only graph queries + "decisions needed"), `/viva-status` |
| **Evidence & rigor** | `/viva-cite-bands`, `/viva-biology-forward`, `/viva-harden-investigation` |

Each names `skills/<name>/SKILL.md`. Vocabulary and on-disk shapes:
`docs/concepts/vivarium-workbench-model.md`.

## Red flags — STOP, you're rationalizing

| Thought | Reality |
|---|---|
| "I'll just read the study YAML and edit it directly" | `/viva-study` — direct edits skip canonicalization + provenance. |
| "I'll write a quick script to run the composite" | `/viva-run` (or `/viva-study run-*`) already does this correctly. |
| "The API call is simple, I'll curl it" | The skill knows the right endpoint and the AI-free/dashboard split. |
| "I'll wrap the tool here, no workspace needed" | Wrapping into a bare dir strands the code — `/viva-workspace` first. |
| "The server's probably up, I'll start" | Verify `.pbg/server/` first, or `/viva-workbench start`. |

---

_Cross-harness support is a spike — see [`docs/cross-harness.md`](docs/cross-harness.md)
for what's portable, what each harness needs, and current limitations. The routing
table and Rule above are kept in sync with `skills/viva-orient/SKILL.md` by
`tests/test_cross_harness.py`._
