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
        proc = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--format",
            fmt,
        )
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
        proc = run_cli(
            "--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "all", "--phase", "collect"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((out / "trial_a_fail" / "evidence.json").is_file())
        self.assertTrue((out / "trial_a_fail" / "candidate-hypotheses.json").is_file())
        self.assertFalse((out / "trial_a_fail" / "analysis.json").exists())
        self.assertFalse((out / "trial_a_fail" / "report.md").exists())


class TestLifecycleAndRerun(unittest.TestCase):
    """Lifecycle tests: empty parameter combinations fail, and reruns purge stale artifacts."""

    def test_collect_phase_with_markdown_format_exits_2(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        proc = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--phase",
            "collect",
            "--format",
            "markdown",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("does not produce markdown reports", proc.stderr)
        self.assertFalse(out.exists())

    def test_rerun_collect_purges_stale_markdown_and_analysis(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"

        # 1. Initial run with all artifacts
        proc1 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--phase",
            "all",
            "--format",
            "both",
        )
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        for name in JSON_ARTIFACTS + MARKDOWN_ARTIFACTS:
            self.assertTrue((out / name).is_file(), f"{name} must exist after run 1")

        # 2. Subsequent rerun with phase collect & format json into the SAME directory
        proc2 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--phase",
            "collect",
            "--format",
            "json",
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)

        # Collect artifacts must exist
        self.assertTrue((out / "evidence.json").is_file())
        self.assertTrue((out / "candidate-hypotheses.json").is_file())

        # Old analysis and markdown reports must be purged
        self.assertFalse((out / "analysis.json").exists())
        for name in MARKDOWN_ARTIFACTS:
            self.assertFalse((out / name).exists(), f"stale {name} must be purged on collect rerun")

    def test_rerun_markdown_purges_stale_json(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"

        # 1. Initial run with all artifacts
        proc1 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--format",
            "both",
        )
        self.assertEqual(proc1.returncode, 0, proc1.stderr)

        # 2. Subsequent rerun with format markdown only
        proc2 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--trial",
            "trial_b_pass",
            "--output",
            str(out),
            "--format",
            "markdown",
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)

        for name in MARKDOWN_ARTIFACTS:
            self.assertTrue((out / name).is_file())
        for name in JSON_ARTIFACTS:
            self.assertFalse(
                (out / name).exists(), f"stale {name} must be purged on markdown-only rerun"
            )

    def test_single_trial_purges_stale_job_summary(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"

        # 1. Multi-trial run produces job_summary.json
        proc1 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--output",
            str(out),
            "--trial",
            "all",
        )
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertTrue((out / "job_summary.json").is_file())

        # 2. Single trial run targeting the same output root purges stale job_summary.json
        proc2 = run_cli(
            "--job",
            str(FIXTURE_JOB),
            "--output",
            str(out),
            "--trial",
            "trial_b_pass",
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertFalse((out / "job_summary.json").exists())

    def test_switching_multi_to_single_preserves_user_files_and_cleans_managed(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"

        # 1. Multi-trial run
        proc1 = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "all")
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertTrue((out / "trial_a_fail" / "report.md").is_file())
        self.assertTrue((out / "job_summary.json").is_file())

        # 2. Add user-authored custom files
        user_root_note = out / "custom_notes.txt"
        user_root_note.write_text("important user notes", encoding="utf-8")
        user_trial_calc = out / "trial_a_fail" / "user_calc.dat"
        user_trial_calc.write_text("some custom calculation", encoding="utf-8")

        # 3. Rerun single trial in same out dir
        proc2 = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "trial_b_pass")
        self.assertEqual(proc2.returncode, 0, proc2.stderr)

        # Single-trial outputs exist at root
        self.assertTrue((out / "evidence.json").is_file())
        self.assertTrue((out / "analysis.json").is_file())
        self.assertFalse((out / "job_summary.json").exists())

        # User files are untouched
        self.assertTrue(user_root_note.is_file())
        self.assertEqual(user_root_note.read_text(encoding="utf-8"), "important user notes")
        self.assertTrue(user_trial_calc.is_file())
        self.assertEqual(user_trial_calc.read_text(encoding="utf-8"), "some custom calculation")

        # Managed trial artifacts inside trial_a_fail were cleaned
        self.assertFalse((out / "trial_a_fail" / "report.md").exists())

    def test_switching_single_to_multi_preserves_user_files_and_cleans_managed(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"

        # 1. Single trial run
        proc1 = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "trial_b_pass")
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertTrue((out / "evidence.json").is_file())
        self.assertTrue((out / "report.md").is_file())

        # 2. Add user file in root
        user_root_note = out / "custom_notes.txt"
        user_root_note.write_text("keep this", encoding="utf-8")

        # 3. Rerun multi-trial in same out dir
        proc2 = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "all")
        self.assertEqual(proc2.returncode, 0, proc2.stderr)

        # Root managed trial artifacts must be purged
        self.assertFalse((out / "report.md").exists())
        self.assertFalse((out / "evidence.json").exists())
        self.assertTrue((out / "job_summary.json").is_file())

        # Multi-trial subdirs exist
        self.assertTrue((out / "trial_a_fail" / "report.md").is_file())
        self.assertTrue((out / "trial_b_pass" / "report.md").is_file())

        # User file is preserved
        self.assertTrue(user_root_note.is_file())
        self.assertEqual(user_root_note.read_text(encoding="utf-8"), "keep this")

    def test_atomic_publish_rollback_leaves_output_untouched_on_failure(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        out.mkdir()
        user_file = out / "existing_work.txt"
        user_file.write_text("do not touch", encoding="utf-8")

        # Point CLI to a non-existent trial to fail early
        proc = run_cli(
            "--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "non_existent_trial"
        )
        self.assertEqual(proc.returncode, 2)

        # out directory contains only the original user file, nothing was written or deleted
        children = list(out.iterdir())
        self.assertEqual(children, [user_file])
        self.assertEqual(user_file.read_text(encoding="utf-8"), "do not touch")

    def test_user_nested_subdirectory_and_report_preserved(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        user_sub = out / "user_dir"
        user_sub.mkdir(parents=True)
        user_report = user_sub / "report.md"
        user_report.write_text("# My User Report", encoding="utf-8")

        proc = run_cli("--job", str(FIXTURE_JOB), "--output", str(out), "--trial", "trial_b_pass")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(user_report.is_file(), "User report in user_dir must not be deleted")
        self.assertEqual(user_report.read_text(encoding="utf-8"), "# My User Report")

    def test_transactional_rollback_restores_pre_publish_state_on_copy_error(self) -> None:
        import shutil
        from unittest.mock import patch

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from analyze_case import _publish_staging_to_output

        tmp = Path(tempfile.mkdtemp())
        out = tmp / "out"
        out.mkdir()
        initial_file = out / "report.md"
        initial_file.write_text("INITIAL_REPORT_V1", encoding="utf-8")
        manifest_file = out / ".cfa_manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "schema_version": "cfa-manifest-v1",
                    "layout": "single",
                    "managed_files": ["report.md", ".cfa_manifest.json"],
                    "managed_dirs": [],
                }
            ),
            encoding="utf-8",
        )

        staging = Path(tempfile.mkdtemp())
        (staging / "report.md").write_text("NEW_REPORT_V2", encoding="utf-8")
        (staging / "analysis.json").write_text('{"new": true}', encoding="utf-8")

        original_copy2 = shutil.copy2
        call_count = 0

        def fail_on_second_copy(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise OSError("Simulated disk error during publish")
            return original_copy2(src, dst)

        with patch("shutil.copy2", side_effect=fail_on_second_copy):
            with self.assertRaises(OSError):
                _publish_staging_to_output(staging, out, is_multi_trial=False)

        # Rollback check: out must be restored to its exact pre-publish state
        self.assertEqual(initial_file.read_text(encoding="utf-8"), "INITIAL_REPORT_V1")
        self.assertFalse((out / "analysis.json").exists())


if __name__ == "__main__":
    unittest.main()
