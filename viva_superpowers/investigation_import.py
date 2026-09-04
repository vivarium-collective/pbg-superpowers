"""Select which investigations an importing workspace carries from an upstream repo.

A workspace that imports another repo as a dependency (e.g. sms-ecoli importing
v2ecoli) often carries a **subset** of that repo's investigations under its own
investigations dir — seeded from upstream, then hand-maintained. This module makes
that selection explicit and enforceable, so a new upstream investigation does not
silently flow in.

Selection lives in ``workspace.yaml``:

  imported_investigations:   allowlist of upstream investigation slugs to carry
  native_investigations:     investigations authored in THIS workspace

Two accepted shapes for ``imported_investigations``:

    # minimal — guard only (no sync source):
    imported_investigations:
      - colonies
      - metabolism-overflow

    # full — guard + additive sync:
    imported_investigations:
      from: v2ecoli                                 # uv.lock package whose pinned rev is the source
      git: https://github.com/vivarium-collective/v2ecoli.git
      subtree: workspace/investigations             # where investigations live upstream (default)
      allow:
        - colonies
        - metabolism-overflow

    native_investigations:
      - cd1-review-comparison

Two operations:

  * ``check(ws_root)`` — conformance guard. Every investigation present on disk must
    be declared (``imported ∪ native``) and the two lists must be disjoint. A stray
    upstream investigation (one deliberately left off the allowlist) fails here. Wire
    it into CI via ``assert_selection_ok`` (a two-line pytest) or the ``check`` CLI.
  * ``sync(ws_root)`` — additive import. Copy any allowlisted investigation that is
    **missing** locally from the **pinned** upstream rev, never overwriting a local
    (divergent) copy. Only allowlisted slugs are ever pulled; the source is the exact
    commit pinned in ``uv.lock`` (not upstream ``main``), so the import is reproducible.

Excluding a future upstream investigation is then just: leave it off the allowlist;
``check`` keeps it out for good.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import find_workspace_root

DEFAULT_SUBTREE = "workspace/investigations"


# ---------------------------------------------------------------------------
# Selection model
# ---------------------------------------------------------------------------


@dataclass
class Source:
    """Where allowlisted investigations are imported from (for ``sync``)."""

    package: str | None = None  # uv.lock package name whose pinned rev is the source
    git: str | None = None      # git URL (used to fetch/clone when no local checkout)
    subtree: str = DEFAULT_SUBTREE  # dir under the upstream repo holding investigations

    @property
    def rev_token(self) -> str | None:
        """The token to anchor the uv.lock rev search on (package or git basename)."""
        if self.package:
            return self.package
        if self.git:
            return self.git.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        return None


@dataclass
class Selection:
    allow: list[str] = field(default_factory=list)   # imported allowlist
    native: list[str] = field(default_factory=list)  # authored-here
    source: Source | None = None

    @property
    def declared(self) -> set[str]:
        return set(self.allow) | set(self.native)


@dataclass
class Problem:
    severity: str  # "error"
    message: str


@dataclass
class SyncResult:
    rev: str
    allow: list[str]
    already_local: list[str]
    added: list[str]
    missing_upstream: list[str]
    dry_run: bool


# ---------------------------------------------------------------------------
# Reading the selection
# ---------------------------------------------------------------------------


def load_selection(ws_root: Path) -> Selection:
    """Parse ``imported_investigations`` / ``native_investigations`` from workspace.yaml."""
    data = yaml.safe_load((ws_root / "workspace.yaml").read_text(encoding="utf-8")) or {}
    imported = data.get("imported_investigations")
    native = list(data.get("native_investigations") or [])

    allow: list[str] = []
    source: Source | None = None
    if isinstance(imported, list):
        allow = [str(s) for s in imported]
    elif isinstance(imported, dict):
        allow = [str(s) for s in (imported.get("allow") or [])]
        source = Source(
            package=imported.get("from"),
            git=imported.get("git"),
            subtree=str(imported.get("subtree") or DEFAULT_SUBTREE),
        )
    elif imported is not None:
        raise ValueError(
            "workspace.yaml: `imported_investigations` must be a list of slugs or a "
            "mapping with an `allow:` list."
        )
    return Selection(allow=allow, native=[str(s) for s in native], source=source)


def investigations_dir(ws_root: Path) -> Path:
    """The workspace's investigations directory, honoring the ``layout:`` override.

    Kept dependency-light on purpose (reads ``layout.investigations`` from
    workspace.yaml directly, defaulting to the flat ``investigations/``), so the
    guard runs in an importing repo's CI without the full workspace_paths stack.
    """
    data = yaml.safe_load((ws_root / "workspace.yaml").read_text(encoding="utf-8")) or {}
    rel = ((data.get("layout") or {}).get("investigations")) or "investigations"
    return ws_root / rel


def present_slugs(ws_root: Path) -> set[str]:
    """Investigation slugs present on disk (layout-aware investigations dir)."""
    inv = investigations_dir(ws_root)
    if not inv.is_dir():
        return set()
    return {p.name for p in inv.iterdir() if (p / "investigation.yaml").is_file()}


# ---------------------------------------------------------------------------
# check — the conformance guard
# ---------------------------------------------------------------------------


def check(ws_root: Path) -> list[Problem]:
    """Return conformance problems for the workspace's investigation selection.

    Empty list == conformant. Problems (all error-severity):
      * an investigation present on disk that is in neither list (undeclared);
      * a slug in both `imported_investigations` and `native_investigations`.
    """
    sel = load_selection(ws_root)
    problems: list[Problem] = []

    overlap = sorted(set(sel.allow) & set(sel.native))
    if overlap:
        problems.append(
            Problem(
                "error",
                f"investigation(s) declared BOTH imported and native: {overlap} — each "
                "is either imported from upstream or authored here, not both.",
            )
        )

    undeclared = sorted(present_slugs(ws_root) - sel.declared)
    if undeclared:
        problems.append(
            Problem(
                "error",
                f"undeclared investigation(s) present under {DEFAULT_SUBTREE}/: "
                f"{undeclared}. Add each to `imported_investigations` (if pulled from "
                "upstream) or `native_investigations` (if authored here) in "
                "workspace.yaml — or remove it. This guard is what keeps a "
                "deliberately-excluded upstream investigation from silently appearing.",
            )
        )
    return problems


def assert_selection_ok(ws_root: Path | str) -> None:
    """Raise AssertionError if the workspace's investigation selection is non-conformant.

    Intended for a two-line guard test in an importing workspace::

        from viva_superpowers.investigation_import import assert_selection_ok
        def test_investigation_selection():
            assert_selection_ok(WORKSPACE_ROOT)
    """
    problems = check(Path(ws_root))
    if problems:
        raise AssertionError("\n".join(p.message for p in problems))


# ---------------------------------------------------------------------------
# sync — additive import from the pinned upstream rev
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def pinned_rev(ws_root: Path, token: str) -> str | None:
    """Extract the pinned commit for ``token`` from uv.lock.

    Matches ``…<token>.git?...#<40-hex>`` — the git-source form uv writes for both the
    inline and the ``[[package]] source = { git = … }`` layouts.
    """
    lock = ws_root / "uv.lock"
    if not lock.is_file():
        return None
    m = re.search(
        re.escape(token) + r"\.git[^#\"]*#([0-9a-f]{40})",
        lock.read_text(encoding="utf-8"),
    )
    return m.group(1) if m else None


def _ensure_source(rev: str, *, git: str | None, src: Path | None, cache_key: str) -> Path:
    """Return a git checkout that has ``rev`` available (for ``git archive``)."""
    if src is not None:
        src = src.expanduser().resolve()
        if not (src / ".git").exists():
            raise RuntimeError(f"--upstream-src {src} is not a git checkout")
        try:
            _git("cat-file", "-e", f"{rev}^{{commit}}", cwd=src)
        except RuntimeError:
            _git("fetch", "origin", rev, cwd=src)
        return src
    if not git:
        raise RuntimeError(
            "no upstream git URL to clone from — declare `imported_investigations.git` "
            "in workspace.yaml or pass --upstream-src PATH."
        )
    cache = Path.home() / ".cache" / "viva-superpowers" / "investigation-import" / cache_key
    if not (cache / ".git").exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--filter=blob:none", git, str(cache))
    try:
        _git("cat-file", "-e", f"{rev}^{{commit}}", cwd=cache)
    except RuntimeError:
        _git("fetch", "origin", rev, cwd=cache)
    return cache


def _upstream_slugs(src: Path, rev: str, subtree: str) -> set[str]:
    out = _git("ls-tree", "-d", "--name-only", rev, f"{subtree}/", cwd=src)
    return {Path(line).name for line in out.splitlines() if line.strip()}


def _copy_investigation(src: Path, rev: str, slug: str, subtree: str, dest_dir: Path) -> None:
    """Extract ``<subtree>/<slug>`` at ``rev`` into ``dest_dir/<slug>``."""
    with tempfile.TemporaryDirectory() as td:
        tar_path = Path(td) / "inv.tar"
        with open(tar_path, "wb") as fh:
            subprocess.run(
                ["git", "archive", rev, f"{subtree}/{slug}"],
                cwd=src, check=True, stdout=fh,
            )
        with tarfile.open(tar_path) as tf:
            tf.extractall(td)  # yields <td>/<subtree>/<slug>/...
        shutil.copytree(Path(td) / subtree / slug, dest_dir / slug)


def sync(
    ws_root: Path,
    *,
    dry_run: bool = False,
    upstream_src: Path | None = None,
    rev: str | None = None,
) -> SyncResult:
    """Additively import allowlisted investigations missing locally, from the pinned rev.

    Never overwrites a local copy; only allowlisted slugs are pulled.
    """
    sel = load_selection(ws_root)
    if sel.source is None:
        raise RuntimeError(
            "workspace.yaml `imported_investigations` is a plain list (guard-only). Add a "
            "`from:`/`git:` source block to enable sync — see investigation_import docstring."
        )
    token = sel.source.rev_token
    rev = rev or (pinned_rev(ws_root, token) if token else None)
    if not rev:
        raise RuntimeError(
            "could not resolve the pinned upstream rev from uv.lock "
            f"(token={token!r}); pass rev= explicitly."
        )

    subtree = sel.source.subtree
    cache_key = token or "upstream"
    src = _ensure_source(rev, git=sel.source.git, src=upstream_src, cache_key=cache_key)
    upstream = _upstream_slugs(src, rev, subtree)
    have = present_slugs(ws_root)

    already_local = sorted(set(sel.allow) & have)
    missing_upstream = [s for s in sel.allow if s not in upstream]
    to_add = [s for s in sel.allow if s not in have and s in upstream]

    if to_add and not dry_run:
        inv_dir = investigations_dir(ws_root)
        inv_dir.mkdir(parents=True, exist_ok=True)
        for slug in to_add:
            _copy_investigation(src, rev, slug, subtree, inv_dir)

    return SyncResult(
        rev=rev,
        allow=list(sel.allow),
        already_local=already_local,
        added=to_add,
        missing_upstream=missing_upstream,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# CLI: python -m viva_superpowers.investigation_import {check,sync}
# ---------------------------------------------------------------------------


def _resolve_ws(ws_arg: str | None) -> Path:
    if ws_arg:
        root = Path(ws_arg).resolve()
        if not (root / "workspace.yaml").is_file():
            sys.exit(f"no workspace.yaml under {root}")
        return root
    return find_workspace_root(Path.cwd())


def _cmd_check(args) -> int:
    ws_root = _resolve_ws(args.ws)
    problems = check(ws_root)
    sel = load_selection(ws_root)
    print(f"imported (allow): {len(sel.allow)}   native: {len(sel.native)}   "
          f"present: {len(present_slugs(ws_root))}")
    if not problems:
        print("OK — every investigation is declared; lists are disjoint.")
        return 0
    for p in problems:
        print(f"[{p.severity}] {p.message}")
    return 1


def _cmd_sync(args) -> int:
    ws_root = _resolve_ws(args.ws)
    res = sync(
        ws_root,
        dry_run=args.dry_run,
        upstream_src=args.upstream_src,
        rev=args.rev,
    )
    print(f"upstream rev:   {res.rev[:12]}")
    print(f"allowlist:      {len(res.allow)} slug(s)")
    print(f"already local:  {res.already_local}")
    if res.missing_upstream:
        print(f"WARN: allowlisted but NOT in upstream@{res.rev[:12]}: {res.missing_upstream}")
    if not res.added:
        print("nothing to add — every allowlisted investigation is already present.")
        return 0
    print(f"to add (additive): {res.added}")
    if res.dry_run:
        print("(dry-run — nothing copied)")
    else:
        for slug in res.added:
            print(f"  + {slug}")
        print(f"added {len(res.added)} investigation(s). (existing copies left untouched)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m viva_superpowers.investigation_import",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--ws", "--workspace", dest="ws", default=None,
                   help="workspace root (default: walk up from CWD).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="guard: every present investigation must be declared.")
    pc.set_defaults(func=_cmd_check)

    ps = sub.add_parser("sync", help="additively import missing allowlisted investigations.")
    ps.add_argument("--dry-run", action="store_true", help="print what would be added; copy nothing.")
    ps.add_argument("--upstream-src", type=Path, default=None,
                    help="use an existing local upstream checkout instead of a cache clone.")
    ps.add_argument("--rev", default=None, help="override the rev (default: pinned in uv.lock).")
    ps.set_defaults(func=_cmd_sync)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
