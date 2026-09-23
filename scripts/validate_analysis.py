#!/usr/bin/env python3
"""
Schema & Attribution Constraint Validator (`scripts/validate_analysis.py`)

Validates `evidence.json`, `analysis.json`, and optional `report.md` against
the `failure-analysis-v1` schema and enforces hard causal attribution rules:
  1. No false-agent-blame when `runtime.agent_started == False`.
  2. Positive agent evidence required when `primary_root_cause.category == "agent"`.
  3. Non-empty `competing_hypotheses` and structured `first_unrecovered_deviation` required
     for all `failed` / `errored` analyses.
  4. Every `evidence_ref` in `analysis.json` (and inside `competing_hypotheses` /
     `first_unrecovered_deviation`) must resolve to a valid entry in `evidence.json`.
  5. Non-agent root causes cannot generate a `skill_prescription`.
  6. `report.md` must include all 11 mandatory `## <N>. <Title>` sections with non-empty body text.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_state import SCHEMA_VERSION


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
    "first_unrecovered_deviation",
    "failure_manifestation",
    "primary_root_cause",
    "contributing_factors",
    "competing_hypotheses",
    "evidence_refs",
    "excluded_hypotheses",
    "recommended_actions",
    "skill_prescription",
}

VALID_CATEGORIES = {"infra", "case", "agent", "verifier", "numerical", "unknown", "none"}

REQUIRED_REPORT_SECTIONS = [
    (1, "Executive Summary"),
    (2, "Case 状态"),
    (3, "执行时间线"),
    (4, "直接失败现象"),
    (5, "主根因"),
    (6, "伴随因素"),
    (7, "证据链"),
    (8, "排除的假设"),
    (9, "建议修复责任方"),
    (10, "Skill 处方"),
    (11, "缺失证据与分析限制"),
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


def collect_positive_agent_evidence_ids(evidence: Dict[str, Any]) -> Set[str]:
    pos_ids: Set[str] = set()
    for sig in evidence.get("behavioral_signals") or []:
        if sig.get("signal_id"):
            pos_ids.add(sig["signal_id"])
    for c in evidence.get("contract_observations") or []:
        if c.get("alignment") == "agent_mismatch" and c.get("contract_id"):
            pos_ids.add(c["contract_id"])
    for ev in evidence.get("timeline") or []:
        if ev.get("actor") == "agent" and ev.get("event_id"):
            pos_ids.add(ev["event_id"])
    for s in evidence.get("scientific_observations") or []:
        if s.get("sci_id"):
            pos_ids.add(s["sci_id"])
    return pos_ids


def validate_report_sections(report_text: str) -> List[str]:
    errors: List[str] = []
    for num, sec_title in REQUIRED_REPORT_SECTIONS:
        # Match start-of-line `## <num>. <sec_title>` (optionally followed by English title or whitespace)
        header_pat = re.compile(
            rf"(?m)^##\s+{num}\.\s+{re.escape(sec_title)}(?:\s.*)?$"
        )
        m = header_pat.search(report_text)
        if not m:
            errors.append(
                f"report.md missing required section header: '## {num}. {sec_title}'"
            )
            continue

        # Extract section body up to the next `## ` level-2 header or EOF
        after_header = report_text[m.end() :]
        next_h2 = re.search(r"(?m)^##\s+", after_header)
        body = after_header[: next_h2.start()] if next_h2 else after_header
        if not body.strip():
            errors.append(
                f"report.md section '## {num}. {sec_title}' has empty body content."
            )
    return errors


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

    if analysis.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"Invalid schema_version: {analysis.get('schema_version')!r}, expected {SCHEMA_VERSION!r}"
        )

    verdict = analysis.get("verdict")
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

    valid_ids = collect_valid_evidence_ids(evidence)

    # 4. Hard Rule: Non-empty evidence_refs and all refs must resolve in evidence.json
    ev_refs = analysis.get("evidence_refs") or []
    if verdict in ("failed", "errored") and not ev_refs:
        errors.append("Failed/errored analysis must cite at least one evidence_ref.")

    for ref in ev_refs:
        if ref not in valid_ids:
            errors.append(f"Unresolved evidence_ref {ref!r} not found in evidence.json")

    # 5. Hard Rule: first_unrecovered_deviation and competing_hypotheses for failed/errored cases
    if verdict in ("failed", "errored"):
        fud = analysis.get("first_unrecovered_deviation")
        if not isinstance(fud, dict):
            errors.append(
                "Failed/errored analysis must provide a structured `first_unrecovered_deviation` object."
            )
        else:
            fud_status = fud.get("status", "identified" if fud.get("event_ref") else "not_identified")
            fud_ref = fud.get("event_ref")
            if fud_status == "identified":
                if not fud_ref:
                    errors.append("`first_unrecovered_deviation` with status='identified' must specify `event_ref`.")
                elif fud_ref not in valid_ids:
                    errors.append(
                        f"Unresolved first_unrecovered_deviation.event_ref {fud_ref!r} not found in evidence.json"
                    )
            elif fud_status != "not_identified":
                errors.append(f"Invalid first_unrecovered_deviation.status: {fud_status!r}")
            if not (fud.get("summary") or "").strip():
                errors.append("`first_unrecovered_deviation.summary` must be non-empty.")

        comp_hyps = analysis.get("competing_hypotheses")
        if not isinstance(comp_hyps, list) or len(comp_hyps) < 1:
            errors.append(
                "Failed/errored analysis must include at least one hypothesis in `competing_hypotheses`."
            )
        else:
            matched_primary = False
            for hyp in comp_hyps:
                if not isinstance(hyp, dict):
                    continue
                if hyp.get("category") == cat:
                    matched_primary = True
                    if cat != "unknown" and not (hyp.get("evidence_for") or []):
                        errors.append(
                            f"Primary hypothesis {hyp.get('hypothesis_id')!r} ({cat}) must list non-empty `evidence_for`."
                        )
                for h_ref in (hyp.get("evidence_for") or []) + (hyp.get("evidence_against") or []):
                    if h_ref not in valid_ids:
                        errors.append(
                            f"Unresolved hypothesis evidence ref {h_ref!r} in {hyp.get('hypothesis_id')!r}"
                        )
            if not matched_primary and cat != "unknown":
                errors.append(
                    f"primary_root_cause.category={cat!r} does not match any hypothesis in `competing_hypotheses`."
                )

    # 6. Hard Rule: Positive agent evidence required when primary_root_cause.category == 'agent'
    if cat == "agent":
        pos_agent_ids = collect_positive_agent_evidence_ids(evidence)
        if not any(r in pos_agent_ids for r in ev_refs):
            errors.append(
                "POSITIVE_AGENT_EVIDENCE violation: primary_root_cause.category is 'agent', "
                "but `evidence_refs` does not cite any positive agent evidence "
                "(behavioral_signal, agent_mismatch contract, agent timeline event, or scientific_observation)."
            )

    # 7. Hard Rule: Skill prescription only allowed when primary_root_cause is 'agent'
    if analysis.get("skill_prescription") is not None and cat != "agent":
        errors.append(
            f"SKILL_PRESCRIPTION_POLICY violation: skill_prescription generated for category={cat!r} (only allowed for 'agent')."
        )

    # 8. Optional report.md section & non-empty body validation
    if report_text is not None:
        errors.extend(validate_report_sections(report_text))

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
