#!/usr/bin/env python3
"""
Heuristic Evidence Strength & Confidence Calculator (`scripts/confidence.py`)

Computes calibrated heuristic evidence scores (`confidence`, `confidence_kind`,
`evidence_strength`) from objective evidence counts, multi-source corroboration,
and competing hypothesis separation rather than hardcoded gate constants.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def compute_evidence_confidence(
    *,
    direct_causal_evidence: int = 0,
    cross_source_corroboration: int = 0,
    counterfactual_supported: bool = False,
    single_keyword_only: bool = False,
    missing_discriminating_evidence: int = 0,
    contradicting_evidence: int = 0,
) -> Tuple[float, str, str]:
    """
    Returns `(confidence, confidence_kind, evidence_strength)`:
      - `confidence`: float in [0.0, 1.0]
      - `confidence_kind`: `"heuristic_evidence_score"`
      - `evidence_strength`: `"high"` | `"medium"` | `"low"`
    """
    score = 0
    if direct_causal_evidence >= 1:
        score += 2
    if direct_causal_evidence >= 2:
        score += 1
    if cross_source_corroboration >= 1:
        score += 1
    if counterfactual_supported:
        score += 2
    if single_keyword_only:
        score -= 2
    if missing_discriminating_evidence > 0:
        score -= min(2, missing_discriminating_evidence)
    if contradicting_evidence > 0:
        score -= 2 * contradicting_evidence

    if score >= 3:
        strength = "high"
        numeric = min(0.96, 0.82 + 0.04 * (score - 3))
    elif score >= 1:
        strength = "medium"
        numeric = 0.65 + 0.07 * (score - 1)
    else:
        strength = "low"
        numeric = max(0.25, 0.40 + 0.05 * score)

    return round(numeric, 2), "heuristic_evidence_score", strength


def attach_confidence_metadata(
    target: Dict[str, Any],
    *,
    direct_causal_evidence: int = 1,
    cross_source_corroboration: int = 0,
    counterfactual_supported: bool = False,
    single_keyword_only: bool = False,
    missing_discriminating_evidence: int = 0,
    contradicting_evidence: int = 0,
) -> Dict[str, Any]:
    conf, kind, strength = compute_evidence_confidence(
        direct_causal_evidence=direct_causal_evidence,
        cross_source_corroboration=cross_source_corroboration,
        counterfactual_supported=counterfactual_supported,
        single_keyword_only=single_keyword_only,
        missing_discriminating_evidence=missing_discriminating_evidence,
        contradicting_evidence=contradicting_evidence,
    )
    target["confidence"] = conf
    target["confidence_kind"] = kind
    target["evidence_strength"] = strength
    return target
