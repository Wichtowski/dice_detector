#!/usr/bin/env python3
"""Wrapper script to launch Blender synthetic dice generation.

Usage:
    python synthetic/generate.py --num-images 10
    python synthetic/generate.py --num-images 100 --seed 42 --output data/my_dataset
    python synthetic/generate.py --config synthetic/blender/configs/default_blender_generation.json
    python synthetic/generate.py --blender-path /usr/local/bin/blender --blend-file my_scene.blend
    python synthetic/generate.py --num-images 100 --workers 4
"""

import argparse
import os
import re
import signal
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BLEND_FILE = PROJECT_ROOT / "blender" / "dices.blend"
DEFAULT_CONFIG = PROJECT_ROOT / "synthetic" / "blender" / "configs" / "default_blender_generation.json"
GENERATOR_SCRIPT = PROJECT_ROOT / "synthetic" / "blender" / "scripts" / "generate_dataset.py"


def _find_missing_indices(output_dir: Path, num_needed: int) -> list[int]:
    """Scan output directory and return missing image indices (gaps), then append new ones if needed."""
    images_dir = output_dir / "images"
    annotations_dir = output_dir / "annotations"

    existing = set()
    if images_dir.exists():
        pattern = re.compile(r"^render_(\d+)\.png$")
        for f in images_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                # Only count as existing if both image and annotation are present
                idx = int(m.group(1))
                ann = annotations_dir / f"render_{idx:06d}.json"
                if ann.exists():
                    existing.add(idx)

    # Find gaps in [0, max_index]
    max_index = max(existing) if existing else -1
    missing = []
    for i in range(max_index + 1):
        if i not in existing:
            missing.append(i)

    # If we still need more, continue after max_index
    next_new = max_index + 1
    while len(missing) < num_needed:
        missing.append(next_new)
        next_new += 1

    return missing[:num_needed]


