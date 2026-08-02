---
name: viva-orient
description: Use when starting any viva-superpowers session or workspace task — orients you to the /viva-* skills, the workspace + workbench preconditions every skill assumes, and which skill to reach for. Auto-injected at session start; not a command to run.
---

# Orienting in a viva-superpowers workspace

viva-superpowers is a Claude Code plugin for building **process-bigraph research workspaces** — wrapping simulators as typed Processes, composing them, and running studies through the **vivarium-workbench** dashboard. The `/viva-*` skills are thin clients: they call the `viva_superpowers` Python helpers and the workbench's HTTP API. **The workbench is the backend — most skills do nothing useful without it.**

## Before touching a workspace: two preconditions

Nearly every `/viva-*` skill assumes both. Check them first; if either is missing, say so and fix it rather than guessing.

1. **A workspace** — a directory with `workspace.yaml` + a `pbg_<pkg>/` package. Don't have one? → `/viva-workspace`.
2. **The workbench running** — the dashboard server the Study/Run/Report skills read from. Skills resolve its URL from `.pbg/server/`. Not running? → `/viva-workbench start`.

Exceptions: `/viva-init` (machine setup, no workspace); `/viva-viz` and `/viva-expert` can run against files without the server.

## The Rule

**When a `/viva-*` skill fits the task, invoke it before acting** — before exploring the workspace, reading YAML, or calling the API by hand. The skills encode the workspace's conventions (canonical `study.yaml`, AI-free/dashboard split, provenance); hand-rolling around them drifts the workspace. If a skill turns out wrong for the situation, you don't have to use it.

## Skill map

| Group | Skills |
|---|---|
| **Wrap & compose** | `/viva-expert` (wrap a simulator as a Process, or compose several) |
| **Workspace lifecycle** | `/viva-workspace` (scaffold), `/viva-workbench` (start/stop the dashboard), `/viva-server` (report-mirror server), `/viva-init` (machine setup) |
| **Studies & runs** | `/viva-study` (design→build→simulate→evaluate→decide), `/viva-run` (run a composite directly), `/viva-investigation` (orchestrate member studies), `/viva-report`, `/viva-viz` |
| **Navigate & status** | `/viva-catalog` (browse/install modules), `/viva-navigate` (read-only linkage queries, "decisions needed"), `/viva-status`, `/viva-explore` |
| **Evidence & rigor** | `/viva-cite-bands` (link references to acceptance bands), `/viva-biology-forward`, `/viva-harden-investigation` |

Vocabulary and on-disk shapes: `docs/concepts/vivarium-workbench-model.md`. Full one-line catalog: `docs/skills.md`. For all other skills, use the **Skill** tool.

## Red flags — STOP

- "I'll just read the study YAML and edit it directly" → use `/viva-study`; direct edits skip canonicalization + provenance.
- "The API call is simple, I'll curl it" → the skill knows the right endpoint and the AI-free/dashboard split.
- "I'll start work, the server's probably up" → verify the two preconditions first.
