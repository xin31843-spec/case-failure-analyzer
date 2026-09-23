#!/usr/bin/env python3
"""
Candidate Hypothesis Generator (`scripts/generate_hypotheses.py`)

Generates structured competing root-cause hypotheses (`candidate-hypotheses.json`)
from objective `evidence.json` observations, attaching supporting evidence,
contradicting evidence, missing discriminating evidence, counterfactual tests,
and heuristic evidence scores (`scripts/confidence.py`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from confidence import attach_confidence_metadata


def generate_candidate_hypotheses(evidence: Dict[str, Any]) -> Dict[str, Any]:
    runtime = evidence.get("runtime") or {}
    agent_started = bool(runtime.get("agent_started", False))
    verifier_started = bool(runtime.get("verifier_started", False))
    errors = evidence.get("error_observations") or []
    contracts = evidence.get("contract_observations") or []
    verifier_obs = evidence.get("verifier_observations") or []
    sci_obs = evidence.get("scientific_observations") or []
    signals = evidence.get("behavioral_signals") or []
    timeline = evidence.get("timeline") or []

    fail_log_obs = next((v for v in verifier_obs if v.get("obs_id") == "ver:fail_log"), None)
    fail_text = fail_log_obs.get("matched_text", "") if fail_log_obs else ""

    candidates: List[Dict[str, Any]] = []
    h_idx = 1

    # 1. Pre-startup / Infrastructure hypotheses
    causal_infra = [e for e in errors if e.get("causal_candidate")]
    if causal_infra:
        primary_err = causal_infra[0]
        ev_for = [e["error_id"] for e in causal_infra]
        ev_against = ["art:trajectory_json"] if agent_started else []
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "infra",
            "subtype": primary_err["subtype"],
            "code": primary_err["code"],
            "claim": f"Infrastructure failure ({primary_err['code']}) during `{primary_err.get('stage')}` blocked execution.",
            "evidence_for": ev_for,
            "evidence_against": ev_against,
            "missing_evidence": [],
            "counterfactual_test": "Pre-pull container image or fix network/runtime environment and re-run.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=len(ev_for),
            cross_source_corroboration=1 if not agent_started else 0,
            contradicting_evidence=len(ev_against),
        )
        candidates.append(h)
        h_idx += 1

    # 2. Case specification hypotheses
    case_defects = [c for c in contracts if c.get("alignment") == "case_defect"]
    if case_defects:
        cd = case_defects[0]
        ev_for = [cd["contract_id"]]
        if fail_log_obs:
            ev_for.append("ver:fail_log")
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "case",
            "subtype": "missing_asset",
            "code": "CASE_MISSING_ASSET",
            "claim": cd["details"],
            "evidence_for": ev_for,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Supply the missing input asset in `environment/assets/` and re-verify.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=len(ev_for),
            cross_source_corroboration=1,
        )
        candidates.append(h)
        h_idx += 1

    # 3. Verifier defect / crash hypotheses
    verifier_crashes = [v for v in verifier_obs if v.get("type") == "verifier_internal_crash"]
    verifier_defects = [c for c in contracts if c.get("alignment") == "verifier_defect"]
    triggered_hazards = [
        v for v in verifier_obs
        if v.get("triggered") and v.get("type") != "verifier_internal_crash"
    ]
    static_hazards = [
        v for v in verifier_obs
        if v.get("hazard_detected") and not v.get("triggered")
    ]

    if verifier_crashes:
        vc = verifier_crashes[0]
        ev_for = [vc["obs_id"], "ver:fail_log"] if fail_log_obs else [vc["obs_id"]]
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "verifier",
            "subtype": "recompute_defect",
            "code": "VERIFIER_RECOMPUTE_DEFECT",
            "claim": vc["summary"],
            "evidence_for": ev_for,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Fix verifier's internal reference/temp file path in `tests/verify.py` and re-run verifier.",
        }
        attach_confidence_metadata(h, direct_causal_evidence=2, cross_source_corroboration=1)
        candidates.append(h)
        h_idx += 1
    elif verifier_defects or triggered_hazards:
        vd = verifier_defects[0] if verifier_defects else None
        th = triggered_hazards[0] if triggered_hazards else None
        is_regex = bool((th and th.get("type") == "parser_hazard") or (vd and "namelist" in vd.get("item", "")))
        ev_for = []
        if vd:
            ev_for.append(vd["contract_id"])
        if th:
            ev_for.append(th["obs_id"])
        if fail_log_obs:
            ev_for.append("ver:fail_log")
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "verifier",
            "subtype": "regex_or_parser_defect" if is_regex else "hidden_contract",
            "code": "VERIFIER_REGEX_OR_PARSER_DEFECT" if is_regex else "VERIFIER_HIDDEN_CONTRACT",
            "claim": vd["details"] if vd else th["summary"],
            "evidence_for": ev_for,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Patch `tests/verify.py` parser/header handling and re-verify existing workspace outputs.",
        }
        attach_confidence_metadata(h, direct_causal_evidence=len(ev_for), cross_source_corroboration=1)
        candidates.append(h)
        h_idx += 1
    elif static_hazards:
        sh = static_hazards[0]
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "verifier",
            "subtype": "regex_or_parser_defect",
            "code": "VERIFIER_REGEX_OR_PARSER_DEFECT",
            "claim": f"Unbound static parser hazard in `verify.py`: {sh['summary']}",
            "evidence_for": [sh["obs_id"]],
            "evidence_against": ["ver:fail_log"] if fail_log_obs else [],
            "missing_evidence": ["Direct binding between failing line and static regex hazard"],
            "counterfactual_test": "Check whether the failing verifier assertion used the static hazard regex.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=0,
            single_keyword_only=True,
            missing_discriminating_evidence=1,
            contradicting_evidence=1 if fail_log_obs else 0,
        )
        candidates.append(h)
        h_idx += 1

    # 4. Numerical trajectory divergence hypothesis (requiring quantitative metric mentions)
    has_structured_numerical = bool(
        re.search(r"(?:trajectory_rmsd\s*=\s*[\d.]+|instantaneous_position.*?>\s*[\d.]+)", fail_text, re.IGNORECASE)
        and re.search(r"(?:ensemble average matches|ensemble.*within tolerance|conserved.*matches)", fail_text, re.IGNORECASE)
    )
    has_partial_numerical_metric = bool(
        re.search(r"(?:trajectory_rmsd|instantaneous_position|ensemble average)", fail_text, re.IGNORECASE)
    )
    if has_structured_numerical:
        ev_for = ["ver:fail_log"] if fail_log_obs else []
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "numerical",
            "subtype": "trajectory_divergence",
            "code": "NUMERICAL_TRAJECTORY_DIVERGENCE",
            "claim": "Lyapunov-sensitive MD trajectory divergence across float/parallel accumulation while ensemble averages match.",
            "evidence_for": ev_for,
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Verify ensemble averages or pin MPI/OMP thread count and RNG seed.",
        }
        attach_confidence_metadata(h, direct_causal_evidence=2, cross_source_corroboration=1)
        candidates.append(h)
        h_idx += 1
    elif has_partial_numerical_metric:
        ev_for = ["ver:fail_log"] if fail_log_obs else []
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "numerical",
            "subtype": "trajectory_divergence",
            "code": "NUMERICAL_TRAJECTORY_DIVERGENCE",
            "claim": "Partial trajectory or ensemble metric mentioned in verifier log without complete trajectory-vs-ensemble comparison.",
            "evidence_for": ev_for,
            "evidence_against": [],
            "missing_evidence": ["Quantitative trajectory RMSD vs ensemble average data", "RNG seed / thread comparison"],
            "counterfactual_test": "Compare agent output trajectory statistics against reference ensemble averages.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=1,
            single_keyword_only=True,
            missing_discriminating_evidence=1,
        )
        candidates.append(h)
        h_idx += 1

    # 5. Agent behavioral / scientific hypotheses
    agent_pos_refs: List[str] = []
    for s in sci_obs:
        agent_pos_refs.append(s["sci_id"])
    for sig in signals:
        if sig.get("signal_type") in (
            "repeated_failed_action",
            "premature_completion",
            "wrong_output_path",
            "scientific_parameter_changed",
            "asset_modified",
        ):
            agent_pos_refs.append(sig["signal_id"])
    for c in contracts:
        if c.get("alignment") == "agent_mismatch":
            agent_pos_refs.append(c["contract_id"])

    if agent_started and agent_pos_refs:
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "agent",
            "subtype": "error_diagnosis" if sci_obs else "task_understanding",
            "code": "AGENT_ERROR_DIAGNOSIS" if sci_obs else "AGENT_TASK_UNDERSTANDING",
            "claim": "Agent decision, input parameter, or missing output violated explicit task requirements.",
            "evidence_for": agent_pos_refs[:4],
            "evidence_against": [],
            "missing_evidence": [],
            "counterfactual_test": "Fix the agent's simulation input or output schema and run `verify.py`.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=len(agent_pos_refs),
            cross_source_corroboration=1 if (sci_obs and signals) else 0,
        )
        candidates.append(h)
        h_idx += 1
    else:
        avail_against = [e["error_id"] for e in causal_infra] or (["ver:internal_crash"] if verifier_crashes else [])
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "agent",
            "subtype": "result_validation",
            "code": "AGENT_RESULT_VALIDATION",
            "claim": "Agent produced invalid or missing simulation results.",
            "evidence_for": [],
            "evidence_against": avail_against,
            "missing_evidence": ["Positive behavioral, scientific, or contract-mismatch evidence implicating agent decisions"],
            "counterfactual_test": "Inspect agent trajectory and generated workspace files for explicit errors.",
        }
        attach_confidence_metadata(
            h,
            direct_causal_evidence=0,
            missing_discriminating_evidence=2,
            contradicting_evidence=len(avail_against) or (1 if not agent_started else 0),
        )
        candidates.append(h)
        h_idx += 1

    # Ensure at least 2 competing hypotheses exist for any non-passed case
    if len(candidates) < 2:
        avail = [a["artifact_id"] for a in (evidence.get("artifacts") or []) if a.get("exists")][:1]
        h = {
            "hypothesis_id": f"H{h_idx}",
            "category": "unknown",
            "subtype": "insufficient_evidence",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
            "claim": "Available logs and artifacts cannot deterministically isolate a single root cause.",
            "evidence_for": avail,
            "evidence_against": [],
            "missing_evidence": ["Complete trajectory and verifier diagnostic logs"],
            "counterfactual_test": "Re-run with full runner and verifier logging enabled.",
        }
        attach_confidence_metadata(h, direct_causal_evidence=0, missing_discriminating_evidence=2)
        candidates.append(h)

    return {
        "case_id": evidence.get("case_id", "unknown"),
        "trial_name": evidence.get("trial_name", "unknown"),
        "candidate_hypotheses": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate candidate root-cause hypotheses from evidence.json.")
    parser.add_argument("--evidence", required=True, type=Path, help="Path to evidence.json")
    parser.add_argument("--output", required=True, type=Path, help="Path to candidate-hypotheses.json")
    args = parser.parse_args()

    ev = json.loads(args.evidence.read_text(encoding="utf-8"))
    res = generate_candidate_hypotheses(ev)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
