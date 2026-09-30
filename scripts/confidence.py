#!/usr/bin/env python3
"""
Heuristic Evidence Strength & Confidence Calculator (`scripts/confidence.py`)

Computes heuristic evidence scores (`confidence`, `confidence_kind`,
`evidence_strength`) from objective evidence counts, multi-source corroboration,
and competing hypothesis separation rather than hardcoded gate constants.

Design notes:
- The returned score is an *evidence strength heuristic*, NOT a calibrated
  probability: it ranks hypotheses by the net weight of objective evidence
  and must not be read as a likelihood of being the true root cause.
- The score denominator is dynamic: it starts at the base 6-point scale
  (`MAX_EVIDENCE_POINTS`) and grows by 2 when a quantitative `margin_ratio`
  is supplied, by 1 for `check_localization`, and by 1 for
  `hypothesis_separation`. Callers that contribute richer case-specific
  evidence are therefore scored on a finer scale instead of saturating the
  base formula. A component that carries no usable measurement (missing,
  NaN, non-positive margin ratio, or an unrecognized localization label) is
  treated as *not supplied*: it neither adds points nor expands the
  denominator.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


MAX_EVIDENCE_POINTS = 6

# Case-specific discriminative components extend the base scale by at most
# 2 (margin) + 1 (localization) + 1 (separation) points.
_CHECK_LOCALIZATION_LABELS = ("single", "widespread")
_SEPARATION_HIGH_THRESHOLD = 0.6
_MARGIN_STRONG_RATIO = 4.0
_MARGIN_MODERATE_RATIO = 2.0


def _normalized_margin_ratio(margin_ratio: Optional[float]) -> Optional[float]:
    """Return the usable margin ratio, or ``None`` when no measurement exists.

    Per the scoring contract, ``None``, ``NaN`` and non-positive ratios are
    treated as "not supplied": the component adds no points and does not
    expand the dynamic denominator.
    """
    if margin_ratio is None:
        return None
    try:
        value = float(margin_ratio)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or value <= 0:
        return None
    return value


def _normalized_localization(check_localization: Optional[str]) -> Optional[str]:
    """Return the localization label, or ``None`` when unrecognized.

    Only the exact labels ``"single"`` / ``"widespread"`` count as supplied;
    any other string is treated as "not supplied" (no points, no denominator
    expansion).
    """
    if check_localization in _CHECK_LOCALIZATION_LABELS:
        return check_localization
    return None


def _normalized_separation(hypothesis_separation: Optional[float]) -> Optional[float]:
    """Return the usable hypothesis separation, or ``None`` when not usable.

    Non-finite values (``NaN`` / ``inf``) carry no separation measurement and
    are treated as "not supplied", mirroring the margin-ratio NaN rule.
    """
    if hypothesis_separation is None:
        return None
    try:
        value = float(hypothesis_separation)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


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
    margin_ratio: Optional[float] = None,
    check_localization: Optional[str] = None,
    hypothesis_separation: Optional[float] = None,
) -> Tuple[float, str, str]:
    """
    Returns `(confidence, confidence_kind, evidence_strength)` computed as the
    normalized ratio `points / denominator`:
      - `confidence`: float in [0.0, 1.0] — heuristic evidence strength, not a
        calibrated probability;
      - `confidence_kind`: `"heuristic_evidence_score"`
      - `evidence_strength`: `"high"` | `"medium"` | `"low"`

    Base scale (0..`MAX_EVIDENCE_POINTS` = 6): the original evidence-count
    formula, preserved verbatim for backward compatibility (calling without
    the three case-specific kwargs yields exactly the legacy scores).

    Case-specific discriminative components (all keyword-only, default
    `None` = not supplied):
      - `margin_ratio` (`|reported - recomputed| / tolerance`): `>= 4` adds
        +2, `2 <= ratio < 4` adds +1, `< 2` adds +0. `None`, `NaN` and
        non-positive ratios count as not supplied (+0, no denominator share).
      - `check_localization` (`"single"` | `"widespread"`): `"single"` adds
        +1, `"widespread"` adds -1, any other string counts as not supplied.
      - `hypothesis_separation` (normalized lead of the top hypothesis over
        the runner-up, expected in [0.0, 1.0]): `>= 0.6` adds +1, `< 0.6`
        adds +0; non-finite values count as not supplied.
      - `counterfactual_supported=True` adds +2 (unchanged legacy parameter,
        part of the base formula).

    The denominator is `6` expanded by the supplied components: `+2` when a
    usable `margin_ratio` is given, `+1` for a recognized
    `check_localization`, `+1` for a usable `hypothesis_separation` — so a
    fully stacked call scores on a 10-point scale and `points` are clamped to
    `[0, denominator]` before rounding to 2 decimals.

    Strength thresholds are bound to the score: `>= 0.65` high, `>= 0.4`
    medium, else low (without the new kwargs, legacy strengths are preserved,
    e.g. 4/6 = 0.67 still ranks "high").

    The `ruled_out` / `verdict_passed` short-circuits (0.0 / 1.0) are
    unaffected by the new components.
    """
    if ruled_out:
        return 0.0, "heuristic_evidence_score", "low"
    if verdict_passed:
        return 1.0, "heuristic_evidence_score", "high"

    # Normalize case-specific components: unusable measurements count as
    # "not supplied" (no points, no denominator expansion).
    margin = _normalized_margin_ratio(margin_ratio)
    localization = _normalized_localization(check_localization)
    separation = _normalized_separation(hypothesis_separation)

    points = (
        min(3, max(0, int(direct_causal_evidence)))
        + (1 if int(cross_source_corroboration) >= 1 else 0)
        + (2 if counterfactual_supported else 0)
        - (1 if single_keyword_only else 0)
        - min(2, max(0, int(missing_discriminating_evidence)))
        - 2 * max(0, int(contradicting_evidence))
        # Case-specific discriminative components.
        + (2 if margin is not None and margin >= _MARGIN_STRONG_RATIO else 0)
        + (
            1
            if margin is not None and _MARGIN_MODERATE_RATIO <= margin < _MARGIN_STRONG_RATIO
            else 0
        )
        + (1 if localization == "single" else 0)
        - (1 if localization == "widespread" else 0)
        + (1 if separation is not None and separation >= _SEPARATION_HIGH_THRESHOLD else 0)
    )
    denominator = (
        MAX_EVIDENCE_POINTS
        + (2 if margin is not None else 0)
        + (1 if localization is not None else 0)
        + (1 if separation is not None else 0)
    )
    clamped = max(0, min(denominator, points))
    numeric = round(clamped / float(denominator), 2)

    if numeric >= 0.65:
        strength = "high"
    elif numeric >= 0.4:
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
    margin_ratio: Optional[float] = None,
    check_localization: Optional[str] = None,
    hypothesis_separation: Optional[float] = None,
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
        margin_ratio=margin_ratio,
        check_localization=check_localization,
        hypothesis_separation=hypothesis_separation,
    )
    target["confidence"] = conf
    target["confidence_kind"] = kind
    target["evidence_strength"] = strength
    return target
