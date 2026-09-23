#!/usr/bin/env python3
"""
Phase 5: Scientific Software Error Knowledge Layer (`scripts/extract_scientific_errors.py`)

Runs deterministic error-family adapters across CP2K, Quantum ESPRESSO, LAMMPS,
xTB, ASE, and RDKit over trajectory observations and verifier logs.
Outputs structured `scientific_observations` with `candidate_causes` and
`required_discriminating_evidence` without jumping directly to agent blame.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AdapterPattern = Tuple[str, str, re.Pattern[str], List[str], List[str]]

SCIENTIFIC_ADAPTERS: List[AdapterPattern] = [
    # ── CP2K ───────────────────────────────────────────────────────────────────
    (
        "cp2k",
        "basis_or_potential_missing",
        re.compile(
            r"(?:The specified OLD file <.*?> cannot be opened|cannot find basis set|"
            r"BASIS_MOLOPT.*cannot be opened|GTH_POTENTIALS.*cannot be opened)",
            re.IGNORECASE,
        ),
        [
            "missing_symlink_or_copy_from_opt_cp2k_data",
            "wrong_filename_in_dft_section",
            "missing_basis_in_container_image",
        ],
        [
            "`/opt/cp2k/data/` directory contents",
            "Agent `cp` or `ln -s` command history",
            "`BASIS_SET_FILE_NAME` and `POTENTIAL_FILE_NAME` in `.inp`",
        ],
    ),
    (
        "cp2k",
        "scf_nonconvergence",
        re.compile(r"(?:SCF run NOT converged|Leaving inner SCF loop.*not converged)", re.IGNORECASE),
        [
            "bad_initial_guess",
            "insufficient_scf_iterations",
            "inappropriate_mixing_or_ot",
            "invalid_geometry",
            "resource_termination",
        ],
        [
            "SCF iteration history",
            "geometry sanity",
            "MAX_SCF setting",
            "process exit reason",
        ],
    ),
    (
        "cp2k",
        "cholesky_decomposition_failure",
        re.compile(
            r"(?:Cholesky decomposition failed|dbcsr_cholesky_decompose|matrix is not positive definite)",
            re.IGNORECASE,
        ),
        [
            "overlapping_atomic_coordinates",
            "basis_set_linear_dependency",
            "wrong_cell_dimensions_abc",
        ],
        [
            "Minimum interatomic distance in `&COORD`",
            "`&CELL ABC` and `PERIODIC` settings",
            "`EPS_PGF_ORB` setting",
        ],
    ),
    (
        "cp2k",
        "geoopt_not_converged",
        re.compile(r"(?:MAXIMUM NUMBER OF OPTIMIZATION STEPS REACHED|Geometry optimization NOT converged)", re.IGNORECASE),
        [
            "insufficient_max_iter",
            "noisy_forces_low_cutoff",
            "bad_initial_geometry",
        ],
        [
            "`MAX_ITER` and `MAX_FORCE` settings",
            "Force progression across optimization steps",
        ],
    ),
    (
        "cp2k",
        "input_parser_error",
        re.compile(r"(?:found an unknown keyword|unknown subsection|CPASSERT failed)", re.IGNORECASE),
        [
            "agent_input_syntax_error",
            "cp2k_version_keyword_mismatch",
            "corrupt_provided_inp_asset",
        ],
        [
            "CP2K parser error line number",
            "Diff between `/workspace/assets/*.inp` and executed `.inp`",
        ],
    ),
    # ── Quantum ESPRESSO ───────────────────────────────────────────────────────
    (
        "quantum-espresso",
        "scf_convergence_not_achieved",
        re.compile(r"(?:convergence NOT achieved after \d+ iterations)", re.IGNORECASE),
        [
            "insufficient_electron_maxstep",
            "high_mixing_beta",
            "metallic_system_without_smearing",
            "bad_crystal_structure",
        ],
        [
            "`electron_maxstep` and `mixing_beta` in `&ELECTRONS`",
            "`occupations` and `degauss` in `&SYSTEM`",
            "SCF accuracy progression per iteration",
        ],
    ),
    (
        "quantum-espresso",
        "c_bands_or_diagonalization_failure",
        re.compile(r"(?:c_bands:.*eigenvalues not converged|S matrix not positive definite|davcio)", re.IGNORECASE),
        [
            "overlapping_atoms_or_wrong_units",
            "corrupt_charge_density_in_outdir",
            "inappropriate_diagonalization_algorithm",
        ],
        [
            "`ATOMIC_POSITIONS` unit card (`alat` vs `angstrom` vs `crystal`)",
            "`CELL_PARAMETERS` / `celldm(1)`",
            "`outdir` and `prefix` consistency",
        ],
    ),
    (
        "quantum-espresso",
        "pseudopotential_mismatch_or_missing",
        re.compile(r"(?:Error in routine readpp|file .*\.upf not found|wrong charge)", re.IGNORECASE),
        [
            "wrong_pseudo_dir_path",
            "missing_upf_in_task_assets",
            "wrong_atomic_species_filename",
        ],
        [
            "`pseudo_dir` in `&CONTROL`",
            "Contents of `/workspace/assets/` and `/opt/qe/pseudo/`",
            "`ATOMIC_SPECIES` card",
        ],
    ),
    (
        "quantum-espresso",
        "workflow_prefix_or_outdir_mismatch",
        re.compile(r"(?:outdir mismatch|prefix mismatch|pwscf\.xml.*not found|cannot open xml data file)", re.IGNORECASE),
        [
            "inconsistent_outdir_or_prefix_between_scf_and_bands",
            "verifier_namelist_regex_slash_truncation_defect",
            "missing_scf_step_before_bands",
        ],
        [
            "`prefix` and `outdir` in `si_scf.in`, `si_bands.in`, and `bandsx.in`",
            "Whether `outdir/pwscf.xml` exists on disk",
            "Verifier `parse_namelists` regex behavior on paths containing `/`",
        ],
    ),
    # ── LAMMPS ─────────────────────────────────────────────────────────────────
    (
        "lammps",
        "lost_atoms",
        re.compile(r"(?:ERROR: Lost atoms|Lost atoms: original)", re.IGNORECASE),
        [
            "excessive_timestep",
            "overlapping_initial_geometry",
            "missing_energy_minimization",
            "fixed_boundary_escape",
        ],
        [
            "`timestep` and `units` settings",
            "Initial potential energy and forces at step 0",
            "`boundary` settings (`p p p` vs `f f f`)",
        ],
    ),
    (
        "lammps",
        "non_numeric_pressure_or_energy",
        re.compile(r"(?:Non-numeric pressure - simulation unstable|nan\s+nan)", re.IGNORECASE),
        [
            "overlapping_atoms_in_data_file",
            "wrong_pair_coeff_parameters",
            "unstable_npt_barostat_damping",
        ],
        [
            "Step 0 `PotEng` and `Press` values",
            "`pair_style` and `pair_coeff` arguments",
            "Interatomic distances in input `.data`",
        ],
    ),
    (
        "lammps",
        "bond_atoms_missing",
        re.compile(r"(?:Bond atoms .* missing on proc|Angle atoms .* missing)", re.IGNORECASE),
        [
            "communication_cutoff_too_small",
            "excessive_bond_stretching_from_bad_timestep",
            "inconsistent_molecular_topology",
        ],
        [
            "`comm_modify cutoff` and `neighbor` settings",
            "`timestep` and `fix shake` / bond parameters",
        ],
    ),
    (
        "lammps",
        "restart_continuation_divergence",
        re.compile(
            r"(?:Continuation must start at step|final_pe=.*differs from ref|first_pe=.*differs from ref)",
            re.IGNORECASE,
        ),
        [
            "agent_used_read_data_or_reinitialized_velocities_instead_of_read_restart",
            "agent_called_reset_timestep",
            "different_ensemble_or_fix_parameters_after_restart",
            "wrong_timestep_or_pair_style_in_continuation",
        ],
        [
            "Whether `read_restart` vs `read_data` was used in LAMMPS input",
            "Whether `reset_timestep` or `velocity create` was called",
            "`fix nve` / `fix nvt` parameters compared to `instruction.md`",
            "Step 1000 `first_pe` match vs Step 3000 `final_pe` drift",
        ],
    ),
    (
        "lammps",
        "thermo_column_or_ecoh_mismatch",
        re.compile(r"(?:ecoh=.*!= log last line|Expected >=2 thermo lines)", re.IGNORECASE),
        [
            "verifier_hardcoded_thermo_column_index",
            "agent_custom_thermo_style_column_order",
            "inconsistent_post_processing_formula",
        ],
        [
            "`thermo_style` header line (`Step ...`) in `log.lammps`",
            "Column index assumed by `tests/verify.py` (`thermo[-1].split()[1]`)",
            "Whether `results.json` `ecoh` passed Layer 3 reference check",
        ],
    ),
    # ── xTB ────────────────────────────────────────────────────────────────────
    (
        "xtb",
        "scc_nonconvergence",
        re.compile(r"(?:convergence criteria cannot be satisfied|self consistent charge iterator did not converge)", re.IGNORECASE),
        [
            "wrong_molecular_charge_or_uhf",
            "unphysical_initial_xyz_coordinates",
            "small_homo_lumo_gap_requiring_etemp",
        ],
        [
            "`--chrg` and `--uhf` CLI flags",
            "Input `.xyz` structure sanity",
            "`--etemp` / `--iterations` settings",
        ],
    ),
    (
        "xtb",
        "invalid_charge_or_multiplicity",
        re.compile(r"(?:Number of electrons and spin multiplicity do not match)", re.IGNORECASE),
        [
            "mismatch_between_electron_count_and_uhf",
            "missing_atoms_in_xyz",
        ],
        [
            "Total electron count vs `--chrg` and `--uhf`",
        ],
    ),
    # ── ASE ────────────────────────────────────────────────────────────────────
    (
        "ase",
        "calculator_or_property_error",
        re.compile(r"(?:Atoms object has no calculator|PropertyNotImplementedError)", re.IGNORECASE),
        [
            "calculator_not_assigned_to_atoms",
            "atoms_copy_stripped_calculator",
        ],
        [
            "`atoms.calc = ...` assignment in script",
            "`atoms.copy()` calls before `get_potential_energy()`",
        ],
    ),
    (
        "ase",
        "optimizer_or_neb_nonconvergence",
        re.compile(r"(?:NEB.*not converged|fmax.*not reached|Maximum number of steps reached)", re.IGNORECASE),
        [
            "insufficient_optimizer_steps",
            "inappropriate_neb_interpolation_or_spring_constant",
            "wrong_constraints_fixatoms",
        ],
        [
            "`opt.run(fmax=..., steps=...)` arguments",
            "`FixAtoms` constraint indices",
        ],
    ),
    # ── RDKit ──────────────────────────────────────────────────────────────────
    (
        "rdkit",
        "smiles_or_sanitization_error",
        re.compile(
            r"(?:SMILES Parse Error|Explicit valence for atom .* is greater than permitted|"
            r"MolSanitizeException|KekulizeException)",
            re.IGNORECASE,
        ),
        [
            "invalid_smiles_or_unhandled_none_molecule",
            "missing_rdmolstandardize_cleanup_or_uncharger",
            "csv_header_parsed_as_smiles",
        ],
        [
            "Input SMILES string and `Chem.MolFromSmiles` null checks",
            "Standardization pipeline (`Cleanup`, `LargestFragmentChooser`, `Uncharger`)",
        ],
    ),
    (
        "rdkit",
        "conformer_or_mmff_error",
        re.compile(
            r"(?:Bad Conformer Id|MMFFGetMoleculeProperties returned None|EmbedMultipleConfs.*-1)",
            re.IGNORECASE,
        ),
        [
            "missing_explicit_hydrogens_before_embedding",
            "missing_uff_fallback_when_mmff_unavailable",
            "unseeded_etkdg_conformer_generation",
        ],
        [
            "Whether `Chem.AddHs(mol)` was called prior to `EmbedMultipleConfs`",
            "`randomSeed` parameter in `ETKDGv3()`",
        ],
    ),
]


def extract_scientific_errors(
    trial_dir: Optional[Path],
    normalized_traj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observations: List[Dict[str, Any]] = []
    seen = set()
    sci_counter = 1

    # 1. Scan trajectory events
    if normalized_traj:
        for ev in normalized_traj.get("events") or []:
            text = f"{ev.get('command') or ''}\n{ev.get('observation') or ''}"
            ev_id = ev.get("event_id", "trajectory:unknown")
            for sw, family, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
                m = pattern.search(text)
                if m:
                    dedup_key = (sw, family, m.group(0)[:80])
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    observations.append(
                        {
                            "sci_id": f"sci:{sci_counter}",
                            "software": sw,
                            "error_family": family,
                            "matched_text": m.group(0)[:240],
                            "source_ref": ev_id,
                            "candidate_causes": causes,
                            "required_discriminating_evidence": req_ev,
                        }
                    )
                    sci_counter += 1

    # 2. Scan verifier/verify.log
    if trial_dir and (trial_dir / "verifier" / "verify.log").is_file():
        vlog = (trial_dir / "verifier" / "verify.log").read_text(encoding="utf-8", errors="replace")
        for sw, family, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
            m = pattern.search(vlog)
            if m:
                dedup_key = (sw, family, m.group(0)[:80])
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                observations.append(
                    {
                        "sci_id": f"sci:{sci_counter}",
                        "software": sw,
                        "error_family": family,
                        "matched_text": vlog.splitlines()[0][:240] if vlog.splitlines() else m.group(0),
                        "source_ref": "verifier/verify.log",
                        "candidate_causes": causes,
                        "required_discriminating_evidence": req_ev,
                    }
                )
                sci_counter += 1

    return {"scientific_observations": observations}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract scientific software error observations.")
    parser.add_argument("--trial-dir", required=False, type=Path, default=None, help="Path to trial directory")
    parser.add_argument("--trajectory-norm", required=False, type=Path, default=None, help="Normalized trajectory JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    norm_traj = None
    if args.trajectory_norm and args.trajectory_norm.is_file():
        norm_traj = json.loads(args.trajectory_norm.read_text(encoding="utf-8", errors="replace"))

    res = extract_scientific_errors(trial_dir=args.trial_dir, normalized_traj=norm_traj)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
