#!/usr/bin/env python3
"""
Gate 4 - structured numerical / stochastic trajectory drift.
Hard Rule 1: a bare keyword is never enough; both the divergence and the
ensemble-agreement structure must be present.

Extracted once from the former `analyze_case._build_raw_causal_attribution`, so the
gate logic is byte-identical to the code it replaced. There is no generator in this
repository - these modules are maintained by hand from here, and
`tests/test_attribution_characterization.py` will show any behavior change as a
reviewable baseline diff.
"""

from __future__ import annotations

from confidence import attach_confidence_metadata
import re

from typing import Any, Dict, Optional

from ..context import AttributionContext


def gate4_numerical_divergence(ctx: AttributionContext) -> Optional[Dict[str, Any]]:
    case_id = ctx.case_id
    fail_log_obs = ctx.fail_log_obs
    fail_text = ctx.fail_text
    runtime = ctx.runtime
    trial_name = ctx.trial_name

    has_structured_numerical = bool(
        re.search(
            r"(?:trajectory_rmsd\s*=\s*[\d.]+|instantaneous_position.*?>\s*[\d.]+)",
            fail_text,
            re.IGNORECASE,
        )
        and re.search(
            r"(?:ensemble average matches|ensemble.*within tolerance|conserved.*matches)",
            fail_text,
            re.IGNORECASE,
        )
    )

    if not has_structured_numerical:
        ctx.trace.record(
            gate_id="gate4_numerical_divergence",
            matched=False,
            reason="verifier log lacks the structured divergence + ensemble-agreement pair",
            checks={"has_structured_numerical": has_structured_numerical},
        )
        return None

    ev_refs = ["ver:fail_log"] if fail_log_obs else ["art:trial_result"]
    prc = attach_confidence_metadata(
        {
            "category": "verifier",
            "subtype": "tolerance_too_strict",
            "code": "VERIFIER_TOLERANCE_TOO_STRICT",
            "summary": "Verifier compared instantaneous late-step coordinates/energies rather than ensemble averages despite physical/numerical chaos.",
        },
        direct_causal_evidence=2,
        cross_source_corroboration=1,
    )
    cf_case = attach_confidence_metadata(
        {
            "category": "case",
            "subtype": "ambiguous_contract",
            "code": "CASE_AMBIGUOUS_CONTRACT",
            "summary": "Benchmark case did not fix RNG seeds or specify ensemble statistical verification bounds.",
        },
        direct_causal_evidence=1,
    )
    h1 = attach_confidence_metadata(
        {
            "hypothesis_id": "H1",
            "category": "verifier",
            "subtype": "tolerance_too_strict",
            "claim": "Verifier evaluated instantaneous trajectory/position divergence rather than ensemble averages, causing failure despite valid ensemble statistics.",
            "evidence_for": ev_refs,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Compare ensemble averages or pin MPI/OMP thread counts.",
        },
        direct_causal_evidence=2,
        cross_source_corroboration=1,
    )
    h2 = attach_confidence_metadata(
        {
            "hypothesis_id": "H2",
            "category": "agent",
            "subtype": "scientific_parameter_selection",
            "claim": "Agent configured wrong ensemble or thermodynamic state.",
            "evidence_for": [],
            "evidence_against": ev_refs,
            "missing_evidence": [],
            "counterfactual_test": "Check ensemble average match reported in `verify.log`.",
        },
        direct_causal_evidence=0,
        contradicting_evidence=1,
    )
    ctx.trace.record(
        gate_id="gate4_numerical_divergence",
        matched=True,
        reason="verifier log shows divergence with matching ensemble statistics",
        checks={"has_structured_numerical": has_structured_numerical},
    )

    return {
        "schema_version": "failure-analysis-v1",
        "case_id": case_id,
        "trial_name": trial_name,
        "verdict": "failed",
        "failure_stage": "verifier_execution",
        "detection_stage": "verifier_execution",
        "first_unrecovered_deviation": {
            "status": "identified",
            "event_ref": ev_refs[0],
            "timestamp": runtime.get("finished_at"),
            "summary": "Lyapunov-sensitive MD trajectory divergence while ensemble statistics remained consistent.",
        },
        "failure_manifestation": {
            "type": "numerical_trajectory_divergence",
            "summary": fail_text[:240],
        },
        "primary_root_cause": prc,
        "contributing_factors": [cf_case],
        "competing_hypotheses": [h1, h2],
        "evidence_refs": ev_refs,
        "excluded_hypotheses": [
            {
                "hypothesis_id": "H2",
                "category": "agent",
                "reason": "Agent used the requested parameters and ensemble averages matched reference tolerances; divergence reflects finite-precision floating-point accumulation sensitivity.",
            }
        ],
        "recommended_actions": [
            {
                "owner": "Verifier",
                "action": "Verify ensemble averages or conserved-quantity drift rather than late-step instantaneous values, or pin MPI/OMP thread counts.",
            }
        ],
        "skill_prescription": None,
    }
