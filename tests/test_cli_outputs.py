#!/usr/bin/env python3
"""
CLI output-shape tests (`tests/test_cli_outputs.py`)

Locks in the parts of the `analyze_case.py` CLI contract that the existing suite
did not exercise: the `--format` filter, the multi-trial output layout (per-trial
subdirectories plus `job_summary.json`), and `--phase collect`.

Every subprocess test in the suite before this file ran a single-trial job, so the
multi-trial branch in `main()` was entirely untested.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "scripts" / "analyze_case.py"
FIXTURE_JOB = REPO_ROOT / "tests" / "fixtures" / "regressions" / "mixed-job-success-trial" / "job"

JSON_ARTIFACTS = ("evidence.json", "analysis.json", "candidate-hypotheses.json")
MARKDOWN_ARTIFACTS = ("report.md", "report.zh.md", "report.en.md")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
    )


class TestFormatFilter(unittest.TestCase):
    def _run(self, fmt: str) -> Path:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        proc = run_cli("--job", str(FIXTURE_JOB), "--trial", "trial_b_pass",
                       "--output", str(out), "--format", fmt)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out

    def test_json_format_suppresses_markdown(self) -> None:
        out = self._run("json")
        for name in JSON_ARTIFACTS:
            self.assertTrue((out / name).is_file(), f"{name} should exist")
        for name in MARKDOWN_ARTIFACTS:
            self.assertFalse((out / name).exists(), f"{name} should be suppressed")

    def test_markdown_format_suppresses_json(self) -> None:
        out = self._run("markdown")
        for name in MARKDOWN_ARTIFACTS:
            self.assertTrue((out / name).is_file(), f"{name} should exist")
        for name in JSON_ARTIFACTS:
            self.assertFalse((out / name).exists(), f"{name} should be suppressed")

    def test_both_format_writes_everything(self) -> None:
        out = self._run("both")
        for name in JSON_ARTIFACTS + MARKDOWN_ARTIFACTS:
            self.assertTrue((out / name).is_file(), f"{name} should exist")


class TestMultiTrialLayout(unittest.TestCase):
    """The committed fixture has one failing and one passing trial."""

    def test_per_trial_subdirectories_and_job_summary(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        proc = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "all")
        self.assertEqual(proc.returncode, 0, proc.stderr)

        for trial in ("trial_a_fail", "trial_b_pass"):
            self.assertTrue((out / trial / "analysis.json").is_file(), trial)

        # The failing trial must not be polluted by the job-level errored count,
        # and the passing trial must stay passed.
        fail = json.loads((out / "trial_a_fail" / "analysis.json").read_text(encoding="utf-8"))
        passed = json.loads((out / "trial_b_pass" / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(passed["verdict"], "passed")
        self.assertEqual(passed["primary_root_cause"]["category"], "none")
        self.assertNotEqual(fail["verdict"], "passed")

        summary = json.loads((out / "job_summary.json").read_text(encoding="utf-8"))
        stats = summary["batch_statistics"]
        self.assertEqual(stats["total_trials"], 2)
        verdicts = {row["trial_name"]: row["verdict"] for row in summary["trials"]}
        self.assertEqual(verdicts, {"trial_a_fail": fail["verdict"], "trial_b_pass": "passed"})

    def test_phase_collect_writes_no_analysis(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        proc = run_cli("--job", str(FIXTURE_JOB), "--output", str(out),
                       "--trial", "all", "--phase", "collect")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((out / "trial_a_fail" / "evidence.json").is_file())
        self.assertTrue((out / "trial_a_fail" / "candidate-hypotheses.json").is_file())
        self.assertFalse((out / "trial_a_fail" / "analysis.json").exists())
        self.assertFalse((out / "trial_a_fail" / "report.md").exists())


class TestInvalidInputWritesNothing(unittest.TestCase):
    """`--job` resolution failures must exit 2 before creating the output tree."""

    def test_nonexistent_job_creates_no_output_directory(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        proc = run_cli("--job", str(tmp / "does-not-exist"), "--output", str(out))
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(out.exists(), "a rejected run must not create its output directory")


if __name__ == "__main__":
    unittest.main()