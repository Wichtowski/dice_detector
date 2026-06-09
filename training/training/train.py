"""Training script for dice detection model."""

import argparse
import json
import os
from pathlib import Path

from .dataset import DatasetManager

ID_TO_NAME = {0: "D4", 1: "D6", 2: "D8", 3: "D10", 4: "D12", 5: "D20", 6: "D100"}


def train_yolo(
    data_yaml: str,
    model: str = "yolo11n.pt",
    epochs: int = 150,
    imgsz: int = 640,
    batch: int = 16,
    project: str = "runs/detect",
    name: str = "dice_detector",
    resume: bool = False,
):
    try:
        from ultralytics import YOLO

        checkpoint = Path(project) / name / "weights" / "last.pt"
        if resume and checkpoint.exists():
            print(f"Resuming from {checkpoint}")
            yolo = YOLO(str(checkpoint))
        else:
            yolo = YOLO(model)

        results = yolo.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            project=project,
            name=name,
            exist_ok=True,
            resume=resume and checkpoint.exists(),
            patience=25,
            save=True,
            save_period=10,
            plots=True,
            verbose=True,
            hsv_h=0.015,
            hsv_s=0.4,
            hsv_v=0.3,
            degrees=15.0,
            translate=0.1,
            scale=0.3,
            flipud=0.5,
            fliplr=0.5,
            mosaic=1.0,
            mixup=0.1,
        )

        print(f"\nTraining complete!")
        print(f"Best model saved to: {results.save_dir}/weights/best.pt")

        return results

    except ImportError:
        print("Error: ultralytics package not installed")
        print("Install with: pip install ultralytics")
        return None


def evaluate_model(
    model_path: str,
    data_yaml: str,
    split: str = "test",
    output_dir: str | None = None,
):
    try:
        from ultralytics import YOLO

        model = YOLO(model_path)
        results = model.val(data=data_yaml, split=split, plots=True)

        print(f"\nTest Results:")
        print(f"  mAP50:     {results.box.map50:.4f}")
        print(f"  mAP50-95:  {results.box.map:.4f}")
        print(f"  Precision: {results.box.mp:.4f}")
        print(f"  Recall:    {results.box.mr:.4f}")

        per_class = {}
        for class_id, ap in enumerate(results.box.maps):
            class_name = ID_TO_NAME.get(class_id, f"class_{class_id}")
            per_class[class_name] = float(ap)

        print(f"\nPer-class mAP50-95:")
        for name, ap in per_class.items():
            print(f"  {name}: {ap:.4f}")

        worst = min(per_class, key=per_class.get)
        print(f"\nWeakest class: {worst} ({per_class[worst]:.4f})")

        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            with open(out / "per_class_test_ap.json", "w") as f:
                json.dump(per_class, f, indent=2)
            with open(out / "eval_summary.json", "w") as f:
                json.dump({
                    "map50": float(results.box.map50),
                    "map50_95": float(results.box.map),
                    "precision": float(results.box.mp),
                    "recall": float(results.box.mr),
                    "per_class_ap": per_class,
                }, f, indent=2)

        return results

    except ImportError:
        print("Error: ultralytics package not installed")
        return None


def export_model(
    model_path: str,
    format: str = "onnx",
):
    """Export model to different format.

    Args:
        model_path: Path to trained model.
        format: Export format (onnx, torchscript, etc.).
    """
    try:
        from ultralytics import YOLO

        model = YOLO(model_path)
        model.export(format=format)

        print(f"Model exported to {format} format")

    except ImportError:
        print("Error: ultralytics package not installed")


def prepare_dataset():
    """Prepare dataset for training."""
    dataset = DatasetManager()
    stats = dataset.get_statistics()

    print("Dataset Statistics:")
    print(f"  Total images: {stats['total_images']}")
    print(f"  Total annotations: {stats['total_annotations']}")
    print(f"  By class: {stats['by_class']}")
    print(f"  By split: {stats['by_split']}")

    if stats["total_images"] < 50:
        print("\nWarning: Dataset is very small. Consider adding more samples.")
        print("Minimum recommended: 100+ images per class")
        return False

    # Export to YOLO format
    export_dir = "data/yolo_export"
    print(f"\nExporting dataset to {export_dir}...")
    dataset.export_yolo_format(export_dir)

    print("Dataset exported successfully!")
    print(f"Data YAML: {export_dir}/data.yaml")

    return True


def main():
    """Main training entry point."""
    parser = argparse.ArgumentParser(description="Train dice detection model")
    parser.add_argument(
        "--action",
        choices=["prepare", "train", "evaluate", "export"],
        default="train",
        help="Action to perform",
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/yolo_export/data.yaml",
        help="Path to data.yaml",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolo11n.pt",
        help="Base model or trained model path",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Image size",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="onnx",
        help="Export format",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from last checkpoint",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory for evaluation artifacts",
    )

    args = parser.parse_args()

    if args.action == "prepare":
        prepare_dataset()

    elif args.action == "train":
        if not os.path.exists(args.data):
            print(f"Data file not found: {args.data}")
            print("Run with --action prepare first")
            return

        train_yolo(
            data_yaml=args.data,
            model=args.model,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            resume=args.resume,
        )

    elif args.action == "evaluate":
        if not os.path.exists(args.model):
            print(f"Model not found: {args.model}")
            return

        evaluate_model(args.model, args.data, output_dir=args.output)

    elif args.action == "export":
        if not os.path.exists(args.model):
            print(f"Model not found: {args.model}")
            return

        export_model(args.model, args.format)


if __name__ == "__main__":
    main()
