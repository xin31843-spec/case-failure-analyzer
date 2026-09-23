#!/usr/bin/env python3
"""
Heuristic Evidence Strength & Confidence Calculator (`scripts/confidence.py`)

Computes calibrated heuristic evidence scores (`confidence`, `confidence_kind`,
`evidence_strength`) from objective evidence counts, multi-source corroboration,
and competing hypothesis separation rather than hardcoded gate constants.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


MAX_EVIDENCE_POINTS = 6


def compute_evidence_confidence(
    *,
    direct_causal_evidence: int = 0,
    cross_source_corroboration: int = 0,
    counterfactual_supported: bool = False,
    single_keyword_only: bool = False,
    missing_discriminating_evidence: int = 0,
    contradicting_evidence: int = 0,
    verdict_passed: bool = False,
    ruled_out: bool = False,
) -> Tuple[float, str, str]:
    """
    Returns `(confidence, confidence_kind, evidence_strength)` computed directly
    as the normalized ratio `net_evidence_points / MAX_EVIDENCE_POINTS`:
      - `confidence`: float in [0.0, 1.0]
      - `confidence_kind`: `"heuristic_evidence_score"`
      - `evidence_strength`: `"high"` | `"medium"` | `"low"`
    """
    if ruled_out:
        return 0.0, "heuristic_evidence_score", "low"
    if verdict_passed:
        return 1.0, "heuristic_evidence_score", "high"

    points = (
        min(3, max(0, int(direct_causal_evidence)))
        + (1 if int(cross_source_corroboration) >= 1 else 0)
        + (2 if counterfactual_supported else 0)
        - (1 if single_keyword_only else 0)
        - min(2, max(0, int(missing_discriminating_evidence)))
        - 2 * max(0, int(contradicting_evidence))
    )
    clamped = max(0, min(MAX_EVIDENCE_POINTS, points))
    numeric = round(clamped / float(MAX_EVIDENCE_POINTS), 2)

    if clamped >= 4:
        strength = "high"
    elif clamped >= 2:
        strength = "medium"
    else:
        strength = "low"

    return numeric, "heuristic_evidence_score", strength


def attach_confidence_metadata(
    target: Dict[str, Any],
    *,
    direct_causal_evidence: int = 1,
    cross_source_corroboration: int = 0,
    counterfactual_supported: bool = False,
    single_keyword_only: bool = False,
    missing_discriminating_evidence: int = 0,
    contradicting_evidence: int = 0,
    verdict_passed: bool = False,
    ruled_out: bool = False,
) -> Dict[str, Any]:
    conf, kind, strength = compute_evidence_confidence(
        direct_causal_evidence=direct_causal_evidence,
        cross_source_corroboration=cross_source_corroboration,
        counterfactual_supported=counterfactual_supported,
        single_keyword_only=single_keyword_only,
        missing_discriminating_evidence=missing_discriminating_evidence,
        contradicting_evidence=contradicting_evidence,
        verdict_passed=verdict_passed,
        ruled_out=ruled_out,
    )
    target["confidence"] = conf
    target["confidence_kind"] = kind
    target["evidence_strength"] = strength
    return target
