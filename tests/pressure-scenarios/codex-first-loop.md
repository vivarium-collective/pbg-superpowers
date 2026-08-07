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

### 2026-08-07 — PROXY run (NOT real Codex)

Run by a Claude subagent constrained to Codex-like conditions (only `AGENTS.md` +
reading `SKILL.md` files + shell; no Skill tool / slash commands / superpowers).
This checks whether the docs are **self-sufficient**; it does not substitute for a
real Codex session (still TODO).

- **Gateway honored?** ✅ Yes. `AGENTS.md`'s routing table forced workspace-first
  (no bare script). Opened `viva-workspace`, `viva-workbench`, `viva-catalog`,
  `viva-run` SKILL.md in order.
- **Idiom map sufficient?** ✅ For what it hit (ignored `allowed-tools`, read files
  instead of a Skill tool). The dispatch/`superpowers:` mappings weren't exercised
  (none of those 4 skills use them).
- **Loop outcome:** ✅ full loop reached — workspace scaffolded + committed,
  dashboard served, `spatio-flux` installed, composite ran 5 steps and emitted real
  observables (`{glucose, biomass, acetate}`).
- **Stalls it had to route around by reading source (→ now fixed in this PR):**
  1. `viva-run` + `viva-catalog` one-liners had `\"` inside f-strings → hard
     `SyntaxError` on copy-paste (all harnesses). **Fixed.**
  2. `viva-run` documented `/api/composite-test-run` as synchronous; it's
     **detached** (`202 {run_id}` → poll `/api/composite-run/<id>/status` → read
     `.pbg/runs/<id>/observables.json`). Following the old doc → silent "0
     observables". **Fixed.**
  3. Fresh scaffold ships zero composites, and after `catalog-install` the manifest
     needs a **server restart** before composites appear. **Noted in viva-catalog.**
- **Outcome:** **PASS** (docs self-sufficient once the 2 real bugs above are fixed).
  Real-Codex run still pending.

## Failure modes to watch (from the scope's risks)

- Gateway not honored because `AGENTS.md` wasn't loaded → the "softer off Claude"
  risk; note whether Codex read it unprompted.
- Skill body's "use the Skill tool" / dispatch phrasing confuses the agent → the
  idiom map needs a clearer entry.
- `superpowers:` reference hit with the plugin absent → confirm the inline fallback
  wording was enough.
