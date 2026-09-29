# Evidence & Analysis JSON Schemas (`failure-analysis-v1`)

**[English](evidence-schema.md) | [简体中文](../zh/evidence-schema.md)**

## 1. `evidence.json` Schema

`evidence.json` stores purely objective observations extracted by deterministic scripts (`discover_artifacts.py`, `runtime_state.py`, `normalize_trajectory.py`, `extract_runtime_errors.py`, `audit_contract.py`, `extract_scientific_errors.py`). It must never contain subjective root-cause labels.

```json
{
  "case_id": "string (e.g. ccb-cp2k-aimd-water or trial_name)",
  "job_dir": "string",
  "task_dir": "string",
  "trial_name": "string",
  "artifacts": [
    {
      "artifact_id": "art:trial_result",
      "rel_path": "result.json",
      "scope": "trial|job|task",
      "exists": true,
      "size_bytes": 3869,
      "sha256": "sha256:..."
    }
  ],
  "runtime": {
    "started_at": "ISO-8601 or null",
    "finished_at": "ISO-8601 or null",
    "execution_status": "completed|errored|not_started|unknown",
    "verification_status": "passed|failed|not_run",
    "verdict": "passed|failed|errored|unknown",
    "exit_status": "completed|failed|errored|unknown",
    "reward": 0.0,
    "agent_started": true,
    "verifier_started": true,
    "state_conflicts": [],
    "stages": {
      "environment_setup": {"started_at": "...", "finished_at": "..."},
      "agent_setup": {"started_at": "...", "finished_at": "..."},
      "agent_execution": {"started_at": "...", "finished_at": "..."},
      "verifier": {"started_at": "...", "finished_at": "..."}
    }
  },
  "timeline": [
    {
      "event_id": "trajectory:step:1",
      "timestamp": "2026-09-19T05:45:50.652Z",
      "actor": "user|agent|runner|verifier",
      "event_type": "user_instruction|agent_reasoning|tool_call|tool_output|shell_error|file_read|file_write|repeated_command|final_response|verifier_result|runtime_exception",
      "tool_name": "Bash|Read|Write|Edit|null",
      "command": "string or null",
      "observation": "truncated string or null",
      "observation_sha256": "sha256:... or null",
      "exit_code": 0,
      "source_file": "agent/trajectory.json",
      "source_pointer": "/steps/0"
    }
  ],
  "behavioral_signals": [
    {
      "signal_id": "sig:repeated_fail:2:0",
      "signal_type": "repeated_failed_action|ignored_error|missing_log_inspection|unverified_output|premature_completion|wrong_output_path|asset_modified|dependency_search_attempted|scientific_parameter_changed|fallback_attempted",
      "description": "string",
      "event_ref": "trajectory:step:2:tool:0"
    }
  ],
  "error_observations": [
    {
      "error_id": "err:1",
      "code": "INFRA_CONTAINER_BUILD",
      "subtype": "container_build",
      "stage": "environment_build",
      "matched_text": "string",
      "causal_candidate": true,
      "transient": false,
      "source_file": "result.json",
      "source_pointer": "/exception_info/exception_message"
    }
  ],
  "contract_observations": [
    {
      "contract_id": "contract:1",
      "item": "results.json",
      "prompt_requirement": "required",
      "verifier_requirement": "required",
      "agent_output_status": "present",
      "alignment": "consistent|implicit_consistent|agent_missing_output|agent_schema_mismatch|verifier_hidden_requirement|verifier_schema_mismatch|verifier_defect|case_defect",
      "details": "string",
      "source_refs": ["task:instruction.md", "task:tests/verify.py"]
    }
  ],
  "verifier_observations": [
    {
      "obs_id": "ver:hazard:1",
      "type": "verifier_fail_message|parser_hazard|implicit_column_assumption|verifier_internal_crash",
      "summary": "string",
      "matched_text": "string",
      "hazard_detected": true,
      "failure_binding": "direct|indirect|none",
      "binding_evidence": ["ver:fail_log"],
      "affected_input": "string or null",
      "affected_parser": "string or null",
      "triggered": true,
      "source_file": "tests/verify.py",
      "source_pointer": "AST"
    }
  ],
  "scientific_observations": [
    {
      "sci_id": "sci:1",
      "software": "cp2k|quantum-espresso|lammps|xtb|ase|rdkit|vasp|gaussian|orca|gromacs|pyscf",
      "error_family": "scf_nonconvergence",
      "aliases": [],
      "reference_anchor": "references/software/cp2k.md#scf_nonconvergence",
      "matched_text": "string",
      "source_ref": "trajectory:step:8",
      "candidate_causes": ["bad_initial_guess", "insufficient_scf_iterations"],
      "required_discriminating_evidence": ["SCF iteration history", "MAX_SCF setting"]
    }
  ],
  "missing_artifacts": [
    "agent/trajectory.json"
  ]
}
```

---

## 2. `analysis.json` Schema

`analysis.json` stores the structured causal attribution and must pass `scripts/validate_analysis.py`.

```json
{
  "schema_version": "failure-analysis-v1",
  "case_id": "cp2k-aimd-water",
  "trial_name": "cp2k-aimd-water__kGRrYBg",
  "verdict": "failed|errored|passed",
  "failure_stage": "environment_build|environment_runtime|agent_setup|agent_execution|verifier_execution|none|unknown",
  "detection_stage": "runner|verifier_execution|agent_execution",
  "first_unrecovered_deviation": {
    "status": "identified|not_identified",
    "event_ref": "err:1 or null",
    "timestamp": "2026-09-18T21:45:37.672525",
    "summary": "Docker image pull/build failed during environment setup before agent startup"
  },
  "failure_manifestation": {
    "type": "dependency_install_failure|verifier_check_failed|verifier_internal_crash|...",
    "summary": "Human-readable description of the final failure symptom"
  },
  "primary_root_cause": {
    "category": "infra|case|agent|verifier|unknown|none",
    "subtype": "external_network",
    "code": "INFRA_EXTERNAL_NETWORK",
    "confidence": 0.86,
    "confidence_kind": "heuristic_evidence_score",
    "evidence_strength": "high|medium|low",
    "summary": "Explanation of why this is the singular primary root cause"
  },
  "contributing_factors": [],
  "competing_hypotheses": [
    {
      "hypothesis_id": "H1",
      "category": "infra",
      "subtype": "external_network",
      "claim": "Docker build failed due to network timeout/unreachability before agent started",
      "evidence_for": ["err:1"],
      "evidence_against": [],
      "missing_evidence": [],
      "counterfactual_test": "Pre-pull image or build with working network mirror",
      "confidence": 0.86,
      "confidence_kind": "heuristic_evidence_score",
      "evidence_strength": "high"
    }
  ],
  "evidence_refs": ["err:1", "art:trial_result"],
  "excluded_hypotheses": [
    {
      "hypothesis_id": "H2",
      "category": "agent",
      "reason": "Agent never started (runtime.agent_started == false); missing trajectory is a consequence of pre-startup build failure."
    }
  ],
  "recommended_actions": [
    {
      "owner": "Infra|Case|Verifier|Agent Policy",
      "action": "Concrete remediation step"
    }
  ],
  "skill_prescription": null
}
```
