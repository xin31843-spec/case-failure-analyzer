#!/usr/bin/env python3
"""Unit tests for Phase 2 (`scripts/normalize_trajectory.py`)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from normalize_trajectory import normalize_trajectory


class TestTrajectoryNormalization(unittest.TestCase):
    def test_atif_v1_7_normalization_and_behavioral_signals(self) -> None:
        sample_traj = {
            "schema_version": "ATIF-v1.7",
            "session_id": "sess-1",
            "steps": [
                {
                    "step_id": 1,
                    "timestamp": "2026-09-19T05:00:00Z",
                    "source": "user",
                    "message": "Run CP2K and write results.json",
                },
                {
                    "step_id": 2,
                    "timestamp": "2026-09-19T05:01:00Z",
                    "source": "agent",
                    "message": "Running CP2K",
                    "tool_calls": [
                        {
                            "tool_call_id": "c1",
                            "function_name": "Bash",
                            "arguments": {"command": "cp2k.psmp -i h2o.inp -o h2o.out"},
                        }
                    ],
                    "observation": {
                        "results": [
                            {
                                "source_call_id": "c1",
                                "content": "ERROR: SCF run NOT converged\nExit code: 1",
                            }
                        ]
                    },
                },
                {
                    "step_id": 3,
                    "timestamp": "2026-09-19T05:02:00Z",
                    "source": "agent",
                    "message": "Retrying exact same command",
                    "tool_calls": [
                        {
                            "tool_call_id": "c2",
                            "function_name": "Bash",
                            "arguments": {"command": "cp2k.psmp -i h2o.inp -o h2o.out"},
                        }
                    ],
                    "observation": {
                        "results": [
                            {
                                "source_call_id": "c2",
                                "content": "ERROR: SCF run NOT converged\nExit code: 1",
                            }
                        ]
                    },
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "trajectory.json"
            p.write_text(json.dumps(sample_traj), encoding="utf-8")
            norm = normalize_trajectory(p, max_obs_bytes=500)
            self.assertTrue(norm["exists"])
            self.assertEqual(norm["schema_version"], "ATIF-v1.7")
            sig_types = {s["signal_type"] for s in norm["behavioral_signals"]}
            self.assertIn("repeated_failed_action", sig_types)
            self.assertIn("premature_completion", sig_types)

    def test_unknown_schema_and_truncation(self) -> None:
        sample_traj = {
            "schema_version": "CUSTOM-v9.9",
            "steps": [
                {
                    "step_id": 1,
                    "source": "user",
                    "message": "A" * 5000,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "trajectory.json"
            p.write_text(json.dumps(sample_traj), encoding="utf-8")
            norm = normalize_trajectory(p, max_obs_bytes=400)
            self.assertTrue(any("Unknown trajectory schema_version" in w for w in norm["warnings"]))
            ev = norm["events"][0]
            self.assertIn("TRUNCATED", ev["observation"])
            self.assertTrue(ev["observation_sha256"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
