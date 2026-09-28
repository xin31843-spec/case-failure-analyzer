#!/usr/bin/env python3
"""
Unified Entrypoint, Evidence Collector & Conservative Causal Attribution Engine (`scripts/analyze_case.py`)

Pipeline:
  1. Artifact Discovery (`discover_artifacts.py` + `runtime_state.py`)
  2. Trajectory Normalization (`normalize_trajectory.py`)
  3. Runtime & Infra Error Extraction (`extract_runtime_errors.py`)
  4. Prompt / Task / Verifier Contract Audit (`audit_contract.py`)
  5. Scientific Software Error Extraction (`extract_scientific_errors.py`)
  6. Candidate Hypothesis Generation (`generate_hypotheses.py`)
  7. Conservative Causal Attribution (`analysis.json`)
  8. Schema & Attribution Constraint Validation (`validate_analysis.py`)
  9. Bilingual Report & Skill Prescription Rendering (`render_report.py`)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_contract import audit_contract
from confidence import attach_confidence_metadata
from discover_artifacts import discover_all, discover_trials
from extract_runtime_errors import extract_runtime_errors
from extract_scientific_errors import extract_scientific_errors
from generate_hypotheses import generate_candidate_hypotheses
from normalize_trajectory import normalize_trajectory
from render_report import render_report_markdown, render_skill_prescription_markdown
from runtime_state import SCHEMA_VERSION, resolve_trajectory_path
from validate_analysis import validate_all
from attribution.engine import run_attribution_engine


class ReplayNotSupportedError(RuntimeError):
    """Raised when `--replay` is requested without a supported isolated container runtime."""


def run_isolated_verifier_replay(
    task_dir: Optional[Path], trial_dir: Optional[Path], timeout_sec: int = 30
) -> Dict[str, Any]:
    raise ReplayNotSupportedError(
        "Verifier/simulation replay is not implemented for offline static task analysis. "
        "Use `--replay none` (default) for read-only forensic analysis."
    )


def collect_case_evidence(
    trial_inv: Dict[str, Any],
    job_dir: Path,
    max_log_bytes: int = 120000,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    trial_dir = Path(trial_inv["trial_dir"]) if trial_inv.get("trial_dir") else None
    task_dir = Path(trial_inv["task_dir"]) if trial_inv.get("task_dir") else None

    traj_path = resolve_trajectory_path(trial_dir)
    norm_traj = normalize_trajectory(traj_path, max_obs_bytes=max(1500, max_log_bytes // 40))

    runtime_err_res = extract_runtime_errors(
        job_dir=job_dir,
        trial_dir=trial_dir,
        max_log_bytes=max_log_bytes,
    )

    contract_res = audit_contract(
        task_dir=task_dir,
        trial_dir=trial_dir,
        normalized_traj=norm_traj,
    )

    sci_res = extract_scientific_errors(
        trial_dir=trial_dir,
        normalized_traj=norm_traj,
    )

    evidence: Dict[str, Any] = {
        "case_id": trial_inv["case_id"],
        "trial_name": trial_inv["trial_name"],
        "job_dir": trial_inv["job_dir"],
        "trial_dir": trial_inv["trial_dir"],
        "task_dir": trial_inv["task_dir"],
        "artifacts": trial_inv["artifacts"],
        "runtime": trial_inv["runtime"],
        "metadata": trial_inv.get("metadata", {}),
        "timeline": norm_traj["events"],
        "behavioral_signals": norm_traj["behavioral_signals"],
        "error_observations": runtime_err_res["error_observations"],
        "contract_observations": contract_res["contract_observations"],
        "verifier_observations": contract_res["verifier_observations"],
        "scientific_observations": sci_res["scientific_observations"],
        "missing_artifacts": trial_inv["missing_artifacts"],
    }
    cand_hyps = generate_candidate_hypotheses(evidence)
    return evidence, norm_traj, contract_res, cand_hyps


def _reconcile_competing_hypotheses(
    branch_hyps: List[Dict[str, Any]],
    cand_hyps: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merges branch-specific hypotheses with all candidate hypotheses produced by
    `generate_candidate_hypotheses(evidence)` so every gate's `competing_hypotheses`
    is driven by the unified candidate hypothesis set.
    """
    merged: List[Dict[str, Any]] = [dict(h) for h in (branch_hyps or [])]
    seen_keys = {(h.get("category"), h.get("subtype")) for h in merged}
    raw_candidates = (cand_hyps or {}).get("candidate_hypotheses") or []
    for cand in raw_candidates:
        if not isinstance(cand, dict):
            continue
        key = (cand.get("category"), cand.get("subtype"))
        if key in seen_keys:
            for existing in merged:
                if (existing.get("category"), existing.get("subtype")) == key:
                    merged_for = list(dict.fromkeys((existing.get("evidence_for") or []) + (cand.get("evidence_for") or [])))
                    existing["evidence_for"] = merged_for
                    break
            continue
        seen_keys.add(key)
        cloned = dict(cand)
        cloned["hypothesis_id"] = f"H{len(merged) + 1}"
        merged.append(cloned)
    return merged


