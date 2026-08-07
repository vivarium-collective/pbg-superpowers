---
name: viva-init
description: Use when setting up a machine so Claude can invoke the /viva-* skills — a one-shot per-machine install of the skills into ~/.claude/skills/.
user-invocable: true
allowed-tools: Bash(*) Read Write
argument-hint: (no args)
---

# /viva-init

> **Legacy fallback.** The supported install path is `/plugin install
> viva-superpowers` via the marketplace (see the README). This manual
> installer exists for local plugin development — editing skills in a
> working tree and symlinking them into `~/.claude/skills/` without a
> marketplace round-trip.

One-shot installer that makes every `viva-*` skill in this plugin available
to Claude in any conversation, regardless of cwd.

## When to run

Once per machine — after cloning the `viva-superpowers` plugin (or after
adding a brand-new skill that hasn't propagated yet).

## What it does

For every `skills/viva-*/SKILL.md` in this plugin:

1. If `~/.claude/skills/<name>/` already exists, compare mtimes.
   - If the plugin copy is newer **and** the existing target is a regular
     directory (not a symlink), back it up to `~/.claude/skills/<name>.bak`
     and overwrite.
   - Otherwise, leave it alone (the user might be editing it locally).
2. If the target does not exist, create a **symlink** from
   `~/.claude/skills/<name>` → the plugin's `skills/<name>` directory.
   Symlinks beat copies because future plugin updates take effect
   immediately, no re-install needed.
3. Print a summary table: `name | status (linked|kept|backed-up)` and the
   description from each SKILL.md frontmatter.

## Usage

```bash
/viva-init
```

No arguments. Idempotent — running twice is a no-op (everything stays
"kept").

## Implementation outline

```bash
#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILLS_SRC="$PLUGIN_DIR/skills"
SKILLS_DEST="$HOME/.claude/skills"
mkdir -p "$SKILLS_DEST"

printf "%-22s  %s\n" "NAME" "STATUS"
for src in "$SKILLS_SRC"/viva-*/; do
  name="$(basename "$src")"
  dest="$SKILLS_DEST/$name"
  if [ -L "$dest" ]; then
    printf "%-22s  kept (symlink)\n" "$name"
  elif [ -d "$dest" ]; then
    mv "$dest" "$dest.bak.$(date +%s)"
    ln -s "$src" "$dest"
    printf "%-22s  backed-up + linked\n" "$name"
  else
    ln -s "$src" "$dest"
    printf "%-22s  linked\n" "$name"
  fi
done
echo
echo "Installed viva-* skills:"
ls -1 "$SKILLS_DEST" | grep -E '^viva-'
```

## Verification

After running, in any Claude conversation:

```text
/viva-catalog
```

If the slash command is recognized (not "no such skill"), installation
worked. If it fails with "skill not found", the agent's skills cache may
need a refresh — restart the conversation.

## Reference

- Plugin root: the directory containing `.claude-plugin/` and `skills/`.
- Claude's per-user skill directory: `~/.claude/skills/`.
- All other `viva-*` skills read `.pbg/server/server-info` for the running
  workbench URL and POST/GET against its API — they have no other runtime
  dependency on viva-superpowers.
