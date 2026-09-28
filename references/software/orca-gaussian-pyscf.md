# Molecular Quantum Chemistry Knowledge Base (`orca-gaussian-pyscf`: ORCA, Gaussian, PySCF, Psi4, Q-Chem, NWChem)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for molecular quantum chemistry and ab initio wave-function packages (`ORCA`, `Gaussian 09/16`, `PySCF`, `Psi4`, `Q-Chem`, `NWChem`).
Remember: **Matching an error family does NOT automatically blame the agent.**

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `scf_diis_convergence_failure` | `SCF NOT CONVERGED AFTER .* CYCLES`, `Convergence failure -- run terminated`, `Error termination via Lnk1e.*l502.exe`, `SCF did not converge` | `open_shell_transition_metal_without_slowconv_or_soscf`, `wrong_charge_or_multiplicity_assignment`, `oscillating_diis_without_level_shift_or_damping` | Check SCF energy/DIIS error oscillation and whether `SlowConv`, `SOSCF`, `KDIIS`, or `SCF=(XQC,MaxCycle)` was enabled |
| `geometry_opt_ts_imaginary_freq` | `Error termination request processed by link 9999`, `THE OPTIMIZATION DID NOT CONVERGE`, `imaginary frequencies.*found`, `Eigenvalue .* of internal coordinate B-matrix is zero` | `flat_potential_energy_surface_without_calcfc_or_tightopt`, `transition_state_missing_single_imaginary_mode`, `linear_bend_internal_coordinate_singularity` | Inspect Hessian vibrational frequency spectrum and `MaxIter` / `Recalc_Hess` / `Opt=(CalcFC,TS)` keywords |
| `basis_set_linear_dependence` | `Near linear dependence in overlap matrix`, `Basis set .* not recognized`, `AuxJ basis set is missing`, `Error termination via Lnk1e.*l301.exe` | `diffuse_functions_causing_overlap_singularity`, `missing_auxiliary_ri_jk_basis_set`, `unsupported_element_for_chosen_basis` | Check smallest overlap eigenvalue (`S-Matrix`), `sthresh` / `lindep` threshold, and auxiliary basis specification |
| `charge_spin_multiplicity_invalid` | `Multiplicity .* is incompatible with number of electrons`, `The combination of multiplicity .* and .* electrons is impossible`, `num_elec .* and spin .* are not consistent` | `odd_even_electron_parity_violation`, `missing_counterion_or_protonation_state_charge`, `pyscf_2s_spin_convention_vs_2s_plus_1_multiplicity` | Verify total electron count $N_e$ against charge $Q$ and multiplicity $2S+1$ (or PySCF `mol.spin = 2S`) |
| `post_hf_memory_integral_overflow` | `not enough memory for CCSD`, `MaxCore.*exceeded`, `Out-of-memory error in .* integral`, `Write error in NtrExt1` | `insufficient_maxcore_per_mpi_rank`, `missing_dlpno_or_resolution_of_identity_approximation`, `scratch_disk_full_for_two_electron_integrals` | Compare `%maxcore` * `%pal nprocs` (or `%mem`) against container memory and scratch disk quota |
