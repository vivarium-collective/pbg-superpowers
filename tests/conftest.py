# tests/conftest.py
from pathlib import Path
import pytest


@pytest.fixture
def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def fixtures_dir(plugin_root) -> Path:
    return plugin_root / "tests" / "fixtures"


@pytest.fixture
def schemas_dir(plugin_root) -> Path:
    return plugin_root / "tests" / "schemas"
