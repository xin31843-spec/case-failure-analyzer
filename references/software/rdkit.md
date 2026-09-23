# RDKit Error Knowledge Base (`rdkit`)

This reference defines the diagnostic error families, candidate causes, and required discriminating evidence for RDKit cheminformatics scripts.

## Error Families

| Error Family | Signature Patterns | Candidate Causes | Required Discriminating Evidence |
|---|---|---|---|
| `smiles_parse_or_none_mol` | `SMILES Parse Error`, `AttributeError: 'NoneType' object has no attribute` | `unhandled_none_from_molfromsmiles`, `malformed_smiles_line_in_batch`, `header_line_parsed_as_smiles` | Check if `Chem.MolFromSmiles()` return value was checked for `None` and whether CSV/TSV header was skipped |
| `sanitization_or_valence_error` | `Explicit valence for atom .* is greater than permitted`, `MolSanitizeException`, `KekulizeException` | `incorrect_nitrogen_or_sulfur_valence_state`, `missing_charge_normalization`, `unescaped_aromatic_tautomer` | Check `rdMolStandardize.Normalizer` / `Cleanup` usage and `sanitize=False` handling |
| `conformer_embedding_failure` | `EmbedMolecule` or `EmbedMultipleConfs` returned `-1` or `0` conformers, `Bad Conformer Id` | `missing_explicit_hydrogens_addhs`, `strained_macrocycle_without_etkdg_random_coords`, `unseeded_random_seed` | Check whether `Chem.AddHs(mol)` was called before `AllChem.EmbedMultipleConfs` and check `randomSeed` parameter |
| `force_field_parameter_failure` | `MMFFGetMoleculeProperties returned None`, `UFFHasAllAtomParams` | `organometallic_or_unsupported_atom_in_mmff94`, `missing_uff_fallback`, `unminimized_conformer_energy` | Check `AllChem.MMFFHasAllMoleculeParams(mol)` and whether `MMFFGetMoleculeForceField` returned `None` |
| `stereochemistry_or_canonicalization_mismatch` | `isomericSmiles`, `tautomer`, `uncharger` mismatch vs reference | `dropped_chiral_tags_during_standardization`, `wrong_canonical_tautomer_enumeration_order`, `salt_fragment_selection` | Compare `rdMolStandardize.LargestFragmentChooser`, `Uncharger`, and `TautomerEnumerator` call order |