def find_blender() -> str | None:
    """Find the Blender executable."""
    blender = shutil.which("blender")
    if blender:
        return blender

    # Common install locations
    common_paths = [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/snap/bin/blender",
        os.path.expanduser("~/blender/blender"),
    ]
    for p in common_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic dice dataset using Blender",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --num-images 1                     Generate 1 test image
  %(prog)s --num-images 100 --seed 42         Generate 100 images with fixed seed
  %(prog)s --num-images 100 --workers 4       Generate 100 images using 4 parallel Blender workers
  %(prog)s --config my_config.json            Use custom config file
  %(prog)s --no-background                    Run Blender with GUI (for debugging)
        """,
    )

    parser.add_argument("--num-images", "-n", type=int, help="Number of images to generate")
    parser.add_argument("--seed", "-s", type=int, help="Random seed for reproducibility")
    parser.add_argument("--output", "-o", type=str, help="Output directory")
    parser.add_argument("--config", "-c", type=str, help="Path to config JSON file")
    parser.add_argument("--workers", "-w", type=int, default=1,
                        help="Number of parallel Blender workers (must be even, >= 2)")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Global starting index (resume from this image number)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing images (default: skip existing)")

    parser.add_argument("--blend-file", type=str, default=str(DEFAULT_BLEND_FILE),
                        help=f"Path to .blend file (default: {DEFAULT_BLEND_FILE.relative_to(PROJECT_ROOT)})")
    parser.add_argument("--blender-path", type=str, help="Path to Blender executable")
    parser.add_argument("--no-background", action="store_true",
                        help="Run Blender with GUI (useful for debugging)")
    parser.add_argument("--add-annotated-images", action="store_true",
                        help="Create annotated images with bounding boxes drawn")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the command without executing it")

    args = parser.parse_args()

    # Validate workers
    if args.workers > 1 and args.workers % 2 != 0:
        print(f"Error: --workers must be even (got {args.workers})", file=sys.stderr)
        sys.exit(1)

    if args.workers > 1 and args.no_background:
        print("Error: --workers > 1 is not compatible with --no-background", file=sys.stderr)
        sys.exit(1)

    # Find Blender
    blender = args.blender_path or find_blender()
    if not blender:
        print("Error: Blender not found. Install Blender or use --blender-path.", file=sys.stderr)
        sys.exit(1)

    # Validate paths
    blend_file = Path(args.blend_file)
    if not blend_file.exists():
        print(f"Error: Blend file not found: {blend_file}", file=sys.stderr)
        sys.exit(1)

    if not GENERATOR_SCRIPT.exists():
        print(f"Error: Generator script not found: {GENERATOR_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    num_images = args.num_images or 100

    # Compute indices to generate: fill gaps first, then append new ones
    if args.start_from == 0 and not args.overwrite:
        output_dir = Path(args.output).resolve() if args.output else PROJECT_ROOT / "data" / "generated" / "blender"
        indices = _find_missing_indices(output_dir, num_images)
        # Count how many are gap-fills vs new appends
        max_existing = max(indices) - num_images + len(indices) if indices else -1
        gaps = [i for i in indices if i <= max_existing]
        if gaps:
            print(f"Found {len(gaps)} gaps to fill, plus {num_images - len(gaps)} new images")
        else:
            start = indices[0] if indices else 0
            print(f"No gaps found, generating from index {start}")
        args._indices = indices
    else:
        args._indices = list(range(args.start_from, args.start_from + num_images))

    if args.workers > 1:
        _run_parallel(args, blender, blend_file, num_images)
    else:
        cmd = _build_cmd(blender, blend_file, args, num_images, indices=args._indices, worker_id=0)
        _print_cmd(cmd)
        if args.dry_run:
            return
        try:
            result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
            sys.exit(result.returncode)
        except KeyboardInterrupt:
            print("\nGeneration interrupted.")
            sys.exit(130)


def _build_cmd(
    blender: str,
    blend_file: Path,
    args: argparse.Namespace,
    num_images: int,
    indices: list[int] | None = None,
    worker_id: int = 0,
) -> list[str]:
    """Build the Blender command for a single worker."""
    cmd = [blender, str(blend_file)]

    if not args.no_background:
        cmd.append("--background")

    cmd.extend(["--python", str(GENERATOR_SCRIPT), "--"])

    # Config file
    if args.config:
        cmd.extend(["--config", str(Path(args.config).resolve())])
    elif DEFAULT_CONFIG.exists():
        cmd.extend(["--config", str(DEFAULT_CONFIG)])

    cmd.extend(["--num-images", str(num_images)])

    if args.seed is not None:
        # Each worker gets a unique seed derived from the base seed
        cmd.extend(["--seed", str(args.seed + worker_id)])

    if args.output:
        cmd.extend(["--output", str(Path(args.output).resolve())])

    if indices is not None:
        cmd.extend(["--indices", ",".join(str(i) for i in indices)])

    cmd.extend(["--worker-id", str(worker_id)])

    if args.overwrite:
        cmd.append("--overwrite")

    if args.add_annotated_images:
        cmd.append("--add-annotated-images")

    return cmd


def _print_cmd(cmd: list[str]):
    """Print a command for display."""
    print(f"Running: {' '.join(cmd)}\n")


def _run_parallel(args: argparse.Namespace, blender: str, blend_file: Path, num_images: int):
    """Run multiple Blender workers in parallel."""
    workers = args.workers

    print(f"Parallel generation: {num_images} images across {workers} workers")
    if not args.overwrite:
        print(f"  Skipping existing images")
    print()

    # Build commands for each worker
    cmds = []
    all_indices = args._indices
    chunk_size = len(all_indices) // workers
    remainder = len(all_indices) % workers
    offset = 0
    for w in range(workers):
        chunk = chunk_size + (1 if w < remainder else 0)
        worker_indices = all_indices[offset:offset + chunk]
        cmd = _build_cmd(blender, blend_file, args, chunk, indices=worker_indices, worker_id=w)
        cmds.append((cmd, w))
        print(f"  Worker {w}: {chunk} images (indices: {worker_indices[0]}..{worker_indices[-1]})")
        offset += chunk

    if args.dry_run:
        print()
        for cmd, w in cmds:
            print(f"Worker {w}: {' '.join(cmd)}")
        return

    print()

    # Resolve output dir for PID file
    output_dir = Path(args.output).resolve() if args.output else PROJECT_ROOT / "data" / "generated" / "blender"
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    pid_file = logs_dir / "workers.pid"

    # Launch all workers with Popen
    processes: dict[int, subprocess.Popen] = {}
    try:
        for cmd, w in cmds:
            proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
            processes[w] = proc
            print(f"  Worker {w} started (PID {proc.pid})")

        # Write PID file
        with open(pid_file, "w") as f:
            f.write(f"# Blender workers started at {datetime.now().isoformat()}\n")
            f.write(f"# Kill all: kill {' '.join(str(p.pid) for p in processes.values())}\n")
            for w, proc in processes.items():
                f.write(f"{w}:{proc.pid}\n")
        print(f"\n  PIDs saved to {pid_file}")
        print(f"  Kill all workers: kill {' '.join(str(p.pid) for p in processes.values())}\n")

        # Wait for all workers to finish
        results = {}
        remaining = set(processes.keys())
        while remaining:
            for w in list(remaining):
                retcode = processes[w].poll()
                if retcode is not None:
                    remaining.discard(w)
                    results[w] = retcode
                    status = "OK" if retcode == 0 else f"FAILED (exit {retcode})"
                    print(f"Worker {w} (PID {processes[w].pid}) finished: {status}")
            if remaining:
                # Brief sleep to avoid busy-waiting — use first remaining process
                try:
                    next_w = next(iter(remaining))
                    processes[next_w].wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

        # Summary
        failed = [w for w, rc in results.items() if rc != 0]
        if failed:
            print(f"\n{len(failed)}/{workers} workers failed: {failed}")
            sys.exit(1)
        else:
            print(f"\nAll {workers} workers completed successfully.")

    except KeyboardInterrupt:
        print("\nGeneration interrupted — killing workers...")
        for w, proc in processes.items():
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                print(f"  Sent SIGINT to worker {w} (PID {proc.pid})")
        # Give them a moment to exit gracefully
        for w, proc in processes.items():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  Killed worker {w} (PID {proc.pid})")
        sys.exit(130)
    finally:
        # Clean up PID file
        if pid_file.exists():
            pid_file.unlink()


if __name__ == "__main__":
    main()
