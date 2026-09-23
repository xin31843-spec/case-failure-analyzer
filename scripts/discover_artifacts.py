#!/usr/bin/env python3
"""
Phase 1: Artifact Discovery (`scripts/discover_artifacts.py`)

Discovers job-level, trial-level, and task-level artifacts, computes SHA256
hashes, parses JSON/TOML metadata, determines whether the agent and verifier
actually started, and lists missing artifacts without failing on partial runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_sha256(path: Path, max_bytes: Optional[int] = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        remaining = max_bytes
        while True:
            chunk_size = 65536 if remaining is None else min(65536, remaining)
            if chunk_size <= 0:
                break
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
            if remaining is not None:
                remaining -= len(data)
    return f"sha256:{h.hexdigest()}"


def safe_load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {"_value": data}
    except Exception as exc:
        return {"_parse_error": str(exc)}


def safe_load_toml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        import tomllib  # Python 3.11+

        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        # Minimal fallback key=value parser
        result: Dict[str, Any] = {}
        try:
            section = result
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    sec_name = line[1:-1].strip()
                    section = result.setdefault(sec_name, {})
                elif "=" in line:
                    k, v = line.split("=", 1)
                    section[k.strip()] = v.strip().strip("'\"")
        except Exception as exc:
            return {"_parse_error": str(exc)}
        return result


def is_trial_dir(path: Path) -> bool:
    """Determine if a directory is a trial directory inside a job."""
    if not path.is_dir() or path.name.startswith("."):
        return False
    trial_markers = ("trial.log", "agent", "verifier", "exception.txt")
    if any((path / m).exists() for m in trial_markers):
        return True
    res = safe_load_json(path / "result.json")
    if res and ("trial_name" in res or "agent_execution" in res):
        return True
    return False


def discover_trials(job_path: Path, trial_filter: str = "all") -> List[Path]:
    """Return sorted list of trial directories for a given job_path."""
    if is_trial_dir(job_path):
        return [job_path]
    trials: List[Path] = []
    if job_path.is_dir():
        for child in sorted(job_path.iterdir()):
            if is_trial_dir(child):
                if trial_filter in ("all", child.name):
                    trials.append(child)
    return trials


def make_artifact_entry(
    artifact_id: str,
    base_dir: Path,
    rel_path: str,
    scope: str,
) -> Dict[str, Any]:
    full_path = base_dir / rel_path
    exists = full_path.is_file()
    entry: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "rel_path": rel_path,
        "abs_path": str(full_path.resolve()) if exists else str(full_path),
        "scope": scope,
        "exists": exists,
        "size_bytes": full_path.stat().st_size if exists else 0,
        "sha256": compute_sha256(full_path) if exists else None,
    }
    return entry


def build_trial_inventory(
    job_dir: Path,
    task_dir: Optional[Path],
    trial_dir: Optional[Path],
    include_session_files: bool = False,
) -> Dict[str, Any]:
    artifacts: List[Dict[str, Any]] = []
    missing_artifacts: List[str] = []

    # 1. Job-level files
    job_files = [
        ("art:job_config", "config.json"),
        ("art:job_log", "job.log"),
        ("art:job_lock", "lock.json"),
        ("art:job_result", "result.json"),
    ]
    for aid, rel in job_files:
        entry = make_artifact_entry(aid, job_dir, rel, "job")
        artifacts.append(entry)
        if not entry["exists"]:
            missing_artifacts.append(f"job:{rel}")

    # 2. Trial-level files
    trial_files = [
        ("art:trial_config", "config.json"),
        ("art:trial_lock", "lock.json"),
        ("art:trial_result", "result.json"),
        ("art:exception_txt", "exception.txt"),
        ("art:trial_log", "trial.log"),
        ("art:manifest_json", "artifacts/manifest.json"),
        ("art:trajectory_json", "agent/trajectory.json"),
        ("art:claude_code_txt", "agent/claude-code.txt"),
        ("art:verify_log", "verifier/verify.log"),
        ("art:test_stdout", "verifier/test-stdout.txt"),
        ("art:reward_txt", "verifier/reward.txt"),
    ]
    if trial_dir is not None and trial_dir.is_dir():
        for aid, rel in trial_files:
            entry = make_artifact_entry(aid, trial_dir, rel, "trial")
            artifacts.append(entry)
            # Note: exception.txt is only expected on exceptions; others are tracked if missing
            if not entry["exists"] and rel != "exception.txt":
                missing_artifacts.append(rel)

        if include_session_files:
            sessions_dir = trial_dir / "agent" / "sessions"
            if sessions_dir.is_dir():
                for idx, sf in enumerate(sorted(sessions_dir.rglob("*"))):
                    if sf.is_file():
                        rel = str(sf.relative_to(trial_dir))
                        artifacts.append(
                            make_artifact_entry(f"art:session_{idx}", trial_dir, rel, "trial")
                        )
    else:
        for _, rel in trial_files:
            if rel != "exception.txt":
                missing_artifacts.append(rel)

    # 3. Auto-resolve task_dir from config/result if not supplied
    job_result = safe_load_json(job_dir / "result.json") or {}
    trial_result = (
        safe_load_json(trial_dir / "result.json")
        if (trial_dir and trial_dir.is_dir())
        else None
    ) or {}
    if task_dir is None:
        task_rel = (
            trial_result.get("task_id", {}).get("path")
            or trial_result.get("config", {}).get("task", {}).get("path")
        )
        if task_rel:
            candidate = job_dir.parent.parent / task_rel
            if candidate.is_dir():
                task_dir = candidate

    # 4. Task-level files
    if task_dir is not None and task_dir.is_dir():
        task_files = [
            ("art:instruction_md", "instruction.md"),
            ("art:task_toml", "task.toml"),
            ("art:dockerfile", "environment/Dockerfile"),
            ("art:verify_py", "tests/verify.py"),
            ("art:test_sh", "tests/test.sh"),
            ("art:refs_json", "tests/refs.json"),
        ]
        for aid, rel in task_files:
            entry = make_artifact_entry(aid, task_dir, rel, "task")
            artifacts.append(entry)
            if not entry["exists"]:
                missing_artifacts.append(f"task:{rel}")

        assets_dir = task_dir / "environment" / "assets"
        if assets_dir.is_dir():
            for idx, af in enumerate(sorted(assets_dir.rglob("*"))):
                if af.is_file() and not af.name.startswith("."):
                    rel = str(af.relative_to(task_dir))
                    artifacts.append(
                        make_artifact_entry(f"art:asset_{idx}", task_dir, rel, "task")
                    )

    # 5. Determine runtime status and stage gates
    traj_exists = bool(
        trial_dir and (trial_dir / "agent" / "trajectory.json").is_file()
    )
    claude_txt_exists = bool(
        trial_dir
        and (trial_dir / "agent" / "claude-code.txt").is_file()
        and (trial_dir / "agent" / "claude-code.txt").stat().st_size > 0
    )
    verify_log_exists = bool(
        trial_dir and (trial_dir / "verifier" / "verify.log").is_file()
    )
    reward_txt_path = trial_dir / "verifier" / "reward.txt" if trial_dir else None
    reward_val: Optional[float] = None
    if reward_txt_path and reward_txt_path.is_file():
        try:
            reward_val = float(reward_txt_path.read_text(encoding="utf-8").strip())
        except Exception:
            reward_val = None
    if reward_val is None:
        vr = trial_result.get("verifier_result")
        if isinstance(vr, dict) and isinstance(vr.get("rewards"), dict):
            r = vr["rewards"].get("reward")
            if isinstance(r, (int, float)):
                reward_val = float(r)

    agent_exec_stage = trial_result.get("agent_execution") or {}
    verifier_stage = trial_result.get("verifier") or {}
    env_setup_stage = trial_result.get("environment_setup") or {}
    agent_setup_stage = trial_result.get("agent_setup") or {}

    agent_started = bool(
        traj_exists
        or claude_txt_exists
        or agent_exec_stage.get("started_at")
        or trial_result.get("agent_result") is not None
    )
    verifier_started = bool(
        verify_log_exists
        or (reward_txt_path and reward_txt_path.is_file())
        or verifier_stage.get("started_at")
        or trial_result.get("verifier_result") is not None
    )

    exc_info = trial_result.get("exception_info")
    n_errored = job_result.get("stats", {}).get("n_errored_trials", 0)

    if exc_info is not None or n_errored > 0 or (
        trial_dir and (trial_dir / "exception.txt").is_file()
    ):
        exit_status = "errored"
    elif reward_val is not None and reward_val >= 1.0:
        exit_status = "completed"
    elif reward_val is not None and reward_val < 1.0:
        exit_status = "failed"
    else:
        exit_status = "unknown"

    case_id = (
        trial_result.get("task_name")
        or (task_dir.name if task_dir else None)
        or job_dir.name
    )
    trial_name = (
        trial_result.get("trial_name")
        or (trial_dir.name if trial_dir else job_dir.name)
    )

    return {
        "case_id": case_id,
        "trial_name": trial_name,
        "job_dir": str(job_dir.resolve()),
        "trial_dir": str(trial_dir.resolve()) if trial_dir else None,
        "task_dir": str(task_dir.resolve()) if task_dir and task_dir.is_dir() else None,
        "artifacts": artifacts,
        "runtime": {
            "started_at": trial_result.get("started_at") or job_result.get("started_at"),
            "finished_at": trial_result.get("finished_at") or job_result.get("finished_at"),
            "exit_status": exit_status,
            "reward": reward_val,
            "agent_started": agent_started,
            "verifier_started": verifier_started,
            "stages": {
                "environment_setup": env_setup_stage,
                "agent_setup": agent_setup_stage,
                "agent_execution": agent_exec_stage,
                "verifier": verifier_stage,
            },
        },
        "metadata": {
            "job_result_summary": {
                "n_total_trials": job_result.get("n_total_trials"),
                "n_errored_trials": n_errored,
            },
            "agent_info": trial_result.get("agent_info"),
            "task_toml": safe_load_toml(task_dir / "task.toml")
            if (task_dir and task_dir.is_dir())
            else None,
        },
        "missing_artifacts": missing_artifacts,
    }


def discover_all(
    job_path: Path,
    task_path: Optional[Path] = None,
    trial_filter: str = "all",
    include_session_files: bool = False,
) -> Dict[str, Any]:
    trials = discover_trials(job_path, trial_filter=trial_filter)
    job_dir = job_path.parent if is_trial_dir(job_path) else job_path
    if not trials:
        # Job-level failure before any trial directory was created
        inv = build_trial_inventory(
            job_dir=job_dir,
            task_dir=task_path,
            trial_dir=None,
            include_session_files=include_session_files,
        )
        return {"job_dir": str(job_dir.resolve()), "trials": [inv]}

    trial_inventories = [
        build_trial_inventory(
            job_dir=job_dir,
            task_dir=task_path,
            trial_dir=t,
            include_session_files=include_session_files,
        )
        for t in trials
    ]
    return {"job_dir": str(job_dir.resolve()), "trials": trial_inventories}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover job, trial, and task artifacts.")
    parser.add_argument("--job", required=True, type=Path, help="Path to job or trial directory")
    parser.add_argument("--task", required=False, type=Path, default=None, help="Path to task directory")
    parser.add_argument("--trial", default="all", help="Trial name or 'all'")
    parser.add_argument("--include-session-files", action="store_true", help="Include agent session files")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON file path")
    args = parser.parse_args()

    result = discover_all(
        job_path=args.job,
        task_path=args.task,
        trial_filter=args.trial,
        include_session_files=args.include_session_files,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
