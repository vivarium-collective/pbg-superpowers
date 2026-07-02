"""parameter_validation.py — structure introspection + author-time parameter
validation.

The parameter-side analog of ``readout_validation`` (which validates authored
*observables/readouts* against a built composite).  Here we validate a study
variant's ``parameter_overrides`` against the composite's declared parameters,
so an agent can NEVER persist ``{"nonexistent_param": 3}`` silently.

Two public functions:

    available_parameters(spec, core=None, state=None, schema=None) -> dict
        Enumerate the parameters that are actually *settable* on a composite —
        i.e. the keys a ``parameter_overrides`` dict may contain without the run
        rejecting them.  Returns ``{"settable": [...], "referenced": [...] | None,
        "inert": [...], "declared": {name: {...}}}``.

    validate_parameter_overrides(overrides, spec=None, core=None, state=None,
                                 schema=None, *, available=None) -> list[dict]
        For each key in ``overrides``, tag it against the settable set.  Returns
        one ``{name, status, detail}`` per key, where ``status`` is one of
        ``ok | not_settable | unknown`` — mirroring ``validate_readouts``'
        ``{name, status, detail}`` shape and its never-fabricate flagging.

WHY THE SPEC, NOT THE BUILT COMPOSITE, IS THE SOURCE OF TRUTH
------------------------------------------------------------
Unlike observables — which are emittable leaves of the *built* composite state
and are therefore recoverable from ``state``/``schema`` — parameters are a
*spec-level* concept that is **consumed at build time**:

  * process-bigraph's ``CompositeSpec.to_document(overrides)`` calls
    ``_merged_params(overrides)``, whose sole gate is::

        unknown = set(overrides) - set(self.parameters)
        if unknown: raise KeyError(f"unknown override(s): {sorted(unknown)}")

    So the *exact* set of settable keys at run time is
    ``spec["parameters"].keys()`` — nothing more, nothing less.  This is what
    ``run-variant`` / ``build_composite_from_spec`` funnel every override
    through.

  * For a **static** spec, an override then fills ``${name}`` placeholders in
    ``state``/``schema`` via ``substitute_parameters``.  A declared parameter
    with *no* ``${name}`` placeholder is accepted by the KeyError gate but has
    no effect on the document — we surface that as ``not_settable`` (declared
    but inert), never as a silent no-op.

  * For a **generator** spec, the merged params flow into the builder as
    ``**kwargs`` (``fn(core=core, **merged)``); they never appear as
    ``${name}`` placeholders.  We cannot statically know which kwargs the
    builder actually consumes without running it, so we do NOT flag inertness
    for generator specs (``referenced`` is ``None``): every declared parameter
    is reported ``settable``.

The built ``core``/``state``/``schema`` are therefore *not* the source of the
parameter catalog (the placeholders are already gone post-build; generator
kwargs never were placeholders).  They are accepted here only for API symmetry
with ``available_observables`` and are unused by the current checks.

WHAT THIS VALIDATOR CAN AND CANNOT CATCH
----------------------------------------
CAN catch:
  * an override key that is not a declared parameter at all → ``unknown``
    (this is precisely the run-time ``KeyError`` case);
  * a declared-but-inert parameter on a *static* spec (no ``${name}`` use) →
    ``not_settable``.

CANNOT catch (documented, not silently passed):
  * whether a declared parameter actually *propagates* to the deep model.  A
    v2ecoli-style ``config_overrides`` knob may be a legitimate top-level
    parameter yet only reach a shallow layer, while the science it names lives
    in a deep ParCa-injected value that ``config_overrides`` can't touch.  That
    is an *enforcement* concern (see ``param_enforcement.py``, which compares
    declared-vs-applied at run time), not an *availability* concern.  A key
    reported ``ok`` here means "the run will accept it", NOT "it demonstrably
    changed the biology".
  * for a generator spec, an inert kwarg the builder ignores (we cannot see
    inside the builder statically).
"""
from __future__ import annotations

import re
from typing import Any

# Mirror process_bigraph.composite_spec's placeholder grammar so our notion of
# "referenced" matches what substitute_parameters actually resolves.
_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# ---------------------------------------------------------------------------
# Spec accessors (accept a plain dict spec or a CompositeSpec-like object)
# ---------------------------------------------------------------------------

def _get(spec: Any, key: str, default: Any = None) -> Any:
    if spec is None:
        return default
    if isinstance(spec, dict):
        return spec.get(key, default)
    return getattr(spec, key, default)


def _declared_parameters(spec: Any) -> dict:
    """Return the composite's declared ``parameters`` dict (the settable set)."""
    params = _get(spec, "parameters") or {}
    return dict(params) if isinstance(params, dict) else {}


def _is_generator(spec: Any) -> bool:
    """A generator spec carries a ``builder`` and no inline ``state``."""
    if _get(spec, "builder") is not None:
        return True
    # A static spec always has a state document; its absence with no builder is
    # treated as static-with-empty-state (referenced set is simply empty).
    return False


# ---------------------------------------------------------------------------
# Placeholder scan — which declared params are actually referenced (static)
# ---------------------------------------------------------------------------

