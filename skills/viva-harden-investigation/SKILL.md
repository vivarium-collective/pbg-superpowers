---
name: viva-harden-investigation
description: Use when an existing viva Investigation or Study needs to be made more rigorous, trustworthy, or defensible — a verdict that overclaims its evidence, a failing or partial report-card gate, a deferred/scaffolded study presented as a result, an unresolved decisions_needed, a single-seed/uncalibrated claim, or a reviewer asking "is this actually real?". Also triggers on "harden", "shore up", "de-risk", "stress-test", or "make rigorous" an investigation.
user-invocable: true
allowed-tools: Bash(*) Read Write Edit Glob
argument-hint: [investigation-slug]
---

# viva-harden-investigation

Take an investigation that *looks* done and make its conclusions survive scrutiny. Hardening is
not "sprinkle more seeds everywhere" — it is: **verify the source is canonical, find the one gap
that most weakens the headline claim, and close that gap the right way for its kind.**

**Two failures this skill exists to prevent** (both observed in baseline agents):
1. Diagnosing from a summary / memory / a tree you never confirmed is current. Investigation
   content drifts across branches and worktrees — a study called a "deferred scaffold" on one
   branch may have *run and passed* on `origin/main`. Trusting the wrong tree gives a wrong premise.
2. Producing an undifferentiated rigor checklist (n≥4 seeds, add stats, add provenance…) without
   first locating the *load-bearing* weakness or root-causing a real divergence. Generic rigor
   poured onto an un-diagnosed failing gate hides the signal instead of explaining it.

## Workflow

**0. Verify canonical source — before reading anything for content.**
`git fetch origin main` and confirm the tree you are about to diagnose IS current `origin/main`
(or the branch you intend). Re-derive each study's state from its actual canonical axes in
`study.yaml` — `simulation_status`, `gate_status`, `evaluation_status`, and the investigation's
`executive.verdict_status` / `decisions_needed` — **not** from a memory, a prior survey, or prose.

**1. Survey & triage — locate the load-bearing gap.**
Run `/viva-report --audit` if available (Pass A surfaces verdict↔chart drift, stale framings,
uncommitted state, suggested follow-ups); else audit the gate axes by hand. Rank
the gaps by *leverage on the headline claim* and pick the ONE that matters most. Do not enumerate;
prioritize.

**2. Classify the hardening mode — each needs different work:**

| Gap | Do this |
|-----|---------|
| Unbacked claim / deferred scaffold (`evidence_for` items are *targets*) | RUN it, measure, replace targets with real numbers |
| Passed-but-thin (single seed, one generation, uncalibrated, directional-only gate) | Re-run at scale; add seeds, statistics, tolerance bands, fitted metrics (the generic-rigor part) |
| Failing / partial report-card gate with a real divergence | **ROOT-CAUSE it first — REQUIRED: superpowers:systematic-debugging.** No fix, no added rigor, until you can state the cause. A verdict of *real & understood* (no bug) is a COMPLETE hardening: document the mechanism, resolve the decide, recommend an optional fix — do **not** force a code patch |
| Overclaimed verdict (`verdict: pass, confidence: high` on thin evidence) | Reconcile `verdict_status`/confidence to the evidence via `/viva-study set-verdicts` / `set-conclusion` |
| Open `decisions_needed` / empty followups | Resolve, or fill with concrete follow-up proposals (`/viva-study propose-followup`, `seed-from-followup`) |

**3. Look for cross-investigation leverage.** The same signature (e.g. an O₂ exchange deficit)
often weakens two investigations at once. Root-cause once; update *every* study/investigation that
cites it, including the `decisions_needed` your finding resolves.

**4. Execute in isolation, integrate carefully.** Work in a dedicated worktree off *current*
`origin/main` (REQUIRED: superpowers:using-git-worktrees); never commit in the shared checkout.
Commit deliverables early and often. Keep **run-only scaffolding out of what you land** — SUMMARY
files, env-shadow helpers, local `.gitignore`/`.deps` entries are for the run, not the canonical
branch. If the worktree needs a dependency newer than a shared venv, shadow it locally
(git-ignored) — never mutate a venv other running work depends on.

**Integrating a headless / parallel agent's branch:** its base is almost always stale (origin
moved on while it ran). A whole-branch merge — or reading `git diff origin/main..branch` — shows
**phantom reversions**: files `main` added *after* the agent branched appear deleted. Do NOT merge
wholesale. **Cherry-pick per commit** onto current `origin/main`, then verify
`git diff --stat origin/main HEAD` contains ONLY your deliverables — any unrelated deletion (CI
config, lockfile, audit allowlists) is a base-gap artifact to drop.

**5. Close the loop.** Record findings (`/viva-study findings`, `set-verdicts`), resolve/fill
`decisions_needed`, seed follow-ups, then re-run `/viva-report --audit` until the drift it flagged
is gone. A hardening is done when the report card and the verdict tell the same story as the data.

**Landing & publishing.** These repos use strict protection (`enforce_admins`, required review,
up-to-date-required). A PR you authored can't be self-approved, and with `enforce_admins` ON,
`gh pr merge --admin` is *refused* — don't thrash it. Landing needs a reviewer, or (only on the
owner's explicit say-so) a **minimal** `enforce_admins` toggle OFF → merge → **restore ON**,
verified, touching nothing else in the protection config. Strict mode serializes a batch: each
merge puts the siblings BEHIND, so `update-branch` + re-run CI between merges. After merge, the
read-only dashboard auto-publishes from `main` on `workspace/**` changes — confirm the Publish
workflow goes **green** (a triggered run ≠ a successful one).

## Red flags — STOP

- "The survey/memory says study X is a scaffold" → confirm on current `origin/main` first (step 0).
- "Let me add seeds and statistics to this failing gate" → root-cause it first (step 2).
- "Here are 11 things to improve" with no ranking → you skipped triage (step 1).
- Hardening the investigation you were handed without checking a sibling has the same defect (step 3).
- Committing in the shared `~/code/<repo>` checkout instead of a worktree (step 4).
- Merging an agent's whole branch, or trusting `diff origin/main..branch` — cherry-pick per commit and check the landed diff is deliverables-only (step 4).
- Landing an agent's `SUMMARY.md` / env-shadow helpers into the canonical branch (step 4).
- Forcing a code patch when the root cause is real, understood biology → document + resolve the decide instead (step 2).
- Re-trying `gh pr merge --admin` against `enforce_admins` — it won't bypass; get a review or an owner-authorized minimal toggle (step 5).
- Any branch-protection change beyond a minimal, restored-immediately `enforce_admins` toggle, or without explicit owner authorization (step 5).

## Real-world impact

On `v2ecoli-baseline-showcase` a survey (read off a stale branch) claimed the two foundational
studies were "deferred scaffolds" — headline unbacked. Step 0 against `origin/main` showed both had
run and passed; the real gap was a *single* failing report-card group (#143, O₂ −40% / CO₂ −20%),
which also drives the sibling `ketchup` decision. Triage + cross-investigation leverage turned
"harden the flagship" into one root-cause that hardened two investigations — verdict: real FBA
behavior + an averaging-window fragility, *not* a bug, so it closed by documenting + resolving the
decide (no forced patch). Landing it exposed the base-gap trap: the headless agent's branch diff
falsely showed `ci.yml` deleted; a per-commit cherry-pick + a deliverables-only check kept main's
newer work intact.
