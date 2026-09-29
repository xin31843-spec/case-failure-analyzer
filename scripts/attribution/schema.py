#!/usr/bin/env python3
"""
Attribution output contract (`scripts/attribution/schema.py`)

Every attribution return path produces the same 15 keys in the same order. That
key set and order is part of the output contract consumed by `validate_analysis.py`
(`REQUIRED_ANALYSIS_KEYS` is these 15 minus `trial_name`) and by `render_report.py`.

`make_attribution` is the single place the contract is enforced, so a gate that
forgets a key fails loudly at construction instead of surfacing as a validator
error at the end of the pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

# Order IS the contract: outputs are serialized in this order and the
# characterization baselines compare serialized text.
OUTCOME_KEYS: Tuple[str, ...] = (
    "schema_version",
    "case_id",
    "trial_name",
    "verdict",
    "failure_stage",
    "detection_stage",
    "first_unrecovered_deviation",
    "failure_manifestation",
    "primary_root_cause",
    "contributing_factors",
    "competing_hypotheses",
    "evidence_refs",
    "excluded_hypotheses",
    "recommended_actions",
    "skill_prescription",
)


def make_attribution(**fields: Any) -> Dict[str, Any]:
    """
    Build an attribution dict with exactly `OUTCOME_KEYS`, in that order.

    Values are placed by reference, never copied: `evidence_refs` is deliberately
    the SAME list object as the synthetic hypotheses' `evidence_for` /
    `evidence_against` (see the gates). Copying here would silently break that
    aliasing, which `_reconcile_competing_hypotheses` relies on not mutating.

    `schema_version` is passed by each gate rather than defaulted: the original
    implementation hard-coded the literal `"failure-analysis-v1"` on 5 of its 8
    return paths and used the `SCHEMA_VERSION` constant on the other 3. They are
    equal today; that is preserved deliberately rather than normalized, so a
    future version bump stays a separate, deliberate decision.
    """
    missing = [k for k in OUTCOME_KEYS if k not in fields]
    extra = [k for k in fields if k not in OUTCOME_KEYS]
    if missing or extra:
        raise TypeError(f"make_attribution contract violation: missing={missing} extra={extra}")
    return {key: fields[key] for key in OUTCOME_KEYS}
