#!/usr/bin/env python3
"""Unit tests for Phase 4 (`scripts/audit_contract.py`)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_contract import audit_contract


class TestContractAudit(unittest.TestCase):
    def test_detects_missing_asset_and_verifier_regex_defect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "tasks" / "sample-task"
            (task_dir / "environment" / "assets").mkdir(parents=True)
            (task_dir / "tests").mkdir(parents=True)
            (task_dir / "instruction.md").write_text(
                "Copy `/workspace/assets/Si_missing.UPF` and write `results.json`:\n"
                '```json\n{"values": {"energy": -10.0}, "units": {"energy": "Ry"}}\n```',
                encoding="utf-8",
            )
            (task_dir / "tests" / "verify.py").write_text(
                "import re\n"
                "ENERGY_RE = re.compile(r'ENERGY:\\s*([-\\d.E+]+)')\n"
                "for m in re.finditer(r'&(\\w+)\\b(.*?)/', text, re.DOTALL):\n"
                "    pass\n",
                encoding="utf-8",
            )

            trial_dir = Path(tmp) / "jobs" / "trial1"
            (trial_dir / "verifier").mkdir(parents=True)
            (trial_dir / "verifier" / "verify.log").write_text(
                "FAIL: outdir mismatch: scf '' vs bands '' — value 1.23D+03",
                encoding="utf-8",
            )

            res = audit_contract(task_dir=task_dir, trial_dir=trial_dir)
            alignments = {c["alignment"] for c in res["contract_observations"]}
            self.assertIn("case_defect", alignments)
            self.assertIn("verifier_defect", alignments)
            hazard_subtypes = {v["matched_text"] for v in res["verifier_observations"]}
            self.assertIn("namelist_slash_truncation", hazard_subtypes)
            self.assertIn("scientific_notation_missing_d_exponent", hazard_subtypes)


if __name__ == "__main__":
    unittest.main()
