from pbg_superpowers import study_outcomes as so


def test_canonical_prefers_flag_over_position():
    spec = {"runs": [
        {"name": "a", "status": "completed", "canonical": True},
        {"name": "b", "status": "completed"},
    ]}
    assert so.canonical_run(spec)["name"] == "a"


def test_canonical_falls_back_to_newest_completed():
    spec = {"runs": [
        {"name": "old", "status": "completed", "timestamp": "2026-01-01T00:00:00Z"},
        {"name": "new", "status": "completed", "timestamp": "2026-02-01T00:00:00Z"},
        {"name": "running", "status": "running", "timestamp": "2026-03-01T00:00:00Z"},
    ]}
    assert so.canonical_run(spec)["name"] == "new"


def test_canonical_last_resort_is_last_entry():
    spec = {"runs": [{"name": "a", "status": "running"}, {"name": "b", "status": "running"}]}
    assert so.canonical_run(spec)["name"] == "b"


def test_canonical_none_when_no_runs():
    assert so.canonical_run({"runs": []}) is None
    assert so.canonical_run({}) is None
