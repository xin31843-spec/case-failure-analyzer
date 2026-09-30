#!/usr/bin/env python3
"""
Archetype fixture builders (`tests/archetype_builders.py`)

Builds the on-disk `jobs/<job>/` + `tasks/<task>/` trees for the Golden Case
archetypes. Each builder takes a root directory and returns `(job_dir, task_dir)`,
creating the layout the discovery layer expects (`<root>/jobs/<name>` and
`<root>/tasks/<name>`, so that `job_dir.parent.parent / task_rel` resolves).

These were previously inlined per-test in `test_report_validation.py`; they live
here so the characterization net (`test_attribution_characterization.py`) and the
golden tests build byte-identical trees from one definition.

Archetypes 1-7 are the 7 Golden Cases from Section 13.2 of the implementation
specification. Archetype 8 covers the pre-startup rule with no recognizable
infrastructure signature (Gate 1b), which no golden case exercised before.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, Tuple

# ── Archetype 1: Docker apt / network failure before the Agent starts ─────────


def build_golden1_infra_docker_network(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-docker-fail"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "cp2k-aimd-water"
    trial_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "task_name": "cp2k-aimd-water",
                "trial_name": "trial_1",
                "agent_result": None,
                "verifier_result": None,
                "exception_info": {
                    "exception_type": "RuntimeError",
                    "exception_message": "Docker compose command failed for environment. apt-get Failed to fetch",
                },
            }
        ),
        encoding="utf-8",
    )
    return job_dir, task_dir


# ── Archetype 2: Prompt references a non-existent asset ──────────────────────


def build_golden2_case_missing_pseudopotential(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-missing-upf"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "qe-missing-upf"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    (task_dir / "environment" / "assets").mkdir(parents=True)
    (task_dir / "tests").mkdir(parents=True)
    (task_dir / "instruction.md").write_text(
        "Use the provided pseudopotential `/workspace/assets/Ge_nonexistent.UPF`.",
        encoding="utf-8",
    )
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
    )
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 3: File exists in the container, but the Agent never searched ──


def build_golden3_agent_missing_dependency_search(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-no-search"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "cp2k-sp"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps(
            {
                "schema_version": "ATIF-v1.7",
                "steps": [
                    {
                        "step_id": 1,
                        "source": "agent",
                        "tool_calls": [
                            {
                                "tool_call_id": "c1",
                                "function_name": "Bash",
                                "arguments": {"command": "cp2k.psmp -i sp.inp"},
                            }
                        ],
                        "observation": {
                            "results": [
                                {
                                    "source_call_id": "c1",
                                    "content": "The specified OLD file <BASIS_MOLOPT> cannot be opened",
                                }
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 4: SCF error, Agent repeats identical parameters ───────────────


def build_golden4_agent_scf_error_repeated_command(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-scf-repeat"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "qe-scf"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    task_dir.mkdir(parents=True)

    def _scf_step(step_id: int, call_id: str) -> dict:
        return {
            "step_id": step_id,
            "source": "agent",
            "tool_calls": [
                {
                    "tool_call_id": call_id,
                    "function_name": "Bash",
                    "arguments": {"command": "pw.x < scf.in > scf.out"},
                }
            ],
            "observation": {
                "results": [
                    {
                        "source_call_id": call_id,
                        "content": "convergence NOT achieved after 100 iterations",
                    }
                ]
            },
        }

    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps(
            {
                "schema_version": "ATIF-v1.7",
                "steps": [_scf_step(1, "c1"), _scf_step(2, "c2")],
            }
        ),
        encoding="utf-8",
    )
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 5: Value is physical, but the verifier regex rejects it ────────


def build_golden5_verifier_regex_d_exponent(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-verifier-regex"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "qe-regex"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    (task_dir / "tests").mkdir(parents=True)
    (task_dir / "instruction.md").write_text("Run calculation.", encoding="utf-8")
    (task_dir / "tests" / "verify.py").write_text(
        "import re\nVAL_RE = re.compile(r'VAL=\\s*([-\\d.E+]+)')\n",
        encoding="utf-8",
    )
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
    )
    (trial_dir / "verifier" / "verify.log").write_text(
        "FAIL: could not parse line 'VAL= -0.12345D+03'", encoding="utf-8"
    )
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 6: Instantaneous MD divergence, ensemble statistics agree ──────


def build_golden6_numerical_md_trajectory_divergence(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-num-md"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "md-task"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    (task_dir / "tests").mkdir(parents=True, exist_ok=True)
    (task_dir / "instruction.md").write_text(
        "Run NVE molecular dynamics simulation and verify energy conservation.",
        encoding="utf-8",
    )
    (task_dir / "tests" / "verify.py").write_text(
        "import sys\n"
        "# Verify instantaneous trajectory\n"
        "trajectory_rmsd = 0.45\n"
        "assert trajectory_rmsd < 0.01, f'instantaneous_position trajectory_rmsd={trajectory_rmsd} > 0.01 (ensemble average matches)'\n",
        encoding="utf-8",
    )
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
    )
    (trial_dir / "verifier" / "verify.log").write_text(
        "FAIL: instantaneous_position trajectory_rmsd=0.45 > 0.01 (ensemble average matches)",
        encoding="utf-8",
    )
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 7: Missing logs and irreproducible state ───────────────────────


def build_golden7_unknown_missing_logs(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-empty"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "empty-task"
    trial_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 8: Pre-startup failure with no infrastructure signature ────────
#
# The trial never started, but the recorded exception matches no known
# infrastructure error family, so no *causal* infrastructure observation exists.
# Hard rule 3b requires `unknown` here (and forbids `agent`). This is the
# counterpart to archetype 1, where a recognizable apt/network signature makes
# the same pre-startup state attributable to `infra`.


def build_golden8_prestartup_no_infra_evidence(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-prestartup-silent"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "silent-task"
    trial_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "exception.txt").write_text(
        "RuntimeError: container build failed\n", encoding="utf-8"
    )
    return job_dir, task_dir


# ── Archetype 9: Trial passed verification (reward >= 1.0) ───────────────────
#
# Gate 0. No golden case covered the passing path, even though it is the only
# return that keeps an empty `competing_hypotheses` (reconciliation is skipped
# for `verdict == "passed"`).


def build_golden9_passed_trial(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "ccb-passed"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "passed-task"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
    )
    (trial_dir / "verifier" / "reward.txt").write_text("1.0", encoding="utf-8")
    return job_dir, task_dir


# ── Archetype 10: Failure with no positive Agent evidence ────────────────────
#
# Gate 5. The trial failed and the Agent did start, but nothing positively
# implicates Agent behaviour: no unrecovered scientific observation, no repeated
# failed action, no premature completion, no agent_mismatch contract, and no
# agent timeline event corroborated by `fail_text`. The `chaotic` token in
# verify.log is a bare keyword and must NOT become a root cause (Hard Rule 1);
# the calibrated answer is `unknown`.

_ARCHETYPE10_VERIFY_LOG = (
    "FAIL: agent output absent; protocol note mentions chaotic behaviour of the reference run"
)


def build_golden10_insufficient_positive_agent_evidence(root: Path) -> Tuple[Path, Path]:
    job_dir = root / "jobs" / "bare-chaotic"
    trial_dir = job_dir / "trial_1"
    task_dir = root / "tasks" / "md-task"
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (trial_dir / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
    )
    (trial_dir / "verifier" / "verify.log").write_text(_ARCHETYPE10_VERIFY_LOG, encoding="utf-8")
    (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
    return job_dir, task_dir


ARCHETYPES: Dict[str, Callable[[Path], Tuple[Path, Path]]] = {
    "golden1_infra_docker_network": build_golden1_infra_docker_network,
    "golden2_case_missing_pseudopotential": build_golden2_case_missing_pseudopotential,
    "golden3_agent_missing_dependency_search": build_golden3_agent_missing_dependency_search,
    "golden4_agent_scf_error_repeated_command": build_golden4_agent_scf_error_repeated_command,
    "golden5_verifier_regex_d_exponent": build_golden5_verifier_regex_d_exponent,
    "golden6_numerical_md_trajectory_divergence": build_golden6_numerical_md_trajectory_divergence,
    "golden7_unknown_missing_logs": build_golden7_unknown_missing_logs,
    "golden8_prestartup_no_infra_evidence": build_golden8_prestartup_no_infra_evidence,
    "golden9_passed_trial": build_golden9_passed_trial,
    "golden10_insufficient_positive_agent_evidence": build_golden10_insufficient_positive_agent_evidence,
}
