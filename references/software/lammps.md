# LAMMPS Error Knowledge Base (`lammps`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for LAMMPS simulations.

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `lost_atoms` | `ERROR: Lost atoms: original`, `Lost atoms` | `excessive_timestep`, `overlapping_initial_coordinates`, `fixed_boundary_without_wall`, `wrong_units_conversion` | Check `timestep` vs `units` (`lj` vs `metal` vs `real`), initial `minimize`, and `boundary` setting |
| `non_numeric_pressure_or_energy` | `Non-numeric pressure - simulation unstable`, `nan`, `-nan`, `inf` in thermo | `bad_pair_coeff_mapping`, `unphysical_initial_density_or_overlap`, `barostat_instability` | Inspect step 0 `PotEng` and `Press`, `pair_coeff` atom type ordering, and box dimensions |
| `bond_or_topology_missing` | `Bond atoms .* missing on proc`, `Angle atoms .* missing`, `Dihedral atoms .* missing` | `communication_cutoff_too_short`, `unstable_bond_stretching`, `bad_data_file_topology` | Check `comm_modify cutoff`, `neighbor` skin, bond lengths in data file, and `special_bonds` |
| `atom_style_or_data_format_error` | `Incorrect atom format in data file`, `Unknown atom style`, `Invalid atom type` | `mismatch_between_atom_style_and_read_data_columns`, `missing_masses_or_header_counts` | Compare `atom_style` (`atomic`, `charge`, `full`, `molecular`) with column count in `Atoms` section of `.data` |
| `pair_coeff_or_potential_file_error` | `Cannot open EAM potential file`, `Incorrect args for pair coefficients`, `All pair coeffs are not set` | `wrong_potential_path`, `missing_element_mapping_in_eam_alloy`, `modified_pinned_asset` | Check `pair_style` and `pair_coeff` arguments, `/workspace/assets/` path, and SHA256 of potential file |
| `neighbor_list_overflow` | `Neighbor list overflow, boost neigh_modify one` | `collapsed_box_high_density`, `cutoff_larger_than_box`, `units_mismatch` | Check `pair_style` cutoff radius vs `units` (`real` Å vs `lj` $\sigma$) and box density |
| `restart_or_timestep_continuation_mismatch` | `reset_timestep`, `Continuation must start at step`, `first_pe` mismatch | `agent_used_read_data_instead_of_read_restart`, `agent_called_reset_timestep`, `wrong_thermo_interval` | Check whether `read_restart` was used, whether `reset_timestep` was invoked, and first/last thermo step numbers |
| `thermo_column_or_log_format_mismatch` | `log last line`, `Expected .* thermo lines` | `verifier_implicit_thermo_column_index`, `agent_custom_thermo_style_order`, `multiple_runs_in_same_log_lammps` | Compare `Step ...` header line in `log.lammps` with the column indices parsed in `tests/verify.py` |
