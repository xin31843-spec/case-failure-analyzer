#!/usr/bin/env python3
"""
Error-family matching (`scripts/attribution/families.py`)

Pure leaf module: no local imports, so any gate or module may depend on it
without creating a cycle. Relocated verbatim from `analyze_case.py` so the
attribution gates no longer have to import back into the entrypoint.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

# Unrecovered error families that indicate the Agent failed to *locate* a file,
# potential, force field, or checkpoint that exists in the container. Used by
# subcase 5b.
DEPENDENCY_DISCOVERY_FAMILIES: Tuple[str, ...] = (
    "basis_or_potential_missing",
    "pseudopotential_read_failure",
    "pseudopotential_mismatch_or_missing",
    "potcar_psp_element_mismatch",
    "checkpoint_architecture_incompatibility",
    "missing_forcefield_parameters",
    "basis_set_linear_dependence",
)

# Unrecovered error families indicating a state/restart continuation mismatch.
# Used by subcase 5c.
CONTINUATION_FAMILIES: Tuple[str, ...] = (
    "restart_or_timestep_continuation_mismatch",
    "restart_continuation_divergence",
)


def matches_family(sci_entry: Dict[str, Any], targets: Tuple[str, ...]) -> bool:
    """True when a scientific observation's family (or one of its aliases) is in `targets`."""
    fam = sci_entry.get("error_family", "")
    aliases = sci_entry.get("aliases") or []
    return fam in targets or any(a in targets for a in aliases)