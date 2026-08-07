# Pass-A Audit Reviewer Prompt Template

Use this template when dispatching a Pass-A reviewer-readiness audit as a
subagent, one per investigation, instead of running Pass A inline in the
coordinating agent. Model: obra/superpowers' `requesting-code-review` —
"reviewing the diff inline burns the context window — dispatch a reviewer
subagent; only the findings come back." Here the "diff" is one investigation's
YAML + charts + git state, and the reviewer is a fresh-eyes subagent scoped to
exactly that investigation.

**Purpose:** Run the Pass-A audit (checks A1–A8 from `viva-report`'s
`SKILL.md`) against a single investigation and report findings back, without
the coordinator having to read every `investigation.yaml`, chart
`meta.json`, and git-log entry itself.

```
Subagent (general-purpose):
  description: "Pass-A audit: [INVESTIGATION_SLUG]"
  prompt: |
    You are auditing ONE investigation for reviewer-readiness, as Pass A of
    the /viva-report skill. You have fresh eyes — you have not seen any other
    part of this session. Read what you need directly; do not assume context.

    ## Investigation to audit

    Slug: [INVESTIGATION_SLUG]
    Path: $INVESTIGATIONS_DIR/[INVESTIGATION_SLUG]/investigation.yaml

    (Resolve $INVESTIGATIONS_DIR yourself first, from the workspace root, the
    same way /viva-report does:
    `eval "$(python -m viva_superpowers.paths --env --workspace [WORKSPACE_ROOT])"`.)

    ## What to run

    Run the full A1–A8 checklist from `skills/viva-report/SKILL.md`'s "Pass A
    — Reviewer-readiness audit" section, scoped to this one investigation and
    its member studies only:

    - A1 Branch state (uncommitted changes touching this investigation's
      studies/investigation.yaml; commits ahead of origin/main)
    - A2 Executive-verdict freshness (chart mtimes vs investigation.yaml mtime)
    - A3 Chart-reference integrity (missing files; demoted-but-still-cited
      charts)
    - A3b Superseded-run chart hygiene (multiple runs'/seeds' files coexisting
      in a study's charts/ dir)
    - A4 Numerical-claim consistency (verdict text vs chart-meta values)
    - A5 Decisions_needed audit
    - A6 Suggested follow-ups (mine preliminary_findings, open_questions,
      mass-listener gaps, stale review-thread topics, non-`completed` run
      outcomes / `env_stale` / `nondeterministic` provenance flags)
    - A8 Propose new visualizations (>=2 per investigation; build the cheap
      ones now per the SKILL.md initiative rule, note what you built)

    Read `skills/viva-report/SKILL.md` itself for the exact check definitions,
    thresholds, and severities — do not improvise the checklist from memory.

    ## Read-only reviewer discipline

    Your audit is read-only on this checkout, with ONE narrow exception
    matching Pass A's own carve-out: you may add a new chart FILE (plus its
    generator entry) if an A8 proposal is cheap and buildable now — never edit
    or delete an existing chart, verdict, or YAML field, and never touch
    `workspace.yaml`, `decisions.yaml`, or any study's `status`/verdict
    fields. Beyond that: do not mutate the working tree, the index, HEAD, or
    branch state in any way. Use read-only commands (`git status`, `git log`,
    `git diff`, `find`, `stat`, `curl -s GET ...`) to inspect state. Never
    move HEAD on this checkout, never `git add`/`git commit` on the
    coordinator's behalf, never stash. An audit that mutates the workspace
    mid-render is a real hazard — the coordinator (or another parallel
    reviewer auditing a sibling investigation) may be reading the same tree
    concurrently.

    ## What comes back

    The investigation's YAML, its studies' charts and meta.json files, and
    the git log you inspect all live in YOUR context only — do not paste them
    back verbatim. Return ONLY the findings, in the Pass-A output format from
    SKILL.md's A7 section:

    ```
    == Pass A: reviewer-readiness audit — [INVESTIGATION_SLUG] ==
      blocking:  <N> findings
      warning:   <N> findings
      info:      <N> findings

    Findings (severity, scope, message, suggested fix):
      [blocking|warning|info] <check>: <message + exact path/line + suggested fix>
      ...

    Suggested follow-ups before sending to reviewer:
      1. <title> — <one-line evidence change> — <effort>
      ...

    Proposed visualizations (>=2; A8):
      1. <title + form> — sharpens <finding> — from <data source> — <effort>
      ...
      Built this pass: <list any cheap ones you drew on the spot, with paths>
    ```

    Keep it to findings only — do not restate the investigation's narrative,
    its full verdict text, or its study list. The coordinator already knows
    what the investigation is about; it needs to know what's wrong with it.
```

**Placeholders:**
- `[INVESTIGATION_SLUG]` — the investigation directory name under
  `$INVESTIGATIONS_DIR`
- `[WORKSPACE_ROOT]` — the workspace root the coordinator resolved

**Reviewer returns:** the A7-format findings block above for this one
investigation — severity counts, findings, suggested follow-ups, proposed
visualizations (and what it built). Nothing else comes back to the
coordinator's context.

## Dispatching one per investigation, in parallel

For a multi-investigation workspace, fill this template once per investigation
slug and dispatch all of them in the same response via
`superpowers:dispatching-parallel-agents` — each reviewer only touches its own
investigation's files, so there is no shared-state conflict between them (the
one exception, an A8-built chart file, only ever adds a new file under that
investigation's own study, never touches another investigation's tree).
Collect each reviewer's findings block and concatenate them under `== Pass A:
reviewer-readiness audit ==` before proceeding to Pass B, exactly as if Pass A
had run inline.
