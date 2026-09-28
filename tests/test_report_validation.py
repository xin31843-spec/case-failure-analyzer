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

Fixture trees are built by the shared builders in `tests/archetype_builders.py`, which
`test_attribution_characterization.py` also consumes, so both suites exercise byte-identical
trees from a single definition.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyze_case import analyze_single_trial
from discover_artifacts import discover_all
from tests.archetype_builders import (
    build_golden1_infra_docker_network,
    build_golden2_case_missing_pseudopotential,
    build_golden3_agent_missing_dependency_search,
    build_golden4_agent_scf_error_repeated_command,
    build_golden5_verifier_regex_d_exponent,
    build_golden6_numerical_md_trajectory_divergence,
    build_golden7_unknown_missing_logs,
)
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
            job_dir, task_dir = build_golden1_infra_docker_network(Path(tmp))
            ev, an, _ = self._run_case(job_dir, task_dir)
            self.assertFalse(ev["runtime"]["agent_started"])
            self.assertEqual(an["primary_root_cause"]["category"], "infra")
            self.assertIsNone(an["skill_prescription"])

    def test_golden_2_case_missing_pseudopotential(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden2_case_missing_pseudopotential(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "case")
            self.assertEqual(an["primary_root_cause"]["code"], "CASE_MISSING_ASSET")

    def test_golden_3_agent_missing_dependency_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden3_agent_missing_dependency_search(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "agent")
            self.assertEqual(an["primary_root_cause"]["code"], "AGENT_PATH_OR_DEPENDENCY_DISCOVERY")

    def test_golden_4_agent_scf_error_repeated_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden4_agent_scf_error_repeated_command(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "agent")
            self.assertEqual(an["primary_root_cause"]["code"], "AGENT_ERROR_DIAGNOSIS")
            self.assertIsNotNone(an["skill_prescription"])

    def test_golden_5_verifier_regex_d_exponent_or_slash_defect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden5_verifier_regex_d_exponent(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "verifier")
            self.assertEqual(an["primary_root_cause"]["code"], "VERIFIER_REGEX_OR_PARSER_DEFECT")
            self.assertIsNone(an["skill_prescription"])

    def test_golden_6_numerical_md_trajectory_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden6_numerical_md_trajectory_divergence(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "numerical")

    def test_golden_7_unknown_missing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = build_golden7_unknown_missing_logs(Path(tmp))
            _, an, _ = self._run_case(job_dir, task_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "unknown")
            self.assertEqual(an["primary_root_cause"]["code"], "UNKNOWN_INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()