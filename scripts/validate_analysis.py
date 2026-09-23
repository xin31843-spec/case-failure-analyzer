#!/usr/bin/env python3
"""
Schema & Attribution Constraint Validator (`scripts/validate_analysis.py`)

Validates `evidence.json`, `analysis.json`, and optional `report.md` against
the `failure-analysis-v1` schema and enforces hard causal attribution rules:
  1. No false-agent-blame when `runtime.agent_started == False`.
  2. Every `evidence_ref` in `analysis.json` must resolve to a valid entry in `evidence.json`.
  3. Non-agent root causes cannot generate a `skill_prescription`.
  4. `report.md` must include all 11 mandatory sections.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


REQUIRED_EVIDENCE_KEYS = {
    "case_id",
    "artifacts",
    "runtime",
    "timeline",
    "error_observations",
    "contract_observations",
    "verifier_observations",
    "scientific_observations",
    "missing_artifacts",
}

REQUIRED_ANALYSIS_KEYS = {
    "schema_version",
    "case_id",
    "verdict",
    "failure_stage",
    "detection_stage",
    "failure_manifestation",
    "primary_root_cause",
    "contributing_factors",
    "evidence_refs",
    "excluded_hypotheses",
    "recommended_actions",
    "skill_prescription",
}

VALID_CATEGORIES = {"infra", "case", "agent", "verifier", "numerical", "unknown", "none"}

REQUIRED_REPORT_SECTIONS = [
    "Executive Summary",
    "Case 状态",
    "执行时间线",
    "直接失败现象",
    "主根因",
    "伴随因素",
    "证据链",
    "排除的假设",
    "建议修复责任方",
    "Skill 处方",
    "缺失证据与分析限制",
]


def collect_valid_evidence_ids(evidence: Dict[str, Any]) -> Set[str]:
    ids: Set[str] = set()
    for a in evidence.get("artifacts") or []:
        if a.get("artifact_id"):
            ids.add(a["artifact_id"])
        if a.get("rel_path"):
            ids.add(a["rel_path"])
            ids.add(f"{a.get('scope', 'trial')}:{a['rel_path']}")
    for ev in evidence.get("timeline") or []:
        if ev.get("event_id"):
            ids.add(ev["event_id"])
    for sig in evidence.get("behavioral_signals") or []:
        if sig.get("signal_id"):
            ids.add(sig["signal_id"])
    for err in evidence.get("error_observations") or []:
        if err.get("error_id"):
            ids.add(err["error_id"])
    for c in evidence.get("contract_observations") or []:
        if c.get("contract_id"):
            ids.add(c["contract_id"])
    for v in evidence.get("verifier_observations") or []:
        if v.get("obs_id"):
            ids.add(v["obs_id"])
    for s in evidence.get("scientific_observations") or []:
        if s.get("sci_id"):
            ids.add(s["sci_id"])
    return ids


def validate_all(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    report_text: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    # 1. Check evidence.json keys
    missing_ev = REQUIRED_EVIDENCE_KEYS - set(evidence.keys())
    if missing_ev:
        errors.append(f"evidence.json missing required keys: {sorted(missing_ev)}")

    # 2. Check analysis.json keys & schema version
    missing_an = REQUIRED_ANALYSIS_KEYS - set(analysis.keys())
    if missing_an:
        errors.append(f"analysis.json missing required keys: {sorted(missing_an)}")

    if analysis.get("schema_version") != "failure-analysis-v1":
        errors.append(
            f"Invalid schema_version: {analysis.get('schema_version')!r}, expected 'failure-analysis-v1'"
        )

    prc = analysis.get("primary_root_cause") or {}
    cat = prc.get("category")
    if cat not in VALID_CATEGORIES:
        errors.append(f"Invalid primary_root_cause.category: {cat!r}")

    conf = prc.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        errors.append(f"Invalid primary_root_cause.confidence: {conf!r}; must be in [0.0, 1.0]")

    # 3. Hard Rule: No false-agent-blame when agent did not start
    agent_started = bool((evidence.get("runtime") or {}).get("agent_started", False))
    if not agent_started and cat == "agent":
        errors.append(
            "FALSE_AGENT_BLAME violation: primary_root_cause.category is 'agent' "
            "when runtime.agent_started is False."
        )

    # 4. Hard Rule: Non-empty evidence_refs and all refs must resolve in evidence.json
    ev_refs = analysis.get("evidence_refs") or []
    if analysis.get("verdict") in ("failed", "errored") and not ev_refs:
        errors.append("Failed/errored analysis must cite at least one evidence_ref.")

    valid_ids = collect_valid_evidence_ids(evidence)
    for ref in ev_refs:
        if ref not in valid_ids:
            errors.append(f"Unresolved evidence_ref {ref!r} not found in evidence.json")

    # 5. Hard Rule: Skill prescription only allowed when primary_root_cause is 'agent'
    if analysis.get("skill_prescription") is not None and cat != "agent":
        errors.append(
            f"SKILL_PRESCRIPTION_POLICY violation: skill_prescription generated for category={cat!r} (only allowed for 'agent')."
        )

    # 6. Optional report.md section validation
    if report_text is not None:
        for sec in REQUIRED_REPORT_SECTIONS:
            if sec not in report_text:
                errors.append(f"report.md missing required section: {sec!r}")

    return len(errors) == 0, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate evidence.json, analysis.json, and report.md.")
    parser.add_argument("--evidence", required=True, type=Path, help="Path to evidence.json")
    parser.add_argument("--analysis", required=True, type=Path, help="Path to analysis.json")
    parser.add_argument("--report", required=False, type=Path, default=None, help="Optional path to report.md")
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    report_text = (
        args.report.read_text(encoding="utf-8") if (args.report and args.report.is_file()) else None
    )

    ok, errors = validate_all(evidence, analysis, report_text)
    if not ok:
        for err in errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print("Validation passed successfully.")


if __name__ == "__main__":
    main()
