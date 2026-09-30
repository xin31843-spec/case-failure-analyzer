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
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_contract import audit_contract
from discover_artifacts import discover_all, discover_trials
from extract_runtime_errors import extract_runtime_errors
from extract_scientific_errors import extract_scientific_errors
from generate_hypotheses import generate_candidate_hypotheses
from normalize_trajectory import normalize_trajectory
from render_report import render_report_markdown, render_skill_prescription_markdown
from runtime_state import resolve_trajectory_path
from validate_analysis import validate_all
from attribution.engine import run_attribution_engine
from diagnostics import format_diagnostic_line, merge_diagnostics


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
        # Additive top-level key: recoveries that degraded evidence on this trial.
        "diagnostics": merge_diagnostics(
            (trial_inv.get("runtime") or {}).get("diagnostics"),
            contract_res.get("diagnostics"),
        ),
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
                    merged_for = list(
                        dict.fromkeys(
                            (existing.get("evidence_for") or []) + (cand.get("evidence_for") or [])
                        )
                    )
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


def _report_diagnostics(evidence: Dict[str, Any]) -> None:
    """Emit one line per degraded-evidence record to stderr (never stdout)."""
    for record in evidence.get("diagnostics") or []:
        print(f"ANALYSIS DIAGNOSTIC: {format_diagnostic_line(record)}", file=sys.stderr)


KNOWN_TRIAL_ARTIFACTS = {
    "evidence.json",
    "candidate-hypotheses.json",
    "analysis.json",
    "report.md",
    "report.zh.md",
    "report.en.md",
    "skill-prescription.md",
    "skill-prescription.zh.md",
    "skill-prescription.en.md",
}
KNOWN_ROOT_ARTIFACTS = {"job_summary.json"}


def _clean_managed_trial_dir(target_dir: Path, allowed_files: Set[str]) -> None:
    """Remove known managed trial files in target_dir that are not in allowed_files."""
    if not target_dir.is_dir():
        return
    for fname in KNOWN_TRIAL_ARTIFACTS:
        if fname not in allowed_files:
            fpath = target_dir / fname
            if fpath.is_file():
                fpath.unlink()


MANIFEST_FILENAME = ".cfa_manifest.json"


def _paths_overlap(p1: Path, p2: Path) -> bool:
    """Check if p1 and p2 are identical, or if either is a parent/child of the other (resolving symlinks)."""
    try:
        r1 = p1.resolve()
        r2 = p2.resolve()
    except Exception:
        r1 = Path(p1.absolute())
        r2 = Path(p2.absolute())
    if r1 == r2:
        return True
    try:
        r1.relative_to(r2)
        return True
    except ValueError:
        pass
    try:
        r2.relative_to(r1)
        return True
    except ValueError:
        pass
    return False


def _validate_input_output_isolation(
    out_dir: Path,
    input_roots: List[Tuple[Optional[Path], str]],
    planned_trial_names: List[str],
) -> None:
    """Enforce strict read-only boundary between output targets and all inputs."""
    resolved_inputs: List[Tuple[Path, str]] = []
    for inp, label in input_roots:
        if inp is not None:
            try:
                resolved_inputs.append((inp.resolve(), label))
            except Exception:
                resolved_inputs.append((Path(inp.absolute()), label))

    def _assert_no_overlap(target: Path, target_label: str) -> None:
        try:
            r_target = target.resolve()
        except Exception:
            r_target = Path(target.absolute())
        for r_inp, inp_label in resolved_inputs:
            is_overlap = False
            if r_target == r_inp:
                is_overlap = True
            else:
                try:
                    r_target.relative_to(r_inp)
                    is_overlap = True
                except ValueError:
                    pass
                if not is_overlap:
                    try:
                        r_inp.relative_to(r_target)
                        is_overlap = True
                    except ValueError:
                        pass
            if is_overlap:
                print(
                    f"ERROR: {target_label} ({target}) cannot be identical to, inside, or a parent of {inp_label} ({r_inp}).",
                    file=sys.stderr,
                )
                sys.exit(2)

    # 1. Check output root
    _assert_no_overlap(out_dir, "--output path")

    # 2. Check each planned trial output directory
    for t_name in planned_trial_names:
        t_dest = out_dir / t_name
        _assert_no_overlap(t_dest, f"--output trial directory '{t_name}'")

    # 3. If out_dir exists or is a symlink, inspect its entire tree without following symlinks to reject links into inputs
    if out_dir.exists() or out_dir.is_symlink():
        if out_dir.is_symlink():
            _assert_no_overlap(out_dir, "--output symlink target")
        for root, dirs, files in os.walk(out_dir, followlinks=False):
            root_path = Path(root)
            for d in dirs:
                d_path = root_path / d
                _assert_no_overlap(d_path, f"output subdirectory '{d_path.relative_to(out_dir)}'")
            for f in files:
                f_path = root_path / f
                if f_path.is_symlink():
                    _assert_no_overlap(f_path, f"output symlink '{f_path.relative_to(out_dir)}'")


