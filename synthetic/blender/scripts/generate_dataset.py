#!/usr/bin/env python3
"""Blender synthetic dice dataset generator.

Run from Blender:
    blender dices.blend --background --python generate_dataset.py -- --config config.json

Or open the .blend file and run from Blender's scripting workspace.
"""

import argparse
import json
import sys
from pathlib import Path

script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from dice_generator import BlenderDiceGenerator, GeneratorConfig



def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    parser = argparse.ArgumentParser(description="Generate synthetic dice dataset with Blender")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--output", type=str, help="Output directory")
    parser.add_argument("--num-images", type=int, help="Number of images to generate")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--start-index", type=int, default=0, help="Starting image index (for parallel workers)")
    parser.add_argument("--worker-id", type=int, default=0, help="Worker ID (for parallel generation)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing images (default: skip)")
    parser.add_argument("--add-annotated-images", action="store_true",
                        help="Create annotated images with bounding boxes drawn")
    parser.add_argument("--indices", type=str, default=None,
                        help="Comma-separated list of specific image indices to generate")

    return parser.parse_args(argv)


def main():
    args = parse_args()

    config = {}
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
        else:
            print(f"Warning: Config file not found: {args.config}")

    if args.output:
        config["output_dir"] = args.output
    if args.num_images is not None:
        config["num_images"] = args.num_images
    if args.seed is not None:
        config["random_seed"] = args.seed
    if args.start_index is not None:
        config["start_index"] = args.start_index
    if args.worker_id is not None:
        config["worker_id"] = args.worker_id
    if args.overwrite:
        config["skip_existing"] = False
    if args.add_annotated_images:
        config["create_annotated_images"] = True
    if args.indices:
        config["indices"] = [int(i) for i in args.indices.split(",")]

    gen_config = GeneratorConfig.from_dict(config)

    generator = BlenderDiceGenerator(gen_config)
    generator.generate_dataset()


if __name__ == "__main__":
    main()
