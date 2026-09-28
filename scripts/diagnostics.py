#!/usr/bin/env python3
"""
Structured diagnostics (`scripts/diagnostics.py`)

Several collectors recover from a parse failure by degrading to a weaker result:
an unparseable `tests/verify.py` yields no AST-derived hazards, an unparseable
`verifier/reward.txt` yields `reward = None`. Those recoveries are correct — a
forensic tool must not crash on malformed input — but they were silent, and each
one changes what the analyzer can conclude:

  * no AST hazards  -> Gate 3 may not fire -> a verifier defect can be missed
  * no reward       -> Gate 0's pass detection can flip -> verdict changes

A silent downgrade that looks identical to "the verifier was clean" is the
dangerous case, so each recovery now emits a record that travels with the
evidence and is printed to stderr.

This generalizes the `_parse_error` / `warnings` fields that `discover_artifacts`
and `normalize_trajectory` already carry, rather than introducing a new concept.

Severity is about the *consequence*, not the exception:
  info     - control flow is correct and nothing is lost (e.g. a deliberate probe)
  warning  - evidence was degraded; a conclusion may rest on less than it appears
  error    - a required input could not be read at all
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

DIAGNOSTICS_SCHEMA_VERSION = "diagnostics-v1"

#: Longest message / error text retained on a record.
MAX_DIAGNOSTIC_TEXT = 400

INFO = "info"
WARNING = "warning"
ERROR = "error"

_SEVERITIES = (INFO, WARNING, ERROR)


def clip_text(text: Any, limit: int = MAX_DIAGNOSTIC_TEXT) -> str:
    """Coerce to a bounded string, so a record can never carry an unbounded log dump."""
    if text is None:
        return ""
    value = text if isinstance(text, str) else str(text)
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def make_diagnostic(
    *,
    stage: str,
    code: str,
    severity: str,
    message: str,
    source_ref: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    impact: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build one diagnostic record.

    `impact` states the causal consequence — what the analyzer can no longer
    conclude because of this recovery — which is the part a reader needs.
    """
    if severity not in _SEVERITIES:
        raise ValueError(f"unknown diagnostic severity: {severity!r}")
    return {
        "diagnostic_id": f"diag:{stage}:{code}",
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "stage": stage,
        "code": code,
        "severity": severity,
        "message": clip_text(message),
        "source_ref": source_ref,
        "error_type": error_type,
        "error_message": clip_text(error_message),
        "impact": impact,
        "context": dict(context or {}),
    }


def merge_diagnostics(*groups: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Concatenate diagnostic lists, preserving order and dropping empties."""
    merged: List[Dict[str, Any]] = []
    for group in groups:
        for record in group or []:
            if isinstance(record, dict):
                merged.append(record)
    return merged


def format_diagnostic_line(record: Dict[str, Any]) -> str:
    """One-line JSON for stderr, so CLI output stays greppable."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True)