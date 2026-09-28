#!/usr/bin/env python3
"""
Phase 2: Trajectory Normalization (`scripts/normalize_trajectory.py`)

Normalizes ATIF-v1.7 (and compatible) `agent/trajectory.json` files into a
unified event timeline and derives objective behavioral signals with exact
JSON pointers back to raw trajectory steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_SCHEMAS = {"ATIF-v1.7", "ATIF-v1.6", "ATIF-v1.5"}


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def truncate_with_head_tail(
    text: Optional[str], max_bytes: int = 2000
) -> Tuple[Optional[str], Optional[str], bool]:
    if text is None:
        return None, None, False
    digest = sha256_text(text)
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, digest, False
    half = max(200, max_bytes // 2)
    head = encoded[:half].decode("utf-8", errors="replace")
    tail = encoded[-half:].decode("utf-8", errors="replace")
    truncated = f"{head}\n... [TRUNCATED {len(encoded)} bytes, sha256={digest}] ...\n{tail}"
    return truncated, digest, True


def extract_exit_code_and_error(obs_text: str) -> Tuple[Optional[int], bool]:
    if not obs_text:
        return None, False
    m = re.search(r"(?:Exit code|Return code|exit status)[:\s]+(\d+)", obs_text, re.IGNORECASE)
    if m:
        code = int(m.group(1))
        return code, code != 0
    error_indicators = (
        "Traceback (most recent call last):",
        "command not found",
        "No such file or directory",
        "Permission denied",
        "ERROR:",
        "Fatal Error",
        "ABORT",
        "Segmentation fault",
        "convergence NOT achieved",
        "NOT converged",
        "SCF NOT CONVERGED",
        "cannot be opened",
        "Lost atoms",
        "CUDA out of memory",
        "RuntimeError:",
        "LinAlgError:",
        "ValueError:",
        "KeyError:",
        "Error EDDDAV",
        "ZBRENT:",
        "LINCS WARNING",
        "link 9999",
        "l502.exe",
    )
    if any(ind in obs_text for ind in error_indicators):
        return 1, True
    return 0, False


def classify_tool_event(
    tool_name: str, args: Dict[str, Any], has_error: bool
) -> Tuple[str, Optional[str]]:
    t_lower = (tool_name or "").lower()
    if t_lower in ("read", "view", "cat"):
        return "file_read", args.get("file_path") or args.get("path")
    if t_lower in ("write", "edit", "multiedit", "replace"):
        return "file_write", args.get("file_path") or args.get("path")
    if t_lower in ("bash", "shell", "exec"):
        cmd = args.get("command") or ""
        if has_error:
            return "shell_error", cmd
        return "tool_call", cmd
    return "tool_call", json.dumps(args, ensure_ascii=False)[:200]


def _parse_trajectory_payload(text: str) -> Dict[str, Any]:
    """Parse standard ATIF JSON, JSON array of messages, or JSONL stream into a normalized dict."""
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            if "steps" not in parsed and isinstance(parsed.get("messages"), list):
                parsed["steps"] = _convert_messages_to_steps(parsed["messages"])
                parsed.setdefault("schema_version", "ATIF-v1.7")
            return parsed
        if isinstance(parsed, list):
            return {"schema_version": "ATIF-v1.7", "steps": _convert_messages_to_steps(parsed)}
    except Exception:
        pass

    # Fallback: try line-delimited JSONL
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if lines:
        objs = []
        for ln in lines:
            objs.append(json.loads(ln))
        return {"schema_version": "ATIF-v1.7", "steps": _convert_messages_to_steps(objs)}
    raise ValueError("Unable to parse trajectory file as JSON or JSONL")


def _convert_messages_to_steps(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert generic OpenAI/Anthropic/JSONL message or step records into ATIF-compatible step dicts."""
    steps: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if "tool_calls" in item or "observation" in item or "step_id" in item:
            steps.append(item)
            continue
        role = item.get("role") or item.get("source") or "agent"
        content = item.get("content")
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            msg_str = "\n".join(t for t in text_parts if t)
        else:
            msg_str = str(content or item.get("message") or "")
        steps.append(
            {
                "step_id": idx + 1,
                "timestamp": item.get("timestamp") or item.get("created_at"),
                "source": "user" if role in ("user", "system") else "agent",
                "message": msg_str,
                "tool_calls": item.get("tool_calls") or [],
            }
        )
    return steps


