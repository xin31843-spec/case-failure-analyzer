# Biomolecular & Classical MD Knowledge Base (`gromacs-amber-openmm`: GROMACS, AMBER, OpenMM, NAMD, CHARMM)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for biomolecular and classical force-field molecular dynamics packages (`GROMACS`, `AMBER`, `OpenMM`, `NAMD`, `CHARMM`).
Remember: **Matching an error family does NOT automatically blame the agent.**

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `lincs_shake_constraint_blowup` | `LINCS WARNING`, `Water molecule starting at atom .* can not be settled`, `Particle coordinate is NaN`, `vlimit exceeded for step`, `SHAKE.*cannot be accomplished` | `unminimized_steric_clashes_before_md`, `timestep_2fs_without_hbond_constraints`, `aggressive_np_barostat_during_initial_equilibration` | Check whether steepest-descent energy minimization (`em.mdp` / `minimizeEnergy`) reached $F_{\max} < 1000\text{ kJ/mol/nm}$ before MD |
| `topology_coordinate_mismatch` | `number of coordinates in coordinate file .* does not match topology`, `Atom .* in residue .* was not found in rtp entry`, `Number of atoms in inpcrd .* does not match prmtop` | `solvent_or_ion_count_not_updated_in_topol_top`, `histidine_protonation_or_terminal_capping_name_mismatch`, `missing_hydrogen_atoms_in_input_pdb` | Compare atom count in `.gro`/`.inpcrd`/`.pdb` against `[ molecules ]` in `topol.top` or `.prmtop` |
| `missing_forcefield_parameters` | `No default Bond types`, `No default Proper Dih. types`, `Could not find bond parameter for`, `No template found for residue` | `unparameterized_small_molecule_ligand_missing_gaff_cgenff_itp`, `missing_include_statement_for_ligand_prm_in_topology`, `nonstandard_residue_or_metal_coordinating_site` | Inspect `#include` directives in `.top` or `ForceField(...)` XML files for ligand/cofactor parameter definitions |
| `pme_barostat_instability` | `Pressure scaling more than 1%`, `box size .* has shifted too much`, `The cut-off length is longer than half the shortest box vector` | `parrinello_rahman_barostat_used_on_unequilibrated_box`, `periodic_box_too_small_for_rcoulomb_rvdw_cutoff`, `vacuum_bubble_from_underpacked_solvent_box` | Check `pcoupl` (`Berendsen`/`C-rescale` vs `Parrinello-Rahman`), box vector lengths, and `rcoulomb`/`rvdw` |
