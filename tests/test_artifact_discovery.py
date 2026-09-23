#!/usr/bin/env python3
"""Unit tests for Phase 1 (`scripts/discover_artifacts.py`)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from discover_artifacts import discover_all


class TestArtifactDiscovery(unittest.TestCase):
    def test_job_only_infra_failure_without_trial_or_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-infra-fail"
            job_dir.mkdir(parents=True)
            (job_dir / "result.json").write_text(
                json.dumps({"stats": {"n_errored_trials": 1}}), encoding="utf-8"
            )
            res = discover_all(job_path=job_dir)
            self.assertEqual(len(res["trials"]), 1)
            trial_inv = res["trials"][0]
            self.assertFalse(trial_inv["runtime"]["agent_started"])
            self.assertFalse(trial_inv["runtime"]["verifier_started"])
            self.assertEqual(trial_inv["runtime"]["exit_status"], "errored")
            self.assertIn("agent/trajectory.json", trial_inv["missing_artifacts"])

    def test_multi_trial_discovery_and_successful_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs" / "ccb-multi"
            t1 = job_dir / "task__trial1"
            t2 = job_dir / "task__trial2"
            for t, reward in [(t1, "0"), (t2, "1")]:
                (t / "agent").mkdir(parents=True)
                (t / "verifier").mkdir(parents=True)
                (t / "agent" / "trajectory.json").write_text(
                    json.dumps({"schema_version": "ATIF-v1.7", "steps": []}),
                    encoding="utf-8",
                )
                (t / "verifier" / "reward.txt").write_text(reward, encoding="utf-8")
                (t / "result.json").write_text(
                    json.dumps({"trial_name": t.name, "task_name": "task"}),
                    encoding="utf-8",
                )

            res = discover_all(job_path=job_dir, trial_filter="all")
            self.assertEqual(len(res["trials"]), 2)
            self.assertEqual(res["trials"][0]["runtime"]["exit_status"], "failed")
            self.assertEqual(res["trials"][1]["runtime"]["exit_status"], "completed")
            self.assertTrue(res["trials"][0]["runtime"]["agent_started"])


if __name__ == "__main__":
    unittest.main()
