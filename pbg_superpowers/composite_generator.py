"""Composite generator convention — decorator + registry.

Sibling to the *.composite.{yaml,json} static-spec convention. A composite
generator is a Python function `(core=None, **kwargs) -> dict` that builds
a process-bigraph document; the decorator records it in a module-level
registry so discovery can enumerate generators without callers having to
maintain a separate list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class GeneratorEntry:
    """One registered composite-generator function."""

    id: str                           # "<dotted_module>.<name>"
    name: str
    description: str
    parameters: dict[str, dict]       # {name: {type, default, description?}}
    func: Callable[..., dict]
    module: str
    default_n_steps: int | None = None  # framework-owned runtime knob; UI pre-fill
    # Canonical visualizations that ship with this composite. Each entry is
    # a Study-spec visualization dict ({name, address, config, ...}). When
    # a Study is built on top of this composite the dashboard merges these
    # defaults into its visualizations list; Studies can still declare extras.
    visualizations: list[dict] = field(default_factory=list)
    # Emitter(s) this composite ships as its default observation sink. Each
    # entry is a lightweight ``{address, config, paths?}`` dict: ``address`` is
    # the registered emitter link (e.g. ``"local:ParquetEmitter"``), ``config``
    # is the base config the workspace merges into the emitter step, and the
    # optional ``paths`` lists dotted observable store-paths to wire. Unlike a
    # full process-node spec, the emit-schema + topology are left for the
    # generator/runner to compute — this declaration only selects which
    # emitter(s) to install and with what base config. Parallel to
    # ``visualizations``: when present, a workspace that builds this composite
    # standalone (no dashboard observable-injection) uses these as its default
    # emitter set, so e.g. a parquet sink travels with the generator instead of
    # being toggled by external override globals. See ``emitter_defaults``.
    emitters: list[dict] = field(default_factory=list)
    # Callables ``(core) -> core | None`` that register the custom types /
    # processes this generator's document references but that a bare
    # ``build_core()`` doesn't know about. v2ecoli friction #16 (2026-05-19):
    # the dashboard runs each composite in a subprocess that calls the
    # workspace's ``build_core()``; when a composite uses types registered by
    # a *different* package (e.g. ``map[pymunk_agent]`` from ``viva_munk``),
    # the subprocess core never gets those registrations and the Composite
    # build dies with "cannot resolve types … pymunk_agent". Declaring the
    # package's ``register_*`` functions here lets the runner apply them to
    # the right core. See ``apply_core_extensions``.
    core_extensions: list[Callable[[Any], Any]] = field(default_factory=list)


# Process-level registry. Populated by @composite_generator on import.
_REGISTRY: dict[str, GeneratorEntry] = {}


def composite_generator(
    *,
    name: str,
    description: str = "",
    parameters: dict[str, dict] | None = None,
    visualizations: list[dict] | None = None,
    emitters: list[dict] | None = None,
    default_n_steps: int | None = None,
    core_extensions: list[Callable[[Any], Any]] | None = None,
) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Decorator: register a doc-building function.

    The wrapped function must accept ``(core=None, **kwargs) -> dict`` and
    return a process-bigraph state document (or a {state, schema} envelope).

    `parameters` declares each kwarg in the same shape that *.composite.yaml
    uses, so the dashboard's parameter-form code is shared across both
    conventions.

    `visualizations` declares the canonical visualization set that ships with
    this composite. Each entry is a Study-spec visualization dict
    (``{name, address, config, ...}``). The dashboard merges these defaults
    into a Study's visualizations list when the Study is built on this
    composite, so callers get the v2ecoli simulation report (or whatever the
    composite author considers canonical) without having to hand-author them
    in every Study spec.

    `emitters` (optional) declares the default observation sink(s) this
    composite ships with. Each entry is a lightweight
    ``{"address": "local:ParquetEmitter", "config": {...}, "paths": [...]}``
    dict — ``address`` selects the registered emitter link, ``config`` is the
    base config merged into the emitter step, and the optional ``paths`` lists
    dotted observable store-paths to wire. The emit-schema and topology are
    NOT part of this declaration; the generator/runner computes them. This is
    the standalone analogue of the dashboard's run-time observable injection:
    when a workspace builds the composite outside the Investigations flow, it
    reads these defaults (via :func:`emitter_defaults`) so the composite still
    has a sink. External override mechanisms a workspace may keep (e.g.
    v2ecoli's ``set_parquet_emitter_override``) take precedence; the declared
    default fills in when none is set. Example::

        @composite_generator(
            name="baseline",
            emitters=[{
                "address": "local:ParquetEmitter",
                "config": {"out_dir": "out/parquet"},
            }],
        )
        def baseline(core=None): ...

    `default_n_steps` (optional) is a UI hint for the Composite Explorer's
    ``steps`` pre-fill. It is NOT a composite-builder kwarg — runtime knobs
    are framework-owned and live next to the generator entry.

    `core_extensions` (optional) is a list of callables ``(core) -> core | None``
    that register the custom types/processes this generator's document
    references but that a bare ``build_core()`` doesn't provide. Declare a
    package's ``register_*`` functions here so the dashboard's subprocess
    runner can apply them to the core it actually runs against — see
    ``apply_core_extensions`` and v2ecoli friction #16. Example::

        from viva_munk import register_pymunk_types, register_processes

        @composite_generator(
            name="attachment",
            core_extensions=[register_pymunk_types, register_processes],
        )
        def attachment(core=None): ...
    """
    validated_emitters = _validate_emitters(emitters, name)

    def decorate(fn: Callable[..., dict]) -> Callable[..., dict]:
        entry = GeneratorEntry(
            id=f"{fn.__module__}.{name}",
            name=name,
            description=description,
            parameters=parameters or {},
            visualizations=list(visualizations or []),
            emitters=validated_emitters,
            func=fn,
            module=fn.__module__,
            default_n_steps=default_n_steps,
            core_extensions=list(core_extensions or []),
        )
        _REGISTRY[entry.id] = entry
        fn._composite_generator_entry = entry  # introspection sidecar
        return fn
    return decorate


