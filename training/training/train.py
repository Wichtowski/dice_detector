"""Training script for dice detection model."""

import argparse
import os

from .dataset import DatasetManager


def train_yolo(
    data_yaml: str,
    model: str = "yolov8n.pt",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    project: str = "runs/detect",
    name: str = "dice_detector",
):
    """Train YOLOv8 model for dice detection.

    Args:
        data_yaml: Path to data.yaml file.
        model: Base model to use.
        epochs: Number of training epochs.
        imgsz: Image size.
        batch: Batch size.
        project: Project directory.
        name: Run name.
    """
    try:
        from ultralytics import YOLO

        # Load model
        yolo = YOLO(model)

        # Train
        results = yolo.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            project=project,
            name=name,
            patience=20,
            save=True,
            plots=True,
            verbose=True,
        )

        print("\nTraining complete!")
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
):
    """Evaluate trained model.

    Args:
        model_path: Path to trained model.
        data_yaml: Path to data.yaml file.
        split: Dataset split to evaluate on.
    """
    try:
        from ultralytics import YOLO

        model = YOLO(model_path)
        results = model.val(data=data_yaml, split=split)

        print("\nEvaluation Results:")
        print(f"mAP50: {results.box.map50:.4f}")
        print(f"mAP50-95: {results.box.map:.4f}")

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
        default="yolov8n.pt",
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
        )

    elif args.action == "evaluate":
        if not os.path.exists(args.model):
            print(f"Model not found: {args.model}")
            return

        evaluate_model(args.model, args.data)

    elif args.action == "export":
        if not os.path.exists(args.model):
            print(f"Model not found: {args.model}")
            return

        export_model(args.model, args.format)


if __name__ == "__main__":
    main()