def normalize_trajectory(
    trajectory_path: Optional[Path],
    max_obs_bytes: int = 2000,
    max_file_bytes: int = 50_000_000,
) -> Dict[str, Any]:
    if trajectory_path is None or not trajectory_path.is_file():
        return {
            "exists": False,
            "schema_version": None,
            "warnings": ["agent/trajectory.json is missing"],
            "events": [],
            "behavioral_signals": [],
            "written_files": [],
            "read_files": [],
        }

    try:
        file_size = trajectory_path.stat().st_size
        if file_size > max_file_bytes:
            return {
                "exists": True,
                "schema_version": None,
                "warnings": [
                    f"trajectory.json size ({file_size} bytes) exceeds max_file_bytes ({max_file_bytes})"
                ],
                "events": [],
                "behavioral_signals": [],
                "written_files": [],
                "read_files": [],
            }
        raw = _parse_trajectory_payload(trajectory_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {
            "exists": True,
            "schema_version": None,
            "warnings": [f"Failed to parse trajectory.json: {exc}"],
            "events": [],
            "behavioral_signals": [],
            "written_files": [],
            "read_files": [],
        }

    schema_version = raw.get("schema_version")
    warnings: List[str] = []
    if schema_version not in SUPPORTED_SCHEMAS:
        warnings.append(
            f"Unknown trajectory schema_version={schema_version!r}; preserving raw step pointers."
        )

    steps = raw.get("steps") or []
    events: List[Dict[str, Any]] = []
    signals: List[Dict[str, Any]] = []
    written_files: List[str] = []
    read_files: List[str] = []

    prev_commands: List[Tuple[str, bool, str]] = []  # (cmd, failed, event_id)
    results_json_written = False
    results_json_verified_after_write = False
    ran_simulation = False
    inspected_sim_log = False

    for idx, step in enumerate(steps):
        step_id = step.get("step_id", idx + 1)
        ts = step.get("timestamp")
        source = step.get("source", "agent")
        msg = step.get("message") or ""
        step_ptr = f"/steps/{idx}"

        if source == "user":
            trunc_msg, msg_sha, _ = truncate_with_head_tail(msg, max_obs_bytes)
            events.append(
                {
                    "event_id": f"trajectory:step:{step_id}",
                    "timestamp": ts,
                    "actor": "user",
                    "event_type": "user_instruction",
                    "tool_name": None,
                    "command": None,
                    "observation": trunc_msg,
                    "observation_sha256": msg_sha,
                    "exit_code": None,
                    "source_file": "agent/trajectory.json",
                    "source_pointer": step_ptr,
                }
            )
            continue

        # Agent reasoning / message event
        if msg:
            is_final = idx == len(steps) - 1 and not step.get("tool_calls")
            trunc_msg, msg_sha, _ = truncate_with_head_tail(msg, max_obs_bytes)
            events.append(
                {
                    "event_id": f"trajectory:step:{step_id}:msg",
                    "timestamp": ts,
                    "actor": "agent",
                    "event_type": "final_response" if is_final else "agent_reasoning",
                    "tool_name": None,
                    "command": None,
                    "observation": trunc_msg,
                    "observation_sha256": msg_sha,
                    "exit_code": None,
                    "source_file": "agent/trajectory.json",
                    "source_pointer": f"{step_ptr}/message",
                }
            )

        # Map tool observations by source_call_id
        obs_by_call_id: Dict[str, str] = {}
        obs_block = step.get("observation") or {}
        for r_idx, res_item in enumerate(obs_block.get("results") or []):
            cid = res_item.get("source_call_id")
            content = res_item.get("content")
            if isinstance(content, list):
                content = "\n".join(str(x) for x in content)
            elif content is not None and not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            if cid:
                obs_by_call_id[cid] = content or ""

        tool_calls = step.get("tool_calls") or []
        for t_idx, tc in enumerate(tool_calls):
            tc_id = tc.get("tool_call_id") or f"call_{t_idx}"
            fn_name = tc.get("function_name") or tc.get("name") or "unknown"
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}

            obs_text = obs_by_call_id.get(tc_id, "")
            exit_code, has_error = extract_exit_code_and_error(obs_text)
            ev_type, cmd_or_path = classify_tool_event(fn_name, args, has_error)
            trunc_obs, obs_sha, _ = truncate_with_head_tail(obs_text, max_obs_bytes)
            ev_id = f"trajectory:step:{step_id}:tool:{t_idx}"
            tc_ptr = f"{step_ptr}/tool_calls/{t_idx}"

            # Check for repeated command
            norm_cmd = (cmd_or_path or "").strip()
            if fn_name.lower() == "bash" and norm_cmd:
                for prev_cmd, prev_failed, prev_ev in prev_commands:
                    if prev_cmd == norm_cmd:
                        ev_type = "repeated_command"
                        if prev_failed:
                            signals.append(
                                {
                                    "signal_id": f"sig:repeated_fail:{step_id}:{t_idx}",
                                    "signal_type": "repeated_failed_action",
                                    "description": f"Agent re-executed identical failing command ({norm_cmd[:100]}) after {prev_ev}",
                                    "event_ref": ev_id,
                                    "source_pointer": tc_ptr,
                                }
                            )
                        break
                prev_commands.append((norm_cmd, has_error, ev_id))

                # Behavioral heuristics on Bash commands
                if any(
                    k in norm_cmd
                    for k in ("which ", "find ", "ls /opt", "ls /workspace/assets", "locate ")
                ):
                    signals.append(
                        {
                            "signal_id": f"sig:dep_search:{step_id}:{t_idx}",
                            "signal_type": "dependency_search_attempted",
                            "description": f"Agent searched for binaries or data files: {norm_cmd[:120]}",
                            "event_ref": ev_id,
                            "source_pointer": tc_ptr,
                        }
                    )

                if any(
                    bin_k in norm_cmd
                    for bin_k in (
                        "cp2k",
                        "pw.x",
                        "bands.x",
                        "lmp",
                        "lammps",
                        "xtb",
                        "vasp",
                        "abacus",
                        "orca",
                        "g16",
                        "g09",
                        "pyscf",
                        "psi4",
                        "nwchem",
                        "gmx",
                        "mdrun",
                        "pmemd",
                        "sander",
                        "openmm",
                        "mace",
                        "nequip",
                        "deepmd",
                        "dp ",
                        "chgnet",
                        "sevennet",
                        "openfoam",
                        "fenics",
                    )
                ):
                    ran_simulation = True

                if any(
                    log_k in norm_cmd
                    for log_k in (
                        ".out",
                        ".log",
                        "log.lammps",
                        ".ener",
                        "pwscf.xml",
                        "OUTCAR",
                        "OSZICAR",
                        "running_scf.log",
                        "md.log",
                    )
                ) and any(r_k in norm_cmd for r_k in ("cat ", "head ", "tail ", "grep ", "python")):
                    inspected_sim_log = True

                if "results.json" in norm_cmd and any(
                    w in norm_cmd for w in (">", "tee", "json.dump", "write_text", "open(")
                ):
                    results_json_written = True
                    results_json_verified_after_write = False
                elif results_json_written and "results.json" in norm_cmd and any(
                    r in norm_cmd for r in ("cat ", "json.load", "head ")
                ):
                    results_json_verified_after_write = True

                # Check if agent modified `/workspace/assets`
                if re.search(r"(?:>|>>|sed\s+-i|cp\s+.*\s+/workspace/assets/|mv\s+.*\s+/workspace/assets/)", norm_cmd):
                    signals.append(
                        {
                            "signal_id": f"sig:asset_mod:{step_id}:{t_idx}",
                            "signal_type": "asset_modified",
                            "description": f"Agent command potentially modified `/workspace/assets/`: {norm_cmd[:120]}",
                            "event_ref": ev_id,
                            "source_pointer": tc_ptr,
                        }
                    )

                # Check if scientific parameters were edited
                if any(
                    p in norm_cmd
                    for p in ("TIMESTEP", "ecutwfc", "MAX_SCF", "mixing_beta", "reset_timestep", "thermo_style")
                ):
                    signals.append(
                        {
                            "signal_id": f"sig:sci_param:{step_id}:{t_idx}",
                            "signal_type": "scientific_parameter_changed",
                            "description": f"Agent set or modified scientific simulation parameter in command: {norm_cmd[:120]}",
                            "event_ref": ev_id,
                            "source_pointer": tc_ptr,
                        }
                    )

            if ev_type == "file_write" and cmd_or_path:
                written_files.append(cmd_or_path)
                if "/workspace/assets/" in cmd_or_path:
                    signals.append(
                        {
                            "signal_id": f"sig:asset_write:{step_id}:{t_idx}",
                            "signal_type": "asset_modified",
                            "description": f"Agent directly wrote/edited asset file: {cmd_or_path}",
                            "event_ref": ev_id,
                            "source_pointer": tc_ptr,
                        }
                    )
                if cmd_or_path.endswith("results.json"):
                    results_json_written = True
                    results_json_verified_after_write = False
                    if not cmd_or_path.startswith("/workspace/results.json") and cmd_or_path != "results.json":
                        signals.append(
                            {
                                "signal_id": f"sig:wrong_path:{step_id}:{t_idx}",
                                "signal_type": "wrong_output_path",
                                "description": f"results.json written to non-standard path: {cmd_or_path}",
                                "event_ref": ev_id,
                                "source_pointer": tc_ptr,
                            }
                        )

            if ev_type == "file_read" and cmd_or_path:
                read_files.append(cmd_or_path)
                if any(k in cmd_or_path for k in (".out", "log.lammps", ".ener")):
                    inspected_sim_log = True
                if cmd_or_path.endswith("results.json") and results_json_written:
                    results_json_verified_after_write = True

            events.append(
                {
                    "event_id": ev_id,
                    "timestamp": ts,
                    "actor": "agent",
                    "event_type": ev_type,
                    "tool_name": fn_name,
                    "command": cmd_or_path,
                    "observation": trunc_obs,
                    "observation_sha256": obs_sha,
                    "exit_code": exit_code,
                    "source_file": "agent/trajectory.json",
                    "source_pointer": tc_ptr,
                }
            )

    # Post-trajectory aggregate behavioral signals
    if ran_simulation and not inspected_sim_log:
        signals.append(
            {
                "signal_id": "sig:missing_log_inspection",
                "signal_type": "missing_log_inspection",
                "description": "Agent executed simulation binary without inspecting output log files.",
                "event_ref": events[-1]["event_id"] if events else "trajectory:root",
                "source_pointer": "/steps",
            }
        )

    if not results_json_written and events:
        signals.append(
            {
                "signal_id": "sig:premature_completion",
                "signal_type": "premature_completion",
                "description": "Agent trajectory ended without writing `results.json`.",
                "event_ref": events[-1]["event_id"],
                "source_pointer": f"/steps/{len(steps) - 1}" if steps else "/steps",
            }
        )
    elif results_json_written and not results_json_verified_after_write and events:
        signals.append(
            {
                "signal_id": "sig:unverified_output",
                "signal_type": "unverified_output",
                "description": "Agent wrote `results.json` without reading/validating its final schema.",
                "event_ref": events[-1]["event_id"],
                "source_pointer": f"/steps/{len(steps) - 1}" if steps else "/steps",
            }
        )

    return {
        "exists": True,
        "schema_version": schema_version,
        "session_id": raw.get("session_id"),
        "warnings": warnings,
        "events": events,
        "behavioral_signals": signals,
        "written_files": sorted(set(written_files)),
        "read_files": sorted(set(read_files)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize ATIF agent trajectory into timeline events.")
    parser.add_argument("--trajectory", required=True, type=Path, help="Path to agent/trajectory.json")
    parser.add_argument("--max-obs-bytes", type=int, default=2000, help="Max bytes per observation snippet")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    res = normalize_trajectory(args.trajectory, max_obs_bytes=args.max_obs_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
