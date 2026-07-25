---
name: pbg-dashboard
description: DEPRECATED ALIAS for /pbg-workbench. The interactive vivarium-workbench server manager was renamed dashboard→workbench. Use /pbg-workbench. Subcommands (unchanged) start, stop, status, open, restart.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: start|stop|status|open|restart [--port N] [--browser] [--investigation SLUG]
---

# pbg-dashboard  →  renamed to `/pbg-workbench`

This skill was renamed **`/pbg-dashboard` → `/pbg-workbench`** to match the
product name (the `vivarium-workbench` pip package; "dashboard" is legacy).

**Use [`/pbg-workbench`](../pbg-workbench/SKILL.md)** — read that skill and follow
it. It documents the same `start` / `stop` / `status` / `open` / `restart`
subcommands, plus the **session-per-tab** model (one workspace per browser tab via
the workspace switcher) that this alias's page predates.

This alias stays functional for back-compat. The backing CLI is unchanged and
available under both module names:

```bash
python -m viva_superpowers.workbench start   # preferred
python -m viva_superpowers.dashboard start   # back-compat alias (identical)
```

Nothing else here — do not maintain launch details in two places. All guidance
lives in `/pbg-workbench`.