def build_causal_attribution(
    evidence: Dict[str, Any],
    norm_traj: Dict[str, Any],
    contract_res: Dict[str, Any],
    cand_hyps: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if cand_hyps is None:
        cand_hyps = generate_candidate_hypotheses(evidence)
    result = _build_raw_causal_attribution(evidence, norm_traj, contract_res, cand_hyps)
    if result.get("verdict") != "passed":
        result["competing_hypotheses"] = _reconcile_competing_hypotheses(
            result.get("competing_hypotheses") or [],
            cand_hyps,
        )
        # Record that the gate's hypothesis list was post-processed after it
        # returned, so the trace does not imply the gate emitted it directly.
        trace = result.get("decision_trace")
        if isinstance(trace, dict):
            trace["reconciled_competing_hypotheses"] = True
    return result


def _build_raw_causal_attribution(
    evidence: Dict[str, Any],
    norm_traj: Dict[str, Any],
    contract_res: Dict[str, Any],
    cand_hyps: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deprecated shim retained for signature stability; delegates to the gate engine.

    The decision logic now lives in `scripts/attribution/` as one function per
    gate. `norm_traj` and `contract_res` were never read by the original
    implementation (the caller passes them positionally), so they remain accepted
    but unused.
    """
    return run_attribution_engine(evidence, cand_hyps)




def analyze_single_trial(
    trial_inv: Dict[str, Any],
    job_dir: Path,
    max_log_bytes: int = 120000,
    replay_mode: str = "none",
) -> Tuple[Dict[str, Any], Dict[str, Any], str, Optional[str]]:
    if replay_mode != "none":
        run_isolated_verifier_replay(
            Path(trial_inv["task_dir"]) if trial_inv.get("task_dir") else None,
            Path(trial_inv["trial_dir"]) if trial_inv.get("trial_dir") else None,
        )

    evidence, norm_traj, contract_res, cand_hyps = collect_case_evidence(
        trial_inv=trial_inv,
        job_dir=job_dir,
        max_log_bytes=max_log_bytes,
    )

    analysis = build_causal_attribution(evidence, norm_traj, contract_res, cand_hyps)
    report_md = render_report_markdown(evidence, analysis, lang="bilingual")

    ok, val_errors = validate_all(evidence, analysis, report_md)
    if not ok:
        raise RuntimeError(f"Generated analysis failed schema/constraint validation: {val_errors}")

    skill_md = None
    if analysis.get("skill_prescription"):
        skill_md = render_skill_prescription_markdown(analysis["skill_prescription"])

    return evidence, analysis, report_md, skill_md


def write_outputs(
    out_dir: Path,
    evidence: Dict[str, Any],
    analysis: Optional[Dict[str, Any]],
    report_md: Optional[str],
    skill_md: Optional[str],
    cand_hyps: Optional[Dict[str, Any]] = None,
    fmt: str = "both",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt in ("json", "both"):
        (out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        effective_cand_hyps = cand_hyps
        if effective_cand_hyps is None and analysis is not None:
            effective_cand_hyps = {
                "case_id": evidence.get("case_id"),
                "trial_name": evidence.get("trial_name"),
                "candidate_hypotheses": analysis.get("competing_hypotheses") or [],
            }
        if effective_cand_hyps is not None:
            (out_dir / "candidate-hypotheses.json").write_text(
                json.dumps(effective_cand_hyps, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if analysis is not None:
            (out_dir / "analysis.json").write_text(
                json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    if fmt in ("markdown", "both") and report_md is not None and analysis is not None:
        (out_dir / "report.md").write_text(report_md, encoding="utf-8")
        (out_dir / "report.zh.md").write_text(
            render_report_markdown(evidence, analysis, lang="zh"), encoding="utf-8"
        )
        (out_dir / "report.en.md").write_text(
            render_report_markdown(evidence, analysis, lang="en"), encoding="utf-8"
        )
        sp = analysis.get("skill_prescription")
        if skill_md and sp:
            (out_dir / "skill-prescription.md").write_text(skill_md, encoding="utf-8")
            (out_dir / "skill-prescription.zh.md").write_text(
                render_skill_prescription_markdown(sp, lang="zh"), encoding="utf-8"
            )
            (out_dir / "skill-prescription.en.md").write_text(
                render_skill_prescription_markdown(sp, lang="en"), encoding="utf-8"
            )


def compute_batch_statistics(summary_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute Stage 10 batch-level aggregation statistics across trials."""
    verdict_counts: Dict[str, int] = {}
    stage_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    code_counts: Dict[str, int] = {}
    agent_started_count = 0
    verifier_started_count = 0

    for row in summary_rows:
        v = str(row.get("verdict") or "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        if row.get("agent_started"):
            agent_started_count += 1
        if row.get("verifier_started"):
            verifier_started_count += 1
        st = row.get("failure_stage")
        if st:
            stage_counts[st] = stage_counts.get(st, 0) + 1
        cat = row.get("category")
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1
        code = row.get("code")
        if code:
            code_counts[code] = code_counts.get(code, 0) + 1

    return {
        "total_trials": len(summary_rows),
        "agent_started_count": agent_started_count,
        "verifier_started_count": verifier_started_count,
        "verdict_counts": verdict_counts,
        "failure_stage_counts": stage_counts,
        "category_counts": category_counts,
        "root_cause_code_counts": dict(sorted(code_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze scientific-computing benchmark case failures (Case Failure Analyzer)."
    )
    parser.add_argument("--job", required=True, type=Path, help="Job or trial directory path")
    parser.add_argument("--task", required=False, type=Path, default=None, help="Task definition directory path")
    parser.add_argument("--trial", default="all", help="Specific trial name or 'all'")
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for evidence.json, candidate-hypotheses.json, analysis.json, report.md",
    )
    parser.add_argument(
        "--phase",
        choices=["all", "collect"],
        default="all",
        help=(
            "Execution phase: 'collect' (evidence + candidate-hypotheses only) "
            "or 'all' (default: full evidence pipeline + conservative attribution + bilingual report)"
        ),
    )
    parser.add_argument(
        "--replay",
        choices=["none", "verifier", "safe"],
        default="none",
        help="Verifier/simulation replay mode (only 'none' is supported for static read-only analysis)",
    )
    parser.add_argument("--max-log-bytes", type=int, default=120000, help="Maximum bytes per log file read")
    parser.add_argument("--include-session-files", action="store_true", help="Include agent session files in inventory")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    # Fail fast on bad input paths or unsupported replay modes before writing any output.
    if args.replay != "none":
        try:
            run_isolated_verifier_replay(args.task, args.job)
        except ReplayNotSupportedError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
    if not args.job.exists():
        print(f"ERROR: --job path does not exist: {args.job}", file=sys.stderr)
        sys.exit(2)
    if args.task is not None and not args.task.exists():
        print(f"ERROR: --task path does not exist: {args.task}", file=sys.stderr)
        sys.exit(2)

    all_trials = discover_trials(args.job, trial_filter="all")
    if args.trial != "all":
        available = [t.name for t in all_trials]
        if args.trial not in available:
            print(
                f"ERROR: --trial '{args.trial}' not found under {args.job}. "
                f"Available trials: {available or 'none'}",
                file=sys.stderr,
            )
            sys.exit(2)
    elif not all_trials:
        # A job-level pre-startup failure is legitimate only when job-level evidence exists.
        has_job_level_evidence = (args.job / "result.json").is_file() or (args.job / "job.log").is_file()
        if not has_job_level_evidence:
            print(
                f"ERROR: no trial directories and no job-level result.json/job.log found under {args.job}. "
                "Refusing to analyze an empty input tree.",
                file=sys.stderr,
            )
            sys.exit(2)

    discovery = discover_all(
        job_path=args.job,
        task_path=args.task,
        trial_filter=args.trial,
        include_session_files=args.include_session_files,
    )
    trials = discovery.get("trials") or []
    job_dir = Path(discovery["job_dir"])

    if len(trials) == 1:
        inv = trials[0]
        if args.phase == "collect":
            ev, _, _, cand_hyps = collect_case_evidence(inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes)
            write_outputs(args.output, ev, None, None, None, cand_hyps=cand_hyps, fmt=args.format)
        else:
            ev, an, rep, skill_md = analyze_single_trial(
                inv,
                job_dir=job_dir,
                max_log_bytes=args.max_log_bytes,
                replay_mode=args.replay,
            )
            write_outputs(args.output, ev, an, rep, skill_md, fmt=args.format)
    else:
        summary_rows = []
        for inv in trials:
            t_out = args.output / inv["trial_name"]
            if args.phase == "collect":
                ev, _, _, cand_hyps = collect_case_evidence(inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes)
                write_outputs(t_out, ev, None, None, None, cand_hyps=cand_hyps, fmt=args.format)
                summary_rows.append(
                    {
                        "trial_name": inv["trial_name"],
                        "verdict": ev["runtime"].get("verdict"),
                        "agent_started": bool(ev["runtime"].get("agent_started")),
                        "verifier_started": bool(ev["runtime"].get("verifier_started")),
                        "phase": "collect",
                    }
                )
            else:
                ev, an, rep, skill_md = analyze_single_trial(
                    inv,
                    job_dir=job_dir,
                    max_log_bytes=args.max_log_bytes,
                    replay_mode=args.replay,
                )
                write_outputs(t_out, ev, an, rep, skill_md, fmt=args.format)
                summary_rows.append(
                    {
                        "trial_name": inv["trial_name"],
                        "verdict": an["verdict"],
                        "agent_started": bool(ev["runtime"].get("agent_started")),
                        "verifier_started": bool(ev["runtime"].get("verifier_started")),
                        "failure_stage": an["failure_stage"],
                        "detection_stage": an["detection_stage"],
                        "category": an["primary_root_cause"]["category"],
                        "code": an["primary_root_cause"]["code"],
                        "confidence": an["primary_root_cause"]["confidence"],
                    }
                )
        args.output.mkdir(parents=True, exist_ok=True)
        batch_stats = compute_batch_statistics(summary_rows)
        (args.output / "job_summary.json").write_text(
            json.dumps(
                {
                    "job_dir": str(job_dir),
                    "batch_statistics": batch_stats,
                    "trials": summary_rows,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
