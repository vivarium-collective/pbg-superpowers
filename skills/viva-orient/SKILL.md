---
name: viva-orient
description: Use when starting any viva-superpowers session or workspace task — orients you to the /viva-* skills, routes a newcomer from zero to a first wrapped process and first study, and states the two preconditions every skill assumes. Auto-injected at session start; not a command to run.
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, ignore this skill and do that task.
</SUBAGENT-STOP>

# Orienting in a viva-superpowers workspace

viva-superpowers builds **process-bigraph research workspaces** — wrapping simulators as typed Processes, composing them, and running studies through the **vivarium-workbench** dashboard. The `/viva-*` skills are thin clients over the `viva_superpowers` Python helpers and the workbench HTTP API. **The workbench is the backend — most skills do nothing useful without it.**

## The Rule

**If there is even a 1% chance a `/viva-*` skill fits what you are about to do, invoke it BEFORE acting** — before reading YAML, exploring the workspace, writing a script, or calling the API by hand. The skills encode this workspace's conventions (canonical `study.yaml`, the AI-free/dashboard split, provenance). Hand-rolling around them silently drifts the workspace. This is not negotiable; you cannot rationalize your way out of it. If a skill turns out wrong for the situation, you don't have to use it — but you must check first. When you do, announce **"Using /viva-X to …"**.

## Where are you? Route by observable state (check top to bottom)

| State you can observe | Route to |
|---|---|
| No `workspace.yaml` in cwd/ancestors, and the user wants to model something | `/viva-workspace <name>` **first** — never wrap tools or write models into a bare directory |
| Workspace exists, but `.pbg/server/` is missing/stale (no dashboard) | `/viva-workbench start` |
| "wrap X" / "use simulator X" / "add a solver" | `/viva-expert` (default bridges the REAL tool; `--lightweight` for in-workspace) |
| "is X true?" / "compare A vs B" / any research question | `/viva-study new` (group several under `/viva-investigation`) |
| "run this composite" / "what does it emit?" | `/viva-run` |
| "what's here?" / lost / just arrived | `/viva-status`, then `/viva-catalog` |

**First session, from nothing:** `/viva-workspace my-model` → `/viva-workbench start` → then ask the user to wrap a tool (`/viva-expert`) or design a study (`/viva-study`). "Model X" always means **workspace first**.

## Skill map

| Group | Skills |
|---|---|
| **Wrap & compose** | `/viva-expert` (wrap a simulator as a Process, or compose several) |
| **Workspace lifecycle** | `/viva-workspace` (scaffold), `/viva-workbench` (dashboard server), `/viva-init` (machine setup) |
| **Studies & runs** | `/viva-study` (design→build→simulate→evaluate→decide), `/viva-run`, `/viva-investigation`, `/viva-report`, `/viva-viz` |
| **Navigate & status** | `/viva-catalog`, `/viva-navigate` (read-only graph queries + "decisions needed"), `/viva-status`, `/viva-explore` |
| **Evidence & rigor** | `/viva-cite-bands`, `/viva-biology-forward`, `/viva-harden-investigation` |

Vocabulary and on-disk shapes: `docs/concepts/vivarium-workbench-model.md`. For any skill, use the **Skill** tool.

## Red flags — STOP, you're rationalizing

| Thought | Reality |
|---|---|
| "I'll just read the study YAML and edit it directly" | `/viva-study` — direct edits skip canonicalization + provenance. |
| "I'll write a quick script to run the composite" | `/viva-run` (or `/viva-study run-*`) already does this correctly. |
| "The API call is simple, I'll curl it" | The skill knows the right endpoint and the AI-free/dashboard split. |
| "I'll wrap the tool here, no workspace needed" | Wrapping into a bare dir strands the code — `/viva-workspace` first. |
| "The server's probably up, I'll start" | Verify `.pbg/server/` first, or `/viva-workbench start`. |