def _referenced_in(node: Any, out: set[str]) -> None:
    """Collect every ``${name}`` placeholder used anywhere under ``node``."""
    if isinstance(node, str):
        out.update(_PLACEHOLDER.findall(node))
    elif isinstance(node, dict):
        for v in node.values():
            _referenced_in(v, out)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _referenced_in(v, out)


def _referenced_names(spec: Any) -> set[str]:
    """The set of parameter names referenced via ``${name}`` in state + schema."""
    out: set[str] = set()
    _referenced_in(_get(spec, "state"), out)
    _referenced_in(_get(spec, "schema"), out)
    return out


# ---------------------------------------------------------------------------
# Structure introspection
# ---------------------------------------------------------------------------

def available_parameters(
    spec: Any,
    core: Any = None,
    state: dict | None = None,
    schema: Any | None = None,
) -> dict:
    """Enumerate the parameters a composite exposes for override.

    Args:
        spec:   the composite spec — a parsed ``*.composite.{yaml,json}`` dict
                (``{name, parameters, state|builder, schema?}``) or a
                ``CompositeSpec``-like object.  This is the authoritative source
                of the settable set (see the module docstring for why the built
                composite is not).
        core:   accepted for API symmetry with ``available_observables``;
                currently unused.
        state:  accepted for API symmetry; currently unused.
        schema: accepted for API symmetry; currently unused.

    Returns:
        A dict with:
          ``settable``   — sorted names a ``parameter_overrides`` may contain
                           without a run-time ``KeyError`` (== declared params).
          ``referenced`` — sorted subset consumed via ``${name}`` in the static
                           state/schema, or ``None`` for a generator spec (where
                           consumption is decided by the builder and cannot be
                           determined statically).
          ``inert``      — sorted ``settable - referenced`` for a static spec
                           (declared but with no placeholder → no document
                           effect); always ``[]`` for a generator spec.
          ``declared``   — ``{name: {type, default, description, referenced}}``
                           mirroring the spec's parameter defs.
    """
    declared = _declared_parameters(spec)
    settable = sorted(declared)

    if _is_generator(spec):
        referenced: list[str] | None = None
        inert: list[str] = []
        ref_set: set[str] = set()
    else:
        ref_set = _referenced_names(spec) & set(declared)
        referenced = sorted(ref_set)
        inert = sorted(set(declared) - ref_set)

    declared_out: dict[str, dict] = {}
    for name, pdef in declared.items():
        pdef = pdef if isinstance(pdef, dict) else {}
        declared_out[name] = {
            "type": pdef.get("type"),
            "default": pdef.get("default"),
            "description": pdef.get("description"),
            # None referenced => generator (unknown); else static membership.
            "referenced": (None if referenced is None else (name in ref_set)),
        }

    return {
        "settable": settable,
        "referenced": referenced,
        "inert": inert,
        "declared": declared_out,
    }


# ---------------------------------------------------------------------------
# Override validation against the settable set
# ---------------------------------------------------------------------------

def _result(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def validate_parameter_overrides(
    overrides: dict | None,
    spec: Any = None,
    core: Any = None,
    state: dict | None = None,
    schema: Any | None = None,
    *,
    available: dict | None = None,
) -> list[dict]:
    """Validate every key in ``overrides`` against the composite's parameters.

    Args:
        overrides: the variant's ``parameter_overrides`` dict.  ``None``/empty
                   yields ``[]``.
        spec:      the composite spec (see ``available_parameters``).
        core:      API-symmetry only; passed through, unused.
        state:     API-symmetry only; passed through, unused.
        schema:    API-symmetry only; passed through, unused.
        available: a pre-computed ``available_parameters`` dict; when given,
                   ``spec``/``core``/``state``/``schema`` are ignored.  This is
                   the headless-friendly path used by unit tests, mirroring
                   ``validate_readouts(..., available=...)``.

    Returns:
        One ``{name, status, detail}`` per override key, in ``overrides``
        iteration order.  ``status`` ∈ ``{ok, not_settable, unknown}``:

          ``ok``           — a declared parameter that the composite consumes
                             (referenced by ``${name}`` for a static spec, or
                             any declared kwarg for a generator spec).
          ``not_settable`` — a declared parameter that is inert on a static spec
                             (no ``${name}`` placeholder → the run accepts it but
                             the document is unchanged); flagged, never a silent
                             no-op.
          ``unknown``      — not a declared parameter at all → the run rejects it
                             (``CompositeSpec._merged_params`` raises ``KeyError``);
                             never invented into existence.
    """
    if available is None:
        if spec is None:
            raise ValueError(
                "validate_parameter_overrides requires either `available=` or `spec=`"
            )
        available = available_parameters(spec, core, state, schema)

    settable: set[str] = set(available.get("settable", []))
    inert: set[str] = set(available.get("inert", []))

    results: list[dict] = []
    for key in (overrides or {}):
        if key not in settable:
            results.append(_result(
                key, "unknown",
                f"{key!r} is not a declared parameter of this composite "
                f"(settable: {sorted(settable)}); a run would raise KeyError",
            ))
        elif key in inert:
            results.append(_result(
                key, "not_settable",
                f"{key!r} is declared but never referenced by a ${{{key}}} "
                "placeholder in the state/schema — the run accepts it but the "
                "composite document is unchanged",
            ))
        else:
            results.append(_result(
                key, "ok",
                f"{key!r} is a declared, consumed parameter",
            ))
    return results
