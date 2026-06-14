#!/usr/bin/env python3
"""Convert JSON annotations to YOLO-format .txt labels.

Usage:
    python synthetic/convert_annotations.py [--data-dir DATA_DIR]

Reads JSON annotations from <data-dir>/annotations/ and writes
YOLO labels to <data-dir>/labels/. Existing labels are overwritten.

Default data dir: data/blender_synthetic
"""

import argparse
import json
from pathlib import Path

DICE_TYPE_TO_CLASS = {
    "D4": 0,
    "D6": 1,
    "D8": 2,
    "D10": 3,
    "D12": 4,
    "D20": 5,
    "D100": 6,
}


def convert_annotation(ann_path: Path) -> list[str]:
    """Convert a single JSON annotation file to YOLO label lines."""
    with open(ann_path) as f:
        data = json.load(f)

    img_w = data["image_width"]
    img_h = data["image_height"]
    lines = []

    for die in data["dice"]:
        class_id = DICE_TYPE_TO_CLASS.get(die["dice_type"])
        if class_id is None:
            continue

        bbox = die["bbox"]
        x_center = (bbox["x"] + bbox["width"] / 2) / img_w
        y_center = (bbox["y"] + bbox["height"] / 2) / img_h
        width = bbox["width"] / img_w
        height = bbox["height"] / img_h

        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        width = max(0.001, min(1.0, width))
        height = max(0.001, min(1.0, height))

        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

    return lines


def main():
    parser = argparse.ArgumentParser(description="Convert JSON annotations to YOLO labels")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/generated/blender"),
        help="Root data directory with annotations/ and images/ subdirs",
    )
    args = parser.parse_args()

    ann_dir = args.data_dir / "annotations"
    labels_dir = args.data_dir / "labels"

    if not ann_dir.exists():
        print(f"Error: annotations directory not found: {ann_dir}")
        raise SystemExit(1)

    labels_dir.mkdir(parents=True, exist_ok=True)

    ann_files = sorted(ann_dir.glob("*.json"))
    print(f"Found {len(ann_files)} annotation files in {ann_dir}")

    converted = 0
    for ann_path in ann_files:
        lines = convert_annotation(ann_path)
        label_path = labels_dir / f"{ann_path.stem}.txt"
        label_path.write_text("\n".join(lines) + "\n" if lines else "")
        converted += 1

    print(f"Wrote {converted} YOLO label files to {labels_dir}")


if __name__ == "__main__":
    main()
