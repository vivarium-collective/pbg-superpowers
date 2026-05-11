"""Composite spec format: a declarative, JSON-able description of a composite.

A composite spec lives in a *.composite.yaml or *.composite.json file inside
any installed bigraph-schema-dependent package. It declares the composite's
state document plus optional parameters that callers can override.

This is the data-first counterpart to process-bigraph's class-based discovery:
processes are CODE (subclasses of Edge), but composites are DATA (declarative
state documents). Discovering them by file glob avoids running arbitrary
Python at discovery time and makes them easy to inspect, diff, render, and
version-control.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def load_spec(path: Path) -> dict:
    """Parse a composite spec file (YAML or JSON). Returns the spec dict."""
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    # default to YAML for .yaml / .yml / anything else
    return yaml.safe_load(text)


def validate_spec(spec: dict) -> None:
    """Raise ValueError if the spec doesn't match the convention.

    Required: name (str), state (dict)
    Optional: description, requires, parameters
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("spec.name is required (non-empty string)")
    state = spec.get("state")
    if not isinstance(state, dict):
        raise ValueError("spec.state is required (dict)")

    params = spec.get("parameters") or {}
    if not isinstance(params, dict):
        raise ValueError("spec.parameters must be a dict if present")
    for pname, pdef in params.items():
        if not isinstance(pdef, dict):
            raise ValueError(f"parameter '{pname}' must be a dict")
        if "type" in pdef and pdef["type"] not in ("float", "int", "string", "str", "bool"):
            raise ValueError(f"parameter '{pname}': type must be one of float|int|string|bool")

    requires = spec.get("requires") or {}
    if requires and not isinstance(requires, dict):
        raise ValueError("spec.requires must be a dict if present")


# ---------------------------------------------------------------------------
# Parameter substitution
# ---------------------------------------------------------------------------

_FULL_PLACEHOLDER = re.compile(r"^\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}$")
_INLINE_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _cast(value: Any, declared_type: str | None) -> Any:
    """Cast a raw parameter value to the declared type."""
    if declared_type is None:
        return value
    if declared_type == "float":
        return float(value)
    if declared_type == "int":
        return int(value)
    if declared_type in ("string", "str"):
        return str(value)
    if declared_type == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    return value


def _resolve_value(value: Any, params: dict[str, dict], overrides: dict[str, Any]) -> Any:
    """Walk a leaf value; substitute ${name} placeholders."""
    if not isinstance(value, str):
        return value

    # Full-string placeholder: substitute with typed value
    m = _FULL_PLACEHOLDER.match(value)
    if m:
        pname = m.group(1)
        if pname not in params:
            raise KeyError(f"parameter '{pname}' referenced in state but not declared in spec.parameters")
        pdef = params[pname]
        raw = overrides.get(pname, pdef.get("default"))
        if raw is None and "default" not in pdef:
            raise KeyError(f"parameter '{pname}' has no default and no override provided")
        return _cast(raw, pdef.get("type"))

    # Inline placeholders: string interpolation
    if _INLINE_PLACEHOLDER.search(value):
        def repl(match: re.Match) -> str:
            pname = match.group(1)
            if pname not in params:
                raise KeyError(f"parameter '{pname}' referenced in state but not declared in spec.parameters")
            pdef = params[pname]
            raw = overrides.get(pname, pdef.get("default"))
            return str(raw)
        return _INLINE_PLACEHOLDER.sub(repl, value)

    return value


def substitute_parameters(state: Any, params: dict[str, dict], overrides: dict[str, Any] | None = None) -> Any:
    """Recursively walk a state structure, substituting ${name} placeholders.

    Returns a new structure; does not mutate the input.
    """
    overrides = overrides or {}
    if isinstance(state, dict):
        return {k: substitute_parameters(v, params, overrides) for k, v in state.items()}
    if isinstance(state, list):
        return [substitute_parameters(v, params, overrides) for v in state]
    return _resolve_value(state, params, overrides)


# ---------------------------------------------------------------------------
# Composite construction
# ---------------------------------------------------------------------------

def build_composite_from_spec(spec: dict, overrides: dict[str, Any] | None = None, core=None):
    """Construct a process_bigraph.Composite from a parsed spec.

    overrides: optional dict of parameter overrides (keys match spec.parameters).
    core:      optional Core; if None, calls allocate_core().
    """
    validate_spec(spec)
    from process_bigraph import Composite, allocate_core

    if core is None:
        core = allocate_core()

    # Pre-flight: verify requires.processes are in the registry.
    requires = spec.get("requires") or {}
    proc_required = requires.get("processes") or []
    link_registry = getattr(core, "link_registry", {}) or {}
    missing = [p for p in proc_required if p not in link_registry]
    if missing:
        raise RuntimeError(
            f"composite spec '{spec.get('name')}' requires processes not in registry: {missing}. "
            f"Install the package(s) that provide them."
        )

    params = spec.get("parameters") or {}
    state = substitute_parameters(spec.get("state") or {}, params, overrides)
    return Composite({"state": state}, core=core)
