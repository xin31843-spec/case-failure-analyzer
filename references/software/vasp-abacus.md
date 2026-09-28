# Solid-State DFT Knowledge Base (`vasp-abacus`: VASP, ABACUS, GPAW, Siesta, FHI-aims)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for plane-wave and LCAO solid-state DFT packages (`VASP`, `ABACUS`, `GPAW`, `Siesta`, `FHI-aims`).
Remember: **Matching an error family does NOT automatically blame the agent.**

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `edddav_zheev_subspace_error` | `Error EDDDAV: Call to ZHEEV failed`, `Sub-Space-Matrix is not hermitian`, `S-matrix is not positive definite`, `LAPACK: Routine ZPOTRF failed` | `overlapping_atomic_positions_in_poscar_stru`, `aggressive_algo_fast_instead_of_normal_all`, `insufficient_symprec_or_corrupt_paw_potcar` | Check minimum interatomic distances in `POSCAR` / `STRU`, and inspect `ALGO` (`Normal` / `All` vs `Fast` / `VeryFast`) and `ISYM` in `INCAR` / `INPUT` |
| `zbrent_brmix_charge_sloshing` | `ZBRENT: fatal error in bracketing`, `BRMIX: very serious problems`, `DENTET: can't reach specified precision` | `charge_sloshing_in_slab_or_metal`, `inappropriate_ismear_sigma_for_semiconductor_or_metal`, `bad_ediffg_step_for_cg_relaxation` | Inspect `AMIX`, `BMIX`, `ISMEAR`, `SIGMA`, and `IBRION` settings in `INCAR` |
| `potcar_psp_element_mismatch` | `POTCAR.*cannot be opened`, `number of potentials.*in POTCAR.*mismatch`, `PSEUDOPOTENTIAL_ERROR`, `Cannot find pseudopotential file`, `NUMERICAL_ORBITAL.*not found` | `poscar_potcar_species_order_mismatch`, `missing_paw_potcar_or_abacus_orb_upf_path`, `wrong_pseudo_dir_in_input` | Compare species order in `POSCAR` / `STRU` against `POTCAR` (`grep TITEL POTCAR`) or `pseudo_dir` |
| `nelm_electronic_nonconvergence` | `electronic self-consistency was not achieved`, `charge density could not be converged`, `Reach the Maximum Electron Steps` | `nelm_too_small_for_magnetic_or_correlated_system`, `missing_spin_polarization_ispin_or_magmom`, `insufficient_kpoint_mesh_or_encut` | Check `OSZICAR` / `running_scf.log` dE progression, `NELM`, `ISPIN`, and `EDIFF` |
| `nbands_ncore_memory_parallel` | `TOO FEW BANDS`, `highest band is occupied`, `NCORE.*incompatible` | `nbands_below_valence_plus_conduction_requirement`, `ncore_kpar_mismatch_with_mpi_ranks`, `out_of_memory_for_hybrid_functional_or_gw` | Compare `NBANDS`, `NELECT`, `NCORE`, and `KPAR` against MPI rank count in `OUTCAR` |
