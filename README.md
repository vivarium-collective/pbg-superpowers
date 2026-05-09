# pbg-superpowers

A Claude Code plugin for building process-bigraph research projects:
scaffold a workspace, walk a canonical PR flow, plan and execute
multi-phase model extensions, and produce interactive HTML reports.

## Install

(inside Claude Code:)

    /plugin install pbg-superpowers
    /reload-plugins

## Quick start

    /pbg-workspace my-research-workspace
    /pbg-add-model ecoli-replication
    ...

The workspace template is the separate `pbg-template` repo, which
`/pbg-workspace` clones automatically. You can also use it directly via
GitHub's "Use this template" flow without installing this plugin.

See `docs/superpowers/specs/` for design.
