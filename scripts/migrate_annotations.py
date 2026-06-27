"""Migrate old annotation JSON files to the current schema.

The annotation schema changed:
  * ``orientation_degrees`` and ``has_6_9_marker`` were removed from each die.
  * ``is_d100_percentile`` was removed.
  * The ``D100_TENS`` and ``D100_ONES`` dice types were consolidated into a
    single ``D100`` type.
  * ``is_6_or_9_value`` / ``has_special_symbol`` are now computed fields.

This script rewrites each file by validating it through the current
``ImageAnnotation`` model, which drops obsolete keys and regenerates computed
fields. Obsolete dice-type strings are normalised before validation so the
files load cleanly.

Usage:
    uv run python scripts/migrate_annotations.py [PATHS ...] [--dry-run] [--no-backup]

PATHS may be JSON files or directories (searched recursively). When omitted,
``data/web/annotations`` is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dice_detector.models.ml import ImageAnnotation

# Obsolete dice-type strings -> current equivalent.
DICE_TYPE_RENAMES = {
    "D100_TENS": "D100",
    "D100_ONES": "D100",
}

# Per-die keys that no longer exist in the schema (informational only; the
# model already ignores unknown keys, but we report when they are present).
REMOVED_DIE_KEYS = (
    "orientation_degrees",
    "has_6_9_marker",
    "is_d100_percentile",
)


def normalize_raw(data: dict) -> tuple[dict, list[str]]:
    """Apply non-model fixups (e.g. enum renames) and report what changed."""
    changes: list[str] = []
    for die in data.get("dice", []):
        old_type = die.get("dice_type")
        if old_type in DICE_TYPE_RENAMES:
            die["dice_type"] = DICE_TYPE_RENAMES[old_type]
            changes.append(f"{old_type} -> {die['dice_type']}")
        for key in REMOVED_DIE_KEYS:
            if key in die:
                changes.append(f"dropped {key}")
    return data, changes


def migrate_file(path: Path, dry_run: bool, backup: bool) -> bool:
    """Migrate a single file. Returns True if it was (or would be) changed."""
    try:
        original_text = path.read_text()
        raw = json.loads(original_text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  SKIP {path}: cannot read ({exc})")
        return False

    raw, changes = normalize_raw(raw)

    try:
        annotation = ImageAnnotation.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - report and continue
        print(f"  SKIP {path}: validation failed ({exc})")
        return False

    new_text = annotation.model_dump_json(indent=2) + "\n"
    if new_text == original_text:
        return False

    summary = ", ".join(dict.fromkeys(changes)) or "schema normalized"
    print(f"  {'WOULD UPDATE' if dry_run else 'UPDATED'} {path}: {summary}")

    if not dry_run:
        if backup:
            path.with_suffix(path.suffix + ".bak").write_text(original_text)
        path.write_text(new_text)
    return True


def collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.json")))
        elif p.suffix == ".json":
            files.append(p)
        else:
            print(f"  SKIP {p}: not a JSON file or directory")
    # Never migrate our own backups.
    return [f for f in files if not f.name.endswith(".json.bak")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("data/web/annotations")],
        help="Annotation files or directories (default: data/web/annotations)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not write .bak copies of modified files",
    )
    args = parser.parse_args()

    files = collect_files(args.paths)
    if not files:
        print("No annotation files found.")
        return 0

    print(f"Scanning {len(files)} annotation file(s)...")
    changed = 0
    for path in files:
        if migrate_file(path, dry_run=args.dry_run, backup=not args.no_backup):
            changed += 1

    verb = "would be updated" if args.dry_run else "updated"
    print(f"\nDone. {changed} file(s) {verb}, {len(files) - changed} already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
