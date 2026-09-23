#!/usr/bin/env python3
"""
Unit & Golden Case tests (`tests/test_report_validation.py`)

Verifies schema validation (`validate_analysis.py`), report rendering (`render_report.py`),
and all 7 Golden Case archetypes from Section 13.2 of the implementation specification:
  1. Docker apt / network failure before agent starts -> `infra` (never `agent`)
  2. Prompt references non-existent pseudopotential -> `case`
  3. File exists in container (`/opt/...`) but Agent did not search -> `agent` (`AGENT_PATH_OR_DEPENDENCY_DISCOVERY`)
  4. SCF error followed by Agent repeating identical parameters -> `agent` (`AGENT_ERROR_DIAGNOSIS`) + `skill_prescription`
  5. Physical value valid (`D+03` / slash path) but verifier regex fails -> `verifier`
  6. MD trajectory instantaneous divergence while ensemble statistics match -> `numerical`
  7. Missing logs and irreproducible state -> `unknown`
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_case import analyze_single_trial
from discover_artifacts import discover_all
from validate_analysis import validate_all


class TestGoldenCasesAndValidation(unittest.TestCase):
    def _run_case(self, job_dir: Path, task_dir: Path) -> tuple[dict, dict, str]:
        disc = discover_all(job_path=job_dir, task_path=task_dir)
        ev, an, rep, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
        ok, errs = validate_all(ev, an, rep)
        self.assertTrue(ok, f"Validation failed: {errs}")
        return ev, an, rep

    def test_golden_1_infra_docker_network_agent_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-docker-fail"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "cp2k-aimd-water"
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
            ev, an, _ = self._run_case(job_dir, task_dir)
            self.assertFalse(ev["runtime"]["agent_started"])
            self.assertEqual(an["primary_root_cause"]["category"], "infra")
            self.assertIsNone(an["skill_prescription"])

    def test_golden_2_case_missing_pseudopotential(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-missing-upf"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "qe-missing-upf"
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
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "case")
            self.assertEqual(an["primary_root_cause"]["code"], "CASE_MISSING_ASSET")

    def test_golden_3_agent_missing_dependency_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-no-search"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "cp2k-sp"
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
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "agent")
            self.assertEqual(an["primary_root_cause"]["code"], "AGENT_PATH_OR_DEPENDENCY_DISCOVERY")

    def test_golden_4_agent_scf_error_repeated_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-scf-repeat"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "qe-scf"
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
                                        "arguments": {"command": "pw.x < scf.in > scf.out"},
                                    }
                                ],
                                "observation": {
                                    "results": [
                                        {
                                            "source_call_id": "c1",
                                            "content": "convergence NOT achieved after 100 iterations",
                                        }
                                    ]
                                },
                            },
                            {
                                "step_id": 2,
                                "source": "agent",
                                "tool_calls": [
                                    {
                                        "tool_call_id": "c2",
                                        "function_name": "Bash",
                                        "arguments": {"command": "pw.x < scf.in > scf.out"},
                                    }
                                ],
                                "observation": {
                                    "results": [
                                        {
                                            "source_call_id": "c2",
                                            "content": "convergence NOT achieved after 100 iterations",
                                        }
                                    ]
                                },
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "agent")
            self.assertEqual(an["primary_root_cause"]["code"], "AGENT_ERROR_DIAGNOSIS")
            self.assertIsNotNone(an["skill_prescription"])

    def test_golden_5_verifier_regex_d_exponent_or_slash_defect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-verifier-regex"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "qe-regex"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            (task_dir / "tests").mkdir(parents=True)
            (task_dir / "instruction.md").write_text("Run calculation.", encoding="utf-8")
            (task_dir / "tests" / "verify.py").write_text(
                "import re\n"
                "VAL_RE = re.compile(r'VAL=\\s*([-\\d.E+]+)')\n",
                encoding="utf-8",
            )
            (trial_dir / "agent" / "trajectory.json").write_text(
                json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
            )
            (trial_dir / "verifier" / "verify.log").write_text(
                "FAIL: could not parse line 'VAL= -0.12345D+03'", encoding="utf-8"
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "verifier")
            self.assertEqual(an["primary_root_cause"]["code"], "VERIFIER_REGEX_OR_PARSER_DEFECT")
            self.assertIsNone(an["skill_prescription"])

    def test_golden_6_numerical_md_trajectory_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-num-md"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "md-task"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            task_dir.mkdir(parents=True)
            (trial_dir / "agent" / "trajectory.json").write_text(
                json.dumps({"schema_version": "ATIF-v1.7", "steps": []}), encoding="utf-8"
            )
            (trial_dir / "verifier" / "verify.log").write_text(
                "FAIL: instantaneous_position trajectory_rmsd=0.45 > 0.01 (ensemble average matches)",
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "numerical")

    def test_golden_7_unknown_missing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-empty"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "empty-task"
            trial_dir.mkdir(parents=True)
            task_dir.mkdir(parents=True)
            (trial_dir / "result.json").write_text(
                json.dumps({"trial_name": "trial_1"}), encoding="utf-8"
            )
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "unknown")
            self.assertEqual(an["primary_root_cause"]["code"], "UNKNOWN_INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
