"""Composite generator convention — decorator + registry.

Sibling to the *.composite.{yaml,json} static-spec convention. A composite
generator is a Python function `(core=None, **kwargs) -> dict` that builds
a process-bigraph document; the decorator records it in a module-level
registry so discovery can enumerate generators without callers having to
maintain a separate list.
"""
from __future__ import annotations

from dataclasses import dataclass
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


# Process-level registry. Populated by @composite_generator on import.
_REGISTRY: dict[str, GeneratorEntry] = {}


def composite_generator(
    *,
    name: str,
    description: str = "",
    parameters: dict[str, dict] | None = None,
) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Decorator: register a doc-building function.

    The wrapped function must accept ``(core=None, **kwargs) -> dict`` and
    return a process-bigraph state document (or a {state, schema} envelope).

    `parameters` declares each kwarg in the same shape that *.composite.yaml
    uses, so the dashboard's parameter-form code is shared across both
    conventions.
    """
    def decorate(fn: Callable[..., dict]) -> Callable[..., dict]:
        entry = GeneratorEntry(
            id=f"{fn.__module__}.{name}",
            name=name,
            description=description,
            parameters=parameters or {},
            func=fn,
            module=fn.__module__,
        )
        _REGISTRY[entry.id] = entry
        fn._composite_generator_entry = entry  # introspection sidecar
        return fn
    return decorate


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

    for mod_name in sorted(targets):
        try:
            importlib.import_module(mod_name)
        except Exception as e:  # noqa: BLE001 — skip any unimportable package
            import warnings
            warnings.warn(
                f"discover_generators: skipping {mod_name!r}: "
                f"{type(e).__name__}: {e}",
                stacklevel=2,
            )
            continue

    return dict(_REGISTRY)
