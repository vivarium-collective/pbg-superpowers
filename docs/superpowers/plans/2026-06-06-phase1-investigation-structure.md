# Phase 1: Investigation-Centric Structure (paths + migration + scaffold) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pbg-superpowers resolve, scaffold, and migrate **nested self-contained investigations** (`investigations/<inv>/studies/<study>/`) while keeping legacy flat workspaces working unchanged.

**Architecture:** Add nested-aware study resolution to the layout layer (`workspace_paths.py` + the vendored copy in vivarium-workbench, kept in sync by the drift guard), expose study helpers in `paths.py`, add a `migrate_nested` tool, and update the `pbg-investigation` scaffold + `pbg-template` to emit the nested layout. Back-compat is load-bearing: a workspace with no nesting still resolves flat.

**Tech Stack:** Python 3.12, pytest, PyYAML, dataclasses, git (`git mv`).

**Spec:** `docs/superpowers/specs/2026-06-06-investigation-centric-restructure-design.md`

---

## File Structure

- `viva_superpowers/workspace_paths.py` — add `study_dir()`, `iter_study_dirs()`, `study_owner()`, nested detection. (VENDORED — mirror to vivarium-workbench in Task 6.)
- `viva_superpowers/paths.py` — expose `study_dir(slug)` CLI + import the new helpers.
- `viva_superpowers/migrate_nested.py` — NEW: flat→nested migration tool + CLI.
- `viva_superpowers/scaffold.py` — emit nested investigation scaffold.
- `tests/test_workspace_paths_nested.py` — NEW resolver tests.
- `tests/test_migrate_nested.py` — NEW migration tests.
- `vivarium-workbench/vivarium_workbench/lib/workspace_paths.py` — mirror the resolver additions (drift guard).
- pbg-template (locate via scaffold) — nested template dirs + `workspace.yaml`.

---

## Task 1: Nested study resolution in `workspace_paths.py`

**Files:**
- Modify: `viva_superpowers/workspace_paths.py`
- Test: `tests/test_workspace_paths_nested.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workspace_paths_nested.py
from pathlib import Path
from viva_superpowers.workspace_paths import WorkspacePaths

def _ws(tmp, nested: bool):
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    if nested:
        d = tmp / "investigations" / "inv-a" / "studies" / "s1"
    else:
        d = tmp / "studies" / "s1"
    d.mkdir(parents=True)
    (d / "study.yaml").write_text(
        ("investigation: inv-a\n" if nested else "") + "name: s1\n", encoding="utf-8")
    return WorkspacePaths.load(tmp)

def test_study_dir_nested(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert wp.study_dir("s1") == tmp_path / "investigations" / "inv-a" / "studies" / "s1"

def test_study_dir_flat_backcompat(tmp_path):
    wp = _ws(tmp_path, nested=False)
    assert wp.study_dir("s1") == tmp_path / "studies" / "s1"

def test_iter_study_dirs_nested(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert [p.name for p in wp.iter_study_dirs()] == ["s1"]

def test_study_owner_nested(tmp_path):
    wp = _ws(tmp_path, nested=True)
    assert wp.study_owner("s1") == "inv-a"

def test_study_owner_flat_is_none(tmp_path):
    wp = _ws(tmp_path, nested=False)
    assert wp.study_owner("s1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workspace_paths_nested.py -v`
Expected: FAIL with `AttributeError: 'WorkspacePaths' object has no attribute 'study_dir'`

- [ ] **Step 3: Add the resolver methods to `WorkspacePaths`**

Add these methods to the `WorkspacePaths` dataclass (after the existing `dir()` accessor):

```python
    def iter_study_dirs(self):
        """Yield every study dir, nested (investigations/<inv>/studies/<s>/) first,
        then flat (studies/<s>/) for legacy workspaces. A dir counts as a study iff
        it contains study.yaml."""
        seen = set()
        inv_root = self.dir("investigations")
        if inv_root.is_dir():
            for inv in sorted(p for p in inv_root.iterdir() if p.is_dir()):
                sroot = inv / "studies"
                if sroot.is_dir():
                    for s in sorted(p for p in sroot.iterdir() if p.is_dir()):
                        if (s / "study.yaml").is_file() and s.name not in seen:
                            seen.add(s.name); yield s
        flat = self.dir("studies")
        if flat.is_dir():
            for s in sorted(p for p in flat.iterdir() if p.is_dir()):
                if (s / "study.yaml").is_file() and s.name not in seen:
                    seen.add(s.name); yield s

    def study_dir(self, slug: str) -> Path:
        """Resolve a study by slug, nested-first then flat. Raises if not found."""
        for s in self.iter_study_dirs():
            if s.name == slug:
                return s
        raise FileNotFoundError(f"study {slug!r} not found under {self.root}")

    def study_owner(self, slug: str):
        """Owning investigation slug for a study (nested layout), else None."""
        import yaml as _yaml
        try:
            d = self.study_dir(slug)
        except FileNotFoundError:
            return None
        # nested path: investigations/<inv>/studies/<slug>
        parts = d.relative_to(self.root).parts
        if len(parts) >= 4 and parts[0] == self.dir("investigations").name and parts[2] == "studies":
            return parts[1]
        # fallback: study.yaml back-ref
        sy = d / "study.yaml"
        if sy.is_file():
            data = _yaml.safe_load(sy.read_text(encoding="utf-8")) or {}
            return data.get("investigation")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workspace_paths_nested.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/workspace_paths.py tests/test_workspace_paths_nested.py
git commit -m "feat(paths): nested-aware study resolution (study_dir/iter_study_dirs/study_owner) + flat back-compat"
```

