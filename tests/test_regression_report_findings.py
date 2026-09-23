#!/usr/bin/env python3
"""
Regression test suite for the 12 verification findings in `/Users/hx/workspace/report.md`
(`tests/test_regression_report_findings.py`).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_case import ReplayNotSupportedError, analyze_single_trial, write_outputs
from discover_artifacts import discover_all
from extract_runtime_errors import extract_runtime_errors
from validate_analysis import validate_all


class TestReportRegressionFindings(unittest.TestCase):
    def test_01_mixed_job_passing_trial_not_polluted_by_job_stats(self) -> None:
        """#1: Job has n_errored_trials=1, but trial with reward=1.0 must be passed."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "mixed-job"
            trial_a = job_dir / "trial_a_fail"
            trial_b = job_dir / "trial_b_pass"
            task_dir = Path(tmp) / "tasks" / "sample-task"
            trial_a.mkdir(parents=True)
            (trial_b / "agent").mkdir(parents=True)
            (trial_b / "verifier").mkdir(parents=True)
            task_dir.mkdir(parents=True)

            (job_dir / "result.json").write_text(
                json.dumps({"n_total_trials": 2, "stats": {"n_errored_trials": 1}}),
                encoding="utf-8",
            )
            (trial_a / "exception.txt").write_text("RuntimeError: container failed", encoding="utf-8")
            (trial_b / "agent" / "trajectory.json").write_text(
                json.dumps({"schema_version": "ATIF-v1.7", "steps": []}),
                encoding="utf-8",
            )
            (trial_b / "verifier" / "reward.txt").write_text("1.0", encoding="utf-8")

            disc = discover_all(job_path=job_dir, task_path=task_dir)
            by_name = {t["trial_name"]: t for t in disc["trials"]}
            self.assertEqual(by_name["trial_b_pass"]["runtime"]["verification_status"], "passed")
            self.assertEqual(by_name["trial_b_pass"]["runtime"]["exit_status"], "completed")

            _, an_b, _, _ = analyze_single_trial(by_name["trial_b_pass"], job_dir=job_dir)
            self.assertEqual(an_b["verdict"], "passed")
            self.assertEqual(an_b["primary_root_cause"]["category"], "none")

    def test_02_bare_chaotic_keyword_does_not_trigger_numerical_or_agent(self) -> None:
        """#2: Bare 'chaotic' word in verify.log without trajectory/ensemble data must be unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "bare-chaotic"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "md-task"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            task_dir.mkdir(parents=True)

            (trial_dir / "agent" / "trajectory.json").write_text(
                json.dumps({"schema_version": "ATIF-v1.7", "steps": []}),
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "verify.log").write_text(
                "FAIL: agent output absent; protocol note mentions chaotic behaviour of the reference run",
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")

            disc = discover_all(job_path=job_dir, task_path=task_dir)
            _, an, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
            self.assertNotEqual(an["primary_root_cause"]["category"], "numerical")
            self.assertNotEqual(an["primary_root_cause"]["category"], "agent")
            self.assertEqual(an["primary_root_cause"]["category"], "unknown")

    def test_03_unrelated_d_exponent_in_reference_does_not_blame_verifier(self) -> None:
        """#3: Agent wrote wrong value 9.99E+02 while verify.log prints reference 1.23D+03 -> not verifier."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "unrelated-d"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "qe-task"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            (task_dir / "tests").mkdir(parents=True)

            (task_dir / "instruction.md").write_text("Compute ENERGY.", encoding="utf-8")
            (task_dir / "tests" / "verify.py").write_text(
                "import re\nVAL_RE = re.compile(r'ENERGY:\\s*([-\\d.E+]+)')\n",
                encoding="utf-8",
            )
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
                                        "function_name": "Write",
                                        "arguments": {"file_path": "/workspace/results.json"},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "verify.log").write_text(
                "FAIL: ENERGY mismatch: got 9.99E+02, expected reference 1.23D+03",
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")

            disc = discover_all(job_path=job_dir, task_path=task_dir)
            ev, an, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
            hazards = [v for v in ev["verifier_observations"] if v.get("type") == "parser_hazard"]
            self.assertEqual(hazards[0]["failure_binding"], "none")
            self.assertFalse(hazards[0]["triggered"])
            self.assertNotEqual(an["primary_root_cause"]["category"], "verifier")
            self.assertEqual(an["primary_root_cause"]["category"], "agent")

    def test_04_verifier_internal_crash_blames_verifier_not_agent(self) -> None:
        """#4: Verifier crashing with FileNotFoundError: /tmp/verify_tmp/refs.json must blame verifier."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "verifier-crash"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "crash-task"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            (task_dir / "tests").mkdir(parents=True)

            (trial_dir / "agent" / "trajectory.json").write_text(
                json.dumps({"schema_version": "ATIF-v1.7", "steps": []}),
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "verify.log").write_text(
                "Traceback (most recent call last):\n"
                "  File '/tests/verify.py', line 14, in <module>\n"
                "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/verify_tmp/refs.json'",
                encoding="utf-8",
            )
            (trial_dir / "verifier" / "reward.txt").write_text("0", encoding="utf-8")

            disc = discover_all(job_path=job_dir, task_path=task_dir)
            _, an, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "verifier")
            self.assertEqual(an["primary_root_cause"]["code"], "VERIFIER_RECOMPUTE_DEFECT")

    def test_05_claude_code_txt_single_source_of_truth_for_agent_started(self) -> None:
        """#5: Trial with only agent/claude-code.txt has agent_started=True in both discover and extract."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "claude-txt-job"
            trial_dir = job_dir / "trial_1"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "agent" / "claude-code.txt").write_text("Agent session log...", encoding="utf-8")

            disc = discover_all(job_path=job_dir)
            ext = extract_runtime_errors(job_dir=job_dir, trial_dir=trial_dir)
            self.assertTrue(disc["trials"][0]["runtime"]["agent_started"])
            self.assertTrue(ext["agent_started"])

    def test_06_null_job_stats_does_not_crash(self) -> None:
        """#6: result.json with {'stats': null} must not raise AttributeError."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "null-stats"
            trial_dir = job_dir / "trial_1"
            trial_dir.mkdir(parents=True)
            (job_dir / "result.json").write_text(json.dumps({"stats": None}), encoding="utf-8")
            (trial_dir / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")

            disc = discover_all(job_path=job_dir)
            self.assertEqual(disc["trials"][0]["metadata"]["job_stats"]["n_errored_trials"], 0)

    def test_08_validator_rejects_missing_hypotheses_and_deviation(self) -> None:
        """#8: validate_all must fail when competing_hypotheses or first_unrecovered_deviation is missing."""
        ev = {
            "case_id": "c1",
            "artifacts": [{"artifact_id": "art:trial_result", "rel_path": "result.json", "scope": "trial"}],
            "runtime": {"agent_started": True, "verifier_started": True},
            "timeline": [],
            "error_observations": [],
            "contract_observations": [],
            "verifier_observations": [],
            "scientific_observations": [],
            "missing_artifacts": [],
        }
        incomplete_analysis = {
            "schema_version": "failure-analysis-v1",
            "case_id": "c1",
            "verdict": "failed",
            "failure_stage": "unknown",
            "detection_stage": "runner",
            "failure_manifestation": {"type": "unknown", "summary": "fail"},
            "primary_root_cause": {"category": "unknown", "subtype": "insufficient_evidence", "code": "UNKNOWN_INSUFFICIENT_EVIDENCE", "confidence": 0.3},
            "contributing_factors": [],
            "evidence_refs": ["art:trial_result"],
            "excluded_hypotheses": [],
            "recommended_actions": [],
            "skill_prescription": None,
        }
        ok, errs = validate_all(ev, incomplete_analysis)
        self.assertFalse(ok)
        self.assertTrue(any("competing_hypotheses" in e or "first_unrecovered_deviation" in e for e in errs))

    def test_09_validator_rejects_single_line_or_empty_section_report(self) -> None:
        """#9: validate_all must reject single-line section titles or empty bodies in report.md."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "empty-case"
            trial_dir = job_dir / "trial_1"
            trial_dir.mkdir(parents=True)
            (trial_dir / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")
            disc = discover_all(job_path=job_dir)
            ev, an, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)

            fake_report = "Executive Summary / Case 状态 / 执行时间线 / 直接失败现象 / 主根因 / 伴随因素 / 证据链 / 排除的假设 / 建议修复责任方 / Skill 处方 / 缺失证据与分析限制"
            ok, errs = validate_all(ev, an, fake_report)
            self.assertFalse(ok)
            self.assertTrue(any("missing required section header" in e for e in errs))

    def test_10_11_replay_modes_raise_explicit_error(self) -> None:
        """#10 & #11: --replay verifier and --replay safe must fail explicitly rather than faking execution."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "replay-job"
            trial_dir = job_dir / "trial_1"
            trial_dir.mkdir(parents=True)
            (trial_dir / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")
            disc = discover_all(job_path=job_dir)
            with self.assertRaises(ReplayNotSupportedError):
                analyze_single_trial(disc["trials"][0], job_dir=job_dir, replay_mode="verifier")
            with self.assertRaises(ReplayNotSupportedError):
                analyze_single_trial(disc["trials"][0], job_dir=job_dir, replay_mode="safe")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "analyze_case.py"),
                    "--job",
                    str(job_dir),
                    "--output",
                    str(Path(tmp) / "out"),
                    "--replay",
                    "safe",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)

    def test_12_bilingual_report_outputs_generated(self) -> None:
        """Verify write_outputs produces bilingual report.md, report.zh.md, and report.en.md."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "bi-job"
            trial_dir = job_dir / "trial_1"
            trial_dir.mkdir(parents=True)
            (trial_dir / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")
            disc = discover_all(job_path=job_dir)
            ev, an, rep, skill_md = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
            out_dir = Path(tmp) / "out"
            write_outputs(out_dir, ev, an, rep, skill_md)
            self.assertTrue((out_dir / "report.md").is_file())
            self.assertTrue((out_dir / "report.zh.md").is_file())
            self.assertTrue((out_dir / "report.en.md").is_file())
            self.assertIn("Part II: English Edition", (out_dir / "report.md").read_text(encoding="utf-8"))

    def test_13_persistent_fixture_tree_and_cli_phases(self) -> None:
        """Verify persistent directory tree fixture under tests/fixtures/regressions/ and CLI --phase/--trial/--format."""
        fixture_job = Path(__file__).resolve().parent / "fixtures" / "regressions" / "mixed-job-success-trial" / "job"
        self.assertTrue(fixture_job.is_dir())
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "cli_out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "analyze_case.py"),
                    "--job",
                    str(fixture_job),
                    "--trial",
                    "trial_b_pass",
                    "--output",
                    str(out_dir),
                    "--phase",
                    "all",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            an = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(an["verdict"], "passed")
            self.assertTrue((out_dir / "candidate-hypotheses.json").is_file())

    def test_14_job_dir_with_stray_agent_folder_not_misclassified_as_single_trial(self) -> None:
        """P2 #12: Job directory containing child trials and a stray agent/ folder must still discover child trials."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "stray-agent-job"
            (job_dir / "agent").mkdir(parents=True)
            trial_1 = job_dir / "trial_1"
            trial_1.mkdir(parents=True)
            (trial_1 / "trial.log").write_text("step 1", encoding="utf-8")
            (trial_1 / "result.json").write_text(json.dumps({"trial_name": "trial_1"}), encoding="utf-8")

            disc = discover_all(job_path=job_dir)
            self.assertEqual(len(disc["trials"]), 1)
            self.assertEqual(disc["trials"][0]["trial_name"], "trial_1")

    def test_15_co_occurring_case_and_verifier_defects_preserved(self) -> None:
        """§7 #3: When both missing asset (case) and verifier defect occur, verifier defect is preserved in contributing_factors."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "co-defect"
            trial_dir = job_dir / "trial_1"
            task_dir = Path(tmp) / "tasks" / "co-task"
            (trial_dir / "agent").mkdir(parents=True)
            (trial_dir / "verifier").mkdir(parents=True)
            (task_dir / "environment" / "assets").mkdir(parents=True)
            (task_dir / "tests").mkdir(parents=True)

            (task_dir / "instruction.md").write_text(
                "Use `/workspace/assets/missing.UPF`.", encoding="utf-8"
            )
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

            disc = discover_all(job_path=job_dir, task_path=task_dir)
            _, an, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
            self.assertEqual(an["primary_root_cause"]["category"], "case")
            self.assertTrue(any(cf["category"] == "verifier" for cf in an["contributing_factors"]))
            # Verify candidate_hypotheses from generate_candidate_hypotheses were merged into competing_hypotheses
            self.assertTrue(any(h["category"] == "verifier" for h in an["competing_hypotheses"]))

    def test_16_non_dict_stats_in_extract_runtime_errors_does_not_crash(self) -> None:
        """Residual #1: {'stats': 'x'} with trial_dir=None must not crash with AttributeError."""
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "string-stats"
            job_dir.mkdir(parents=True)
            (job_dir / "result.json").write_text(
                json.dumps({"stats": "x", "task_id": "string-id", "config": "string-cfg"}),
                encoding="utf-8",
            )
            ext = extract_runtime_errors(job_dir=job_dir, trial_dir=None)
            self.assertFalse(ext["agent_started"])
            disc = discover_all(job_path=job_dir)
            self.assertEqual(disc["trials"][0]["metadata"]["job_stats"]["n_errored_trials"], 0)

    def test_17_error_family_registry_missing_or_empty_raises_explicit_error(self) -> None:
        """Residual #4: Missing or empty error-families.json must raise explicit error instead of returning 0 adapters."""
        from extract_scientific_errors import build_scientific_adapters, load_error_family_registry

        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "nonexistent.json"
            with self.assertRaises(FileNotFoundError):
                load_error_family_registry(missing_path)
            with self.assertRaises(FileNotFoundError):
                build_scientific_adapters(missing_path)

            empty_path = Path(tmp) / "empty.json"
            empty_path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_error_family_registry(empty_path)

    def test_18_confidence_is_pure_evidence_ratio_without_literal_overrides(self) -> None:
        """Residual #3: compute_evidence_confidence uses normalized ratio (points / 6) and no literal overrides exist."""
        from confidence import MAX_EVIDENCE_POINTS, compute_evidence_confidence

        c0, _, s0 = compute_evidence_confidence(ruled_out=True)
        self.assertEqual((c0, s0), (0.0, "low"))
        c_pass, _, s_pass = compute_evidence_confidence(verdict_passed=True)
        self.assertEqual((c_pass, s_pass), (1.0, "high"))
        c3, _, s3 = compute_evidence_confidence(direct_causal_evidence=2, cross_source_corroboration=1)
        self.assertEqual(c3, round(3 / MAX_EVIDENCE_POINTS, 2))
        self.assertEqual(s3, "medium")


if __name__ == "__main__":
    unittest.main()
