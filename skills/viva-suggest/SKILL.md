---
name: viva-suggest
description: Internal dashboard callback — invoked by the vivarium-workbench "Suggest" button to draft a repo name, PR title, or PR body in response to a request file. Not part of the user-facing catalog; do not invoke directly. The dashboard prints the exact `/viva-suggest <id>` to run when needed.
user-invocable: false
argument-hint: <request-id>
---

# /viva-suggest <request-id>

> **Internal callback skill.** This is not part of the v0.9 user-facing
> catalog. It exists because the vivarium-workbench "Suggest" button asks
> the user to paste `/viva-suggest <id>` into Claude Code — the dashboard
> wrote a request file at `.pbg/agent-requests/<id>.json` and is polling
> `.pbg/agent-responses/<id>.json` for the answer.
>
> Do not advertise this skill in docs or invoke it manually. It stays
> registered only so the dashboard callback works.

Read `.pbg/agent-requests/<request-id>.json` from the current workspace. The file contains:
- `kind`: one of `repo-name`, `pr-title`, `pr-body`
- `context`: workspace name, description, active branch, recent commits

Generate a value appropriate for the kind. Write the result to `.pbg/agent-responses/<request-id>.json` with:

```json
{"suggestion": "the value", "rationale": "one-line why"}
```

## Per-kind guidance

### repo-name

Generate a GitHub repo name (kebab-case, no spaces, matches `[A-Za-z0-9._-]+`). Base it on workspace_name. If the workspace is for a research project, the repo name should mirror the project name (e.g. workspace `chromosome-rep1` → repo `chromosome-rep1`). Keep under 50 chars.

### pr-title

Summarize the workstream's commits in a single line under 70 chars. Use imperative voice ("Add observable cell_mass" not "Added"). Reflect the unifying theme of all commits, not just the last one. Format: a short, scannable title that a co-worker reading the PR list would understand at a glance.

### pr-body

Write a markdown PR body in this structure:

```markdown
## Summary

[2-4 bullet points covering what the workstream does]

## Test plan

- [ ] Lint passes: `python scripts/lint-workspace.py`
- [ ] Dashboard renders without errors
- [other relevant checks based on the commits]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Tailor the bullets to the commits — e.g., if commits added datasets, mention "Loads <N> new datasets"; if they touched processes, mention "Wires up <process_name>".

## Constraints

- The response file MUST be written to `.pbg/agent-responses/<request-id>.json`
- The response file MUST contain valid JSON with at minimum a `suggestion` field
- Don't modify the request file
- Don't commit anything — the dashboard handles git via the active-branch workstream
- If the request file doesn't exist, report it and abort
- If `kind` is something other than the three above, abort with a clear message
