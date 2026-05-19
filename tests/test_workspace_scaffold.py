import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


PBG_TEMPLATE = Path(os.environ.get("PBG_TEMPLATE", "~/code/pbg-template")).expanduser().resolve()


@pytest.fixture(autouse=True)
def _check_template_exists():
    if not PBG_TEMPLATE.is_dir():
        pytest.skip(f"pbg-template not found at {PBG_TEMPLATE} (set up Task 9 first)")


def _scaffold(tmp_path, plugin_root, name="demo-ws"):
    target = tmp_path / name
    subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", name, "--target", str(target),
         "--template-source", str(PBG_TEMPLATE)],
        check=True, cwd=plugin_root,
    )
    return target


def test_scaffold_creates_expected_files(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root)
    must_exist = [
        "workspace.yaml",
        "pyproject.toml",
        "README.md",
        ".gitignore",
        ".claude/settings.json",
        "docs/decisions.yaml",
        "references/papers.bib",
        "references/claims.yaml",
        "experiments/_runs.yaml",
        "reports/index.html",
        "scripts/lint-workspace.py",
        ".pbg/schemas/workspace.schema.json",
    ]
    for p in must_exist:
        assert (target / p).exists(), f"missing: {p}"

    # template-init.sh should have self-deleted
    assert not (target / "template-init.sh").exists()
    # init-time .j2 files should have been rendered (and removed); the dashboard's
    # runtime templates under scripts/_templates/ are intentionally preserved.
    leftover_j2 = [p for p in target.rglob("*.j2") if "scripts/_templates" not in str(p)]
    assert not leftover_j2, f"unexpected .j2 leftovers: {leftover_j2}"
    # .git from the source should have been stripped
    assert not (target / ".git").exists()


def test_scaffold_workspace_yaml_validates(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root, name="my-research")
    ws = yaml.safe_load((target / "workspace.yaml").read_text())
    assert ws["name"] == "my-research"
    assert ws["schema_version"] == 2
    assert ws["plugin_version"] == "0.4.16"


def test_scaffold_does_not_leak_template_dev_infra(tmp_path, plugin_root):
    """Regression: pbg-template's own dev infra must never appear in a workspace."""
    target = _scaffold(tmp_path, plugin_root)
    must_not_exist = [
        "tests",                          # pbg-template's own pytest suite
        "docs/superpowers",               # pbg-template's design docs
        ".superpowers/brainstorm",        # transient session cruft
        "use-this-template-init.sh",      # GitHub-flow entry point, plugin path skips it
        "template",                       # subdir name itself
    ]
    for p in must_not_exist:
        assert not (target / p).exists(), f"leaked dev infra: {p}"


def test_lint_passes_on_freshly_scaffolded(tmp_path, plugin_root):
    target = _scaffold(tmp_path, plugin_root)
    r = subprocess.run(
        [sys.executable, "scripts/lint-workspace.py"],
        cwd=target, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"lint failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "OK" in r.stdout


# ---------------------------------------------------------------------------
# Slice A — in-place workspace promotion (mem3dg-readdy friction §1+§3+§4)
# ---------------------------------------------------------------------------


def _make_existing_composite_repo(tmp_path: Path, name: str = "pbg-demo-composite") -> Path:
    """Build a fake 'existing composite repo' that mirrors the shape of
    pbg-mem3dg / pbg-membrane-actin-composite: pyproject + README +
    package dir + git history. The kind of repo --in-place promotes."""
    repo = tmp_path / name
    repo.mkdir()
    (repo / "README.md").write_text("# pbg-demo-composite\n\nExisting repo.\n")
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        'name = "pbg-demo-composite"\n'
        'version = "0.1.0"\n'
        "dependencies = [\n"
        '    "process-bigraph",\n'  # already present; should not be re-added
        '    "numpy",\n'             # foreign dep; should be preserved
        "]\n"
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
    )
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n.venv/\n")
    pkg = repo / "pbg_demo_composite"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""pre-existing package"""\n')
    # git init + initial commit
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
                    "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
                    "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def _run_inplace(repo: Path, plugin_root: Path, name: str = "demo-composite",
                 extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke `scaffold workspace --in-place`. Returns the process result so
    tests can assert on exit code + stdout."""
    env = dict(os.environ)
    # Always route through a tmp HOME so the workspace_catalog.add side-effect
    # doesn't poison the developer's real ~/.pbg/.
    env["HOME"] = str(repo.parent / "_home")
    (repo.parent / "_home" / ".pbg").mkdir(parents=True, exist_ok=True)
    # Overriding HOME hides the developer's ~/.gitconfig from the git subprocess
    # the scaffolder spawns to commit the bootstrap. Production runs have a real
    # git config; the test has to inject one or commits fail with "unable to
    # auto-detect email address". GIT_AUTHOR_* and GIT_COMMITTER_* are the
    # contract-stable way to do this without writing a fake ~/.gitconfig.
    env.setdefault("GIT_AUTHOR_NAME", "scaffold-test")
    env.setdefault("GIT_AUTHOR_EMAIL", "scaffold-test@example.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "scaffold-test")
    env.setdefault("GIT_COMMITTER_EMAIL", "scaffold-test@example.invalid")
    # Make sure auto-pin doesn't accidentally find a sibling dashboard checkout
    # via the default ../vivarium-dashboard path (the test repo's parent is tmp).
    env.pop("VIVARIUM_DASHBOARD_PATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "pbg_superpowers.scaffold", "workspace",
         "--name", name, "--target", str(repo),
         "--template-source", str(PBG_TEMPLATE),
         "--in-place"],
        cwd=plugin_root, env=env, capture_output=True, text=True,
    )


