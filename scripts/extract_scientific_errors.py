#!/usr/bin/env python3
"""
Phase 5: Scientific Software Error Knowledge Layer (`scripts/extract_scientific_errors.py`)

Loads the single-source-of-truth error registry from `references/error-families.json`
and runs deterministic error-family adapters across all 11 scientific computing and MLIP suites
(60 error families across CP2K, Quantum ESPRESSO, VASP/ABACUS, ORCA/Gaussian/PySCF, LAMMPS,
GROMACS/AMBER/OpenMM, MLIP, ASE, xTB, RDKit, and Generic Scientific) over trajectory observations and verifier logs.
Outputs structured `scientific_observations` with `candidate_causes`, `aliases`, and
`required_discriminating_evidence` without jumping directly to agent blame.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "references" / "error-families.json"

AdapterEntry = Tuple[str, str, List[str], re.Pattern[str], List[str], List[str]]


def load_error_family_registry(registry_path: Path = REGISTRY_PATH) -> Dict[str, Dict[str, Any]]:
    if not registry_path.is_file():
        raise FileNotFoundError(
            f"Scientific error family registry not found: {registry_path}"
        )
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(
            f"Scientific error family registry must be a non-empty JSON object: {registry_path}"
        )
    return data


def build_scientific_adapters(
    registry_path: Path = REGISTRY_PATH,
) -> List[AdapterEntry]:
    reg = load_error_family_registry(registry_path)
    adapters: List[AdapterEntry] = []
    for software, families in reg.items():
        if not isinstance(families, dict):
            raise ValueError(f"Invalid family mapping for software {software!r} in {registry_path}")
        for family_name, spec in families.items():
            if not isinstance(spec, dict):
                raise ValueError(f"Invalid family spec for {software}.{family_name} in {registry_path}")
            status = spec.get("status")
            if status not in ("implemented", "planned"):
                raise ValueError(
                    f"Invalid status {status!r} for {software}.{family_name} in {registry_path}"
                )
            if status != "implemented":
                continue
            patterns = spec.get("patterns") or []
            if not patterns:
                raise ValueError(
                    f"Implemented error family {software}.{family_name} has no regex patterns in {registry_path}"
                )
            combined = "(?:" + "|".join(patterns) + ")"
            compiled = re.compile(combined, re.IGNORECASE)
            aliases = spec.get("aliases") or []
            causes = spec.get("candidate_causes") or []
            req_ev = spec.get("required_discriminating_evidence") or []
            adapters.append((software, family_name, aliases, compiled, causes, req_ev))
    if not adapters:
        raise RuntimeError(
            f"Zero implemented scientific error adapters loaded from {registry_path}"
        )
    return adapters


SCIENTIFIC_ADAPTERS: List[AdapterEntry] = build_scientific_adapters()


def extract_scientific_errors(
    trial_dir: Optional[Path],
    normalized_traj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observations: List[Dict[str, Any]] = []
    seen = set()
    sci_counter = 1

    # 1. Scan trajectory events and track whether later simulation runs recovered
    if normalized_traj:
        traj_events = normalized_traj.get("events") or []
        sim_bins = (
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
        for ev_idx, ev in enumerate(traj_events):
            text = f"{ev.get('command') or ''}\n{ev.get('observation') or ''}"
            ev_id = ev.get("event_id", "trajectory:unknown")
            for sw, family, aliases, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
                m = pattern.search(text)
                if m:
                    dedup_key = (sw, family, m.group(0)[:80])
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    # Check if a subsequent trajectory step ran a simulation and succeeded without this error
                    recovery_ref: Optional[str] = None
                    for later_ev in traj_events[ev_idx + 1 :]:
                        later_cmd = (later_ev.get("command") or "").strip()
                        later_obs = later_ev.get("observation") or ""
                        later_exit = later_ev.get("exit_code")
                        later_text = f"{later_cmd}\n{later_obs}"
                        is_sim_cmd = any(b in later_cmd for b in sim_bins)
                        if (
                            is_sim_cmd
                            and later_exit == 0
                            and later_ev.get("event_type") != "shell_error"
                            and not pattern.search(later_text)
                            and not any(p[3].search(later_text) for p in SCIENTIFIC_ADAPTERS if p[0] == sw)
                        ):
                            recovery_ref = later_ev.get("event_id")
                            break

                    observations.append(
                        {
                            "sci_id": f"sci:{sci_counter}",
                            "software": sw,
                            "error_family": family,
                            "aliases": aliases,
                            "reference_anchor": f"references/software/{sw}.md#{family}",
                            "matched_text": m.group(0)[:240],
                            "source_ref": ev_id,
                            "recovered": recovery_ref is not None,
                            "recovery_event_ref": recovery_ref,
                            "candidate_causes": causes,
                            "required_discriminating_evidence": req_ev,
                        }
                    )
                    sci_counter += 1

    # 2. Fallback scan of agent logs when trajectory.json has no events
    if not (normalized_traj and normalized_traj.get("events")) and trial_dir:
        for rel_log in (
            "agent/claude-code.txt",
            "agent/codex.txt",
            "agent/agent.log",
            "agent/stdout.txt",
            "agent/output.log",
        ):
            cc_path = trial_dir / rel_log
            if cc_path.is_file():
                cc_text = _read_bounded_text(cc_path)
                for sw, family, aliases, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
                    m = pattern.search(cc_text)
                    if m:
                        dedup_key = (sw, family, m.group(0)[:80])
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)
                        observations.append(
                            {
                                "sci_id": f"sci:{sci_counter}",
                                "software": sw,
                                "error_family": family,
                                "aliases": aliases,
                                "reference_anchor": f"references/software/{sw}.md#{family}",
                                "matched_text": _extract_match_line(cc_text, m)[:240],
                                "source_ref": "art:claude_code_txt"
                                if rel_log == "agent/claude-code.txt"
                                else rel_log,
                                "candidate_causes": causes,
                                "required_discriminating_evidence": req_ev,
                            }
                        )
                        sci_counter += 1

    # 3. Scan verifier logs (verify.log, test-stdout.txt, pytest.log)
    if trial_dir:
        for rel_vlog in (
            "verifier/verify.log",
            "verifier/test-stdout.txt",
            "verifier/pytest.log",
            "verify.log",
        ):
            vpath = trial_dir / rel_vlog
            if vpath.is_file():
                vlog = _read_bounded_text(vpath)
                for sw, family, aliases, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
                    m = pattern.search(vlog)
                    if m:
                        dedup_key = (sw, family, m.group(0)[:80])
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)
                        observations.append(
                            {
                                "sci_id": f"sci:{sci_counter}",
                                "software": sw,
                                "error_family": family,
                                "aliases": aliases,
                                "reference_anchor": f"references/software/{sw}.md#{family}",
                                "matched_text": _extract_match_line(vlog, m)[:240],
                                "source_ref": "verifier/verify.log"
                                if rel_vlog.startswith("verifier/")
                                else rel_vlog,
                                "candidate_causes": causes,
                                "required_discriminating_evidence": req_ev,
                            }
                        )
                        sci_counter += 1

    return {"scientific_observations": observations}


def _read_bounded_text(path: Path, max_bytes: int = 200000) -> str:
    try:
        file_size = path.stat().st_size
        if file_size <= max_bytes:
            return path.read_bytes().decode("utf-8", errors="replace")
        half = max_bytes // 2
        with path.open("rb") as f:
            head = f.read(half)
            f.seek(max(0, file_size - half))
            tail = f.read(half)
        return (
            head.decode("utf-8", errors="replace")
            + "\n... [TRUNCATED] ...\n"
            + tail.decode("utf-8", errors="replace")
        )
    except OSError:
        return ""


def _extract_match_line(text: str, match: re.Match[str]) -> str:
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    return line or match.group(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract scientific software error observations.")
    parser.add_argument("--trial-dir", required=False, type=Path, default=None, help="Path to trial directory")
    parser.add_argument("--trajectory-norm", required=False, type=Path, default=None, help="Normalized trajectory JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    norm_traj = None
    if args.trajectory_norm and args.trajectory_norm.is_file():
        norm_traj = json.loads(args.trajectory_norm.read_text(encoding="utf-8", errors="replace"))

    res = extract_scientific_errors(trial_dir=args.trial_dir, normalized_traj=norm_traj)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
