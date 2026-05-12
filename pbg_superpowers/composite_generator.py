"""Composite generator convention — decorator + registry.

Sibling to the *.composite.{yaml,json} static-spec convention. A composite
generator is a Python function `(core=None, **kwargs) -> dict` that builds
a process-bigraph document; the decorator records it in a module-level
registry so discovery can enumerate generators without callers having to
maintain a separate list.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