def _is_safe_manifest_relpath(rel_str: Any, out_dir: Path) -> bool:
    """Validate that rel_str is a safe relative path strictly contained inside out_dir."""
    if not isinstance(rel_str, str) or not rel_str.strip():
        return False
    cleaned = rel_str.strip()
    p = Path(cleaned)
    if p.is_absolute() or ".." in p.parts:
        return False
    try:
        resolved_out = out_dir.resolve()
        resolved_target = (out_dir / p).resolve()
        resolved_target.relative_to(resolved_out)
        return True
    except (ValueError, RuntimeError):
        return False


def _publish_staging_to_output(staging_dir: Path, out_dir: Path, is_multi_trial: bool) -> None:
    """Publish staging directory contents into out_dir with atomic file replacement and best-effort rollback.

    Guarantees:
    1. Only managed artifacts recorded in a valid .cfa_manifest.json are cleaned.
    2. Without a previous manifest, pre-existing files (e.g. user report.md) are strictly preserved.
    3. Manifest paths with '..' or escaping out_dir are rejected and never deleted or written.
    4. Each file is written via a hidden temporary file and atomically replaced (os.replace)
       so readers never observe partially written files.
    5. Best-effort rollback: If an error occurs, out_dir is rolled back to its pre-publish state;
       any secondary I/O errors during rollback are captured without masking the primary exception.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect staged files and write manifest into staging_dir
    staged_rel_paths = sorted(
        str(p.relative_to(staging_dir)) for p in staging_dir.rglob("*") if p.is_file()
    )
    staged_dirs = sorted(p.name for p in staging_dir.iterdir() if p.is_dir())
    manifest_data = {
        "schema_version": "cfa-manifest-v1",
        "layout": "multi" if is_multi_trial else "single",
        "managed_files": staged_rel_paths + [MANIFEST_FILENAME],
        "managed_dirs": staged_dirs,
    }
    manifest_file = staging_dir / MANIFEST_FILENAME
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    staged_rel_paths.append(MANIFEST_FILENAME)

    # 2. Determine previous managed artifacts in out_dir from a verified manifest only
    old_manifest_path = out_dir / MANIFEST_FILENAME
    old_managed_files: Set[str] = set()
    old_managed_dirs: Set[str] = set()
    has_valid_old_manifest = False

    if old_manifest_path.is_file():
        try:
            old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
            if (
                isinstance(old_manifest, dict)
                and old_manifest.get("schema_version") == "cfa-manifest-v1"
            ):
                raw_files = old_manifest.get("managed_files") or []
                raw_dirs = old_manifest.get("managed_dirs") or []
                if isinstance(raw_files, list) and isinstance(raw_dirs, list):
                    for f in raw_files:
                        if _is_safe_manifest_relpath(f, out_dir):
                            old_managed_files.add(str(Path(f)))
                    for d in raw_dirs:
                        if _is_safe_manifest_relpath(d, out_dir):
                            old_managed_dirs.add(str(Path(d)))
                    has_valid_old_manifest = True
        except Exception:
            pass

    # If no valid previous manifest exists, CFA assumes ownership of ZERO pre-existing files!
    # Unmanaged files and directories (user notes, reports, data) are NEVER deleted.
    if not has_valid_old_manifest:
        old_managed_files = set()
        old_managed_dirs = set()

    # Managed files to remove (existed previously in manifest, not in new staged files)
    files_to_remove = old_managed_files - set(staged_rel_paths)

    # 3. Create transactional backup of all files in out_dir that will be deleted or overwritten
    backup_dir = Path(tempfile.mkdtemp(prefix="cfa_tx_backup_"))
    backed_up_items: Dict[str, Path] = {}
    pre_publish_files = {str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()}

    try:
        # Back up existing files that will be touched
        for rel_str in files_to_remove | (old_managed_files & set(staged_rel_paths)):
            if not _is_safe_manifest_relpath(rel_str, out_dir):
                continue
            target = out_dir / rel_str
            if target.is_file():
                b_path = backup_dir / rel_str
                b_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, b_path)
                backed_up_items[rel_str] = b_path

        # Step A: Atomically write and replace all staged files into out_dir
        # By putting new files in place first, readers never see missing files before replacement
        for rel_str in staged_rel_paths:
            if not _is_safe_manifest_relpath(rel_str, out_dir):
                continue
            src = staging_dir / rel_str
            dest = out_dir / rel_str
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp_dest = dest.parent / f".{dest.name}.cfa_tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            try:
                shutil.copy2(src, tmp_dest)
                os.replace(tmp_dest, dest)
            except Exception:
                if tmp_dest.is_file() or tmp_dest.is_symlink():
                    try:
                        tmp_dest.unlink()
                    except OSError:
                        pass
                raise

        # Step B: Delete stale managed files (now that new versions are fully in place)
        for rel_str in files_to_remove:
            if not _is_safe_manifest_relpath(rel_str, out_dir):
                continue
            target = out_dir / rel_str
            if target.is_file() or target.is_symlink():
                target.unlink()

        # Step C: Clean old managed trial directories if empty
        for d_name in old_managed_dirs - set(staged_dirs):
            if not _is_safe_manifest_relpath(d_name, out_dir):
                continue
            d_path = out_dir / d_name
            if d_path.is_dir():
                try:
                    d_path.rmdir()
                except OSError:
                    pass  # Keep if user files exist

    except Exception as primary_exc:
        # ROLLBACK: Best-effort restore of out_dir to exact pre-publish state
        rollback_errors: List[Exception] = []
        try:
            current_files = {str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()}
            # 1. Remove newly created files
            for newly_created in current_files - pre_publish_files:
                try:
                    p = out_dir / newly_created
                    if p.is_file() or p.is_symlink():
                        p.unlink()
                except Exception as e:
                    rollback_errors.append(e)

            # 2. Restore all backed up files using atomic replace
            for rel_str, b_path in backed_up_items.items():
                try:
                    dest = out_dir / rel_str
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp_restore = (
                        dest.parent / f".{dest.name}.restore_{os.getpid()}_{uuid.uuid4().hex[:8]}"
                    )
                    shutil.copy2(b_path, tmp_restore)
                    os.replace(tmp_restore, dest)
                except Exception as e:
                    rollback_errors.append(e)

            # 3. Clean any empty dirs created during failed attempt
            for rel_str in staged_rel_paths:
                parent = (out_dir / rel_str).parent
                while parent != out_dir and parent.is_dir():
                    try:
                        parent.rmdir()
                        parent = parent.parent
                    except OSError:
                        break
        except Exception as e:
            rollback_errors.append(e)

        if rollback_errors:
            print(
                f"WARNING: Rollback encountered secondary I/O errors: {rollback_errors[0]}",
                file=sys.stderr,
            )
        raise primary_exc
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


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

    # 1. Determine planned artifacts for the current invocation
    planned_files: Set[str] = set()
    effective_cand_hyps = cand_hyps
    if fmt in ("json", "both"):
        planned_files.add("evidence.json")
        if effective_cand_hyps is None and analysis is not None:
            effective_cand_hyps = {
                "case_id": evidence.get("case_id"),
                "trial_name": evidence.get("trial_name"),
                "candidate_hypotheses": analysis.get("competing_hypotheses") or [],
            }
        if effective_cand_hyps is not None:
            planned_files.add("candidate-hypotheses.json")
        if analysis is not None:
            planned_files.add("analysis.json")

    has_markdown = fmt in ("markdown", "both") and report_md is not None and analysis is not None
    if has_markdown:
        planned_files.add("report.md")
        planned_files.add("report.zh.md")
        planned_files.add("report.en.md")
        sp = analysis.get("skill_prescription")
        if skill_md and sp:
            planned_files.add("skill-prescription.md")
            planned_files.add("skill-prescription.zh.md")
            planned_files.add("skill-prescription.en.md")

    # 2. Lifecycle cleanup: purge stale known trial artifacts from prior runs
    for stale_file in KNOWN_TRIAL_ARTIFACTS - planned_files:
        stale_path = out_dir / stale_file
        if stale_path.is_file():
            stale_path.unlink()

    # 3. Write planned artifacts
    if "evidence.json" in planned_files:
        (out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if "candidate-hypotheses.json" in planned_files and effective_cand_hyps is not None:
        (out_dir / "candidate-hypotheses.json").write_text(
            json.dumps(effective_cand_hyps, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if "analysis.json" in planned_files and analysis is not None:
        (out_dir / "analysis.json").write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if has_markdown and analysis is not None:
        (out_dir / "report.md").write_text(
            render_report_markdown(evidence, analysis, lang="bilingual", output_format=fmt),
            encoding="utf-8",
        )
        (out_dir / "report.zh.md").write_text(
            render_report_markdown(evidence, analysis, lang="zh", output_format=fmt),
            encoding="utf-8",
        )
        (out_dir / "report.en.md").write_text(
            render_report_markdown(evidence, analysis, lang="en", output_format=fmt),
            encoding="utf-8",
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
    parser.add_argument(
        "--task", required=False, type=Path, default=None, help="Task definition directory path"
    )
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
    parser.add_argument(
        "--max-log-bytes", type=int, default=120000, help="Maximum bytes per log file read"
    )
    parser.add_argument(
        "--include-session-files",
        action="store_true",
        help="Include agent session files in inventory",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    args = parser.parse_args()

    if args.phase == "collect" and args.format == "markdown":
        print(
            "ERROR: --phase collect does not produce markdown reports. "
            "Use --format json or --format both.",
            file=sys.stderr,
        )
        sys.exit(2)

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

    _validate_input_output_isolation(
        out_dir=args.output,
        input_roots=[(args.job, "--job"), (args.task, "--task")],
        planned_trial_names=[],
    )

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
        has_job_level_evidence = (args.job / "result.json").is_file() or (
            args.job / "job.log"
        ).is_file()
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
    task_dir_path = Path(discovery["task_dir"]) if discovery.get("task_dir") else None

    all_input_roots: List[Tuple[Optional[Path], str]] = [
        (job_dir, "--job"),
        (task_dir_path, "--task"),
    ]
    for inv in trials:
        t_task = inv.get("task_dir")
        if t_task and Path(t_task) != task_dir_path:
            all_input_roots.append((Path(t_task), "--task"))
        t_path = inv.get("trial_dir")
        if t_path:
            all_input_roots.append((Path(t_path), f"input trial '{inv.get('trial_name')}'"))
    for t in all_trials:
        all_input_roots.append((t, f"input trial '{t.name}'"))

    planned_trial_names = [inv["trial_name"] for inv in trials] if len(trials) > 1 else []
    _validate_input_output_isolation(
        out_dir=args.output,
        input_roots=all_input_roots,
        planned_trial_names=planned_trial_names,
    )

    staging_dir = Path(tempfile.mkdtemp(prefix="cfa_staging_"))
    try:
        if len(trials) == 1:
            inv = trials[0]
            if args.phase == "collect":
                ev, _, _, cand_hyps = collect_case_evidence(
                    inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes
                )
                _report_diagnostics(ev)
                write_outputs(
                    staging_dir, ev, None, None, None, cand_hyps=cand_hyps, fmt=args.format
                )
            else:
                ev, an, rep, skill_md = analyze_single_trial(
                    inv,
                    job_dir=job_dir,
                    max_log_bytes=args.max_log_bytes,
                    replay_mode=args.replay,
                )
                _report_diagnostics(ev)
                write_outputs(staging_dir, ev, an, rep, skill_md, fmt=args.format)
            _publish_staging_to_output(staging_dir, args.output, is_multi_trial=False)
        else:
            summary_rows = []
            for inv in trials:
                t_out = staging_dir / inv["trial_name"]
                if args.phase == "collect":
                    ev, _, _, cand_hyps = collect_case_evidence(
                        inv, job_dir=job_dir, max_log_bytes=args.max_log_bytes
                    )
                    _report_diagnostics(ev)
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
                    _report_diagnostics(ev)
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
            batch_stats = compute_batch_statistics(summary_rows)
            (staging_dir / "job_summary.json").write_text(
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
            _publish_staging_to_output(staging_dir, args.output, is_multi_trial=True)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
