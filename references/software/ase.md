# ASE Error Knowledge Base (`ase`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for Atomic Simulation Environment (`ase`) scripts.

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `calculator_not_attached` | `RuntimeError: Atoms object has no calculator`, `PropertyNotImplementedError` | `forgot_atoms_calc_assignment`, `copied_atoms_without_calculator`, `wrong_calculator_class` | Check `atoms.calc = ...` in Python script and whether `atoms.copy()` stripped the calculator |
| `cell_or_pbc_inconsistency` | `ValueError: Cell must be non-singular`, `PBC mismatch`, `volume is zero` | `missing_cell_on_periodic_system`, `vacuum_not_added_for_molecule_or_slab` | Inspect `atoms.get_cell()`, `atoms.get_pbc()`, and `atoms.center(vacuum=...)` |
| `optimizer_or_neb_nonconvergence` | `BFGS`, `FIRE`, `LBFGS` did not reach `fmax`, `NEB` climbing image divergence | `insufficient_steps`, `too_many_constraints_freezing_all_atoms`, `bad_neb_initial_interpolation` | Check `opt.run(fmax=..., steps=...)` return boolean, `FixAtoms` indices, and NEB `idpp` interpolation |
| `io_format_conversion_error` | `UnknownFileTypeError`, `KeyError` or `ValueError` in `ase.io.read` / `ase.io.write` | `wrong_format_string`, `missing_velocities_or_charges_in_output_format`, `multi_frame_index_omitted` | Check `ase.io.read(path, index=':')` vs single frame `index=-1` and output file schema |
| `vibrations_cache_or_mode_error` | `Vibrations`, `ZeroDivisionError`, `FileNotFoundError` on `vib.*.json` | `stale_vib_cache_from_previous_geometry`, `vib_clean_not_called`, `wrong_indices_list` | Check whether `vib.clean()` was called after changing geometry or calculator parameters |
