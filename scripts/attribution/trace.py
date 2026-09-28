#!/usr/bin/env python3
"""
Decision trace (`scripts/attribution/trace.py`)

Records which gates were evaluated, why each abstained, and which one was
selected. The trace is attached to the finished attribution as an additive 16th
key (`decision_trace`) so an audit reader can see the decision that produced the
verdict instead of only its conclusion.

Two invariants keep the trace safe to serialize into `analysis.json`:

- `checks` holds scalars only (int / bool / short str / None). Evidence dicts and
  matched log text are never stored: `matched_text` is unbounded and would both
  bloat the artifact and leak raw log content into a report.
- Nothing time-dependent is recorded, so `analysis.json` stays byte-deterministic
  for snapshot comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TRACE_SCHEMA_VERSION = "decision-trace-v1"
ENGINE_VERSION = "attribution-engine-v1"

#: Longest string permitted inside a trace `checks` value or `reason`.
MAX_TRACE_STRING = 400

_SCALAR_TYPES = (bool, int, float, str, type(None))


def _clip(value: str, limit: int = MAX_TRACE_STRING) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _scalarize(checks: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only scalar values; anything else is replaced by its type name."""
    out: Dict[str, Any] = {}
    for key, value in checks.items():
        if isinstance(value, _SCALAR_TYPES):
            out[key] = _clip(value) if isinstance(value, str) else value
        else:
            # A list/dict reaching `checks` is a programming error in a gate, but
            # failing the whole analysis over a diagnostic field would be worse
            # than degrading it to a marker.
            out[key] = f"<{type(value).__name__}>"
    return out


@dataclass
class DecisionTrace:
    """Mutable recorder for one attribution decision."""

    gate_order: Tuple[str, ...]
    evaluated: List[Dict[str, Any]] = field(default_factory=list)
    selected: Optional[Dict[str, Any]] = None
    reconciled_competing_hypotheses: bool = False

    def record(
        self,
        *,
        gate_id: str,
        matched: bool,
        reason: str,
        checks: Optional[Dict[str, Any]] = None,
        subcase_id: Optional[str] = None,
    ) -> None:
        """Record one gate evaluation. Called exactly once per gate, matched or not."""
        entry: Dict[str, Any] = {
            "gate_id": gate_id,
            "matched": bool(matched),
            "reason": _clip(reason),
        }
        if subcase_id is not None:
            entry["subcase_id"] = subcase_id
        entry["checks"] = _scalarize(checks or {})
        self.evaluated.append(entry)

    def select(
        self,
        *,
        gate_id: str,
        category: Optional[str],
        code: Optional[str],
        verdict: Optional[str],
        failure_stage: Optional[str],
        subcase_id: Optional[str] = None,
    ) -> None:
        """Record the winning gate. Filled by the engine, never by a gate."""
        selected: Dict[str, Any] = {
            "gate_id": gate_id,
            "category": category,
            "code": code,
            "verdict": verdict,
            "failure_stage": failure_stage,
        }
        if subcase_id is not None:
            selected["subcase_id"] = subcase_id
        self.selected = selected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "engine": ENGINE_VERSION,
            "gate_order": list(self.gate_order),
            "evaluated": self.evaluated,
            "selected": self.selected,
            "reconciled_competing_hypotheses": self.reconciled_competing_hypotheses,
        }