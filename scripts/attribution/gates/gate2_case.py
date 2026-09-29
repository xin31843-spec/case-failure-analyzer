#!/usr/bin/env python3
"""
Gate 2 - a case/prompt contract defect (e.g. a promised asset is absent).

Extracted once from the former `analyze_case._build_raw_causal_attribution`, so the
gate logic is byte-identical to the code it replaced. There is no generator in this
repository - these modules are maintained by hand from here, and
`tests/test_attribution_characterization.py` will show any behavior change as a
reviewable baseline diff.
"""

from __future__ import annotations

from confidence import attach_confidence_metadata
from runtime_state import SCHEMA_VERSION

from typing import Any, Dict, Optional

from ..context import AttributionContext


def gate2_case_definition(ctx: AttributionContext) -> Optional[Dict[str, Any]]:
    case_id = ctx.case_id
    contracts = ctx.contracts
    runtime = ctx.runtime
    trial_name = ctx.trial_name
    verifier_obs = ctx.verifier_obs
    verifier_started = ctx.verifier_started

    case_defects = [c for c in contracts if c.get("alignment") == "case_defect"]

    if not case_defects:
        ctx.trace.record(
            gate_id="gate2_case_definition",
            matched=False,
            reason="no case-alignment contract defect",
            checks={"case_defect_contracts": len(case_defects)},
        )
        return None

    cd = case_defects[0]
    ev_refs = [cd["contract_id"]]
    if any(v["obs_id"] == "ver:fail_log" for v in verifier_obs):
        ev_refs.append("ver:fail_log")

    # Check if downstream verifier defects also co-occurred so neither is silently dropped
    co_verifier_defects = [
        c
        for c in contracts
        if c.get("alignment")
        in ("verifier_defect", "verifier_hidden_requirement", "verifier_schema_mismatch")
    ]
    co_triggered_hazards = [
        v for v in verifier_obs if v.get("triggered") and v.get("failure_binding") == "direct"
    ]
    contributing = []
    rec_actions = [
        {
            "owner": "Case",
            "action": f"Add the missing file ({cd['item']}) to `environment/assets/` or update `instruction.md`.",
        }
    ]
    if co_verifier_defects or co_triggered_hazards:
        co_desc = (
            co_verifier_defects[0]["details"]
            if co_verifier_defects
            else co_triggered_hazards[0]["summary"]
        )
        contributing.append(
            attach_confidence_metadata(
                {
                    "category": "verifier",
                    "subtype": "regex_or_parser_defect",
                    "code": "VERIFIER_REGEX_OR_PARSER_DEFECT",
                    "summary": f"Co-occurring verifier defect observed during verification: {co_desc}",
                },
                direct_causal_evidence=1,
            )
        )
        rec_actions.append(
            {
                "owner": "Verifier",
                "action": f"Also fix co-occurring parser/contract issue in `tests/verify.py`: {co_desc}",
            }
        )

    prc = attach_confidence_metadata(
        {
            "category": "case",
            "subtype": "missing_asset",
            "code": "CASE_MISSING_ASSET",
            "summary": cd["details"],
        },
        direct_causal_evidence=len(ev_refs),
        cross_source_corroboration=1,
    )
    h1 = attach_confidence_metadata(
        {
            "hypothesis_id": "H1",
            "category": "case",
            "subtype": "missing_asset",
            "claim": cd["details"],
            "evidence_for": ev_refs,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Add the missing pseudopotential/input asset to `environment/assets/`.",
        },
        direct_causal_evidence=len(ev_refs),
        cross_source_corroboration=1,
    )
    h2 = attach_confidence_metadata(
        {
            "hypothesis_id": "H2",
            "category": "agent",
            "subtype": "path_or_dependency_discovery",
            "claim": "Agent failed to locate the required asset inside the container.",
            "evidence_for": [],
            "evidence_against": [cd["contract_id"]],
            "missing_evidence": [],
            "counterfactual_test": "Verify `environment/assets/` and `Dockerfile` (file is absent).",
        },
        direct_causal_evidence=0,
        contradicting_evidence=1,
    )
    ctx.trace.record(
        gate_id="gate2_case_definition",
        matched=True,
        reason=f"case contract defect: {cd['item']}",
        checks={
            "case_defect_contracts": len(case_defects),
            "co_verifier_defects": len(co_verifier_defects),
            "co_triggered_hazards": len(co_triggered_hazards),
        },
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "trial_name": trial_name,
        "verdict": "failed",
        "failure_stage": "agent_execution",
        "detection_stage": "verifier_execution" if verifier_started else "agent_execution",
        "first_unrecovered_deviation": {
            "status": "identified",
            "event_ref": cd["contract_id"],
            "timestamp": runtime.get("started_at"),
            "summary": cd["details"],
        },
        "failure_manifestation": {
            "type": "missing_task_asset",
            "summary": cd["details"],
        },
        "primary_root_cause": prc,
        "contributing_factors": contributing,
        "competing_hypotheses": [h1, h2],
        "evidence_refs": ev_refs,
        "excluded_hypotheses": [
            {
                "hypothesis_id": "H2",
                "category": "agent",
                "reason": "The asset explicitly promised in `instruction.md` was absent from the task environment.",
            }
        ],
        "recommended_actions": rec_actions,
        "skill_prescription": None,
    }
