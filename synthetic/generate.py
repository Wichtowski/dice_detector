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

    if args.workers > 1:
        _run_parallel(args, blender, blend_file, num_images)
    else:
        cmd = _build_cmd(blender, blend_file, args, num_images, start_index=args.start_from, worker_id=0)
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
    start_index: int = 0,
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

    cmd.extend(["--start-index", str(start_index)])
    cmd.extend(["--worker-id", str(worker_id)])

    if args.overwrite:
        cmd.append("--overwrite")

    return cmd


def _print_cmd(cmd: list[str]):
    """Print a command for display."""
    print(f"Running: {' '.join(cmd)}\n")


def _run_parallel(args: argparse.Namespace, blender: str, blend_file: Path, num_images: int):
    """Run multiple Blender workers in parallel."""
    workers = args.workers
    images_per_worker = num_images // workers
    remainder = num_images % workers

    print(f"Parallel generation: {num_images} images across {workers} workers")
    print(f"  {images_per_worker} images/worker" + (f" (+1 for first {remainder})" if remainder else ""))
    if args.start_from > 0:
        print(f"  Starting from index {args.start_from}")
    if not args.overwrite:
        print(f"  Skipping existing images")
    print()

    # Build commands for each worker
    cmds = []
    start = args.start_from
    for w in range(workers):
        chunk = images_per_worker + (1 if w < remainder else 0)
        cmd = _build_cmd(blender, blend_file, args, chunk, start_index=start, worker_id=w)
        cmds.append((cmd, w))
        print(f"  Worker {w}: images [{start}..{start + chunk - 1}]")
        start += chunk

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
