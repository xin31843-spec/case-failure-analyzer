#!/usr/bin/env python3
"""
Unified Entrypoint, Evidence Collector & Conservative Causal Attribution Engine (`scripts/analyze_case.py`)

Pipeline:
  1. Artifact Discovery (`discover_artifacts.py` + `runtime_state.py`)
  2. Trajectory Normalization (`normalize_trajectory.py`)
  3. Runtime & Infra Error Extraction (`extract_runtime_errors.py`)
  4. Prompt / Task / Verifier Contract Audit (`audit_contract.py`)
  5. Scientific Software Error Extraction (`extract_scientific_errors.py`)
  6. Candidate Hypothesis Generation (`generate_hypotheses.py`)
  7. Conservative Causal Attribution (`analysis.json`)
  8. Schema & Attribution Constraint Validation (`validate_analysis.py`)
  9. Bilingual Report & Skill Prescription Rendering (`render_report.py`)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_contract import audit_contract
from confidence import attach_confidence_metadata
from discover_artifacts import discover_all, discover_trials
from extract_runtime_errors import extract_runtime_errors
from extract_scientific_errors import extract_scientific_errors
from generate_hypotheses import generate_candidate_hypotheses
from normalize_trajectory import normalize_trajectory
from render_report import render_report_markdown, render_skill_prescription_markdown
from runtime_state import SCHEMA_VERSION
from validate_analysis import validate_all


class ReplayNotSupportedError(RuntimeError):
    """Raised when `--replay` is requested without a supported isolated container runtime."""


def run_isolated_verifier_replay(
    task_dir: Optional[Path], trial_dir: Optional[Path], timeout_sec: int = 30
) -> Dict[str, Any]:
    raise ReplayNotSupportedError(
        "Verifier/simulation replay is not implemented for offline static task analysis. "
        "Use `--replay none` (default) for read-only forensic analysis."
    )


def _matches_family(sci_entry: Dict[str, Any], targets: Tuple[str, ...]) -> bool:
    fam = sci_entry.get("error_family", "")
    aliases = sci_entry.get("aliases") or []
    return fam in targets or any(a in targets for a in aliases)


def collect_case_evidence(
    trial_inv: Dict[str, Any],
    job_dir: Path,
    max_log_bytes: int = 120000,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    trial_dir = Path(trial_inv["trial_dir"]) if trial_inv.get("trial_dir") else None
    task_dir = Path(trial_inv["task_dir"]) if trial_inv.get("task_dir") else None

    traj_path = trial_dir / "agent" / "trajectory.json" if trial_dir else None
    norm_traj = normalize_trajectory(traj_path, max_obs_bytes=max(1500, max_log_bytes // 40))

    runtime_err_res = extract_runtime_errors(
        job_dir=job_dir,
        trial_dir=trial_dir,
        max_log_bytes=max_log_bytes,
    )

    contract_res = audit_contract(
        task_dir=task_dir,
        trial_dir=trial_dir,
        normalized_traj=norm_traj,
    )

    sci_res = extract_scientific_errors(
        trial_dir=trial_dir,
        normalized_traj=norm_traj,
    )

    evidence: Dict[str, Any] = {
        "case_id": trial_inv["case_id"],
        "trial_name": trial_inv["trial_name"],
        "job_dir": trial_inv["job_dir"],
        "trial_dir": trial_inv["trial_dir"],
        "task_dir": trial_inv["task_dir"],
        "artifacts": trial_inv["artifacts"],
        "runtime": trial_inv["runtime"],
        "metadata": trial_inv.get("metadata", {}),
        "timeline": norm_traj["events"],
        "behavioral_signals": norm_traj["behavioral_signals"],
        "error_observations": runtime_err_res["error_observations"],
        "contract_observations": contract_res["contract_observations"],
        "verifier_observations": contract_res["verifier_observations"],
        "scientific_observations": sci_res["scientific_observations"],
        "missing_artifacts": trial_inv["missing_artifacts"],
    }
    cand_hyps = generate_candidate_hypotheses(evidence)
    return evidence, norm_traj, contract_res, cand_hyps


def build_causal_attribution(
    evidence: Dict[str, Any],
    norm_traj: Dict[str, Any],
    contract_res: Dict[str, Any],
    cand_hyps: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if cand_hyps is None:
        cand_hyps = generate_candidate_hypotheses(evidence)

    case_id = evidence.get("case_id", "unknown")
    trial_name = evidence.get("trial_name", case_id)
    runtime = evidence.get("runtime") or {}
    agent_started = bool(runtime.get("agent_started", False))
    verifier_started = bool(runtime.get("verifier_started", False))
    verification_status = runtime.get("verification_status")
    exit_status = runtime.get("exit_status", "unknown")
    reward = runtime.get("reward")

    errors = evidence.get("error_observations") or []
    contracts = evidence.get("contract_observations") or []
    verifier_obs = evidence.get("verifier_observations") or []
    sci_obs = evidence.get("scientific_observations") or []
    signals = evidence.get("behavioral_signals") or []
    timeline = evidence.get("timeline") or []

    # ── Gate 0: Did the trial pass verification? ─────────────────────────────
    if (verification_status == "passed") or (reward is not None and reward >= 1.0):
        prc = attach_confidence_metadata(
            {
                "category": "none",
                "subtype": "none",
                "code": "NONE",
                "summary": "No failure occurred; trial completed and passed verification (reward >= 1.0).",
            },
            direct_causal_evidence=2,
            cross_source_corroboration=1,
        )
        prc["confidence"] = 1.0
        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "passed",
            "failure_stage": "none",
            "detection_stage": "verifier_execution",
            "first_unrecovered_deviation": None,
            "failure_manifestation": {
                "type": "none",
                "summary": "Trial completed and passed all verifier checks (reward=1.0).",
            },
            "primary_root_cause": prc,
            "contributing_factors": [],
            "competing_hypotheses": [],
            "evidence_refs": ["art:trial_result"],
            "excluded_hypotheses": [],
            "recommended_actions": [],
            "skill_prescription": None,
        }

    # ── Gate 1: Did the Agent start? Pre-startup Infrastructure Gate ──────────
    causal_infra_errors = [e for e in errors if e.get("causal_candidate")]
    if not agent_started:
        if causal_infra_errors:
            net_errs = [e for e in causal_infra_errors if e["code"] == "INFRA_EXTERNAL_NETWORK"]
            primary_err = net_errs[0] if net_errs else causal_infra_errors[0]
            secondary_errs = [e for e in causal_infra_errors if e["error_id"] != primary_err["error_id"]]

            contributing = []
            for se in secondary_errs:
                cf = attach_confidence_metadata(
                    {
                        "category": "infra",
                        "subtype": se["subtype"],
                        "code": se["code"],
                        "summary": f"Accompanying infrastructure error: {se['matched_text'][:140]}",
                    },
                    direct_causal_evidence=1,
                )
                contributing.append(cf)

            ev_refs = [e["error_id"] for e in causal_infra_errors]
            if any(a["artifact_id"] == "art:trial_result" and a["exists"] for a in evidence["artifacts"]):
                ev_refs.append("art:trial_result")

            prc = attach_confidence_metadata(
                {
                    "category": "infra",
                    "subtype": primary_err["subtype"],
                    "code": primary_err["code"],
                    "summary": (
                        f"Container environment failed during `{primary_err.get('stage')}` ({primary_err['code']}); "
                        "agent never started (`runtime.agent_started == false`)."
                    ),
                },
                direct_causal_evidence=len(ev_refs),
                cross_source_corroboration=1,
            )

            h1 = attach_confidence_metadata(
                {
                    "hypothesis_id": "H1",
                    "category": "infra",
                    "subtype": primary_err["subtype"],
                    "claim": "Container build / network failure prevented trial startup.",
                    "evidence_for": ev_refs,
                    "evidence_against": [],
                    "missing_evidence": [],
                    "counterfactual_test": "Pre-pull image or configure local Docker/apt mirror and re-run.",
                },
                direct_causal_evidence=len(ev_refs),
                cross_source_corroboration=1,
            )
            h2 = attach_confidence_metadata(
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "subtype": "premature_termination",
                    "claim": "Agent failed to produce output files.",
                    "evidence_for": [],
                    "evidence_against": ev_refs,
                    "missing_evidence": ["agent/trajectory.json"],
                    "counterfactual_test": "N/A (agent never launched)",
                },
                direct_causal_evidence=0,
                contradicting_evidence=2,
            )
            h2["confidence"] = 0.0

            return {
                "schema_version": "failure-analysis-v1",
                "case_id": case_id,
                "trial_name": trial_name,
                "verdict": "errored",
                "failure_stage": primary_err.get("stage", "environment_build"),
                "detection_stage": "runner",
                "first_unrecovered_deviation": {
                    "status": "identified",
                    "event_ref": primary_err["error_id"],
                    "timestamp": runtime.get("started_at"),
                    "summary": f"Environment build/setup failed ({primary_err['code']}) before agent container could start.",
                },
                "failure_manifestation": {
                    "type": "dependency_install_failure"
                    if primary_err["code"] == "INFRA_EXTERNAL_NETWORK"
                    else "container_build_failure",
                    "summary": primary_err["matched_text"][:240],
                },
                "primary_root_cause": prc,
                "contributing_factors": contributing,
                "competing_hypotheses": [h1, h2],
                "evidence_refs": ev_refs,
                "excluded_hypotheses": [
                    {
                        "hypothesis_id": "H2",
                        "category": "agent",
                        "reason": (
                            "Ruled out by Hard Attribution Gate: `runtime.agent_started == false` and "
                            "`agent/trajectory.json` was never created because container setup exited prior to agent launch."
                        ),
                    }
                ],
                "recommended_actions": [
                    {
                        "owner": "Infra",
                        "action": "Pre-pull base Docker images (`docker pull`) and configure resilient registry/apt mirrors before launching benchmark jobs.",
                    }
                ],
                "skill_prescription": None,
            }
        else:
            # Agent did not start AND no logs/errors explain why -> Unknown (never Agent)
            avail_refs = [a["artifact_id"] for a in evidence["artifacts"] if a["exists"]][:2]
            if not avail_refs and evidence["artifacts"]:
                avail_refs = [evidence["artifacts"][0]["artifact_id"]]
            prc = attach_confidence_metadata(
                {
                    "category": "unknown",
                    "subtype": "insufficient_evidence",
                    "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
                    "summary": "Insufficient log artifacts to determine why execution terminated prior to agent startup.",
                },
                direct_causal_evidence=0,
                missing_discriminating_evidence=2,
            )
            return {
                "schema_version": "failure-analysis-v1",
                "case_id": case_id,
                "trial_name": trial_name,
                "verdict": "errored",
                "failure_stage": "unknown",
                "detection_stage": "runner",
                "first_unrecovered_deviation": {
                    "status": "not_identified",
                    "event_ref": None,
                    "timestamp": runtime.get("started_at"),
                    "summary": "Agent did not start and no exception or container build logs are available to pinpoint the failure.",
                },
                "failure_manifestation": {
                    "type": "missing_execution_logs",
                    "summary": "Agent did not start and no exception or build logs are available.",
                },
                "primary_root_cause": prc,
                "contributing_factors": [],
                "competing_hypotheses": cand_hyps["candidate_hypotheses"],
                "evidence_refs": avail_refs,
                "excluded_hypotheses": [
                    {
                        "hypothesis_id": "H_AGENT",
                        "category": "agent",
                        "reason": "Agent never started (`runtime.agent_started == false`); cannot blame agent without trajectory.",
                    }
                ],
                "recommended_actions": [
                    {
                        "owner": "Infra",
                        "action": "Preserve runner `exception.txt` and `trial.log` when container setup aborts.",
                    }
                ],
                "skill_prescription": None,
            }

    # ── Gate 2: Case Definition Defects (e.g., Prompt references non-existent asset) ──
    case_defects = [c for c in contracts if c.get("alignment") == "case_defect"]
    if case_defects:
        cd = case_defects[0]
        ev_refs = [cd["contract_id"]]
        if any(v["obs_id"] == "ver:fail_log" for v in verifier_obs):
            ev_refs.append("ver:fail_log")

        # Check if downstream verifier defects also co-occurred so neither is silently dropped
        co_verifier_defects = [c for c in contracts if c.get("alignment") == "verifier_defect"]
        co_triggered_hazards = [
            v for v in verifier_obs
            if v.get("triggered") and v.get("failure_binding") == "direct"
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

    # ── Gate 3: Verifier Internal Crashes, Parser Defects & Hidden Contracts (`verifier`) ──
    verifier_crashes = [v for v in verifier_obs if v.get("type") == "verifier_internal_crash"]
    verifier_defects = [c for c in contracts if c.get("alignment") == "verifier_defect"]
    triggered_hazards = [
        v for v in verifier_obs
        if v.get("triggered") and v.get("failure_binding") == "direct" and v.get("type") != "verifier_internal_crash"
    ]

    if verifier_crashes or verifier_defects or triggered_hazards:
        vc = verifier_crashes[0] if verifier_crashes else None
        vd = verifier_defects[0] if verifier_defects else None
        th = triggered_hazards[0] if triggered_hazards else None

        if vc:
            code = vc.get("code", "VERIFIER_RECOMPUTE_DEFECT")
            subtype = vc.get("subtype", "recompute_defect")
            summary = vc["summary"]
        else:
            is_regex_defect = bool(
                (th and th.get("type") == "parser_hazard")
                or (vd and "namelist" in vd.get("item", ""))
            )
            code = "VERIFIER_REGEX_OR_PARSER_DEFECT" if is_regex_defect else "VERIFIER_HIDDEN_CONTRACT"
            subtype = "regex_or_parser_defect" if is_regex_defect else "hidden_contract"
            summary = (
                vd["details"]
                if vd
                else (th["summary"] if th else "Verifier parser/contract defect rejected valid agent output.")
            )

        ev_refs = []
        if vc:
            ev_refs.append(vc["obs_id"])
        if vd:
            ev_refs.append(vd["contract_id"])
        if th:
            ev_refs.append(th["obs_id"])
        if any(v["obs_id"] == "ver:fail_log" for v in verifier_obs):
            ev_refs.append("ver:fail_log")

        fail_summary = next(
            (v["summary"] for v in verifier_obs if v["obs_id"] == "ver:fail_log"),
            summary,
        )

        contributing = []
        if not vc:
            contributing.append(
                attach_confidence_metadata(
                    {
                        "category": "case",
                        "subtype": "ambiguous_contract",
                        "code": "CASE_AMBIGUOUS_CONTRACT",
                        "summary": "Prompt did not explicitly constrain input/log syntax formatting assumed by `verify.py`.",
                    },
                    direct_causal_evidence=1,
                )
            )

        prc = attach_confidence_metadata(
            {
                "category": "verifier",
                "subtype": subtype,
                "code": code,
                "summary": summary,
            },
            direct_causal_evidence=len(ev_refs),
            cross_source_corroboration=1,
        )
        h1 = attach_confidence_metadata(
            {
                "hypothesis_id": "H1",
                "category": "verifier",
                "subtype": subtype,
                "claim": summary,
                "evidence_for": ev_refs,
                "evidence_against": [],
                "missing_evidence": [],
                "counterfactual_test": "Fix `tests/verify.py` internal file/parser logic and re-verify existing trial artifacts.",
            },
            direct_causal_evidence=len(ev_refs),
            cross_source_corroboration=1,
        )
        h2 = attach_confidence_metadata(
            {
                "hypothesis_id": "H2",
                "category": "agent",
                "subtype": "result_validation",
                "claim": "Agent produced invalid or missing simulation results.",
                "evidence_for": [],
                "evidence_against": ev_refs,
                "missing_evidence": [],
                "counterfactual_test": "Inspect agent's workspace outputs against `instruction.md` requirements.",
            },
            direct_causal_evidence=0,
            contradicting_evidence=1,
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
                "event_ref": ev_refs[0] if ev_refs else "ver:fail_log",
                "timestamp": (runtime.get("stages", {}).get("verifier") or {}).get("started_at"),
                "summary": summary,
            },
            "failure_manifestation": {
                "type": "verifier_internal_crash" if vc else "verifier_false_rejection",
                "summary": fail_summary,
            },
            "primary_root_cause": prc,
            "contributing_factors": contributing,
            "competing_hypotheses": [h1, h2],
            "evidence_refs": ev_refs,
            "excluded_hypotheses": [
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "reason": (
                        "Verifier crashed internally on its own reference/temp file before validating agent output."
                        if vc
                        else "Agent's simulation outputs satisfied the prompt contract before hitting the causally bound verifier parser/header defect."
                    ),
                }
            ],
            "recommended_actions": [
                {
                    "owner": "Verifier",
                    "action": (
                        f"Fix `tests/verify.py` ({code}): ensure internal reference paths exist and use robust namelist/float/header parsing."
                    ),
                }
            ],
            "skill_prescription": None,
        }

    # ── Gate 4: Numerical / Stochastic Trajectory Drift (`numerical`) ─────────
    fail_log_obs = next((v for v in verifier_obs if v["obs_id"] == "ver:fail_log"), None)
    fail_text = fail_log_obs["matched_text"] if fail_log_obs else ""
    has_structured_numerical = bool(
        re.search(r"(?:trajectory_rmsd\s*=\s*[\d.]+|instantaneous_position.*?>\s*[\d.]+)", fail_text, re.IGNORECASE)
        and re.search(r"(?:ensemble average matches|ensemble.*within tolerance|conserved.*matches)", fail_text, re.IGNORECASE)
    )
    if has_structured_numerical:
        ev_refs = ["ver:fail_log"] if fail_log_obs else ["art:trial_result"]
        prc = attach_confidence_metadata(
            {
                "category": "numerical",
                "subtype": "trajectory_divergence",
                "code": "NUMERICAL_TRAJECTORY_DIVERGENCE",
                "summary": "Floating-point/parallel accumulation caused pointwise MD trajectory drift despite valid ensemble statistics.",
            },
            direct_causal_evidence=2,
            cross_source_corroboration=1,
        )
        cf_tol = attach_confidence_metadata(
            {
                "category": "verifier",
                "subtype": "tolerance_too_strict",
                "code": "VERIFIER_TOLERANCE_TOO_STRICT",
                "summary": "Verifier compared instantaneous late-step coordinates/energies rather than ensemble averages.",
            },
            direct_causal_evidence=1,
        )
        h1 = attach_confidence_metadata(
            {
                "hypothesis_id": "H1",
                "category": "numerical",
                "subtype": "trajectory_divergence",
                "claim": "Chaotic MD trajectory divergence across float accumulation while ensemble averages match.",
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
                "summary": "Chaotic MD trajectory divergence while ensemble statistics remained consistent.",
            },
            "failure_manifestation": {
                "type": "numerical_trajectory_divergence",
                "summary": fail_text[:240],
            },
            "primary_root_cause": prc,
            "contributing_factors": [cf_tol],
            "competing_hypotheses": [h1, h2],
            "evidence_refs": ev_refs,
            "excluded_hypotheses": [
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "reason": "Agent used the requested parameters and ensemble averages matched reference tolerances; divergence is chaotic float sensitivity.",
                }
            ],
            "recommended_actions": [
                {
                    "owner": "Verifier",
                    "action": "Verify ensemble averages or conserved-quantity drift rather than chaotic late-step instantaneous values, or pin MPI/OMP thread counts.",
                }
            ],
            "skill_prescription": None,
        }

    # ── Gate 5: Positive Agent Evidence Check vs Calibrated `unknown` ─────────
    repeated_fail_sigs = [s for s in signals if s["signal_type"] == "repeated_failed_action"]
    dep_search_sigs = [s for s in signals if s["signal_type"] == "dependency_search_attempted"]
    premature_sigs = [s for s in signals if s["signal_type"] == "premature_completion"]
    agent_mismatch_contracts = [c for c in contracts if c.get("alignment") == "agent_mismatch"]
    agent_timeline_events = [ev for ev in timeline if ev.get("actor") == "agent"]

    # Check if there is positive evidence implicating Agent actions/decisions
    has_positive_agent_evidence = bool(
        sci_obs
        or repeated_fail_sigs
        or premature_sigs
        or agent_mismatch_contracts
        or (
            agent_timeline_events
            and fail_text
            and re.search(r"(?:got\s+[-+\d.eEdD]+|mismatch|missing key|Missing:)", fail_text, re.IGNORECASE)
        )
    )

    if not has_positive_agent_evidence:
        avail_refs = []
        if fail_log_obs:
            avail_refs.append("ver:fail_log")
        for a in evidence["artifacts"]:
            if a["exists"] and len(avail_refs) < 2:
                avail_refs.append(a["artifact_id"])
        if not avail_refs and evidence["artifacts"]:
            avail_refs = [evidence["artifacts"][0]["artifact_id"]]

        prc = attach_confidence_metadata(
            {
                "category": "unknown",
                "subtype": "insufficient_evidence",
                "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
                "summary": (
                    "Available logs and trajectory events do not provide positive causal evidence "
                    "to attribute the failure to Agent decisions, Verifier defects, or Infrastructure."
                ),
            },
            direct_causal_evidence=0,
            missing_discriminating_evidence=2,
        )
        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "failed",
            "failure_stage": "unknown",
            "detection_stage": "verifier_execution" if verifier_started else "runner",
            "first_unrecovered_deviation": {
                "status": "not_identified",
                "event_ref": None,
                "timestamp": runtime.get("finished_at"),
                "summary": "No unrecovered agent decision or deterministic infrastructure/verifier defect could be isolated from available artifacts.",
            },
            "failure_manifestation": {
                "type": "unattributed_verification_failure" if fail_text else "unknown_failure",
                "summary": fail_text[:240] if fail_text else "Trial failed without positive causal evidence.",
            },
            "primary_root_cause": prc,
            "contributing_factors": [],
            "competing_hypotheses": cand_hyps["candidate_hypotheses"],
            "evidence_refs": avail_refs,
            "excluded_hypotheses": [],
            "recommended_actions": [
                {
                    "owner": "Infra",
                    "action": "Collect complete `agent/trajectory.json` and detailed `verifier/verify.log` tracebacks to disambiguate competing hypotheses.",
                }
            ],
            "skill_prescription": None,
        }

    # Positive Agent Evidence Attribution
    ev_refs = []
    for s in sci_obs:
        ev_refs.append(s["sci_id"])
    for sig in signals[:3]:
        ev_refs.append(sig["signal_id"])
    for c in agent_mismatch_contracts:
        ev_refs.append(c["contract_id"])
    if not any(r.startswith(("sig:", "contract:", "sci:")) for r in ev_refs) and agent_timeline_events:
        ev_refs.append(agent_timeline_events[-1]["event_id"])
    if fail_log_obs:
        ev_refs.append("ver:fail_log")

    # Subcase 5a: Repeated failed action after scientific software error (e.g. SCF nonconvergence)
    if sci_obs and repeated_fail_sigs:
        first_sci = sci_obs[0]
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
    # Subcase 5b: Missing file/dependency discovery when file exists in container (`/opt/...` or `/workspace/assets/`)
    elif (
        any(
            _matches_family(
                s,
                (
                    "basis_or_potential_missing",
                    "pseudopotential_read_failure",
                    "pseudopotential_mismatch_or_missing",
                ),
            )
            for s in sci_obs
        )
        and not dep_search_sigs
    ):
        first_sci = sci_obs[0]
        subtype = "path_or_dependency_discovery"
        code = "AGENT_PATH_OR_DEPENDENCY_DISCOVERY"
        summary = (
            f"Simulation failed with `{first_sci['error_family']}` because agent did not search container directories "
            "(`/opt/` or `/workspace/assets/`) to locate or symlink existing basis/potential files."
        )
        fud_ref = first_sci["source_ref"]
        skill_prescription = None
    # Subcase 5c: Continuation / state-preservation parameter mismatch
    elif any(
        _matches_family(s, ("restart_or_timestep_continuation_mismatch", "restart_continuation_divergence"))
        for s in sci_obs
    ):
        first_sci = next(
            s
            for s in sci_obs
            if _matches_family(s, ("restart_or_timestep_continuation_mismatch", "restart_continuation_divergence"))
        )
        subtype = "scientific_parameter_selection"
        code = "AGENT_SCIENTIFIC_PARAMETER_SELECTION"
        summary = (
            f"Simulation continuation failed `{first_sci['error_family']}` ({first_sci['software']}) "
            f"due to altered state/parameter continuation settings ({', '.join(first_sci['candidate_causes'][:2])})."
        )
        fud_ref = timeline[-1]["event_id"] if timeline else first_sci["source_ref"]
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
        subtype = "task_understanding" if not premature_sigs else "premature_termination"
        code = "AGENT_TASK_UNDERSTANDING" if not premature_sigs else "AGENT_PREMATURE_TERMINATION"
        summary = (
            f"Agent failed to satisfy explicit output file or JSON schema requirements (`{fail_text[:160] or 'missing required output'}`)."
        )
        fud_ref = premature_sigs[0]["event_ref"] if premature_sigs else (
            agent_mismatch_contracts[0]["contract_id"]
            if agent_mismatch_contracts
            else (timeline[-1]["event_id"] if timeline else "ver:fail_log")
        )
        skill_prescription = None
    else:
        subtype = "result_validation"
        code = "AGENT_RESULT_VALIDATION"
        summary = f"Agent completed execution with trajectory actions, but produced inaccurate physical/numerical values: {fail_text[:200]}"
        fud_ref = agent_timeline_events[-1]["event_id"] if agent_timeline_events else ev_refs[0]
        skill_prescription = None

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

    return {
        "schema_version": "failure-analysis-v1",
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


def analyze_single_trial(
    trial_inv: Dict[str, Any],
    job_dir: Path,
    max_log_bytes: int = 120000,
    replay_mode: str = "none",
) -> Tuple[Dict[str, Any], Dict[str, Any], str, Optional[str]]:
    if replay_mode != "none":
        run_isolated_verifier_replay(
            Path(trial_inv["task_dir"]) if trial_inv.get("task_dir") else None,
            Path(trial_inv["trial_dir"]) if trial_inv.get("trial_dir") else None,
        )

    evidence, norm_traj, contract_res, cand_hyps = collect_case_evidence(
        trial_inv=trial_inv,
        job_dir=job_dir,
        max_log_bytes=max_log_bytes,
    )

    analysis = build_causal_attribution(evidence, norm_traj, contract_res, cand_hyps)
    report_md = render_report_markdown(evidence, analysis, lang="bilingual")

    ok, val_errors = validate_all(evidence, analysis, report_md)
    if not ok:
        raise RuntimeError(f"Generated analysis failed schema/constraint validation: {val_errors}")

    skill_md = None
    if analysis.get("skill_prescription"):
        skill_md = render_skill_prescription_markdown(analysis["skill_prescription"])

    return evidence, analysis, report_md, skill_md


def write_outputs(
    out_dir: Path,
    evidence: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    report_md: Optional[str],
    skill_md: Optional[str],
    cand_hyps: Optional[Dict[str, Any]] = None,
    fmt: str = "both",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt in ("json", "both"):
        (out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if cand_hyps is not None:
            (out_dir / "candidate-hypotheses.json").write_text(
                json.dumps(cand_hyps, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if analysis is not None:
            (out_dir / "analysis.json").write_text(
                json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    if fmt in ("markdown", "both") and report_md is not None and analysis is not None:
        (out_dir / "report.md").write_text(report_md, encoding="utf-8")
        (out_dir / "report.zh.md").write_text(
            render_report_markdown(evidence, analysis, lang="zh"), encoding="utf-8"
        )
        (out_dir / "report.en.md").write_text(
            render_report_markdown(evidence, analysis, lang="en"), encoding="utf-8"
        )
        if skill_md:
            (out_dir / "skill-prescription.md").write_text(skill_md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze scientific-computing benchmark case failures (Case Failure Analyzer)."
    )
    parser.add_argument("--job", required=True, type=Path, help="Job or trial directory path")
    parser.add_argument("--task", required=False, type=Path, default=None, help="Task definition directory path")
    parser.add_argument("--trial", default="all", help="Specific trial name or 'all'")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for evidence.json, candidate-hypotheses.json, analysis.json, report.md",
    )
    parser.add_argument(
        "--phase",
        choices=["all", "collect"],
        default="all",
        help=(
            "Execution phase: 'collect' (evidence + candidate-hypotheses only) "
            "or 'all' (default: full evidence pipeline + conservative attribution + bilingual report)"
        ),
    )
    parser.add_argument("--max-log-bytes", type=int, default=120000, help="Maximum bytes per log file read")
    parser.add_argument("--include-session-files", action="store_true", help="Include agent session files in inventory")
    parser.add_argument(
        "--replay",
        choices=["none", "verifier", "safe"],
        default="none",
        help="Replay mode (default: none; verifier/safe require isolated runtime support)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    if args.replay != "none":
        print(
            f"ERROR: Replay mode '{args.replay}' is not implemented for static task analysis.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Fail fast on bad input paths instead of emitting a confident-but-meaningless report.
    if not args.job.exists():
        print(f"ERROR: --job path does not exist: {args.job}", file=sys.stderr)
        sys.exit(2)
    if args.task is not None and not args.task.exists():
        print(f"ERROR: --task path does not exist: {args.task}", file=sys.stderr)
        sys.exit(2)

    all_trials = discover_trials(args.job, trial_filter="all")
    if args.trial != "all":
        available = [t.name for t in all_trials]
        if args.trial not in available:
            print(
                f"ERROR: --trial '{args.trial}' not found under {args.job}. "
                f"Available trials: {available or 'none'}",
                file=sys.stderr,
            )
            sys.exit(2)
    elif not all_trials:
        # A job-level pre-startup failure is legitimate only when job-level evidence exists.
        has_job_level_evidence = (args.job / "result.json").is_file() or (args.job / "job.log").is_file()
        if not has_job_level_evidence:
            print(
                f"ERROR: no trial directories and no job-level result.json/job.log found under {args.job}. "
                "Refusing to analyze an empty input tree.",
                file=sys.stderr,
            )
            sys.exit(2)

    discovery = discover_all(
        job_path=args.job,
        task_path=args.task,
        trial_filter=args.trial,
        include_session_files=args.include_session_files,
    )
    trials = discovery.get("trials") or []
    job_dir = Path(discovery["job_dir"])

    if len(trials) == 1:
        inv = trials[0]
        if args.phase == "collect":
            ev, _, _, cand_hyps = collect_case_evidence(inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes)
            write_outputs(args.output, ev, None, None, None, cand_hyps=cand_hyps, fmt=args.format)
        else:
            ev, an, rep, skill_md = analyze_single_trial(
                inv,
                job_dir=job_dir,
                max_log_bytes=args.max_log_bytes,
                replay_mode=args.replay,
            )
            cand_hyps = generate_candidate_hypotheses(ev)
            write_outputs(args.output, ev, an, rep, skill_md, cand_hyps=cand_hyps, fmt=args.format)
    else:
        summary_rows = []
        for inv in trials:
            t_out = args.output / inv["trial_name"]
            if args.phase == "collect":
                ev, _, _, cand_hyps = collect_case_evidence(inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes)
                write_outputs(t_out, ev, None, None, None, cand_hyps=cand_hyps, fmt=args.format)
                summary_rows.append(
                    {
                        "trial_name": inv["trial_name"],
                        "verdict": ev["runtime"].get("verdict"),
                        "phase": "collect",
                    }
                )
            else:
                ev, an, rep, skill_md = analyze_single_trial(
                    inv,
                    job_dir=job_dir,
                    max_log_bytes=args.max_log_bytes,
                    replay_mode=args.replay,
                )
                cand_hyps = generate_candidate_hypotheses(ev)
                write_outputs(t_out, ev, an, rep, skill_md, cand_hyps=cand_hyps, fmt=args.format)
                summary_rows.append(
                    {
                        "trial_name": inv["trial_name"],
                        "verdict": an["verdict"],
                        "category": an["primary_root_cause"]["category"],
                        "code": an["primary_root_cause"]["code"],
                        "confidence": an["primary_root_cause"]["confidence"],
                    }
                )
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "job_summary.json").write_text(
            json.dumps({"job_dir": str(job_dir), "trials": summary_rows}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
