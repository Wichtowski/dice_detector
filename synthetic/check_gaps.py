#!/usr/bin/env python3
"""Check for gaps in generated synthetic renders"""

import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "generated" / "blender"


def check_gaps(output_dir: Path, verbose: bool = False) -> None:
    images_dir = output_dir / "images"
    annotations_dir = output_dir / "annotations"

    if not images_dir.exists():
        print(f"No images directory found at {images_dir}")
        return

    # Scan existing files
    pattern = re.compile(r"^render_(\d+)\.png$")
    image_only = set()
    annotation_only = set()
    complete = set()
    all_image_indices = set()

    for f in images_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            idx = int(m.group(1))
            all_image_indices.add(idx)
            ann = annotations_dir / f"render_{idx:06d}.json"
            if ann.exists():
                complete.add(idx)
            else:
                image_only.add(idx)

    # Check for orphan annotations (no image)
    if annotations_dir.exists():
        ann_pattern = re.compile(r"^render_(\d+)\.json$")
        for f in annotations_dir.iterdir():
            m = ann_pattern.match(f.name)
            if m:
                idx = int(m.group(1))
                if idx not in all_image_indices:
                    annotation_only.add(idx)

    if not complete and not image_only:
        print("No renders found.")
        return

    all_indices = complete | image_only
    max_index = max(all_indices)
    min_index = min(all_indices)

    # Find gaps
    missing = sorted(i for i in range(min_index, max_index + 1) if i not in all_indices)
    incomplete = sorted(image_only | annotation_only)

    # Summary
    print(f"Output directory: {output_dir}")
    print(f"Index range: {min_index} - {max_index}")
    print(f"Complete pairs (image + annotation): {len(complete)}")
    print(f"Total gaps (missing entirely): {len(missing)}")
    print(f"Image only (missing annotation): {len(image_only)}")
    print(f"Annotation only (missing image): {len(annotation_only)}")
    print()

    if not missing and not incomplete:
        print("No gaps found! Dataset is contiguous.")
        return

    # Show gap ranges
    if missing:
        ranges = _compress_ranges(missing)
        print(f"Missing ranges ({len(missing)} indices):")
        for start, end in ranges:
            if start == end:
                print(f"  render_{start:06d}")
            else:
                print(f"  render_{start:06d} - render_{end:06d}  ({end - start + 1} images)")

    if image_only and verbose:
        print(f"\nImage only (missing annotation):")
        for idx in sorted(image_only):
            print(f"  render_{idx:06d}")

    if annotation_only and verbose:
        print(f"\nAnnotation only (missing image):")
        for idx in sorted(annotation_only):
            print(f"  render_{idx:06d}")

    # Actionable suggestion
    total_to_fill = len(missing) + len(image_only) + len(annotation_only)
    print(f"\nTo fill all gaps: make synthetic NUM_IMAGES={total_to_fill}")


def _compress_ranges(indices: list[int]) -> list[tuple[int, int]]:
    """Compress a sorted list of integers into (start, end) ranges."""
    if not indices:
        return []
    ranges = []
    start = indices[0]
    prev = indices[0]
    for i in indices[1:]:
        if i == prev + 1:
            prev = i
        else:
            ranges.append((start, prev))
            start = i
            prev = i
    ranges.append((start, prev))
    return ranges


def main():
    parser = argparse.ArgumentParser(description="Check for gaps in synthetic renders")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT),
                        help=f"Output directory (default: {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show individual incomplete files")
    args = parser.parse_args()

    check_gaps(Path(args.output).resolve(), verbose=args.verbose)


if __name__ == "__main__":
    main()
