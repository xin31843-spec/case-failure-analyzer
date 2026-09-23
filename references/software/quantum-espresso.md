# Quantum ESPRESSO Error Knowledge Base (`quantum-espresso`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for Quantum ESPRESSO (`pw.x`, `bands.x`, `dos.x`, `ph.x`).

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `scf_convergence_not_achieved` | `convergence NOT achieved after`, `history of scf` | `insufficient_electron_maxstep`, `high_mixing_beta`, `metallic_state_without_smearing`, `bad_crystal_geometry` | Check `electron_maxstep`, `mixing_beta`, `occupations='smearing'`, and total energy oscillation per SCF iteration |
| `c_bands_or_diagonalization_failure` | `c_bands: .* eigenvalues not converged`, `davcio`, `S matrix not positive definite`, `cholesky` | `overlapping_atomic_positions`, `bad_pseudopotential_choice`, `wrong_celldm_or_units`, `insufficient_ecutwfc` | Check `ATOMIC_POSITIONS` units (`alat` vs `angstrom` vs `crystal`), `ibrav`/`CELL_PARAMETERS`, and interatomic distances |
| `charge_or_electron_count_error` | `charge is wrong`, `two occurrences`, `odd number of electrons` | `wrong_tot_charge`, `missing_nspin_for_open_shell`, `wrong_nbnd` | Compare valence electrons from UPF pseudopotentials against `nbnd`, `tot_charge`, and `nspin` |
| `pseudopotential_read_failure` | `Error in routine readpp`, `file .* not found`, `UPF` | `wrong_pseudo_dir`, `missing_upf_file_in_assets`, `corrupt_upf_header` | Check `pseudo_dir` in `&CONTROL`, `/workspace/assets/` contents, and `$ESPRESSO_PSEUDO` |
| `prefix_or_outdir_chain_mismatch` | `pwscf.xml not found`, `cannot open xml data file`, `outdir mismatch` | `different_prefix_or_outdir_across_steps`, `verifier_namelist_regex_slash_bug`, `scf_not_run_before_nscf_or_bands` | Compare `prefix` and `outdir` in `scf.in`, `bands.in`, and `bandsx.in`; also check if `verify.py` truncated namelist at `/` |
| `ecut_or_kpoint_misconfiguration` | `ecutwfc`, `k-points`, `incompatible nr1, nr2, nr3` | `ecutwfc_differs_from_prompt`, `wrong_kpoint_grid_or_crystal_b_path`, `dual_ecutrho_mismatch_for_uspp` | Compare `ecutwfc`, `ecutrho`, and `K_POINTS` card against `instruction.md` |
