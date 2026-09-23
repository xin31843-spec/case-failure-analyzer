#!/usr/bin/env python3
"""
CLI input-validation & skill-metadata regression tests (`tests/test_cli_validation.py`).

Guards two classes of defects fixed after review:
  1. `analyze_case.py` must fail fast (exit 2) on bad inputs and never emit a
     confident-looking report for a path/trial that does not exist.
  2. Skill metadata must stay discoverable: hyphen-case `SKILL.md` name and a
     standard `agents/openai.yaml` `interface:` block.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "scripts" / "analyze_case.py"

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
    )


class TestCliInputValidation(unittest.TestCase):
    def test_missing_job_path_exits_2_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            res = run_cli("--job", str(Path(tmp) / "does_not_exist"), "--output", str(out))
            self.assertEqual(res.returncode, 2, res.stderr)
            self.assertIn("does not exist", res.stderr)
            self.assertFalse(out.exists(), "no output must be written for a bad --job path")

    def test_empty_job_tree_exits_2_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "empty_job"
            job.mkdir()
            out = Path(tmp) / "out"
            res = run_cli("--job", str(job), "--output", str(out))
            self.assertEqual(res.returncode, 2, res.stderr)
            self.assertFalse(out.exists())

    def test_unknown_trial_exits_2_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "jobs" / "j"
            trial = job / "trial_a"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text(
                json.dumps({"trial_name": "trial_a"}), encoding="utf-8"
            )
            out = Path(tmp) / "out"
            res = run_cli("--job", str(job), "--trial", "nope", "--output", str(out))
            self.assertEqual(res.returncode, 2, res.stderr)
            self.assertIn("not found", res.stderr)
            self.assertFalse(out.exists())

    def test_missing_task_path_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "jobs" / "j"
            trial = job / "trial_a"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text(
                json.dumps({"trial_name": "trial_a"}), encoding="utf-8"
            )
            out = Path(tmp) / "out"
            res = run_cli(
                "--job", str(job), "--task", str(Path(tmp) / "no_task"), "--output", str(out)
            )
            self.assertEqual(res.returncode, 2, res.stderr)
            self.assertFalse(out.exists())

    def test_undocumented_legacy_draft_phase_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "jobs" / "j"
            trial = job / "trial_a"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text(
                json.dumps({"trial_name": "trial_a"}), encoding="utf-8"
            )
            res = run_cli(
                "--job", str(job), "--output", str(Path(tmp) / "out"), "--phase", "legacy-draft"
            )
            self.assertEqual(res.returncode, 2, res.stderr)
            self.assertIn("invalid choice", res.stderr)

    def test_legitimate_job_level_prestartup_failure_still_succeeds(self) -> None:
        """A job dir with result.json but no trial dirs is a valid job-level failure."""
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "jobs" / "job_level_fail"
            job.mkdir(parents=True)
            (job / "result.json").write_text(
                json.dumps({"n_total_trials": 0, "stats": {"n_errored_trials": 1}}),
                encoding="utf-8",
            )
            out = Path(tmp) / "out"
            res = run_cli("--job", str(job), "--output", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue((out / "analysis.json").is_file())


class TestSkillMetadata(unittest.TestCase):
    @unittest.skipIf(yaml is None, "PyYAML not available")
    def test_skill_name_is_hyphen_case(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must start with YAML frontmatter")
        frontmatter = yaml.safe_load(match.group(1))
        name = frontmatter["name"]
        self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$", f"non-compliant skill name: {name}")
        self.assertLessEqual(len(name), 64)

    @unittest.skipIf(yaml is None, "PyYAML not available")
    def test_frontmatter_uses_only_allowed_keys(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(re.match(r"^---\n(.*?)\n---", text, re.DOTALL).group(1))
        allowed = {"name", "description", "license", "allowed-tools", "metadata"}
        self.assertLessEqual(set(frontmatter), allowed)

    @unittest.skipIf(yaml is None, "PyYAML not available")
    def test_openai_yaml_uses_standard_interface_block(self) -> None:
        data = yaml.safe_load((REPO_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))
        self.assertIn("interface", data, "agents/openai.yaml must use the standard interface block")
        interface = data["interface"]
        self.assertIn("display_name", interface)
        short = interface["short_description"]
        self.assertTrue(25 <= len(short) <= 64, f"short_description length out of range: {len(short)}")


if __name__ == "__main__":
    unittest.main()
