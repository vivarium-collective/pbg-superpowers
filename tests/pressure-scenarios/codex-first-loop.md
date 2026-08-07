# Acceptance: drive the first loop from Codex

**Goal (the spike's one proof):** a **Codex** session takes a newcomer through
`/viva-workspace` → `/viva-workbench start` → `/viva-run` end-to-end, using only
`AGENTS.md` as the gateway and `pip install viva-superpowers` — no Claude Code
machinery. This is a behavioral acceptance (run it in a real Codex session), not a
pytest.

## Setup

1. Fresh scratch directory, empty except a checkout of (or path to) this repo so
   Codex can read `AGENTS.md` and `skills/<name>/SKILL.md`.
2. `pip install viva-superpowers` (and `vivarium-workbench`).
3. Start Codex pointed at the directory.

## Prompt

> Set me up a viva-superpowers workspace called `demo`, start the dashboard, and
> run a composite from the catalog for a few steps so I can see what it emits.

## Expected agent behavior (what "pass" looks like)

1. **Reads `AGENTS.md`** and follows the Rule — does NOT start writing a bare
   script. Routes on state: no `workspace.yaml` → `/viva-workspace` first.
2. Opens `skills/viva-workspace/SKILL.md`, translates any Claude idiom via
   `references/codex-tools.md` (ignores `allowed-tools`, reads the file instead of
   "using the Skill tool"), and scaffolds `demo` with the `viva-scaffold` CLI.
3. Opens `skills/viva-workbench/SKILL.md`, starts the server, reads
   `.pbg/server/server-info` for the URL.
4. Opens `skills/viva-run/SKILL.md`, runs a composite for N steps, reports the
   emitted observables.

## Record the result here (fill in when run)

- Date / Codex version:
- Did it honor the gateway (workspace-first, no bare script)? y/n + notes:
- Which SKILL.md files did it open, and did the idiom map suffice? notes:
- Where did it stumble (gateway not auto-loaded? idiom gap? dispatch phrasing?):
- Outcome: **PASS / FAIL**, and the one fix the spike surfaced:

## Failure modes to watch (from the scope's risks)

- Gateway not honored because `AGENTS.md` wasn't loaded → the "softer off Claude"
  risk; note whether Codex read it unprompted.
- Skill body's "use the Skill tool" / dispatch phrasing confuses the agent → the
  idiom map needs a clearer entry.
- `superpowers:` reference hit with the plugin absent → confirm the inline fallback
  wording was enough.
