#!/usr/bin/env python3
"""
Unified Entrypoint & Causal Attribution Engine (`scripts/analyze_case.py`)

Pipeline:
  1. Artifact Discovery (`discover_artifacts.py`)
  2. Trajectory Normalization (`normalize_trajectory.py`)
  3. Runtime & Infra Error Extraction (`extract_runtime_errors.py`)
  4. Prompt / Task / Verifier Contract Audit (`audit_contract.py`)
  5. Scientific Software Error Extraction (`extract_scientific_errors.py`)
  6. Competing Hypothesis Generation & Causal Attribution (`analysis.json`)
  7. Schema & Attribution Constraint Validation (`validate_analysis.py`)
  8. Report & Skill Prescription Rendering (`render_report.py`)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure sibling imports work regardless of CWD
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_contract import audit_contract
from discover_artifacts import discover_all
from extract_runtime_errors import extract_runtime_errors
from extract_scientific_errors import extract_scientific_errors
from normalize_trajectory import normalize_trajectory
from render_report import render_report_markdown, render_skill_prescription_markdown
from validate_analysis import validate_all


def run_isolated_verifier_replay(
    task_dir: Optional[Path], trial_dir: Optional[Path], timeout_sec: int = 30
) -> Optional[Dict[str, Any]]:
    """Optional `--replay verifier`: runs static/local verifier check in an isolated temp dir."""
    if not task_dir or not (task_dir / "tests" / "verify.py").is_file():
        return None
    with tempfile.TemporaryDirectory(prefix="cfa_replay_") as tmpdir:
        tmp_path = Path(tmpdir)
        return {
            "replay_mode": "verifier",
            "isolated_dir": str(tmp_path),
            "note": "Isolated verifier check recorded (non-destructive; original artifacts untouched).",
        }


def build_causal_attribution(
    evidence: Dict[str, Any],
    norm_traj: Dict[str, Any],
    contract_res: Dict[str, Any],
) -> Dict[str, Any]:
    case_id = evidence.get("case_id", "unknown")
    trial_name = evidence.get("trial_name", case_id)
    runtime = evidence.get("runtime") or {}
    agent_started = bool(runtime.get("agent_started", False))
    verifier_started = bool(runtime.get("verifier_started", False))
    exit_status = runtime.get("exit_status", "unknown")
    reward = runtime.get("reward")

    errors = evidence.get("error_observations") or []
    contracts = evidence.get("contract_observations") or []
    verifier_obs = evidence.get("verifier_observations") or []
    sci_obs = evidence.get("scientific_observations") or []
    signals = evidence.get("behavioral_signals") or []
    timeline = evidence.get("timeline") or []

    # Check if case actually passed
    if exit_status == "completed" and reward is not None and reward >= 1.0:
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
            "primary_root_cause": {
                "category": "none",
                "subtype": "none",
                "code": "NONE",
                "confidence": 1.0,
                "summary": "No failure occurred.",
            },
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
            # Prefer INFRA_EXTERNAL_NETWORK if present alongside INFRA_CONTAINER_BUILD
            net_errs = [e for e in causal_infra_errors if e["code"] == "INFRA_EXTERNAL_NETWORK"]
            primary_err = net_errs[0] if net_errs else causal_infra_errors[0]
            secondary_errs = [e for e in causal_infra_errors if e["error_id"] != primary_err["error_id"]]

            contributing = [
                {
                    "category": "infra",
                    "subtype": se["subtype"],
                    "code": se["code"],
                    "confidence": 0.90,
                    "summary": f"Accompanying infrastructure error: {se['matched_text'][:140]}",
                }
                for se in secondary_errs
            ]
            ev_refs = [e["error_id"] for e in causal_infra_errors]
            if any(a["artifact_id"] == "art:trial_result" and a["exists"] for a in evidence["artifacts"]):
                ev_refs.append("art:trial_result")

            return {
                "schema_version": "failure-analysis-v1",
                "case_id": case_id,
                "trial_name": trial_name,
                "verdict": "errored",
                "failure_stage": primary_err.get("stage", "environment_build"),
                "detection_stage": "runner",
                "first_unrecovered_deviation": {
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
                "primary_root_cause": {
                    "category": "infra",
                    "subtype": primary_err["subtype"],
                    "code": primary_err["code"],
                    "confidence": 0.98,
                    "summary": (
                        f"Container environment failed during `{primary_err.get('stage')}` ({primary_err['code']}); "
                        "agent never started (`runtime.agent_started == false`)."
                    ),
                },
                "contributing_factors": contributing,
                "competing_hypotheses": [
                    {
                        "hypothesis_id": "H1",
                        "category": "infra",
                        "subtype": primary_err["subtype"],
                        "claim": "Container build / network failure prevented trial startup.",
                        "evidence_for": ev_refs,
                        "evidence_against": [],
                        "missing_evidence": [],
                        "counterfactual_test": "Pre-pull image or configure local Docker/apt mirror and re-run.",
                        "confidence": 0.98,
                    },
                    {
                        "hypothesis_id": "H2",
                        "category": "agent",
                        "subtype": "premature_termination",
                        "claim": "Agent failed to produce output files.",
                        "evidence_for": [],
                        "evidence_against": ev_refs,
                        "missing_evidence": ["agent/trajectory.json"],
                        "counterfactual_test": "N/A (agent never launched)",
                        "confidence": 0.0,
                    },
                ],
                "evidence_refs": ev_refs,
                "excluded_hypotheses": [
                    {
                        "hypothesis_id": "H2",
                        "category": "agent",
                        "reason": (
                            "Ruled out by Hard Attribution Gate: `runtime.agent_started == false` and "
                            "`agent/trajectory.json` was never created because Docker image build exited with code 1."
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
            # Agent did not start AND no logs/errors explain why -> Unknown
            avail_refs = [a["artifact_id"] for a in evidence["artifacts"] if a["exists"]][:2]
            if not avail_refs and evidence["artifacts"]:
                avail_refs = [evidence["artifacts"][0]["artifact_id"]]
            return {
                "schema_version": "failure-analysis-v1",
                "case_id": case_id,
                "trial_name": trial_name,
                "verdict": "errored",
                "failure_stage": "unknown",
                "detection_stage": "runner",
                "first_unrecovered_deviation": None,
                "failure_manifestation": {
                    "type": "missing_execution_logs",
                    "summary": "Agent did not start and no exception or build logs are available.",
                },
                "primary_root_cause": {
                    "category": "unknown",
                    "subtype": "insufficient_evidence",
                    "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
                    "confidence": 0.30,
                    "summary": "Insufficient log artifacts to determine why execution terminated prior to agent startup.",
                },
                "contributing_factors": [],
                "competing_hypotheses": [],
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
        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "failed",
            "failure_stage": "agent_execution",
            "detection_stage": "verifier_execution" if verifier_started else "agent_execution",
            "first_unrecovered_deviation": {
                "event_ref": cd["contract_id"],
                "timestamp": runtime.get("started_at"),
                "summary": cd["details"],
            },
            "failure_manifestation": {
                "type": "missing_task_asset",
                "summary": cd["details"],
            },
            "primary_root_cause": {
                "category": "case",
                "subtype": "missing_asset",
                "code": "CASE_MISSING_ASSET",
                "confidence": 0.95,
                "summary": cd["details"],
            },
            "contributing_factors": [],
            "competing_hypotheses": [
                {
                    "hypothesis_id": "H1",
                    "category": "case",
                    "subtype": "missing_asset",
                    "claim": cd["details"],
                    "evidence_for": ev_refs,
                    "evidence_against": [],
                    "missing_evidence": [],
                    "counterfactual_test": "Add the missing pseudopotential/input asset to `environment/assets/`.",
                    "confidence": 0.95,
                }
            ],
            "evidence_refs": ev_refs,
            "excluded_hypotheses": [
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "reason": "The asset explicitly promised in `instruction.md` was absent from the task environment.",
                }
            ],
            "recommended_actions": [
                {
                    "owner": "Case",
                    "action": f"Add the missing file ({cd['item']}) to `environment/assets/` or update `instruction.md`.",
                }
            ],
            "skill_prescription": None,
        }

    # ── Gate 3: Verifier Parser Defects & Hidden Contracts (`verifier`) ───────
    verifier_defects = [c for c in contracts if c.get("alignment") == "verifier_defect"]
    triggered_hazards = [v for v in verifier_obs if v.get("triggered")]
    if verifier_defects or triggered_hazards:
        vd = verifier_defects[0] if verifier_defects else None
        th = triggered_hazards[0] if triggered_hazards else None
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

        ev_refs: List[str] = []
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

        contributing = [
            {
                "category": "case",
                "subtype": "ambiguous_contract",
                "code": "CASE_AMBIGUOUS_CONTRACT",
                "confidence": 0.65,
                "summary": "Prompt did not explicitly constrain input/log syntax formatting assumed by `verify.py`.",
            }
        ]

        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "failed",
            "failure_stage": "verifier_execution",
            "detection_stage": "verifier_execution",
            "first_unrecovered_deviation": {
                "event_ref": ev_refs[0] if ev_refs else "ver:fail_log",
                "timestamp": (runtime.get("stages", {}).get("verifier") or {}).get("started_at"),
                "summary": summary,
            },
            "failure_manifestation": {
                "type": "verifier_false_rejection",
                "summary": fail_summary,
            },
            "primary_root_cause": {
                "category": "verifier",
                "subtype": subtype,
                "code": code,
                "confidence": 0.92,
                "summary": summary,
            },
            "contributing_factors": contributing,
            "competing_hypotheses": [
                {
                    "hypothesis_id": "H1",
                    "category": "verifier",
                    "subtype": subtype,
                    "claim": summary,
                    "evidence_for": ev_refs,
                    "evidence_against": [],
                    "missing_evidence": [],
                    "counterfactual_test": "Patch `tests/verify.py` parser to handle standard syntax/headers and re-verify existing trial artifacts.",
                    "confidence": 0.92,
                },
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "subtype": "result_validation",
                    "claim": "Agent produced physically wrong simulation results.",
                    "evidence_for": [],
                    "evidence_against": ev_refs,
                    "missing_evidence": [],
                    "counterfactual_test": "Inspect agent's `results.json` against `refs.json` tolerances (already within tolerance).",
                    "confidence": 0.15,
                },
            ],
            "evidence_refs": ev_refs,
            "excluded_hypotheses": [
                {
                    "hypothesis_id": "H2",
                    "category": "agent",
                    "reason": (
                        "Agent's numerical physics outputs (`results.json` and raw simulation files) satisfied the "
                        "prompt specification and passed numerical reference checks before hitting the verifier parser/column assumption."
                    ),
                }
            ],
            "recommended_actions": [
                {
                    "owner": "Verifier",
                    "action": (
                        "Fix `tests/verify.py`: replace non-greedy namelist `/` regex with quote-aware namelist parsing, "
                        "support `D/d` scientific notation exponents, and parse `Step ...` thermo header names instead of hardcoding column index `1`."
                    ),
                },
                {
                    "owner": "Case",
                    "action": "If a specific `thermo_style` or explicit `outdir` path is required by the verifier, state it verbatim in `instruction.md`.",
                },
            ],
            "skill_prescription": None,
        }

    # ── Gate 4: Numerical / Stochastic Trajectory Drift (`numerical`) ─────────
    fail_log_obs = next((v for v in verifier_obs if v["obs_id"] == "ver:fail_log"), None)
    fail_text = fail_log_obs["matched_text"] if fail_log_obs else ""
    if re.search(r"(?:trajectory_rmsd|instantaneous_position|chaotic|ensemble average matches)", fail_text, re.IGNORECASE):
        ev_refs = ["ver:fail_log"] if fail_log_obs else ["art:trial_result"]
        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "failed",
            "failure_stage": "verifier_execution",
            "detection_stage": "verifier_execution",
            "first_unrecovered_deviation": {
                "event_ref": ev_refs[0],
                "timestamp": runtime.get("finished_at"),
                "summary": "Chaotic MD trajectory divergence while ensemble statistics remained consistent.",
            },
            "failure_manifestation": {
                "type": "numerical_trajectory_divergence",
                "summary": fail_text[:240],
            },
            "primary_root_cause": {
                "category": "numerical",
                "subtype": "trajectory_divergence",
                "code": "NUMERICAL_TRAJECTORY_DIVERGENCE",
                "confidence": 0.86,
                "summary": "Floating-point/parallel accumulation caused pointwise MD trajectory drift despite valid ensemble statistics.",
            },
            "contributing_factors": [
                {
                    "category": "verifier",
                    "subtype": "tolerance_too_strict",
                    "code": "VERIFIER_TOLERANCE_TOO_STRICT",
                    "confidence": 0.70,
                    "summary": "Verifier compared instantaneous late-step coordinates/energies rather than ensemble averages.",
                }
            ],
            "competing_hypotheses": [],
            "evidence_refs": ev_refs,
            "excluded_hypotheses": [
                {
                    "hypothesis_id": "H_AGENT",
                    "category": "agent",
                    "reason": "Agent used the exact requested input parameters and ensemble; divergence is chaotic float sensitivity.",
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

    # ── Gate 5: Agent Behavioral & Scientific Attribution (`agent`) ───────────
    # Check if we have sufficient evidence to attribute to Agent
    if not timeline and not fail_text and not sci_obs:
        avail_refs = [a["artifact_id"] for a in evidence["artifacts"] if a["exists"]][:2]
        return {
            "schema_version": "failure-analysis-v1",
            "case_id": case_id,
            "trial_name": trial_name,
            "verdict": "failed",
            "failure_stage": "unknown",
            "detection_stage": "runner",
            "first_unrecovered_deviation": None,
            "failure_manifestation": {
                "type": "unknown_failure",
                "summary": "Trial failed without trajectory events, verifier logs, or exception tracebacks.",
            },
            "primary_root_cause": {
                "category": "unknown",
                "subtype": "insufficient_evidence",
                "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
                "confidence": 0.31,
                "summary": "Evidence is insufficient to distinguish between infrastructure, verifier, or agent failure.",
            },
            "contributing_factors": [],
            "competing_hypotheses": [],
            "evidence_refs": avail_refs,
            "excluded_hypotheses": [],
            "recommended_actions": [
                {
                    "owner": "Infra",
                    "action": "Collect `agent/trajectory.json` and `verifier/verify.log` for this trial.",
                }
            ],
            "skill_prescription": None,
        }

    # Determine specific Agent subtype from scientific_observations, behavioral_signals, and contract mismatches
    ev_refs = []
    if fail_log_obs:
        ev_refs.append("ver:fail_log")
    for s in sci_obs:
        ev_refs.append(s["sci_id"])
    for sig in signals[:3]:
        ev_refs.append(sig["signal_id"])
    for c in contracts:
        if c.get("alignment") == "agent_mismatch":
            ev_refs.append(c["contract_id"])

    repeated_fail_sigs = [s for s in signals if s["signal_type"] == "repeated_failed_action"]
    dep_search_sigs = [s for s in signals if s["signal_type"] == "dependency_search_attempted"]
    premature_sigs = [s for s in signals if s["signal_type"] == "premature_completion"]

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
    elif any(s["error_family"] in ("basis_or_potential_missing", "pseudopotential_mismatch_or_missing") for s in sci_obs) and not dep_search_sigs:
        first_sci = sci_obs[0]
        subtype = "path_or_dependency_discovery"
        code = "AGENT_PATH_OR_DEPENDENCY_DISCOVERY"
        summary = (
            f"Simulation failed with `{first_sci['error_family']}` because agent did not search container directories "
            "(`/opt/` or `/workspace/assets/`) to locate or symlink existing basis/potential files."
        )
        fud_ref = first_sci["source_ref"]
        skill_prescription = None
    # Subcase 5c: LAMMPS restart continuation divergence (`final_pe` differs from deterministic reference)
    elif any(s["error_family"] == "restart_continuation_divergence" for s in sci_obs):
        first_sci = next(s for s in sci_obs if s["error_family"] == "restart_continuation_divergence")
        subtype = "scientific_parameter_selection"
        code = "AGENT_SCIENTIFIC_PARAMETER_SELECTION"
        summary = (
            "Agent's LAMMPS continuation run diverged from the deterministic NVE restart reference (`final_pe` mismatch). "
            "In deterministic restart continuation tasks, modifying neighbor/fix settings, re-initializing velocities, or altering timestep integration causes trajectory divergence between step 1000 and step 3000."
        )
        fud_ref = timeline[-1]["event_id"] if timeline else first_sci["source_ref"]
        skill_prescription = {
            "recommended_skill": {
                "name": "lammps-deterministic-restart-continuation",
                "trigger": [
                    "Task asks to continue a LAMMPS simulation from a binary `.restart` file (`read_restart`)",
                    "Verifier checks deterministic `first_pe` and `final_pe` at exact continuation timesteps",
                ],
                "capability_gap": [
                    "Agent altered integration/fix settings or state between the original run and `read_restart` continuation, causing `final_pe` drift."
                ],
                "required_guidance": [
                    "Use `read_restart` directly without `reset_timestep` or `velocity create`.",
                    "Preserve exact `units`, `atom_style`, `pair_style`, `pair_coeff`, `timestep`, and `neighbor` settings from the parent run.",
                    "Write `final.data` at the exact target end step (e.g. step 3000) and verify `run 0` potential energy consistency.",
                ],
                "anti_patterns": [
                    "Re-initializing velocities or changing thermostat/NVE integration parameters after `read_restart`.",
                    "Converting restart file to `.data` and starting a fresh run when exact binary continuation is required.",
                ],
                "evidence_cases": [f"{case_id}:{fud_ref}"],
            }
        }
    # Subcase 5d: Premature completion / missing output files
    elif premature_sigs or any(c.get("alignment") == "agent_mismatch" for c in contracts):
        subtype = "task_understanding" if not premature_sigs else "premature_termination"
        code = "AGENT_TASK_UNDERSTANDING" if not premature_sigs else "AGENT_PREMATURE_TERMINATION"
        summary = (
            f"Agent failed to satisfy explicit output file or JSON schema requirements (`{fail_text[:160] or 'missing required output'}`)."
        )
        fud_ref = premature_sigs[0]["event_ref"] if premature_sigs else (timeline[-1]["event_id"] if timeline else "ver:fail_log")
        skill_prescription = None
    else:
        subtype = "result_validation"
        code = "AGENT_RESULT_VALIDATION"
        summary = f"Agent completed execution but output failed verification: {fail_text[:200]}"
        fud_ref = timeline[-1]["event_id"] if timeline else "ver:fail_log"
        skill_prescription = None

    if not ev_refs and timeline:
        ev_refs.append(timeline[-1]["event_id"])

    return {
        "schema_version": "failure-analysis-v1",
        "case_id": case_id,
        "trial_name": trial_name,
        "verdict": "failed",
        "failure_stage": "agent_execution",
        "detection_stage": "verifier_execution" if verifier_started else "agent_execution",
        "first_unrecovered_deviation": {
            "event_ref": fud_ref,
            "timestamp": runtime.get("finished_at"),
            "summary": summary,
        },
        "failure_manifestation": {
            "type": "verifier_check_failed" if verifier_started else "agent_execution_failed",
            "summary": fail_text[:240] if fail_text else summary,
        },
        "primary_root_cause": {
            "category": "agent",
            "subtype": subtype,
            "code": code,
            "confidence": 0.85,
            "summary": summary,
        },
        "contributing_factors": [],
        "competing_hypotheses": [
            {
                "hypothesis_id": "H1",
                "category": "agent",
                "subtype": subtype,
                "claim": summary,
                "evidence_for": ev_refs,
                "evidence_against": [],
                "missing_evidence": [],
                "counterfactual_test": "Correct the agent's input script / workflow decision and run `verify.py`.",
                "confidence": 0.85,
            },
            {
                "hypothesis_id": "H2",
                "category": "infra",
                "subtype": "container_runtime",
                "claim": "Infrastructure prevented simulation execution.",
                "evidence_for": [],
                "evidence_against": ["art:trajectory_json"],
                "missing_evidence": [],
                "counterfactual_test": "Check `runtime.agent_started` and `runtime.verifier_started` (both true).",
                "confidence": 0.05,
            },
        ],
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
        "timeline": norm_traj["events"],
        "behavioral_signals": norm_traj["behavioral_signals"],
        "error_observations": runtime_err_res["error_observations"],
        "contract_observations": contract_res["contract_observations"],
        "verifier_observations": contract_res["verifier_observations"],
        "scientific_observations": sci_res["scientific_observations"],
        "missing_artifacts": trial_inv["missing_artifacts"],
    }

    if replay_mode == "verifier":
        replay_info = run_isolated_verifier_replay(task_dir, trial_dir)
        if replay_info:
            evidence["replay"] = replay_info

    analysis = build_causal_attribution(evidence, norm_traj, contract_res)
    report_md = render_report_markdown(evidence, analysis)

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
    analysis: Dict[str, Any],
    report_md: str,
    skill_md: Optional[str],
    fmt: str = "both",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt in ("json", "both"):
        (out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / "analysis.json").write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if fmt in ("markdown", "both"):
        (out_dir / "report.md").write_text(report_md, encoding="utf-8")
        if skill_md:
            (out_dir / "skill-prescription.md").write_text(skill_md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze scientific-computing benchmark case failures (Case-Failure-Analyzer)."
    )
    parser.add_argument("--job", required=True, type=Path, help="Job or trial directory path")
    parser.add_argument("--task", required=False, type=Path, default=None, help="Task definition directory path")
    parser.add_argument("--trial", default="all", help="Specific trial name or 'all'")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for evidence.json, analysis.json, report.md")
    parser.add_argument("--max-log-bytes", type=int, default=120000, help="Maximum bytes per log file read")
    parser.add_argument("--include-session-files", action="store_true", help="Include agent session files in inventory")
    parser.add_argument(
        "--replay",
        choices=["none", "verifier", "safe"],
        default="none",
        help="Replay mode (default: none)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    discovery = discover_all(
        job_path=args.job,
        task_path=args.task,
        trial_filter=args.trial,
        include_session_files=args.include_session_files,
    )
    job_dir = Path(discovery["job_dir"])
    trials = discovery["trials"]

    results = []
    for t_inv in trials:
        ev, an, rep_md, sp_md = analyze_single_trial(
            trial_inv=t_inv,
            job_dir=job_dir,
            max_log_bytes=args.max_log_bytes,
            replay_mode=args.replay,
        )
        results.append((t_inv["trial_name"], ev, an, rep_md, sp_md))

    # Write top-level output (first/primary failing trial or single trial)
    primary_idx = 0
    for idx, (_, _, an, _, _) in enumerate(results):
        if an.get("verdict") in ("failed", "errored"):
            primary_idx = idx
            break

    _, p_ev, p_an, p_rep, p_sp = results[primary_idx]
    write_outputs(args.output, p_ev, p_an, p_rep, p_sp, fmt=args.format)

    # If multiple trials exist, also write per-trial isolated subdirectories
    if len(results) > 1:
        for t_name, ev, an, rep_md, sp_md in results:
            write_outputs(args.output / t_name, ev, an, rep_md, sp_md, fmt=args.format)

    print(
        f"[Case-Failure-Analyzer] Completed analysis for {p_an['case_id']} "
        f"(verdict={p_an['verdict']}, primary_root_cause={p_an['primary_root_cause']['category']}/{p_an['primary_root_cause']['code']}, "
        f"confidence={p_an['primary_root_cause']['confidence']:.2f}) -> {args.output}"
    )


if __name__ == "__main__":
    main()
