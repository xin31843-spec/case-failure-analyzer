#!/usr/bin/env python3
"""
Attribution context (`scripts/attribution/context.py`)

Precomputes everything the gates share, so each gate is a small pure function of
one context object rather than a slice of a 927-line function's local scope.

Three groups of values are computed here that the original implementation
computed *inside* a gate body but consumed from a later one:

- `fail_log_obs` / `fail_text` were derived in the Gate 4 region but read by
  Gates 4, 5, and 6.
- `verifier_defect_contracts` was duplicated verbatim in the Gate 2 and Gate 3
  bodies (same predicate, same order, both consuming `[0]`).
- the seven signal/observation lists were derived in the Gate 5 region but
  consumed by both Gate 5 and Gate 6.

One deliberate difference from the original: the hoisted derivations use `.get()`
rather than direct subscript. The originals only evaluated these expressions on
the path that reached their own gate, so a malformed `behavioral_signals` entry
missing `signal_type` would previously crash only for Gate 5 and later — from
here it would crash on every path, including a passing trial. `.get()` keeps
Gates 0-4 exactly as tolerant as they were. On well-formed evidence (every
observation is built with a literal `signal_type` / `obs_id` in
`normalize_trajectory.py` and `audit_contract.py`) this is unobservable, and
`tests/test_attribution_decisions.py` pins the malformed case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .trace import DecisionTrace

#: The verifier-alignment contract values that indicate a verifier-side defect.
VERIFIER_DEFECT_ALIGNMENTS = (
    "verifier_defect",
    "verifier_hidden_requirement",
    "verifier_schema_mismatch",
)


@dataclass
class AttributionContext:
    """Shared inputs for one attribution decision."""

    # ── sources ──────────────────────────────────────────────────────────────
    evidence: Dict[str, Any]
    cand_hyps: Dict[str, Any]
    trace: DecisionTrace
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    # ── preamble (mirrors the original local assignments verbatim) ───────────
    case_id: str = "unknown"
    trial_name: str = "unknown"
    runtime: Dict[str, Any] = field(default_factory=dict)
    agent_started: bool = False
    verifier_started: bool = False
    verification_status: Optional[str] = None
    reward: Optional[float] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    verifier_obs: List[Dict[str, Any]] = field(default_factory=list)
    sci_obs: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    # ── hoisted from the Gate 4 region ───────────────────────────────────────
    fail_log_obs: Optional[Dict[str, Any]] = None
    fail_text: str = ""

    # ── hoisted shared derivation (Gate 2 + Gate 3) ──────────────────────────
    verifier_defect_contracts: List[Dict[str, Any]] = field(default_factory=list)

    # ── hoisted from the Gate 5 region ───────────────────────────────────────
    unrecovered_sci_obs: List[Dict[str, Any]] = field(default_factory=list)
    recovered_sci_obs: List[Dict[str, Any]] = field(default_factory=list)
    repeated_fail_sigs: List[Dict[str, Any]] = field(default_factory=list)
    dep_search_sigs: List[Dict[str, Any]] = field(default_factory=list)
    premature_sigs: List[Dict[str, Any]] = field(default_factory=list)
    agent_mismatch_contracts: List[Dict[str, Any]] = field(default_factory=list)
    agent_timeline_events: List[Dict[str, Any]] = field(default_factory=list)


def build_context(
    evidence: Dict[str, Any],
    cand_hyps: Dict[str, Any],
    trace: DecisionTrace,
) -> AttributionContext:
    """Derive an `AttributionContext` from `evidence` without mutating it."""
    runtime = evidence.get("runtime") or {}
    verifier_obs = evidence.get("verifier_observations") or []
    contracts = evidence.get("contract_observations") or []
    sci_obs = evidence.get("scientific_observations") or []
    signals = evidence.get("behavioral_signals") or []
    timeline = evidence.get("timeline") or []

    fail_log_obs = next(
        (v for v in verifier_obs if v.get("obs_id") == "ver:fail_log"), None
    )

    return AttributionContext(
        evidence=evidence,
        cand_hyps=cand_hyps,
        trace=trace,
        diagnostics=list(evidence.get("diagnostics") or []),
        case_id=evidence.get("case_id", "unknown"),
        trial_name=evidence.get("trial_name", evidence.get("case_id", "unknown")),
        runtime=runtime,
        agent_started=bool(runtime.get("agent_started", False)),
        verifier_started=bool(runtime.get("verifier_started", False)),
        verification_status=runtime.get("verification_status"),
        reward=runtime.get("reward"),
        artifacts=evidence.get("artifacts") or [],
        errors=evidence.get("error_observations") or [],
        contracts=contracts,
        verifier_obs=verifier_obs,
        sci_obs=sci_obs,
        signals=signals,
        timeline=timeline,
        fail_log_obs=fail_log_obs,
        fail_text=fail_log_obs.get("matched_text", "") if fail_log_obs else "",
        verifier_defect_contracts=[
            c for c in contracts if c.get("alignment") in VERIFIER_DEFECT_ALIGNMENTS
        ],
        unrecovered_sci_obs=[s for s in sci_obs if not s.get("recovered", False)],
        recovered_sci_obs=[s for s in sci_obs if s.get("recovered", False)],
        repeated_fail_sigs=[
            s for s in signals if s.get("signal_type") == "repeated_failed_action"
        ],
        dep_search_sigs=[
            s for s in signals if s.get("signal_type") == "dependency_search_attempted"
        ],
        premature_sigs=[
            s for s in signals if s.get("signal_type") == "premature_completion"
        ],
        agent_mismatch_contracts=[
            c for c in contracts if c.get("alignment") == "agent_mismatch"
        ],
        agent_timeline_events=[ev for ev in timeline if ev.get("actor") == "agent"],
    )