---

## Task 2: Expose `study_dir` in `paths.py` CLI

**Files:**
- Modify: `viva_superpowers/paths.py`
- Test: `tests/test_workspace_paths_nested.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_paths_cli_study_dir(tmp_path, capsys):
    _ws(tmp_path, nested=True)
    from viva_superpowers.paths import _main
    rc = _main(["--study", "s1", "--workspace", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out.endswith("investigations/inv-a/studies/s1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest "tests/test_workspace_paths_nested.py::test_paths_cli_study_dir" -v`
Expected: FAIL (`--study` not a recognized arg)

- [ ] **Step 3: Add the `--study` branch to `_main`**

In `viva_superpowers/paths.py` `_main`, after the existing argparse setup add:

```python
    ap.add_argument("--study", help="resolve a study dir by slug (nested-aware)")
```

and before the existing name-resolution block:

```python
    if args.study:
        from .workspace_paths import WorkspacePaths
        wp = WorkspacePaths.load(find_workspace_root(args.workspace) if args.workspace else workspace_root())
        print(wp.study_dir(args.study))
        return 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest "tests/test_workspace_paths_nested.py::test_paths_cli_study_dir" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/paths.py tests/test_workspace_paths_nested.py
git commit -m "feat(paths): viva_superpowers.paths --study resolves a study dir nested-aware"
```

---

## Task 3: Migration tool `migrate_nested.py` — discovery + dry-run

**Files:**
- Create: `viva_superpowers/migrate_nested.py`
- Test: `tests/test_migrate_nested.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_nested.py
from pathlib import Path
import subprocess
from viva_superpowers.migrate_nested import plan_migration

def _flat_ws(tmp):
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    (tmp / "workspace.yaml").write_text("name: demo\n", encoding="utf-8")
    inv = tmp / "investigations" / "inv-a"; inv.mkdir(parents=True)
    (inv / "investigation.yaml").write_text(
        "name: inv-a\nstudies:\n  - s1\n  - s2\n", encoding="utf-8")
    for s in ("s1", "s2"):
        d = tmp / "studies" / s; d.mkdir(parents=True)
        (d / "study.yaml").write_text(f"name: {s}\ninvestigation: inv-a\n", encoding="utf-8")
    # an orphan study not owned by any investigation
    d = tmp / "studies" / "orphan"; d.mkdir(parents=True)
    (d / "study.yaml").write_text("name: orphan\n", encoding="utf-8")
    return tmp

def test_plan_maps_studies_to_owning_investigation(tmp_path):
    ws = _flat_ws(tmp_path)
    plan = plan_migration(ws)
    moves = {m["slug"]: m["dest"] for m in plan["moves"]}
    assert moves["s1"].endswith("investigations/inv-a/studies/s1")
    assert moves["s2"].endswith("investigations/inv-a/studies/s2")
    assert "orphan" in [o["slug"] for o in plan["orphans"]]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_migrate_nested.py -v`
Expected: FAIL (`No module named viva_superpowers.migrate_nested`)

- [ ] **Step 3: Implement `plan_migration`**

