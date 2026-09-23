#!/usr/bin/env python3
"""
Phase 4: Prompt, Task, and Verifier Contract Auditor (`scripts/audit_contract.py`)

Builds the Three-Way Contract Matrix (`Prompt <-> Verifier <-> Agent Output`)
by extracting requirements from `instruction.md`, statically inspecting
`tests/verify.py` with Python `ast` + pattern checks, checking `environment/assets/`,
and correlating with `verifier/verify.log` and agent trajectory actions.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def extract_prompt_contract(instruction_text: str, task_dir: Optional[Path]) -> Dict[str, Any]:
    # 1. Extract code-block JSON keys under "values" / "units"
    json_keys: List[str] = []
    for m in re.finditer(r"```json\s*(.*?)```", instruction_text, re.DOTALL):
        block = m.group(1)
        val_block = re.search(r'"values"\s*:\s*\{(.*?)\}', block, re.DOTALL)
        if val_block:
            for km in re.finditer(r'"([a-zA-Z0-9_]+)"\s*:', val_block.group(1)):
                k = km.group(1)
                if k not in json_keys:
                    json_keys.append(k)

    # 2. Extract mentioned input assets in `/workspace/assets/...` or `assets/...`
    asset_refs: List[str] = []
    for m in re.finditer(r"(?:/workspace/)?assets/([A-Za-z0-9_.\-/]+)", instruction_text):
        rel = m.group(1).rstrip("`.,;)")
        if rel and "." in Path(rel).name and rel not in asset_refs:
            asset_refs.append(rel)

    # Check if referenced assets exist in task_dir/environment/assets or Dockerfile
    missing_prompt_assets: List[str] = []
    if task_dir and task_dir.is_dir():
        assets_dir = task_dir / "environment" / "assets"
        dockerfile_text = (
            (task_dir / "environment" / "Dockerfile").read_text(encoding="utf-8", errors="replace")
            if (task_dir / "environment" / "Dockerfile").is_file()
            else ""
        )
        for aref in asset_refs:
            candidate = assets_dir / aref
            if not candidate.exists() and aref not in dockerfile_text:
                missing_prompt_assets.append(aref)

    # 3. Extract mentioned output filenames
    output_files: Set[str] = {"results.json"} if "results.json" in instruction_text else set()
    for m in re.finditer(
        r"`([A-Za-z0-9_.\-/]+\.(?:out|in|ener|xyz|dat|lammps|data|xml|json|csv))`",
        instruction_text,
    ):
        token = m.group(1).lstrip("/")
        if token.startswith("workspace/"):
            token = token[len("workspace/") :]
        if not token.startswith("assets/") and not token.startswith("opt/"):
            output_files.add(token)
    if "log.lammps" in instruction_text:
        output_files.add("log.lammps")

    # 4. Check whether `thermo_style` column order is explicitly specified
    specifies_thermo_columns = bool(
        re.search(r"thermo_style\s+custom\s+step\s+pe\s+lx", instruction_text, re.IGNORECASE)
    )

    return {
        "json_keys": json_keys,
        "asset_refs": asset_refs,
        "missing_prompt_assets": missing_prompt_assets,
        "output_files": sorted(output_files),
        "specifies_thermo_columns": specifies_thermo_columns,
    }


class VerifierASTVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.checked_files: List[str] = []
        self.checked_keys: List[str] = []
        self.regex_patterns: List[str] = []
        self.fail_messages: List[str] = []

    def visit_Call(self, node: ast.Call) -> Any:
        # Detect os.path.isfile(...) or os.path.join(WORKSPACE, "...")
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name == "join" and len(node.args) >= 2:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Name) and first_arg.id == "WORKSPACE":
                parts = [
                    a.value
                    for a in node.args[1:]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                if parts:
                    rel = "/".join(parts)
                    if rel not in self.checked_files:
                        self.checked_files.append(rel)

        if func_name in ("compile", "search", "match", "findall", "finditer") and node.args:
            arg0 = node.args[0]
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                self.regex_patterns.append(arg0.value)

        if func_name in ("check", "fail") and node.args:
            msg_arg = node.args[-1]
            if isinstance(msg_arg, ast.Constant) and isinstance(msg_arg.value, str):
                self.fail_messages.append(msg_arg.value)

        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> Any:
        # Detect `for fname in ("a", "b"):` or `for key in ("k1", "k2"):`
        target_name = node.target.id if isinstance(node.target, ast.Name) else ""
        if isinstance(node.iter, (ast.Tuple, ast.List)):
            items = [
                elt.value
                for elt in node.iter.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            if target_name in ("fname", "name", "f") and items:
                for it in items:
                    if it not in self.checked_files:
                        self.checked_files.append(it)
            elif target_name in ("key", "k") and items:
                for it in items:
                    if it not in self.checked_keys:
                        self.checked_keys.append(it)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        # Detect `KEYS = ("gamma_band4_eV", ...)`
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in ("KEYS", "REQUIRED_KEYS"):
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            if elt.value not in self.checked_keys:
                                self.checked_keys.append(elt.value)
        self.generic_visit(node)


def inspect_verifier_code(verify_py_path: Optional[Path]) -> Dict[str, Any]:
    if verify_py_path is None or not verify_py_path.is_file():
        return {
            "exists": False,
            "checked_files": [],
            "checked_keys": [],
            "regex_patterns": [],
            "hazards": [],
        }

    code_text = verify_py_path.read_text(encoding="utf-8", errors="replace")
    visitor = VerifierASTVisitor()
    try:
        tree = ast.parse(code_text)
        visitor.visit(tree)
    except Exception:
        pass

    hazards: List[Dict[str, str]] = []

    # Hazard 1: Namelist regex `r"&(\w+)\b(.*?)/"` truncating at first `/` inside string values
    if re.search(r'r["\']&(\(\\w\+\)|\\w\+)\\b\(\.\*\?\)/["\']', code_text):
        hazards.append(
            {
                "hazard_type": "VERIFIER_REGEX_OR_PARSER_DEFECT",
                "subtype": "namelist_slash_truncation",
                "description": (
                    "Verifier uses `re.finditer(r'&(\\w+)\\b(.*?)/', text, re.DOTALL)` to parse Fortran namelists; "
                    "any `/` inside quoted file paths (e.g. `pseudo_dir = '/workspace/assets'` or `outdir = './outdir'`) "
                    "prematurely terminates the namelist match and drops subsequent keys such as `outdir`."
                ),
            }
        )

    # Hazard 2: Scientific notation regex that omits Fortran `D`/`d` exponent (`1.23D+03`)
    for pat in visitor.regex_patterns:
        pat_without_digit_esc = pat.replace("\\d", "")
        if ("[-\\d.E+]+" in pat or "[-\\d.eE+]+" in pat) and "d" not in pat_without_digit_esc.lower():
            hazards.append(
                {
                    "hazard_type": "VERIFIER_REGEX_OR_PARSER_DEFECT",
                    "subtype": "scientific_notation_missing_d_exponent",
                    "description": f"Verifier regex `{pat}` parses floating-point numbers without Fortran `D/d` exponent support.",
                }
            )

    # Hazard 3: Implicit positional thermo column indexing (`thermo[-1].split()`)
    if "thermo[-1].split()" in code_text and "last_pe" in code_text:
        hazards.append(
            {
                "hazard_type": "VERIFIER_HIDDEN_CONTRACT",
                "subtype": "implicit_thermo_column_index",
                "description": (
                    "Verifier indexes `thermo[-1].split()[1]` assuming column 1 is `PotEng` (`pe`) and column 2 is `lx` "
                    "without parsing the `Step ...` thermo header column names."
                ),
            }
        )

    return {
        "exists": True,
        "checked_files": visitor.checked_files,
        "checked_keys": visitor.checked_keys,
        "regex_patterns": visitor.regex_patterns,
        "hazards": hazards,
    }


def audit_contract(
    task_dir: Optional[Path],
    trial_dir: Optional[Path],
    normalized_traj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    instruction_path = task_dir / "instruction.md" if task_dir else None
    verify_py_path = task_dir / "tests" / "verify.py" if task_dir else None
    refs_json_path = task_dir / "tests" / "refs.json" if task_dir else None

    instruction_text = (
        instruction_path.read_text(encoding="utf-8", errors="replace")
        if (instruction_path and instruction_path.is_file())
        else ""
    )
    prompt_info = extract_prompt_contract(instruction_text, task_dir)
    verifier_info = inspect_verifier_code(verify_py_path)

    verify_log_text = ""
    if trial_dir and (trial_dir / "verifier" / "verify.log").is_file():
        verify_log_text = (
            (trial_dir / "verifier" / "verify.log")
            .read_text(encoding="utf-8", errors="replace")
            .strip()
        )
    elif trial_dir and (trial_dir / "verifier" / "test-stdout.txt").is_file():
        verify_log_text = (
            (trial_dir / "verifier" / "test-stdout.txt")
            .read_text(encoding="utf-8", errors="replace")
            .strip()
        )

    contract_observations: List[Dict[str, Any]] = []
    verifier_observations: List[Dict[str, Any]] = []
    cid = 1

    # 1. Check missing assets referenced by Prompt
    for missing_asset in prompt_info["missing_prompt_assets"]:
        contract_observations.append(
            {
                "contract_id": f"contract:{cid}",
                "item": f"asset:{missing_asset}",
                "prompt_requirement": "provided_in_assets",
                "verifier_requirement": "required",
                "agent_output_status": "missing_in_task_environment",
                "alignment": "case_defect",
                "details": f"Prompt references asset `{missing_asset}`, which does not exist in `environment/assets/` or `Dockerfile`.",
                "source_refs": ["task:instruction.md", "task:environment/Dockerfile"],
            }
        )
        cid += 1

    # 2. Compare required files between Prompt and Verifier
    prompt_files = set(prompt_info["output_files"])
    for vfile in verifier_info["checked_files"]:
        in_prompt = vfile in prompt_files or any(
            vfile.endswith(pf) or pf.endswith(vfile) for pf in prompt_files
        )
        missing_in_verify = f"Missing: {vfile}" in verify_log_text
        status = "missing_at_verify" if missing_in_verify else "present"
        if not in_prompt:
            alignment = "verifier_hidden_requirement" if missing_in_verify else "implicit_consistent"
        else:
            alignment = "agent_mismatch" if missing_in_verify else "consistent"

        contract_observations.append(
            {
                "contract_id": f"contract:{cid}",
                "item": f"file:{vfile}",
                "prompt_requirement": "required" if in_prompt else "not_explicitly_mentioned",
                "verifier_requirement": "required",
                "agent_output_status": status,
                "alignment": alignment,
                "details": (
                    f"File `{vfile}` required by verifier; prompt_declared={in_prompt}, agent_status={status}."
                ),
                "source_refs": ["task:instruction.md", "task:tests/verify.py"],
            }
        )
        cid += 1

    # 3. Compare JSON schema keys between Prompt and Verifier
    prompt_keys = set(prompt_info["json_keys"])
    for vkey in verifier_info["checked_keys"]:
        in_prompt = (not prompt_keys) or (vkey in prompt_keys)
        missing_key = f"missing key: {vkey}" in verify_log_text
        if not in_prompt:
            alignment = "verifier_schema_mismatch"
        elif missing_key:
            alignment = "agent_mismatch"
        else:
            alignment = "consistent"
        contract_observations.append(
            {
                "contract_id": f"contract:{cid}",
                "item": f"results.json:values.{vkey}",
                "prompt_requirement": "required" if in_prompt else "absent_or_different_key",
                "verifier_requirement": "required",
                "agent_output_status": "missing" if missing_key else "present",
                "alignment": alignment,
                "details": f"JSON key `{vkey}` checked by verifier (in_prompt={in_prompt}).",
                "source_refs": ["task:instruction.md", "task:tests/verify.py"],
            }
        )
        cid += 1

    # 4. Record Verifier failure message & correlate with hazards
    if verify_log_text:
        verifier_observations.append(
            {
                "obs_id": "ver:fail_log",
                "type": "verifier_fail_message",
                "summary": verify_log_text.splitlines()[0][:240],
                "matched_text": verify_log_text[:500],
                "source_file": "verifier/verify.log",
                "source_pointer": "L1",
            }
        )

    for h_idx, h in enumerate(verifier_info["hazards"], start=1):
        sub = h["subtype"]
        triggered = False
        if sub == "namelist_slash_truncation" and (
            "outdir mismatch" in verify_log_text or "prefix mismatch" in verify_log_text
        ):
            triggered = True
            contract_observations.append(
                {
                    "contract_id": f"contract:{cid}",
                    "item": "namelist:outdir_parser",
                    "prompt_requirement": "reuse_scf_charge_density",
                    "verifier_requirement": "regex_namelist_parse",
                    "agent_output_status": "valid_namelist_with_slash_path",
                    "alignment": "verifier_defect",
                    "details": h["description"],
                    "source_refs": ["task:tests/verify.py", "verifier/verify.log"],
                }
            )
            cid += 1
        elif sub == "implicit_thermo_column_index" and (
            "!= log last line" in verify_log_text
            and not prompt_info["specifies_thermo_columns"]
        ):
            triggered = True
            contract_observations.append(
                {
                    "contract_id": f"contract:{cid}",
                    "item": "log.lammps:thermo_style_columns",
                    "prompt_requirement": "not_specified",
                    "verifier_requirement": "hardcoded_column_1_as_pe",
                    "agent_output_status": "ecoh_in_results_json_passed_ref_tolerance",
                    "alignment": "verifier_defect",
                    "details": (
                        "Agent's `results.json` `a0` and `ecoh` passed Layer 3 reference tolerance (`refs.json`), "
                        "but `verify.py` Layer 4 hardcoded `thermo[-1].split()[1]` as `pe` without checking the `Step` header columns."
                    ),
                    "source_refs": ["task:instruction.md", "task:tests/verify.py", "verifier/verify.log"],
                }
            )
            cid += 1
        elif sub == "scientific_notation_missing_d_exponent":
            # Also check if D+ or d+ appears in agent outputs or verify failure
            if re.search(r"\d+\.\d+[Dd][+-]\d+", verify_log_text):
                triggered = True
            verifier_observations.append(
                {
                    "obs_id": f"ver:hazard:{h_idx}",
                    "type": "parser_hazard",
                    "summary": h["description"],
                    "matched_text": h["subtype"],
                    "triggered": triggered,
                    "source_file": "tests/verify.py",
                    "source_pointer": "AST",
                }
            )
            continue

        verifier_observations.append(
            {
                "obs_id": f"ver:hazard:{h_idx}",
                "type": "parser_hazard" if "REGEX" in h["hazard_type"] else "implicit_column_assumption",
                "summary": h["description"],
                "matched_text": h["subtype"],
                "triggered": triggered,
                "source_file": "tests/verify.py",
                "source_pointer": "AST",
            }
        )

    return {
        "prompt_contract": prompt_info,
        "verifier_contract": verifier_info,
        "contract_observations": contract_observations,
        "verifier_observations": verifier_observations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit contract between Prompt, Verifier, and Agent output.")
    parser.add_argument("--task", required=False, type=Path, default=None, help="Path to task directory")
    parser.add_argument("--trial-dir", required=False, type=Path, default=None, help="Path to trial directory")
    parser.add_argument("--trajectory-norm", required=False, type=Path, default=None, help="Normalized trajectory JSON")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    norm_traj = None
    if args.trajectory_norm and args.trajectory_norm.is_file():
        norm_traj = json.loads(args.trajectory_norm.read_text(encoding="utf-8", errors="replace"))

    res = audit_contract(task_dir=args.task, trial_dir=args.trial_dir, normalized_traj=norm_traj)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
