# Investigation-centric structure — dashboard + pbg ecosystem restructure

**Date:** 2026-06-06
**Author:** Eran (+ Claude)
**Status:** approved design — building (user authorized build without further approval; merges still require explicit approval)
**Repos:** `pbg-template`, `pbg-superpowers`, `vivarium-workbench` (+ migration of consuming repos, e.g. `v2ecoli`)

## Goal

Reorient the dashboard and the pbg ecosystem around a **GitHub-repo + investigation**
structure. A repo holds a growing **record of all its past investigations and their
studies**; each investigation is a self-contained, preserved artifact. The dashboard's
top-left switcher selects a **repo**; an **Investigations** list shows that repo's
investigations; selecting one opens the existing investigation detail view and syncs
the left-sidebar **Studies** list to that investigation. One investigation proceeds per
branch/draft-PR; on merge to `main` the artifact is preserved and can be returned to by
subsequent investigations.

## Decisions (locked)

1. **Discovery model — "checkout = archive + current".** The Investigations list is
   whatever exists in the current checkout's `investigations/` dir. Because branches are
   cut from `main`, a `main` checkout shows *all merged investigations* (the archive); a
   feature branch shows the archive + its own in-progress investigation. No cross-branch
   reading. (Lifecycle badges come from a light "is this investigation in `main`?" check.)
2. **On-disk structure — nested, self-contained investigations.**
   `investigations/<slug>/{investigation.yaml, studies/<study>/study.yaml, …}`. A study
   belongs to exactly one investigation.
3. **Repo switching — multi-server navigation.** Each repo runs its own dashboard
   (existing `~/.pbg/servers/*.json` + `~/.pbg/workspaces.json`). The top-left switcher
   lists known repos; picking one opens/navigates to that repo's dashboard URL,
   auto-starting its server if needed. No single-server re-rooting refactor.
4. **`composites/`, `references/`, `datasets/` stay repo-level** (shared across
   investigations). **`studies/` AND `reports/` (publications) nest per-investigation** —
   each investigation carries its own publication; there is NO global repo-wide report.
5. **One spec, phased implementation** (3 PRs, ordered).

## Architecture

### On-disk structure (nested)

```
<repo>/
  workspace.yaml                      # layout: investigations root holds nested studies
  investigations/
    <inv-slug>/
      investigation.yaml              # record: lead, biology, studies[], executive, seeded_from…
      studies/
        <study-slug>/
          study.yaml                  # carries `investigation: <inv-slug>` back-ref
          charts/  runs/  feedback-*/  reports/
      reports/                        # investigation-level report (index.html etc.)
  composites/  references/  datasets/  notes/  experiments/   # repo-level, shared
  .pbg/  scripts/  tests/  pbg_<name>/
```

- A study is addressed as `investigations/<inv>/studies/<study>/`.
- `study.yaml.investigation` is the authoritative owner back-ref; `investigation.yaml.studies[]`
  remains the ordered membership list (both kept; consistency checked by the linter).
- `composites/references/datasets` resolve repo-relative as today.

### Discovery / paths

- `viva_superpowers/workspace_paths.py` (a.k.a. `paths.py`): study resolution becomes
  investigation-scoped. Add a resolver `study_dir(ws, study_slug)` that finds the study
  under its owning investigation (via `study.yaml.investigation` or by scanning
  `investigations/*/studies/<slug>/`). `studies_root` is no longer a single flat dir;
  helpers iterate `investigations/*/studies/*`.
- `workspace.yaml` `layout:` gains an explicit `investigations: investigations` (nested
  studies implied) and **drops the top-level `studies:` key**; a back-compat shim treats a
  present top-level `studies:` as the legacy flat layout (so un-migrated repos still load).
- Dashboard discovery (`server.py`) reuses `iset-list` / `iset/<name>` but resolves member
  studies under `investigations/<slug>/studies/`.
- **Reports/publications are per-investigation**: resolve at `investigations/<slug>/reports/`
  (add a `report_dir(inv_slug)` resolver in Phase 2). The legacy repo-level `reports/` (the
  workspace-wide `index.html`) is retired in favor of one publication per investigation;
  the dashboard renders the selected investigation's report, not a global one.

### Lifecycle (one investigation per branch/draft PR)

- `pbg-investigation new <slug>` → branch `<slug>` (or `investigation/<slug>`) +
  `investigations/<slug>/{investigation.yaml, studies/}` (nested scaffold).