```python
# viva_superpowers/migrate_nested.py
"""Migrate a workspace from flat studies/ to nested investigations/<inv>/studies/.

Maps each flat studies/<slug>/ to its owning investigation (investigation.yaml
studies[] ∪ study.yaml `investigation:` back-ref), moves with `git mv` to preserve
history, rewrites workspace.yaml layout. Studies with no owner are reported as
orphans and left in place. Idempotent.

CLI: python -m viva_superpowers.migrate_nested --workspace <ws> [--dry-run]
"""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
import yaml
from .workspace_paths import WorkspacePaths


def _owner_map(wp: WorkspacePaths) -> dict[str, str]:
    """study slug -> investigation slug from investigation.yaml studies[] + back-refs."""
    out: dict[str, str] = {}
    inv_root = wp.dir("investigations")
    if inv_root.is_dir():
        for invf in sorted(inv_root.glob("*/investigation.yaml")):
            inv = yaml.safe_load(invf.read_text(encoding="utf-8")) or {}
            islug = inv.get("name") or invf.parent.name
            for s in (inv.get("studies") or []):
                slug = s if isinstance(s, str) else (s or {}).get("study")
                if slug:
                    out.setdefault(slug, islug)
    flat = wp.dir("studies")
    if flat.is_dir():
        for sy in sorted(flat.glob("*/study.yaml")):
            data = yaml.safe_load(sy.read_text(encoding="utf-8")) or {}
            inv = data.get("investigation")
            if inv:
                out.setdefault(sy.parent.name, inv)
    return out


def plan_migration(workspace: Path) -> dict:
    wp = WorkspacePaths.load(workspace)
    owners = _owner_map(wp)
    flat = wp.dir("studies")
    moves, orphans = [], []
    if flat.is_dir():
        for s in sorted(p for p in flat.iterdir() if p.is_dir()):
            if not (s / "study.yaml").is_file():
                continue
            inv = owners.get(s.name)
            if inv:
                dest = wp.dir("investigations") / inv / "studies" / s.name
                moves.append({"slug": s.name, "src": str(s), "dest": str(dest), "investigation": inv})
            else:
                orphans.append({"slug": s.name, "src": str(s)})
    return {"workspace": str(workspace), "moves": moves, "orphans": orphans}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_migrate_nested.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/migrate_nested.py tests/test_migrate_nested.py
git commit -m "feat(migrate): plan_migration maps flat studies to owning investigation + orphan report"
```

---

## Task 4: Migration tool — apply with `git mv` + layout rewrite + idempotency

**Files:**
- Modify: `viva_superpowers/migrate_nested.py`
- Test: `tests/test_migrate_nested.py` (append)

- [ ] **Step 1: Write the failing test**

```python
from viva_superpowers.migrate_nested import migrate

def test_migrate_moves_and_is_idempotent(tmp_path):
    ws = _flat_ws(tmp_path)
    res = migrate(ws)
    assert (ws / "investigations" / "inv-a" / "studies" / "s1" / "study.yaml").is_file()
    assert not (ws / "studies" / "s1").exists()
    assert (ws / "studies" / "orphan").exists()        # orphan left in place
    layout = (yaml.safe_load((ws / "workspace.yaml").read_text()) or {}).get("layout", {})
    assert "studies" not in layout                      # top-level studies key dropped
    res2 = migrate(ws)                                  # idempotent
    assert res2["moves"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest "tests/test_migrate_nested.py::test_migrate_moves_and_is_idempotent" -v`
Expected: FAIL (`cannot import name 'migrate'`)

- [ ] **Step 3: Implement `migrate` + `main`**

Append to `migrate_nested.py`:

```python
def _git_mv(src: Path, dest: Path, ws: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "mv", str(src), str(dest)], cwd=ws, capture_output=True, text=True)
    if r.returncode != 0:  # not tracked / not a git repo → plain move
        src.replace(dest)


def _rewrite_layout(ws: Path) -> None:
    f = ws / "workspace.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    layout = data.get("layout") or {}
    layout.pop("studies", None)                 # nested-implied; drop flat key
    layout["investigations"] = layout.get("investigations", "investigations")
    data["layout"] = layout
    f.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def migrate(workspace: Path, *, dry_run: bool = False) -> dict:
    workspace = Path(workspace)
    plan = plan_migration(workspace)
    if dry_run:
        return plan
    for m in plan["moves"]:
        _git_mv(Path(m["src"]), Path(m["dest"]), workspace)
    if plan["moves"]:
        _rewrite_layout(workspace)
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    res = migrate(Path(args.workspace), dry_run=args.dry_run)
    print(f"moves: {len(res['moves'])} | orphans: {len(res['orphans'])}")
    for m in res["moves"]:
        print(f"  {m['slug']} -> investigations/{m['investigation']}/studies/{m['slug']}")
    for o in res["orphans"]:
        print(f"  ORPHAN (left in place): {o['slug']}")
    if args.dry_run:
        print("(dry-run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `_owner_map` is called inside `plan_migration`; after a real migration the flat
`studies/` no longer has the moved dirs, so a re-run yields `moves == []` (idempotent).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_migrate_nested.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viva_superpowers/migrate_nested.py tests/test_migrate_nested.py
git commit -m "feat(migrate): apply migration with git mv + layout rewrite; idempotent"
```

---

## Task 5: Console-script entry for the migration tool

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the entry**

In `[project.scripts]` (next to `pbg-backfill-runs`/`pbg-scaffold`):

```toml
pbg-migrate-nested = "viva_superpowers.migrate_nested:main"
```

- [ ] **Step 2: Verify it resolves**

Run: `.venv/bin/python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print('pbg-migrate-nested' in d['project']['scripts'])"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: pbg-migrate-nested console script"
```

