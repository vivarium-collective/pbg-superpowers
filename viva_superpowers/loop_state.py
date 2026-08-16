"""Persisted protocol state for the agentic model-building loop.

`.pbg/loop/<study>.json` (schema model_build_loop/v1) is the loop's audit trail
AND the seam that lets a supervised in-session run become an autonomous dispatched
run — any executor reads/advances the same file. Pure: stdlib + viva_superpowers
intra-imports only (AI-free; no process_bigraph / workbench). See
docs/superpowers/specs/2026-08-16-agentic-model-building-loop-design.md §3-§4.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from viva_superpowers import paths, study_io

SCHEMA = "model_build_loop/v1"
STATES = ("AUTHOR", "AUDIT", "LOCK", "BUILD", "RUN", "EVALUATE",
          "DECIDE", "NAVIGATE", "DONE", "GIVE_UP")


def loop_path(ws_root, study: str) -> Path:
    return paths.workspace_dir("pbg", root=ws_root) / "loop" / f"{study}.json"


def create(ws_root, study: str, question: str, *, max_iterations: int = 12) -> dict:
    return {
        "schema": SCHEMA,
        "study": study,
        "question": question,
        "state": "AUTHOR",
        "iteration": 0,
        "budget": {"max_iterations": int(max_iterations), "spent": 0},
        "audit": None,
        "locked_tests_hash": None,
        "prereg_record": {"locked_at_iteration": None, "prior_hashes": []},
        "reopen_count": 0,
        "last_verdict": None,
        "history": [],
    }


def save(ws_root, study: str, state: dict) -> Path:
    p = loop_path(ws_root, study)
    p.parent.mkdir(parents=True, exist_ok=True)
    study_io.atomic_write(p, json.dumps(state, indent=1, sort_keys=False) + "\n")
    return p


def load(ws_root, study: str) -> "dict | None":
    p = loop_path(ws_root, study)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