def test_inplace_promotes_existing_composite_repo(tmp_path, plugin_root):
    """Happy path: existing composite repo gets workspace.yaml, the template
    tree files (notes/, references/, etc.), and a workspace branch."""
    repo = _make_existing_composite_repo(tmp_path)
    r = _run_inplace(repo, plugin_root)
    assert r.returncode == 0, (
        f"--in-place failed:\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    )

    # Workspace marker landed.
    assert (repo / "workspace.yaml").is_file()
    # Template-shipped trees landed.
    for sub in ("notes", "references", "scripts", ".pbg"):
        assert (repo / sub).is_dir(), f"missing template dir: {sub}"
    # The notes convention from F6 ships through too.
    assert (repo / "notes" / "README.md").is_file()
    # Existing files preserved (NOT clobbered).
    assert "Existing repo" in (repo / "README.md").read_text()
    # .j2 files should all be rendered away.
    leftover = list(repo.rglob("*.j2"))
    leftover_outside_scripts = [p for p in leftover if "scripts/" not in str(p)]
    assert not leftover_outside_scripts, (
        f"unrendered .j2 files: {leftover_outside_scripts}"
    )


def test_inplace_preserves_existing_pyproject_and_merges_deps(tmp_path, plugin_root):
    """The existing repo's pyproject must keep its own dependencies
    (numpy) AND gain the template's missing ones (vivarium-dashboard,
    pyyaml, jsonschema, etc.). process-bigraph is in both — must not
    be duplicated."""
    repo = _make_existing_composite_repo(tmp_path)
    r = _run_inplace(repo, plugin_root)
    assert r.returncode == 0, r.stderr

    text = (repo / "pyproject.toml").read_text()
    # Existing foreign dep preserved.
    assert '"numpy"' in text
    # Template deps added.
    assert "vivarium-dashboard" in text
    assert "pyyaml" in text or "PyYAML" in text
    # process-bigraph appears exactly once (no duplicate).
    assert text.count('"process-bigraph"') == 1


def test_inplace_merges_gitignore_without_duplicates(tmp_path, plugin_root):
    """Existing .gitignore entries must stay; template entries must be
    appended; already-present lines must not be duplicated."""
    repo = _make_existing_composite_repo(tmp_path)
    r = _run_inplace(repo, plugin_root)
    assert r.returncode == 0, r.stderr

    text = (repo / ".gitignore").read_text()
    # Existing entries preserved.
    assert "__pycache__/" in text
    assert ".venv/" in text
    # Template entries appended.
    assert ".pbg/server/" in text
    assert "investigations/*/runs.db" in text
    # No duplicates (one of the easy ones to check).
    assert text.count(".venv/") == 1


def test_inplace_creates_workspace_branch(tmp_path, plugin_root):
    """A new git branch named <repo>-workspace (or --branch <name>) gets
    created with a single bootstrap commit. The original main is intact."""
    repo = _make_existing_composite_repo(tmp_path)
    r = _run_inplace(repo, plugin_root)
    assert r.returncode == 0, r.stderr

    current = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--show-current"], text=True).strip()
    assert current.endswith("-workspace"), f"expected workspace branch, got {current}"
    # The bootstrap commit message names the scaffolder.
    last_msg = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--pretty=%B"], text=True)
    assert "workspace bootstrap" in last_msg


def test_inplace_refuses_when_workspace_yaml_already_present(tmp_path, plugin_root):
    """Pre-existing workspace.yaml means the repo is already a workspace —
    don't overlay (would silently merge two pyprojects, two .gitignores)."""
    repo = _make_existing_composite_repo(tmp_path)
    (repo / "workspace.yaml").write_text("name: existing\n")
    r = _run_inplace(repo, plugin_root)
    assert r.returncode != 0
    assert "already has workspace.yaml" in (r.stderr + r.stdout)


def test_inplace_refuses_non_git_directory(tmp_path, plugin_root):
    """Without .git/, the commit step can't run — refuse early with a
    clear error rather than partial-init the workspace."""
    repo = tmp_path / "no-git"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    r = _run_inplace(repo, plugin_root)
    assert r.returncode != 0
    assert "not a git repo" in (r.stderr + r.stdout)


def test_inplace_autopin_pings_sibling_vivarium_dashboard(tmp_path, plugin_root):
    """When a sibling ../vivarium-dashboard exists, the in-place scaffolder
    appends a [tool.uv.sources] block so `uv pip install` resolves the
    dep without further user action (friction #6)."""
    sibling = tmp_path / "vivarium-dashboard"
    sibling.mkdir()
    (sibling / "pyproject.toml").write_text("[project]\nname='vivarium-dashboard'\nversion='0'\n")
    repo = _make_existing_composite_repo(tmp_path)
    r = _run_inplace(repo, plugin_root,
                     extra_env={"VIVARIUM_DASHBOARD_PATH": str(sibling)})
    assert r.returncode == 0, r.stderr

    text = (repo / "pyproject.toml").read_text()
    assert "[tool.uv.sources]" in text
    assert "vivarium-dashboard" in text
    assert str(sibling) in text


def test_inplace_keeps_existing_package_dir(tmp_path, plugin_root):
    """The composite's pbg_<slug>/ already has its own code — the
    scaffolder must NOT clobber __init__.py. (The default package name is
    derived from --name, so for this test we explicitly pass --package to
    point at the existing dir.)"""
    repo = _make_existing_composite_repo(tmp_path)
    original = (repo / "pbg_demo_composite" / "__init__.py").read_text()
    # default --name 'demo-composite' would yield pbg_demo_composite — same as
    # the existing dir, so the scaffolder should NOT touch it.
    r = _run_inplace(repo, plugin_root)
    assert r.returncode == 0, r.stderr
    assert (repo / "pbg_demo_composite" / "__init__.py").read_text() == original
