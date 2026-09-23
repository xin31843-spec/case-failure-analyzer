# xTB Error Knowledge Base (`xtb`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for `xtb` calculations.

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `scc_nonconvergence` | `convergence criteria cannot be satisfied`, `self consistent charge iterator did not converge` | `wrong_charge_or_uhf`, `bad_input_geometry`, `insufficient_etemp_for_small_gap` | Check `--chrg`, `--uhf`, electronic temperature `--etemp`, and input `.xyz` bond distances |
| `invalid_charge_or_multiplicity` | `Number of electrons and spin multiplicity do not match`, `odd number of electrons` | `incompatible_chrg_and_uhf_flags`, `missing_hydrogen_atoms_in_structure` | Count total atomic numbers $Z - \text{charge}$ and compare parity with `--uhf` |
| `geometry_read_failure` | `could not read geometry`, `invalid coordinate file`, `atom count mismatch` | `malformed_xyz_header`, `wrong_file_format_passed_to_xtb` | Inspect line 1 (integer atom count), line 2 (comment), and coordinate lines of input file |
| `opt_or_hessian_failure` | `ANCopt failed`, `negative frequencies`, `imaginary frequency` | `tight_optimization_threshold_not_met`, `saddle_point_geometry`, `hessian_evaluated_at_non_stationary_point` | Check `--opt` level (`normal`, `tight`, `vtight`), `xtbopt.xyz` usage before `--hess`, and imaginary mode count |
| `abnormal_termination` | `[ERROR] Program stopped due to fatal error`, `abnormal termination of xtb` | `stack_overflow_omp_stacksize`, `unsupported_element_or_gfn_version` | Check `OMP_STACKSIZE`, `--gfn 1|2|ff`, and stderr traceback |
