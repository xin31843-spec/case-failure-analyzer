#!/usr/bin/env python3
"""
Safe Skill Packaging & Export Tool (`scripts/export_skill.py`)

Exports a clean production skill directory (SKILL.md, agents/, scripts/, references/)
to a specified target destination with strict path safety guards and non-destructive sync:
  1. Validates destination safety:
     - Refuses root filesystem `/` and critical system directories (`/etc`, `/usr`, etc.).
     - Refuses user home directory root (`Path.home()`).
     - Refuses current repository root or its parent.
  2. Non-destructive file synchronization:
     - Copies SKILL.md, agents/, scripts/, and references/.
     - Excludes `__pycache__`, `*.pyc`, `.DS_Store`, etc.
     - Never performs blanket deletion (`rsync --delete`) on unmanaged user files.
     - Tracks exported files via `.cfa_export_manifest.json` for managed cleanup if `--clean` is given.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

MANAGED_COMPONENTS = ["SKILL.md", "agents", "scripts", "references"]

EXCLUDED_NAMES = {
    "__pycache__",
    ".DS_Store",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
}

EXCLUDED_EXTENSIONS = {".pyc", ".pyo", ".tmp", ".swp"}

RAW_SYSTEM_DIRS = {
    "/",
    "/usr",
    "/etc",
    "/bin",
    "/sbin",
    "/var",
    "/dev",
    "/sys",
    "/proc",
    "/System",
    "/Library",
    "/Applications",
    "/private/etc",
    "/private/var",
}

SYSTEM_DIRECTORIES = {
    Path(p).resolve() for p in RAW_SYSTEM_DIRS if Path(p).exists()
} | {Path("/")}

MANIFEST_FILENAME = ".cfa_export_manifest.json"


class ExportSafetyError(ValueError):
    """Raised when destination path violates safety constraints."""


def validate_destination(dest_path_str: str, repo_root: Path = REPO_ROOT) -> Path:
    """
    Validates destination path against critical safety rules:
      - Cannot be empty
      - Cannot be root or system directory
      - Cannot be home directory root
      - Cannot be current repository root or its parent
    """
    if not dest_path_str or not dest_path_str.strip():
        raise ExportSafetyError("Destination path cannot be empty.")

    dest = Path(dest_path_str).expanduser().resolve()
    resolved_root = repo_root.resolve()
    user_home = Path.home().resolve()

    # 1. System root & critical directories check
    if dest in SYSTEM_DIRECTORIES:
        raise ExportSafetyError(f"Refusing to export to system directory: {dest}")

    for sys_dir in SYSTEM_DIRECTORIES:
        if sys_dir != Path("/") and dest == sys_dir:
            raise ExportSafetyError(f"Refusing to export to system directory: {dest}")

    # 2. User home root check
    if dest == user_home:
        raise ExportSafetyError(f"Refusing to export directly to user home directory: {dest}")

    # 3. Current repository check
    if dest == resolved_root:
        raise ExportSafetyError(
            f"Refusing to export into the source repository root itself: {dest}"
        )
    if dest == resolved_root.parent:
        raise ExportSafetyError(
            f"Refusing to export into the parent directory of source repository: {dest}"
        )

    return dest


def should_include_file(p: Path) -> bool:
    for part in p.parts:
        if part in EXCLUDED_NAMES:
            return False
    if p.suffix in EXCLUDED_EXTENSIONS:
        return False
    if p.name.startswith("._"):
        return False
    return True


def collect_export_files(source_root: Path = REPO_ROOT) -> Dict[str, Path]:
    """
    Collects all files belonging to the skill distribution:
      - SKILL.md
      - agents/**
      - scripts/**
      - references/**
    Returns mapping of rel_path -> src_path.
    """
    files: Dict[str, Path] = {}

    skill_md = source_root / "SKILL.md"
    if skill_md.is_file():
        files["SKILL.md"] = skill_md

    for comp in ["agents", "scripts", "references"]:
        comp_dir = source_root / comp
        if not comp_dir.is_dir():
            continue
        for root, dirs, filenames in os.walk(comp_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_NAMES]
            for fn in filenames:
                src_file = Path(root) / fn
                if should_include_file(src_file):
                    rel_p = str(src_file.relative_to(source_root))
                    files[rel_p] = src_file

    return files


def export_skill(
    dest_path: Path,
    source_root: Path = REPO_ROOT,
    clean: bool = False,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    Performs non-destructive export to dest_path.
    Returns (num_copied_files, num_cleaned_files).
    """
    dest = validate_destination(str(dest_path), repo_root=source_root)
    files_to_export = collect_export_files(source_root)

    manifest_file = dest / MANIFEST_FILENAME
    old_managed: Set[str] = set()
    if manifest_file.is_file():
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            old_managed = set(manifest_data.get("files", []))
        except (json.JSONDecodeError, OSError):
            old_managed = set()

    cleaned_count = 0
    if clean and old_managed:
        current_relpaths = set(files_to_export.keys())
        stale_files = old_managed - current_relpaths
        for stale in stale_files:
            target_stale = dest / stale
            if target_stale.is_file():
                if not dry_run:
                    target_stale.unlink(missing_ok=True)
                cleaned_count += 1

    copied_count = 0
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    new_managed: List[str] = []
    for rel_path, src_path in sorted(files_to_export.items()):
        target_file = dest / rel_path
        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, target_file)
        new_managed.append(rel_path)
        copied_count += 1

    if not dry_run:
        manifest_payload = {
            "name": "case-failure-analyzer",
            "files": sorted(new_managed),
        }
        manifest_file.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return copied_count, cleaned_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe export tool for case-failure-analyzer skill."
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Target destination directory path for the exported skill",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Prune obsolete previously-exported files tracked in .cfa_export_manifest.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview export without making filesystem modifications",
    )
    args = parser.parse_args()

    try:
        dest = validate_destination(args.dest)
    except ExportSafetyError as err:
        print(f"EXPORT SAFETY ERROR: {err}", file=sys.stderr)
        sys.exit(2)

    try:
        copied, cleaned = export_skill(dest, clean=args.clean, dry_run=args.dry_run)
        print(
            f"export-skill: successfully exported {copied} files to {dest} "
            f"(cleaned: {cleaned} stale files, dry_run: {args.dry_run})"
        )
    except Exception as err:
        print(f"EXPORT FAILED: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
