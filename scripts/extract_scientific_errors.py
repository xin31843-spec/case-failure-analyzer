#!/usr/bin/env python3
"""
Phase 5: Scientific Software Error Knowledge Layer (`scripts/extract_scientific_errors.py`)

Loads the single-source-of-truth error registry from `references/error-families.json`
and runs deterministic error-family adapters across CP2K, Quantum ESPRESSO, LAMMPS,
xTB, ASE, and RDKit over trajectory observations and verifier logs.
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
        return {}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def build_scientific_adapters(
    registry_path: Path = REGISTRY_PATH,
) -> List[AdapterEntry]:
    reg = load_error_family_registry(registry_path)
    adapters: List[AdapterEntry] = []
    for software, families in reg.items():
        for family_name, spec in families.items():
            if spec.get("status") != "implemented":
                continue
            patterns = spec.get("patterns") or []
            if not patterns:
                continue
            combined = "(?:" + "|".join(patterns) + ")"
            compiled = re.compile(combined, re.IGNORECASE)
            aliases = spec.get("aliases") or []
            causes = spec.get("candidate_causes") or []
            req_ev = spec.get("required_discriminating_evidence") or []
            adapters.append((software, family_name, aliases, compiled, causes, req_ev))
    return adapters


SCIENTIFIC_ADAPTERS: List[AdapterEntry] = build_scientific_adapters()


def extract_scientific_errors(
    trial_dir: Optional[Path],
    normalized_traj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observations: List[Dict[str, Any]] = []
    seen = set()
    sci_counter = 1

    # 1. Scan trajectory events
    if normalized_traj:
        for ev in normalized_traj.get("events") or []:
            text = f"{ev.get('command') or ''}\n{ev.get('observation') or ''}"
            ev_id = ev.get("event_id", "trajectory:unknown")
            for sw, family, aliases, pattern, causes, req_ev in SCIENTIFIC_ADAPTERS:
                m = pattern.search(text)
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
                            "matched_text": m.group(0)[:240],
                            "source_ref": ev_id,
                            "candidate_causes": causes,
                            "required_discriminating_evidence": req_ev,
                        }
                    )
                    sci_counter += 1

    # 2. Scan verifier/verify.log
    if trial_dir and (trial_dir / "verifier" / "verify.log").is_file():
        vlog = (trial_dir / "verifier" / "verify.log").read_text(encoding="utf-8", errors="replace")
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
                        "matched_text": vlog.splitlines()[0][:240] if vlog.splitlines() else m.group(0),
                        "source_ref": "verifier/verify.log",
                        "candidate_causes": causes,
                        "required_discriminating_evidence": req_ev,
                    }
                )
                sci_counter += 1

    return {"scientific_observations": observations}


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