- Work on the branch → draft PR → review → merge to `main`. The investigation dir is
  preserved in `main` as the archived artifact.
- "Return to" prior investigations: `investigation.yaml.seeded_from` references a prior
  investigation/study; the prior artifact is readable because every new branch is cut from
  `main` (which contains it). No cross-branch machinery.
- Lifecycle state for the list badges:
  - `merged · main` — the investigation dir exists in `git merge-base HEAD main`'s tree.
  - `branch · WIP` — present in the checkout but not in `main`.
  - `draft PR` / `open PR #N` — optional enhancement via `gh pr list` keyed on the branch.

### Dashboard UI (vivarium-workbench)

- **Top-left repo switcher** (replaces the investigation-level role of the current
  switcher). Data: `~/.pbg/workspaces.json` (+ live `~/.pbg/servers/*.json`). Selecting a
  repo opens its dashboard URL, auto-starting the server (reuse `viva_superpowers.dashboard`
  start logic) if no live server is registered. The existing cross-worktree/branch
  discovery stays available as a secondary affordance (Branch menu) but is no longer the
  top-left's job.
- **Menu label `Investigation` → `Investigations`**; the tab renders a **list view** of
  the checkout's investigations (cards: title, status, n_studies, lifecycle badge), backed
  by `/api/iset-list` (made nested-aware).
- **Select an investigation** → existing `_openInvestigationDetail` / `/api/iset/<name>`
  detail view; sets `window._currentIsetSlug`; the left **Studies** sidebar already filters
  to the current investigation via `_renderRailInvestigationGroups` — now resolving studies
  under the nested path. Empty-state ("select an investigation") until one is chosen.
- Static SPA assets touched: `investigation-switcher.js` (becomes repo-switcher), a new
  Investigations list render in `walkthrough.js`, menu label, study-path resolution.

### Migration

- `viva_superpowers/migrate_nested.py` (CLI `pbg-migrate-nested --workspace <ws> [--dry-run]`):
  for each `investigations/<inv>/investigation.yaml`, move each member `studies/<slug>/`
  (resolved via `studies[]` + `study.yaml.investigation`) to
  `investigations/<inv>/studies/<slug>/` with `git mv` (preserve history); rewrite
  `workspace.yaml` `layout:`; report orphan studies (no owning investigation) without
  moving them. Idempotent; safe to re-run.
- `pbg-template`: update the scaffold + `workspace.yaml` template to the nested layout.
- Consuming repos (e.g. `v2ecoli`) migrate on a branch → verify dashboard renders → merge.

## Phasing (3 PRs, in order)

1. **Structure + paths** (`pbg-template`, `pbg-superpowers`): nested template + `paths.py`
   investigation-scoped resolution + back-compat shim + `pbg-investigation` scaffold update
   + `pbg-migrate-nested` tool + tests.
2. **Dashboard** (`vivarium-workbench`): nested study resolution, repo switcher,
   Investigations list view, label change, studies sync, lifecycle badges + tests.
3. **Migrate consumers** (`v2ecoli` first): run `pbg-migrate-nested`, verify the dashboard,
   open the migration PR.

Each phase is its own PR; Phase 2 depends on Phase 1's `paths.py`; Phase 3 depends on both.

## Testing

- **paths.py**: unit tests for `study_dir` resolution (nested + legacy-flat back-compat),
  `iter studies under investigations`, layout shim.
- **migrate_nested**: fixture workspace (flat) → migrate → assert nested tree + rewritten
  layout + history preserved (`git log --follow`) + idempotency + orphan reporting.
- **dashboard**: `iset-list`/`iset/<name>` resolve nested studies; the studies-sidebar sync
  test; repo-switcher registry test; badge derivation (in-main vs branch).
- Back-compat: an un-migrated (flat) workspace still loads in both `paths.py` and the
  dashboard (the shim).

## Risks / notes

- **Back-compat is load-bearing**: many repos are still flat. The layout shim + dual-path
  resolution must keep flat workspaces working until each is migrated. Tests pin this.
- **History preservation**: migration uses `git mv` so `git log --follow` on a study
  survives the move.
- **Repo switcher auto-start**: starting a peer dashboard from the browser needs the
  workspace catalog to be populated; missing entries fall back to a "register this repo"
  affordance rather than failing silently.
- **Out of scope**: cross-branch/GitHub-API investigation discovery (rejected — checkout
  model chosen); single-server re-rooting (rejected — multi-server chosen); nesting
  composites/references/datasets (rejected — repo-level).
