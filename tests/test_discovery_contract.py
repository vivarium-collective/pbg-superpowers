"""Tests for the bigraph-schema auto-discovery contract.

Verifies that a Process subclass defined in a module is picked up by
``recursive_dynamic_import`` and ends up in ``core.link_registry`` — the same
path that ``allocate_core()`` walks for every pip-installed ``pbg-*`` package.

We use the simpler in-memory variant (no pip install required) so the test
runs offline without touching the filesystem beyond the source tree.
See docs/conventions/discovery.md for the full convention.
"""

import types

import pytest

from process_bigraph import Process, allocate_core
from bigraph_schema.package.discover import (
    recursive_dynamic_import,
    find_edges,
    find_types,
)


# ---------------------------------------------------------------------------
# Fixture: a minimal Process subclass in a synthetic module
# ---------------------------------------------------------------------------

def _make_fixture_module(name: str = "pbg_discovery_fixture") -> types.ModuleType:
    """Build an in-memory module that contains one Process subclass."""
    mod = types.ModuleType(name)
    mod.__name__ = name
    # No __path__ → recursive_dynamic_import will NOT try to recurse into submodules.

    class FixtureProcess(Process):
        """Minimal compliant Process — inherits Edge via Process → Open → Edge."""

        config_schema = {
            "rate": {"_type": "float", "_default": 0.1},
        }

        def inputs(self):
            return {"substrate": "float"}

        def outputs(self):
            return {"product": "float"}

        def update(self, state, interval):
            return {"product": state["substrate"] * self.config["rate"] * interval}

    # Patch __module__ so find_edges sees it as "defined here" (not an import).
    FixtureProcess.__module__ = name
    mod.FixtureProcess = FixtureProcess
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFindEdges:
    """Unit-level: find_edges picks up Process subclasses, skips bare classes."""

    def test_finds_process_subclass(self):
        mod = _make_fixture_module()
        import inspect
        mapping = inspect.getmembers(mod, inspect.isclass)
        edges = find_edges(mapping, module_name=mod.__name__)
        names = [cls.__name__ for _, cls in edges]
        assert "FixtureProcess" in names, f"Expected FixtureProcess in {names}"

    def test_skips_plain_class(self):
        """A class that does not inherit Edge must not appear in find_edges output."""
        mod = types.ModuleType("plain_module")

        class NotAProcess:
            def update(self, state, interval):
                return {}

        NotAProcess.__module__ = "plain_module"
        mod.NotAProcess = NotAProcess

        import inspect
        mapping = inspect.getmembers(mod, inspect.isclass)
        edges = find_edges(mapping, module_name="plain_module")
        names = [cls.__name__ for _, cls in edges]
        assert "NotAProcess" not in names, "Plain class should not be discovered"


class TestRecursiveDynamicImport:
    """recursive_dynamic_import returns edges for compliant in-memory modules."""

    def test_discovers_fixture_process(self):
        mod = _make_fixture_module()
        core = allocate_core()

        _core, edges, _types, _visited = recursive_dynamic_import(core, mod)

        edge_class_names = [cls.__name__ for _, cls in edges]
        assert "FixtureProcess" in edge_class_names, (
            f"FixtureProcess not found in discovered edges: {edge_class_names}"
        )

    def test_discovered_fq_name_format(self):
        """Primary registration key should be fully-qualified module.ClassName."""
        mod = _make_fixture_module("pbg_foo_fixture")
        core = allocate_core()

        _core, edges, _types, _visited = recursive_dynamic_import(core, mod)

        fq_names = [fq for fq, _ in edges]
        assert any("FixtureProcess" in fq and "pbg_foo_fixture" in fq for fq in fq_names), (
            f"Expected FQ name like 'pbg_foo_fixture.FixtureProcess', got: {fq_names}"
        )

    def test_register_types_hook_called(self):
        """If a module exposes register_types(core), it must be called during import."""
        hook_called = []

        mod = types.ModuleType("pbg_hook_fixture")
        mod.__name__ = "pbg_hook_fixture"

        def register_types(core):
            hook_called.append(True)
            return core

        mod.register_types = register_types

        core = allocate_core()
        recursive_dynamic_import(core, mod)

        assert hook_called, "register_types hook was not called by recursive_dynamic_import"

    def test_no_duplicate_visit(self):
        """The visited set prevents re-scanning a module already seen."""
        mod = _make_fixture_module("pbg_dedup_fixture")
        core = allocate_core()

        visited = {mod.__name__}  # pre-mark as visited
        _core, edges, _types, _visited = recursive_dynamic_import(core, mod, visited=visited)

        assert edges == [], (
            "Already-visited module should yield no edges, got: {edges}"
        )


class TestAllocateCoreTopDict:
    """allocate_core(top=...) registers inline classes, matching the 'top' path
    in load_local_modules — useful for test-only process classes that are not
    pip-installed.
    """

    def test_inline_process_via_top(self):
        class InlineProcess(Process):
            config_schema = {}

            def inputs(self):
                return {"x": "float"}

            def outputs(self):
                return {"y": "float"}

            def update(self, state, interval):
                return {"y": state["x"]}

        core = allocate_core(top={"InlineProcess": InlineProcess})
        assert "InlineProcess" in core.link_registry, (
            "InlineProcess should be registered via allocate_core(top=...)"
        )


class TestDiscoveryContract:
    """Integration: the full discovery path from module → link_registry."""

    def test_end_to_end_registration(self):
        """Simulate what discover_packages does: import module, find edges,
        register them. Assert short name ends up in link_registry.

        This is the exact sequence allocate_core() executes for every installed
        pbg-* package.
        """
        mod = _make_fixture_module("pbg_e2e_fixture")
        core = allocate_core()

        _core, edges, _types, _visited = recursive_dynamic_import(core, mod)

        # Replicate what discover_packages does after recursive_dynamic_import:
        for fq_name, edge_cls in edges:
            core.link_registry[fq_name] = edge_cls
            short = fq_name.split(".")[-1]
            if short not in core.link_registry:
                core.link_registry[short] = edge_cls

        assert "FixtureProcess" in core.link_registry, (
            "Short name 'FixtureProcess' must be in core.link_registry after registration"
        )
        assert "pbg_e2e_fixture.FixtureProcess" in core.link_registry, (
            "Fully-qualified name must also be in core.link_registry"
        )

    def test_stub_class_not_registered(self):
        """A stub class (no Edge inheritance) must not end up in link_registry."""
        mod = types.ModuleType("pbg_stub_fixture")
        mod.__name__ = "pbg_stub_fixture"

        class StubProcess:
            """This is the anti-pattern: duck-typed, not a real Process subclass."""
            config_schema = {}

            def inputs(self):
                return {"x": "float"}

            def outputs(self):
                return {"y": "float"}

            def update(self, state, interval):
                return {"y": state["x"]}

        StubProcess.__module__ = "pbg_stub_fixture"
        mod.StubProcess = StubProcess

        core = allocate_core()
        _core, edges, _types, _visited = recursive_dynamic_import(core, mod)

        edge_names = [cls.__name__ for _, cls in edges]
        assert "StubProcess" not in edge_names, (
            "Stub class (no Edge inheritance) must not be discovered"
        )
