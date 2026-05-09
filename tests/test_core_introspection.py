from pbg_superpowers.core_introspection import (
    list_processes, list_types, registry_snapshot,
)


class FakeCore:
    def __init__(self):
        self._links = {"ProcA": object(), "StepB": object()}
        self._types = {"my_type": {"_inherit": "float", "_default": 0.0}}

    def list_processes(self):
        return list(self._links.keys())

    def list_types(self):
        return list(self._types.keys())

    def access(self, name):
        return self._types.get(name, {})


def test_list_processes_returns_registered():
    c = FakeCore()
    assert sorted(list_processes(c)) == ["ProcA", "StepB"]


def test_list_types_returns_registered():
    c = FakeCore()
    assert "my_type" in list_types(c)


def test_registry_snapshot_is_stable_dict():
    c = FakeCore()
    snap = registry_snapshot(c)
    assert "processes" in snap and "types" in snap
    assert sorted(snap["processes"]) == ["ProcA", "StepB"]
    assert sorted(snap["types"]) == ["my_type"]