---

## Task 6: Mirror the resolver to the vendored canonical copy (drift guard)

**Files:**
- Modify: `vivarium-workbench/vivarium_workbench/lib/workspace_paths.py`

- [ ] **Step 1: Check the drift guard**

Run: `cd ~/code/pbg-superpowers && .venv/bin/python -m pytest tests/test_workspace_paths.py -v`
Expected: PASS today (copies in sync for `LAYOUT_DEFAULTS`). Read the guard to see exactly what it compares (it may compare only `LAYOUT_DEFAULTS`, in which case the new methods don't trip it — confirm).

- [ ] **Step 2: Add the same three methods** (`iter_study_dirs`, `study_dir`, `study_owner`) verbatim from Task 1 to the `WorkspacePaths` class in `vivarium-workbench/vivarium_workbench/lib/workspace_paths.py`.

- [ ] **Step 3: Verify both import + guard passes**

Run: `cd ~/code/pbg-superpowers && .venv/bin/python -m pytest tests/test_workspace_paths.py tests/test_workspace_paths_nested.py -v`
Expected: PASS

- [ ] **Step 4: Commit (in vivarium-workbench repo, on a Phase-1 branch there)**

```bash
cd ~/code/vivarium-workbench && git checkout -b feat/nested-study-resolution origin/main
git add vivarium_workbench/lib/workspace_paths.py
git commit -m "feat(paths): mirror nested study resolver (sync with pbg-superpowers vendored copy)"
```

---

## Task 7: Scaffold nested investigations (`scaffold.py`) + pbg-template

**Files:**
- Modify: `viva_superpowers/scaffold.py` (and `tests/test_workspace_scaffold*.py` expectations)
- Modify: pbg-template (locate the template root referenced by scaffold)

- [ ] **Step 1: Locate the template + read scaffold's investigation/study creation**

Run: `grep -rn "investigations" viva_superpowers/scaffold.py | head` and find where it writes `investigations/<slug>/` and `studies/<slug>/`. Identify the pbg-template path it copies from.

- [ ] **Step 2: Write/extend the failing test** — scaffold a new study under an investigation and assert it lands at `investigations/<inv>/studies/<study>/study.yaml` with `investigation: <inv>` back-ref. (Mirror the style of `tests/test_workspace_scaffold.py`; reuse its tmp-workspace fixture.)

- [ ] **Step 3: Run to verify it fails.** Expected: study created at the old flat `studies/<slug>/`.

- [ ] **Step 4: Update `scaffold.py`** so new studies are created under their investigation (`wp.dir("investigations")/<inv>/studies/<slug>/`), writing the `investigation:` back-ref into `study.yaml`. Update the pbg-template `workspace.yaml` to the nested `layout:` (drop top-level `studies:`).

- [ ] **Step 5: Run the scaffold tests.** Run: `.venv/bin/python -m pytest tests/test_workspace_scaffold.py tests/test_workspace_scaffold_snapshot.py -v` and update the snapshot/manifest to the nested layout. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add viva_superpowers/scaffold.py tests/test_workspace_scaffold*.py
git commit -m "feat(scaffold): create studies nested under their investigation (+ back-ref); nested template"
```

---

## Task 8: Phase-1 green + push (no merge)

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: the new tests pass; the 4 pre-existing failures (`test_expert_search`, `test_workspace_scaffold*`, `test_workspace_schema_sync`) are either fixed by Task 7's snapshot update or unchanged-pre-existing — document which.

- [ ] **Step 2: Push both branches (NO merge — awaiting explicit approval)**

```bash
cd ~/code/pbg-superpowers && git push origin feat/investigation-centric-structure
cd ~/code/vivarium-workbench && git push origin feat/nested-study-resolution
```

- [ ] **Step 3: Open draft PRs** referencing the spec; summarize the nested resolver, migration tool, and scaffold; note Phase 2 (dashboard) + Phase 3 (migrate v2ecoli) follow.

---

## Self-Review

- **Spec coverage:** nested structure (Task 1,7) ✓; checkout-discovery (resolver is checkout-local — Task 1) ✓; paths resolution + shim (Task 1,2) ✓; migration tool (Task 3,4,5) ✓; scaffold/template (Task 7) ✓; vendored-copy sync (Task 6) ✓. Dashboard UI + lifecycle badges + repo switcher = **Phase 2 plan** (out of this plan, by design). Migrate v2ecoli = **Phase 3**.
- **Placeholders:** Tasks 1–5 carry full code; Tasks 6–7 reference verbatim code from Task 1 / existing test fixtures (acceptable — locating template + snapshot values must be done against the live repo).
- **Type consistency:** `study_dir`/`iter_study_dirs`/`study_owner` signatures identical across Tasks 1, 2, 6. `plan_migration`/`migrate`/`_owner_map` consistent across Tasks 3–4.
