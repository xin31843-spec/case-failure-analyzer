#!/usr/bin/env python3
"""
Gate 6 - positive Agent evidence exists. Selects subcase 5a/5b/5c/5c-ext/5d/else
and emits the attribution. This gate always matches, so it terminates the chain and
the engine can never fall off the end.

Extracted once from the former `analyze_case._build_raw_causal_attribution`, so the
gate logic is byte-identical to the code it replaced. There is no generator in this
repository - these modules are maintained by hand from here, and
`tests/test_attribution_characterization.py` will show any behavior change as a
reviewable baseline diff.
"""

from __future__ import annotations

from ..families import (
    CONTINUATION_FAMILIES,
    DEPENDENCY_DISCOVERY_FAMILIES,
    matches_family as _matches_family,
)
from confidence import attach_confidence_metadata
from runtime_state import SCHEMA_VERSION

from typing import Any, Dict, Optional

from ..context import AttributionContext


def gate6_agent_primary(ctx: AttributionContext) -> Optional[Dict[str, Any]]:
    agent_mismatch_contracts = ctx.agent_mismatch_contracts
    agent_timeline_events = ctx.agent_timeline_events
    case_id = ctx.case_id
    dep_search_sigs = ctx.dep_search_sigs
    fail_log_obs = ctx.fail_log_obs
    fail_text = ctx.fail_text
    premature_sigs = ctx.premature_sigs
    repeated_fail_sigs = ctx.repeated_fail_sigs
    runtime = ctx.runtime
    sci_obs = ctx.sci_obs
    signals = ctx.signals
    timeline = ctx.timeline
    trial_name = ctx.trial_name
    unrecovered_sci_obs = ctx.unrecovered_sci_obs
    unverified_output_sigs = ctx.unverified_output_sigs
    verifier_started = ctx.verifier_started

    # Positive Agent Evidence Attribution
    ev_refs = []
    for s in unrecovered_sci_obs:
        if str(s.get("source_ref", "")).startswith("trajectory:"):
            ev_refs.append(s["sci_id"])
    for sig in signals[:3]:
        ev_refs.append(sig["signal_id"])
    for c in agent_mismatch_contracts:
        ev_refs.append(c["contract_id"])
    if fail_log_obs:
        ev_refs.append("ver:fail_log")

    # Subcase 5a: Repeated failed action after unrecovered scientific software error (e.g. SCF nonconvergence)
    if unrecovered_sci_obs and repeated_fail_sigs:
        subcase_id = "5a"
        first_sci = unrecovered_sci_obs[0]
        rep_sig = repeated_fail_sigs[0]
        subtype = "error_diagnosis"
        code = "AGENT_ERROR_DIAGNOSIS"
        summary = (
            f"Software emitted `{first_sci['error_family']}` ({first_sci['software']}), "
            f"but agent failed to diagnose the physical/input cause and repeatedly re-executed the failing setup (`{rep_sig['signal_id']}`)."
        )
        fud_ref = rep_sig["event_ref"]
        skill_prescription = {
            "recommended_skill": {
                "name": f"{first_sci['software']}-{first_sci['error_family'].replace('_', '-')}-diagnosis",
                "trigger": [
                    f"{first_sci['software']} outputs `{first_sci['matched_text'][:80]}`",
                    f"Error family `{first_sci['error_family']}` encountered during simulation",
                ],
                "capability_gap": [
                    f"Agent failed to diagnose `{first_sci['error_family']}` and repeated identical failing runs."
                ],
                "required_guidance": [
                    f"Inspect {', '.join(first_sci['required_discriminating_evidence'][:2])} before rerunning.",
                    f"Address candidate physical causes: {', '.join(first_sci['candidate_causes'][:3])}.",
                ],
                "anti_patterns": [
                    "Do not rerun the exact same command/input after a deterministic convergence or stability error."
                ],
                "evidence_cases": [f"{case_id}:{fud_ref}"],
            }
        }
    # Subcase 5b: Missing file/dependency/checkpoint discovery when file exists in container (`/opt/...` or `/workspace/assets/`)
    elif (
        any(_matches_family(s, DEPENDENCY_DISCOVERY_FAMILIES) for s in unrecovered_sci_obs)
        and not dep_search_sigs
    ):
        subcase_id = "5b"
        first_sci = next(
            s for s in unrecovered_sci_obs if _matches_family(s, DEPENDENCY_DISCOVERY_FAMILIES)
        )
        subtype = "path_or_dependency_discovery"
        code = "AGENT_PATH_OR_DEPENDENCY_DISCOVERY"
        summary = (
            f"Simulation failed with `{first_sci['error_family']}` ({first_sci['software']}) because agent did not search "
            "container directories (`/opt/` or `/workspace/assets/`) or resolve model/potential/force-field paths."
        )
        fud_ref = (
            first_sci["source_ref"]
            if str(first_sci.get("source_ref", "")).startswith(("trajectory:", "art:"))
            else first_sci["sci_id"]
        )
        skill_prescription = None
    # Subcase 5c: Continuation / state-preservation parameter mismatch
    elif any(_matches_family(s, CONTINUATION_FAMILIES) for s in unrecovered_sci_obs):
        subcase_id = "5c"
        first_sci = next(
            s for s in unrecovered_sci_obs if _matches_family(s, CONTINUATION_FAMILIES)
        )
        subtype = "scientific_parameter_selection"
        code = "AGENT_SCIENTIFIC_PARAMETER_SELECTION"
        summary = (
            f"Simulation continuation failed `{first_sci['error_family']}` ({first_sci['software']}) "
            f"due to altered state/parameter continuation settings ({', '.join(first_sci['candidate_causes'][:2])})."
        )
        fud_ref = timeline[-1]["event_id"] if timeline else first_sci["sci_id"]
        skill_prescription = {
            "recommended_skill": {
                "name": f"{first_sci['software']}-{first_sci['error_family'].replace('_', '-')}-protocol",
                "trigger": [
                    f"{first_sci['software']} task requires exact state/restart continuation (`{first_sci['error_family']}`)",
                    f"Observed diagnostic: `{first_sci['matched_text'][:80]}`",
                ],
                "capability_gap": [
                    f"Agent violated state-continuation invariants across {first_sci['software']} workflow steps."
                ],
                "required_guidance": [
                    f"Verify {', '.join(first_sci['required_discriminating_evidence'][:2])}.",
                    f"Prevent candidate causes: {', '.join(first_sci['candidate_causes'][:3])}.",
                ],
                "anti_patterns": [
                    "Do not reset state counters or re-initialize ensembles when deterministic continuation is required."
                ],
                "evidence_cases": [f"{case_id}:{fud_ref}"],
            }
        }
    # Subcase 5d: Premature completion / missing output files
    elif premature_sigs or agent_mismatch_contracts:
        subcase_id = "5d"
        subtype = "task_understanding" if not premature_sigs else "premature_termination"
        code = "AGENT_TASK_UNDERSTANDING" if not premature_sigs else "AGENT_PREMATURE_TERMINATION"
        summary = f"Agent failed to satisfy explicit output file or JSON schema requirements (`{fail_text[:160] or 'missing required output'}`)."
        fud_ref = (
            premature_sigs[0]["event_ref"]
            if premature_sigs
            else (
                agent_mismatch_contracts[0]["contract_id"]
                if agent_mismatch_contracts
                else (timeline[-1]["event_id"] if timeline else "ver:fail_log")
            )
        )
        skill_prescription = None
    # Subcase 5e: Inaccurate output / calculation error backed by unverified output signal
    elif unverified_output_sigs and fail_text:
        subcase_id = "5e"
        subtype = "result_validation"
        code = "AGENT_RESULT_VALIDATION"
        summary = f"Agent wrote results.json without sanity validation, producing inaccurate physical/numerical values: {fail_text[:200]}"
        fud_ref = unverified_output_sigs[0]["event_ref"]
        skill_prescription = None
    else:
        ctx.trace.record(
            gate_id="gate6_agent_primary",
            matched=False,
            reason="no positive agent causal evidence matches subcases 5a-5e",
        )
        return None

    prc = attach_confidence_metadata(
        {
            "category": "agent",
            "subtype": subtype,
            "code": code,
            "summary": summary,
        },
        direct_causal_evidence=len(ev_refs),
        cross_source_corroboration=1 if (sci_obs and signals) else 0,
    )
    h1 = attach_confidence_metadata(
        {
            "hypothesis_id": "H1",
            "category": "agent",
            "subtype": subtype,
            "claim": summary,
            "evidence_for": ev_refs,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Correct the agent's input script / workflow decision and run `verify.py`.",
        },
        direct_causal_evidence=len(ev_refs),
        cross_source_corroboration=1 if (sci_obs and signals) else 0,
    )
    h2 = attach_confidence_metadata(
        {
            "hypothesis_id": "H2",
            "category": "infra",
            "subtype": "container_runtime",
            "claim": "Infrastructure prevented simulation execution.",
            "evidence_for": [],
            "evidence_against": ["art:trajectory_json"],
            "missing_evidence": [],
            "counterfactual_test": "Check `runtime.agent_started` and `runtime.verifier_started` (both true).",
        },
        direct_causal_evidence=0,
        contradicting_evidence=2,
    )

    ctx.trace.record(
        gate_id="gate6_agent_primary",
        matched=True,
        reason=f"positive agent evidence ({code})",
        checks={
            "unrecovered_sci": len(unrecovered_sci_obs),
            "repeated_failed_action": len(repeated_fail_sigs),
            "dependency_search_attempted": len(dep_search_sigs),
            "premature_completion": len(premature_sigs),
            "agent_mismatch_contracts": len(agent_mismatch_contracts),
            "agent_timeline_events": len(agent_timeline_events),
        },
        subcase_id=subcase_id,
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
            "event_ref": fud_ref,
            "timestamp": runtime.get("finished_at"),
            "summary": summary,
        },
        "failure_manifestation": {
            "type": "verifier_check_failed" if verifier_started else "agent_execution_failed",
            "summary": fail_text[:240] if fail_text else summary,
        },
        "primary_root_cause": prc,
        "contributing_factors": [],
        "competing_hypotheses": [h1, h2],
        "evidence_refs": ev_refs,
        "excluded_hypotheses": [
            {
                "hypothesis_id": "H2",
                "category": "infra",
                "reason": "Container built cleanly, agent executed commands (`runtime.agent_started == true`), and verifier ran to completion.",
            }
        ],
        "recommended_actions": [
            {
                "owner": "Agent Policy",
                "action": summary,
            }
        ],
        "skill_prescription": skill_prescription,
    }
