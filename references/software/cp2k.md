# CP2K Error Knowledge Base (`cp2k`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for CP2K calculations.
Remember: **Matching an error family does NOT automatically blame the agent.**

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `basis_or_potential_missing` | `The specified OLD file <...> cannot be opened`, `BASIS_SET_FILE_NAME`, `POTENTIAL_FILE_NAME`, `cannot find basis set` | `missing_symlink_to_cp2k_data`, `wrong_filename_in_input`, `container_missing_cp2k_data_dir`, `unmatched_kind_basis_name` | Inspect `/opt/cp2k/data/` availability, agent's `cp`/`ln -s` commands, and `&DFT` / `&KIND` sections |
| `scf_nonconvergence` | `SCF run NOT converged`, `Leaving inner SCF loop` | `bad_initial_guess`, `insufficient_scf_iterations`, `inappropriate_mixing_or_ot`, `invalid_geometry_overlap`, `metallic_system_without_smearing` | Check `MAX_SCF`, `EPS_SCF`, `&OT` vs diagonalization, minimum interatomic distance, and whether input was locked by task |
| `cholesky_or_overlap_failure` | `Cholesky decomposition failed`, `matrix is not positive definite`, `dbcsr_cholesky_decompose` | `overlapping_atoms_in_coord`, `diffuse_basis_linear_dependency`, `wrong_cell_dimensions`, `corrupt_asset_geometry` | Inspect interatomic distance matrix ($d_{ij} < 0.5\text{ \AA}$), cell `ABC`, and `EPS_PGF_ORB` |
| `geoopt_or_cellopt_nonconvergence` | `MAXIMUM NUMBER OF OPTIMIZATION STEPS REACHED`, `Geometry optimization NOT converged` | `insufficient_max_iter`, `noisy_forces_low_cutoff`, `unphysical_initial_structure`, `wrong_optimizer_choice` | Check `MAX_ITER`, `MAX_FORCE`, `CUTOFF` convergence, and force trajectory progression |
| `md_abnormal_termination` | `Temperature out of range`, `Cons Qty` explosion, premature `.ener` row count | `excessive_timestep`, `unconverged_scf_forces`, `missing_thermostat_or_wrong_ensemble`, `process_timeout_kill` | Compare `TIMESTEP` (e.g. $>1.0\text{ fs}$ for light H atoms), `.ener` step count vs `STEPS`, and `PROGRAM ENDED AT` footer |
| `periodicity_poisson_mismatch` | `Poisson solver`, `PERIODIC NONE` vs `WAVELET`/`MT` mismatch | `Incompatible CELL%PERIODIC and POISSON%PERIODIC`, `box_too_small_for_mt_solver` | Compare `&CELL PERIODIC` and `&POISSON PERIODIC` / `POISSON_SOLVER` |
| `input_parser_error` | `found an unknown keyword`, `unknown subsection`, `CPASSERT failed` | `agent_syntax_error_in_inp`, `cp2k_version_keyword_deprecation`, `corrupt_provided_inp` | Check line number reported by CP2K parser against modifications made to `.inp` |
| `mpi_or_runtime_crash` | `MPI_Abort`, `Segmentation fault`, `Killed` (exit 137/139) | `container_oom`, `oversubscribed_mpi_ranks`, `stack_size_limit` | Check `mpirun -np` count vs container CPU/RAM limits and kernel/stderr exit code |