def _validate_emitters(emitters: list[dict] | None, name: str) -> list[dict]:
    """Normalise + sanity-check the decorator's ``emitters`` declaration.

    Each entry must be a dict with a non-empty string ``address``. ``config``,
    when present, must be a dict; ``paths``, when present, must be a list of
    strings. We validate at decoration time (not first use) so a malformed
    declaration fails loudly on import — the same place a bad ``parameters``
    block would. Returns a fresh list of copied dicts so later mutation of the
    caller's literal can't leak into the registry.
    """
    out: list[dict] = []
    for i, em in enumerate(emitters or []):
        where = f"{name!r} emitters[{i}]"
        if not isinstance(em, dict):
            raise ValueError(f"{where}: each emitter must be a dict, got {type(em).__name__}")
        address = em.get("address")
        if not isinstance(address, str) or not address:
            raise ValueError(f"{where}: 'address' must be a non-empty string")
        config = em.get("config", {})
        if not isinstance(config, dict):
            raise ValueError(f"{where}: 'config' must be a dict")
        paths = em.get("paths")
        if paths is not None and not (
            isinstance(paths, list) and all(isinstance(p, str) for p in paths)
        ):
            raise ValueError(f"{where}: 'paths' must be a list of strings")
        out.append(dict(em))
    return out


def emitter_defaults(fn_or_entry: Any) -> list[dict]:
    """Return the declared default emitter(s) for a generator.

    Accepts either a decorated generator function (reads its
    ``_composite_generator_entry`` sidecar) or a :class:`GeneratorEntry`.
    Returns the (possibly empty) ``emitters`` list — a workspace builds the
    composite's default sink from this when it isn't running under the
    dashboard's observable-injection flow. Returns ``[]`` for anything that
    isn't a registered generator, so callers can use it unconditionally.
    """
    entry = getattr(fn_or_entry, "_composite_generator_entry", fn_or_entry)
    return list(getattr(entry, "emitters", []) or [])


def apply_core_extensions(entry: GeneratorEntry, core: Any) -> Any:
    """Run ``entry.core_extensions`` against ``core``; return the final core.

    Each extension is a callable ``(core) -> core | None`` that registers
    custom types/processes (e.g. ``viva_munk.register_pymunk_types``). By the
    ``register_types`` convention an extension may return a (possibly new)
    core; when it returns ``None`` we keep the one we passed in.

    Failures are **not** swallowed. A missing registration is exactly the
    kind of silent gap v2ecoli friction #16 is about — letting the exception
    propagate surfaces it (with the offending function name) instead of
    deferring to a cryptic "cannot resolve types" error at Composite-build
    time.
    """
    for ext in entry.core_extensions or []:
        result = ext(core)
        if result is not None:
            core = result
    return core


