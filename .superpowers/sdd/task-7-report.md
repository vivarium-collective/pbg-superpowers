# Task 7 Report — composite_generator shim

## What was done

`pbg_superpowers/composite_generator.py` rewritten as a thin shim over
`process_bigraph.composite_spec` (`_cs`).  The public surface is unchanged;
the backing store is now the process-bigraph registry.

### Key implementation decisions

**`_RegistryView` with identity cache**
The view wraps `_cs.all_specs()` and returns `GeneratorEntry` objects, but
caches by spec-id so that `fn._composite_generator_entry is _REGISTRY[id]`
still holds — required by the existing identity test.  `clear()` empties both
the local cache and `_cs.clear_registry()`.

**`@composite_generator` shim**
1. Calls `_validate_emitters` at decoration time (keeps the existing fail-loud
   guarantee on import).
2. Delegates to `_cs.composite_spec(...)(fn)` which registers a `CompositeSpec`
   in the process-bigraph registry.
3. Immediately calls `_REGISTRY[spec_id]` (populates cache) and stores the
   resulting `GeneratorEntry` on `fn._composite_generator_entry`.

**`build_generator`**
Retains the explicit `ValueError` raise for unknown overrides (the existing test
expects `ValueError`, while `CompositeSpec._merged_params` raises `KeyError`).
After validation, delegates to `spec.to_document(overrides, core=core)`.

**`_import_bigraph_packages` + `discover_generators`**
The distribution-walking body extracted into `_import_bigraph_packages(extra_packages)`.
`discover_generators` calls it then returns `{sid: _entry_for(s) for ... if s.kind == "generator"}`.
Parameter name kept as `extra_packages` (existing tests call it that way).

**Preserved intact (no changes)**
`GeneratorEntry`, `_validate_emitters`, `emitter_defaults`, `_emitter_node_from_decl`,
`install_default_emitters`, `apply_core_extensions`.

### Test update

One existing assertion updated:
```python
# Before
assert entry.parameters == {"x": {"type": "int", "default": 7}}
# After
assert entry.parameters == {"x": {"type": "integer", "default": 7}}
```
`CompositeSpec.__post_init__` normalises `"int"` → `"integer"` (canonical vocabulary);
this is expected behaviour demonstrated by the new delegation test itself.

## Test command and output

```
cd /Users/eranagmon/code/pbg-spec-shim && \
PYTHONPATH=/Users/eranagmon/code/pbg-composite-spec:/Users/eranagmon/code/pbg-spec-shim \
/Users/eranagmon/code/pbg-superpowers/.venv/bin/python -m pytest tests/test_composite_generator.py -v
```

**Result:** 32 passed, 21 warnings in 1.48 s (31 existing + 1 new delegation test).

## Ruff

```
ruff check pbg_superpowers/composite_generator.py
# All checks passed!
```

## Commit

`bfd616d`  feat(shim): composite_generator delegates to process-bigraph CompositeSpec registry

## Concerns / deviations

**Type normalisation (minor, expected)**  
`CompositeSpec.__post_init__` normalises type aliases (`int`→`integer`, `bool`→`boolean`,
etc.) in-place on the `parameters` dict it receives.  This means
`GeneratorEntry.parameters` now returns canonical types even when the decorator
was called with an alias.  The one affected existing assertion was updated to
`"integer"`; the fixture source (`fake_generator_pkg`) still says `"int"` to
demonstrate the normalisation path.  Dashboard code that previously stored raw
aliases (e.g. `"int"`) in its config schema will now see `"integer"` — this is
a backwards-compatible widening since both map to the same semantic type.

**`discover_generators` stacklevel shift (cosmetic)**  
Warning messages from `_import_bigraph_packages` reference the helper function
rather than `discover_generators` in their call stack.  No test checks warning
text; no behavioural change.

**No changes outside scope**  
`composite_spec.py`, `composite_discovery.py` untouched (Task 8 scope).

---

## Post-review fixes (commit `faec0d5`)

### FIX 1 — avoid private `_resolve_builder` in common case

In `_entry_for(spec)`, the `func=` assignment now uses the builder directly when
it is already callable, falling back to `_cs._resolve_builder(spec.builder,
spec.module)` only for string builders:

```python
func=(spec.builder if callable(spec.builder)
      else _cs._resolve_builder(spec.builder, spec.module)),
```

For decorator-registered generators `spec.builder` is the live function, so the
private helper is never called in the normal path.

### FIX 2 — `build_generator` descriptive error + rebuild path

`build_generator` was replaced with a four-branch implementation:

1. **`CompositeSpec` passed directly** — uses it as-is.
2. **Registered entry** — looks up `_cs.get(entry.id)` and delegates to
   `spec.to_document`.
3. **Out-of-registry `GeneratorEntry` with callable `.func`** — rebuilds a
   transient `CompositeSpec` from the entry's fields and delegates.
4. **Otherwise** — raises a descriptive `ValueError("build_generator: no
   registered composite for …")` instead of `AttributeError`.

The existing `ValueError` raise for unknown overrides is preserved at the top of
the function (before the new lookup logic) because `CompositeSpec._merged_params`
raises `KeyError`, not `ValueError`, and the existing test suite asserts
`ValueError`.

### Regression test

`test_build_generator_descriptive_error_for_unregistered_id` added to
`tests/test_composite_generator.py`. Constructs a `GeneratorEntry` with
`func=None` after clearing the registry; asserts `ValueError` with
`match="no registered composite"`.

### Test command and output

```
cd /Users/eranagmon/code/pbg-spec-shim && \
PYTHONPATH=/Users/eranagmon/code/pbg-composite-spec:/Users/eranagmon/code/pbg-spec-shim \
/Users/eranagmon/code/pbg-superpowers/.venv/bin/python -m pytest tests/test_composite_generator.py -v
```

**Result:** 33 passed, 21 warnings in 3.08s (32 prior + 1 new regression test).

### Ruff

```
ruff check pbg_superpowers/composite_generator.py
# All checks passed!
```

### Commit

`faec0d5`  fix(shim): avoid private _resolve_builder in common case; descriptive build_generator error + rebuild path
