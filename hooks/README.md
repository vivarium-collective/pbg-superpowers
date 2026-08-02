# hooks/

Plugin hooks for viva-superpowers.

## SessionStart → viva-orient gateway

`hooks.json` registers a `SessionStart` hook (on `startup|clear|compact`) that
runs `session-start` via the cross-platform `run-hook.cmd` wrapper. The script
reads `skills/viva-orient/SKILL.md` and injects it as session context, so every
session opens already oriented to the `/viva-*` skills and the two workspace +
workbench preconditions — no manual skill invocation needed.

| File | Role |
|---|---|
| `hooks.json` | Registers the SessionStart hook (auto-discovered by Claude Code; no `plugin.json` entry needed). |
| `run-hook.cmd` | Polyglot Unix/Windows wrapper that locates bash and runs the named hook script. |
| `session-start` | Reads `viva-orient` and emits the platform-appropriate context-injection JSON. |

The mechanism mirrors the upstream [obra/superpowers](https://github.com/obra/superpowers)
`using-superpowers` gateway. To change what every session sees, edit
`skills/viva-orient/SKILL.md` — the hook picks it up on the next session.