def build_generator(
    entry: GeneratorEntry,
    overrides: dict[str, Any] | None = None,
    core: Any = None,
) -> dict:
    """Call the wrapped function with merged defaults + overrides.

    Unknown override keys raise ValueError so dashboards / callers can't
    silently smuggle in parameters that the generator doesn't declare.
    """
    overrides = overrides or {}
    unknown = set(overrides) - set(entry.parameters)
    if unknown:
        raise ValueError(
            f"unknown parameter(s) for {entry.id}: {sorted(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    for pname, pdecl in entry.parameters.items():
        if pname in overrides:
            kwargs[pname] = overrides[pname]
        elif "default" in pdecl:
            kwargs[pname] = pdecl["default"]
    return entry.func(core=core, **kwargs)


def discover_generators(
    extra_packages: list[str] | None = None,
) -> dict[str, GeneratorEntry]:
    """Discover composite generators from installed packages.

    Walks every installed distribution that depends on `bigraph-schema`,
    imports each top-level package so its `@composite_generator` decorators
    fire, then returns whatever ended up in `_REGISTRY`.

    Unlike `discover_composites` (file-glob; imports only to resolve
    package paths, not to run decorator side-effects), this MUST import
    the host packages so the decorators fire. Subsequent calls return the
    same registry; there is no automatic invalidation. Hot-reload callers
    can `_REGISTRY.clear()` before re-importing.
    """
    import importlib
    import importlib.metadata as md

    extra_packages = extra_packages or []
    targets: set[str] = set(extra_packages)

    for dist in md.distributions():
        deps = dist.requires or []
        if not any("bigraph-schema" in (d or "") for d in deps):
            continue
        # Find the importable top-level packages for this distribution.
        # Prefer top_level.txt when present (wheel installs); fall back to
        # the normalised package name (hyphens → underscores) for editable
        # installs built with hatchling / PEP 660, which omit top_level.txt.
        top_level_txt = dist.read_text("top_level.txt") or ""
        mods_from_txt = [
            line.strip()
            for line in top_level_txt.splitlines()
            if line.strip() and not line.strip().startswith("_")
        ]
        if mods_from_txt:
            targets.update(mods_from_txt)
        else:
            dist_name = dist.metadata.get("Name") or ""
            fallback = dist_name.replace("-", "_")
            if fallback and not fallback.startswith("_"):
                targets.add(fallback)

    import pkgutil
    import warnings

    for mod_name in sorted(targets):
        try:
            top = importlib.import_module(mod_name)
        except Exception as e:  # noqa: BLE001 — skip any unimportable package
            warnings.warn(
                f"discover_generators: skipping {mod_name!r}: "
                f"{type(e).__name__}: {e}",
                stacklevel=2,
            )
            continue
        # mem3dg-readdy friction #22: @composite_generator decorators
        # only fire when their containing module is imported. Importing
        # the top-level package alone misses subpackages like
        # `pbg_<ws>/composites/__init__.py` unless the top-level
        # __init__.py eagerly does `from . import composites`. Walk the
        # subpackage tree so workspaces don't have to remember.
        pkg_path = getattr(top, "__path__", None)
        if not pkg_path:
            continue  # single-file module — nothing to walk
        # pkgutil.walk_packages imports each subpackage during descent;
        # without `onerror`, any subpackage that raises at top level
        # (e.g. ecoli.analysis.antibiotics_colony's data-file probe)
        # would abort the whole walk. Swallow + warn via the same path
        # the per-import try/except below uses.
        def _walk_onerror(name, _e=None):
            warnings.warn(
                f"discover_generators: skipping subpackage {name!r} "
                f"(walk failed during import)",
                stacklevel=2,
            )
        for finder, sub_name, is_pkg in pkgutil.walk_packages(
            pkg_path, prefix=mod_name + ".", onerror=_walk_onerror,
        ):
            # v2ecoli friction #4: skip subpaths that look like CLI scripts
            # (e.g. `<pkg>.scripts.compare_runs`). Discovery should walk the
            # library, not the CLI tool layer — and CLI scripts commonly
            # have module-level `sys.exit()` / argparse / etc. that crash
            # under import.
            tail = sub_name.split(".")
            if any(seg == "scripts" for seg in tail):
                continue
            try:
                importlib.import_module(sub_name)
            except SystemExit as e:  # noqa: BLE001
                # `sys.exit(N)` at module level is NOT a subclass of
                # Exception; without this branch it would propagate out of
                # discover_generators and crash the dashboard. v2ecoli's
                # `scripts/compare-runs.py` had a top-level sys.exit(0)
                # that took the whole subprocess down before this catch.
                warnings.warn(
                    f"discover_generators: subpackage {sub_name!r} called "
                    f"sys.exit({e.code!r}) at import time; skipping. "
                    "Wrap top-level CLI logic in `if __name__ == \"__main__\":`.",
                    stacklevel=2,
                )
            except Exception as e:  # noqa: BLE001
                warnings.warn(
                    f"discover_generators: skipping subpackage {sub_name!r}: "
                    f"{type(e).__name__}: {e}",
                    stacklevel=2,
                )

    return dict(_REGISTRY)
