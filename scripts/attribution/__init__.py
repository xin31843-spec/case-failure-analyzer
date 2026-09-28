#!/usr/bin/env python3
"""
Causal attribution engine (`scripts/attribution/`)

Splits the causal attribution decision out of `analyze_case.py`. The decision is a
strictly ordered sequence of gates, each of which either abstains or returns a
complete attribution. The first gate to match wins.

    gate0  passed ...................... trial verified (reward >= 1.0)
    gate1a infra pre-startup ........... fatal infrastructure evidence, agent never ran
    gate1b pre-startup, no evidence .... agent never ran, nothing to attribute
    gate2  case defect ................. prompt/asset contract defect
    gate3  verifier defect ............. verifier crash, parser defect, or bound hazard
    gate4  numerical divergence ........ structured numerical drift
    gate5  no positive agent evidence .. failed, but nothing implicates the Agent
    gate6  agent primary ............... positive Agent evidence, subcase 5a-5d/else

The gate order is load-bearing and is preserved verbatim from the original
implementation; several regression tests pin the boundaries between gates.

Import convention: this package is reached by importing `attribution.*` top-level
after `scripts/` has been placed on `sys.path` (see the SCRIPT_DIR preamble in
`analyze_case.py` and the test modules). Do not import it as `scripts.attribution.*`
— that would create a second module identity with distinct classes.

No module in this package may import `analyze_case`: the dependency direction is
one-way. `tests/test_attribution_decisions.py` enforces both rules.
"""
from __future__ import annotations

__all__ = ["OUTCOME_KEYS", "make_attribution"]