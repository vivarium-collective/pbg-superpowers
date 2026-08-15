"""Typed check/axis contract for report_card_verdict/v2.

`check()` produces one v2 axis dict (v1 axis fields plus expected/margin/severity/
knob/citation) with a computed verdict + signed margin. Pure stdlib; the axis dict
is exactly what verdict_json/TestBuilder embed under groups[g]['axes'].
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict

from viva_superpowers.test_vocab import normalize_verdict


@dataclass(frozen=True)
class Expected:
    kind: str                       # "value" | "band" | "predicate"
    value: float | None = None
    low: float | None = None
    high: float | None = None
    op: str = "~="
    tol: float = 0.05
    statement: str | None = None
    def to_dict(self) -> dict:
        return asdict(self)


def value(target, op="~=", tol=0.05) -> Expected:
    return Expected(kind="value", value=float(target), op=op, tol=float(tol))

def band(low, high) -> Expected:
    return Expected(kind="band", low=float(low), high=float(high))

def predicate(statement) -> Expected:
    return Expected(kind="predicate", statement=str(statement))


def sanitize(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


def _margin(observed: float, e: Expected):
    if e.kind == "band":
        return min(observed - e.low, e.high - observed)
    # kind == "value"
    t, target, op = e.tol, e.value, e.op
    if op == "~=":
        scale = abs(target) if target != 0 else 1.0
        return t * scale - abs(observed - target)
    if op in ("<=", "<"):
        return target - observed
    if op in (">=", ">"):
        return observed - target
    if op == "==":
        return -abs(observed - target)
    raise ValueError(f"unknown op {op!r}")


def _passes(margin: float, e: Expected) -> bool:
    if e.kind == "value" and e.op in ("<", ">"):
        return margin > 0          # strict
    return margin >= 0


def _meter(margin: float, e: Expected):
    ref = abs(e.value or e.high or e.low or 1.0) or 1.0
    return max(0.0, min(1.0, 0.5 + margin / (2.0 * ref)))


def check(id, label, observed, expected: Expected, *, severity="hard",
          units=None, knob=None, cite=None, detail=None, verdict=None) -> dict:
    margin = None
    meter = None
    if expected.kind != "predicate" and isinstance(observed, (int, float)):
        obs = float(observed)
        margin = _margin(obs, expected)
        passed = _passes(margin, expected)
        if passed:
            v = "within_tol"
        elif severity == "directional":
            v = "drift"
        else:
            v = "mismatch"
        meter = _meter(margin, expected)
    else:
        v = normalize_verdict(verdict)
    return {
        "id": id, "label": label, "verdict": v,
        "value": observed, "meter": meter, "detail": detail,
        "expected": expected.to_dict(), "margin": margin,
        "severity": severity, "units": units,
        "knob": list(knob) if knob else None, "citation": cite,
    }
