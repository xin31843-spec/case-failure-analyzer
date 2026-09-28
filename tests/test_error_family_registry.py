#!/usr/bin/env python3
"""
Scientific Error Family Registry Alignment Test (`tests/test_error_family_registry.py`)

Verifies that `references/error-families.json`, `scripts/extract_scientific_errors.py`,
and all 11 `references/software/*.md` knowledge base tables use identical `error_family`
identifiers and that every documented family is registered and implemented.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT_DIR / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from extract_scientific_errors import SCIENTIFIC_ADAPTERS, load_error_family_registry


class TestErrorFamilyRegistryAlignment(unittest.TestCase):
    def test_documented_families_match_registry_and_adapters(self) -> None:
        registry = load_error_family_registry()
        self.assertTrue(registry, "error-families.json must not be empty")

        adapter_pairs = {(sw, fam) for sw, fam, *_ in SCIENTIFIC_ADAPTERS}

        software_files = sorted((ROOT_DIR / "references" / "software").glob("*.md"))
        self.assertEqual(len(software_files), 11)

        total_documented = 0
        for md_path in software_files:
            software = md_path.stem
            self.assertIn(software, registry, f"Software {software} missing from error-families.json")
            reg_families = registry[software]

            text = md_path.read_text(encoding="utf-8")
            # Extract table row first-column backticked identifiers `family_name`
            doc_families = re.findall(r"(?m)^\|\s*`([a-z0-9_]+)`\s*\|", text)
            self.assertGreater(len(doc_families), 0, f"No error families found in {md_path.name}")

            for fam in doc_families:
                total_documented += 1
                self.assertIn(
                    fam,
                    reg_families,
                    f"Documented family `{fam}` in `{md_path.name}` is missing from `references/error-families.json`",
                )
                spec = reg_families[fam]
                self.assertEqual(spec.get("status"), "implemented")
                self.assertTrue(spec.get("patterns"), f"Family `{fam}` must have regex patterns")
                self.assertTrue(
                    spec.get("required_discriminating_evidence"),
                    f"Family `{fam}` must declare required_discriminating_evidence",
                )
                self.assertIn(
                    (software, fam),
                    adapter_pairs,
                    f"Family `{software}:{fam}` is not active in SCIENTIFIC_ADAPTERS",
                )

        self.assertEqual(total_documented, 60)

    def test_broad_domain_mlip_vasp_orca_gromacs_generic_extraction(self) -> None:
        from extract_scientific_errors import extract_scientific_errors

        fake_traj = {
            "events": [
                {
                    "event_id": "trajectory:step:1",
                    "command": "python run_mace_md.py",
                    "observation": "RuntimeError: NaN detected in predicted forces during MACE rollout",
                },
                {
                    "event_id": "trajectory:step:2",
                    "command": "mpirun -np 4 vasp_std",
                    "observation": "Error EDDDAV: Call to ZHEEV failed, returncode = 6 1 9",
                },
                {
                    "event_id": "trajectory:step:3",
                    "command": "orca sp.inp > sp.out",
                    "observation": "Multiplicity 2 is incompatible with number of electrons (18)",
                },
                {
                    "event_id": "trajectory:step:4",
                    "command": "gmx mdrun -deffnm npt",
                    "observation": "Water molecule starting at atom 1423 can not be settled",
                },
                {
                    "event_id": "trajectory:step:5",
                    "command": "python solve_pde.py",
                    "observation": "numpy.linalg.LinAlgError: Singular matrix in stiffness assembly",
                },
            ]
        }
        res = extract_scientific_errors(trial_dir=None, normalized_traj=fake_traj)
        families = {(o["software"], o["error_family"]) for o in res["scientific_observations"]}
        self.assertIn(("mlip", "mlip_rollout_ood_instability"), families)
        self.assertIn(("vasp-abacus", "edddav_zheev_subspace_error"), families)
        self.assertIn(("orca-gaussian-pyscf", "charge_spin_multiplicity_invalid"), families)
        self.assertIn(("gromacs-amber-openmm", "lincs_shake_constraint_blowup"), families)
        self.assertIn(("generic-scientific", "linalg_singular_ill_conditioned"), families)


if __name__ == "__main__":
    unittest.main()
