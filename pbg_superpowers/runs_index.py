"""Global run index across all studies, tagged by investigation/study/emitter."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def emitter_type_of(emitter_path: str | None) -> str:
    p = str(emitter_path or "").lower()
    if ".zarr" in p:
        return "XArray"
    if ".parquet" in p:
        return "Parquet"
    return "SQLite"
