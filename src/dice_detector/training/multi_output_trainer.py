import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from dice_detector.models import (
    ConfusionMatrixData,
    DiceType,
    EvaluationMetrics,
    EvaluationReport,
)
from dice_detector.training.multi_output_dataset import MultiOutputDatasetManager


class MultiOutputTrainer:
    def __init__(
        self,
        dataset_dir: str = "data/dataset_v2",
        output_dir: str = "runs/multi_output",
    ):
        self.dataset = MultiOutputDatasetManager(dataset_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_detection_data(self, export_dir: str | None = None) -> str:
        export_path = Path(export_dir or self.output_dir / "detection_data")
        self.dataset.export_yolo_detection(str(export_path))
        return str(export_path / "data.yaml")

    def prepare_recognition_data(self, export_dir: str | None = None) -> str:
        export_path = Path(export_dir or self.output_dir / "recognition_data")
        self.dataset.export_recognition_crops(str(export_path))
        return str(export_path)

    def train_detection_model(
        self,
        data_yaml: str,
        base_model: str = "yolo26n.pt",
        epochs: int = 100,
        imgsz: int = 640,
        batch: int = 16,
        name: str = "dice_detector",
    ) -> str | None:
        try:
            from ultralytics import YOLO

            model = YOLO(base_model)
            results = model.train(
                data=data_yaml,
                epochs=epochs,
                imgsz=imgsz,
                batch=batch,
                project=str(self.output_dir / "detection"),
                name=name,
                patience=20,
                save=True,
                plots=True,
                verbose=True,
            )

            best_model = results.save_dir / "weights" / "best.pt"
            print(f"Detection model trained: {best_model}")
            return str(best_model)

        except ImportError:
            print("Error: ultralytics package not installed")
            return None
        except Exception as e:
            print(f"Training failed: {e}")
            return None

    def train_recognition_model(
        self,
        data_dir: str,
        epochs: int = 50,
        batch: int = 32,
        name: str = "dice_recognizer",
    ) -> str | None:
        try:
            import torch
            import torch.nn as nn
            from torch.utils.data import DataLoader

            train_loader = self._create_recognition_dataloader(data_dir, "train", batch)
            val_loader = self._create_recognition_dataloader(data_dir, "val", batch)

            if train_loader is None:
                print("No training data found")
                return None

            model = self._create_recognition_model()
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=epochs
            )

            best_val_acc = 0.0
            best_model_path = self.output_dir / "recognition" / name / "best.pt"
            best_model_path.parent.mkdir(parents=True, exist_ok=True)

            for epoch in range(epochs):
                model.train()
                train_loss = 0.0
                for batch_data in train_loader:
                    loss = self._train_step(model, batch_data, optimizer)
                    train_loss += loss

                model.eval()
                val_acc = self._validate(model, val_loader)

                scheduler.step()

                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    torch.save(model.state_dict(), best_model_path)

                if (epoch + 1) % 10 == 0:
                    print(f"Epoch {epoch + 1}/{epochs} - "
                          f"Loss: {train_loss:.4f}, Val Acc: {val_acc:.4f}")

            print(f"Recognition model trained: {best_model_path}")
            return str(best_model_path)

        except ImportError as e:
            print(f"Error: Required package not installed: {e}")
            return None
        except Exception as e:
            print(f"Training failed: {e}")
            return None

    def _create_recognition_dataloader(self, data_dir: str, split: str, batch_size: int):
        try:
            import torch
            from torch.utils.data import Dataset, DataLoader
            import cv2
            import numpy as np

            class RecognitionDataset(Dataset):
                def __init__(self, data_dir: str, split: str):
                    self.crops_dir = Path(data_dir) / "crops" / split
                    self.annotations_dir = Path(data_dir) / "annotations" / split
                    self.samples = list(self.crops_dir.glob("*.jpg"))

                def __len__(self):
                    return len(self.samples)

                def __getitem__(self, idx):
                    crop_path = self.samples[idx]
                    ann_path = self.annotations_dir / f"{crop_path.stem}.json"

                    image = cv2.imread(str(crop_path))
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    image = cv2.resize(image, (64, 64))
                    image = image.astype(np.float32) / 255.0
                    image = np.transpose(image, (2, 0, 1))

                    with open(ann_path, "r") as f:
                        ann = json.load(f)

                    return {
                        "image": torch.tensor(image),
                        "dice_type": ann.get("dice_type", "UNKNOWN"),
                        "value": ann.get("value", 0),
                        "orientation": (ann.get("orientation_degrees", 0) or 0) / 360.0,
                    }

            dataset = RecognitionDataset(data_dir, split)
            if len(dataset) == 0:
                return None

            return DataLoader(
                dataset,
                batch_size=batch_size,
                shuffle=(split == "train"),
                num_workers=4,
            )

        except Exception as e:
            print(f"Error creating dataloader: {e}")
            return None

    def _create_recognition_model(self):
        import torch
        import torch.nn as nn

        class MultiOutputRecognizer(nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = nn.Sequential(
                    nn.Conv2d(3, 32, 3, padding=1),
                    nn.BatchNorm2d(32),
                    nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(32, 64, 3, padding=1),
                    nn.BatchNorm2d(64),
                    nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(64, 128, 3, padding=1),
                    nn.BatchNorm2d(128),
                    nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(128, 256, 3, padding=1),
                    nn.BatchNorm2d(256),
                    nn.ReLU(),
                    nn.AdaptiveAvgPool2d(1),
                    nn.Flatten(),
                )

                self.dice_type_head = nn.Sequential(
                    nn.Linear(256, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, 8),
                )
                self.value_head = nn.Sequential(
                    nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, 21),
                )
                self.orientation_head = nn.Sequential(
                    nn.Linear(256, 64), nn.ReLU(), nn.Linear(64, 1), nn.Sigmoid(),
                )
                self.special_head = nn.Sequential(
                    nn.Linear(256, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1),
                    nn.Sigmoid(),
                )

            def forward(self, x):
                features = self.backbone(x)
                return {
                    "dice_type": self.dice_type_head(features),
                    "value": self.value_head(features),
                    "orientation": self.orientation_head(features),
                    "special": self.special_head(features),
                }

        return MultiOutputRecognizer()

    def _train_step(self, model, batch, optimizer):
        import torch
        import torch.nn.functional as F

        optimizer.zero_grad()
        outputs = model(batch["image"])

        value_targets = torch.tensor([v if isinstance(v, int) else 0 for v in batch["value"]]).long()
        loss = F.cross_entropy(outputs["value"], value_targets)
        loss += F.mse_loss(outputs["orientation"], batch["orientation"].float().unsqueeze(1))

        loss.backward()
        optimizer.step()
        return loss.item()

    def _validate(self, model, val_loader) -> float:
        import torch

        if val_loader is None:
            return 0.0

        correct, total = 0, 0
        with torch.no_grad():
            for batch in val_loader:
                outputs = model(batch["image"])
                value_preds = outputs["value"].argmax(dim=1)
                value_targets = torch.tensor([v if isinstance(v, int) else 0 for v in batch["value"]]).long()
                correct += (value_preds == value_targets).sum().item()
                total += len(value_targets)

        return correct / total if total > 0 else 0.0


class MultiOutputEvaluator:
    def __init__(self, dataset_dir: str = "data/dataset_v2"):
        self.dataset = MultiOutputDatasetManager(dataset_dir)

    def evaluate_detection(self, model_path: str, data_yaml: str, split: str = "test") -> dict:
        try:
            from ultralytics import YOLO

            model = YOLO(model_path)
            results = model.val(data=data_yaml, split=split)

            return {
                "map50": float(results.box.map50),
                "map50_95": float(results.box.map),
                "precision": float(results.box.mp),
                "recall": float(results.box.mr),
            }

        except Exception as e:
            print(f"Evaluation failed: {e}")
            return {}

    def evaluate_recognition(self, model_path: str, data_dir: str, split: str = "test") -> EvaluationReport:
        import json
        from collections import defaultdict
        from pathlib import Path

        try:
            import torch
            model = self._load_recognition_model(model_path)
            model.eval()
        except Exception as e:
            print(f"Could not load model: {e}")
            return self._empty_report()

        # Load test data
        crops_dir = Path(data_dir) / "crops" / split
        annotations_dir = Path(data_dir) / "annotations" / split

        if not crops_dir.exists():
            print(f"No test data found at {crops_dir}")
            return self._empty_report()

        # Collect predictions and ground truth
        predictions = []
        ground_truth = []
        dice_type_correct = defaultdict(lambda: {"correct": 0, "total": 0})
        value_correct = defaultdict(lambda: {"correct": 0, "total": 0})
        six_nine_confusion = {"total": 0, "confused": 0}
        d4_stats = {"correct": 0, "total": 0}
        special_symbol_stats = {"correct": 0, "total": 0}

        for crop_path in crops_dir.glob("*.jpg"):
            ann_path = annotations_dir / f"{crop_path.stem}.json"
            if not ann_path.exists():
                continue

            with open(ann_path, "r") as f:
                ann = json.load(f)

            # Get prediction
            pred = self._predict_single(model, str(crop_path))
            if pred is None:
                continue

            gt_type = ann.get("dice_type", "UNKNOWN")
            gt_value = ann.get("value", 0)

            predictions.append(pred)
            ground_truth.append(ann)

            # Dice type accuracy
            dice_type_correct[gt_type]["total"] += 1
            if pred["dice_type"] == gt_type:
                dice_type_correct[gt_type]["correct"] += 1

            # Value accuracy
            value_correct[gt_type]["total"] += 1
            if pred["value"] == gt_value:
                value_correct[gt_type]["correct"] += 1

            # 6/9 confusion
            if gt_value in (6, 9):
                six_nine_confusion["total"] += 1
                if pred["value"] in (6, 9) and pred["value"] != gt_value:
                    six_nine_confusion["confused"] += 1

            # D4 stats
            if gt_type == "D4":
                d4_stats["total"] += 1
                if pred["value"] == gt_value:
                    d4_stats["correct"] += 1

            # Special symbol stats
            if ann.get("special_value"):
                special_symbol_stats["total"] += 1
                if pred.get("special_value") == ann.get("special_value"):
                    special_symbol_stats["correct"] += 1

        # Calculate metrics
        total_samples = len(predictions)
        if total_samples == 0:
            return self._empty_report()

        # Overall accuracies
        dice_type_acc = sum(
            d["correct"] for d in dice_type_correct.values()
        ) / sum(d["total"] for d in dice_type_correct.values())

        value_acc = sum(
            d["correct"] for d in value_correct.values()
        ) / sum(d["total"] for d in value_correct.values())

        # Per-type accuracies
        dice_type_per_class = {
            k: v["correct"] / v["total"] if v["total"] > 0 else 0.0
            for k, v in dice_type_correct.items()
        }

        value_acc_per_type = {
            k: v["correct"] / v["total"] if v["total"] > 0 else 0.0
            for k, v in value_correct.items()
        }

        # Build metrics
        metrics = EvaluationMetrics(
            detection_map50=0.0,  # Not evaluated here
            detection_map50_95=0.0,
            detection_precision=0.0,
            detection_recall=0.0,
            dice_type_accuracy=dice_type_acc,
            dice_type_per_class=dice_type_per_class,
            value_accuracy=value_acc,
            value_accuracy_per_type=value_acc_per_type,
            six_nine_confusion_rate=(
                six_nine_confusion["confused"] / six_nine_confusion["total"]
                if six_nine_confusion["total"] > 0 else 0.0
            ),
            d4_accuracy=(
                d4_stats["correct"] / d4_stats["total"]
                if d4_stats["total"] > 0 else 0.0
            ),
            special_symbol_accuracy=(
                special_symbol_stats["correct"] / special_symbol_stats["total"]
                if special_symbol_stats["total"] > 0 else 0.0
            ),
            d100_accuracy=value_acc_per_type.get("D100", 0.0),
            confirmation_request_rate=0.0,
            false_confirmation_rate=0.0,
            total_samples=total_samples,
            total_dice=total_samples,
        )

        return EvaluationReport(
            metrics=metrics,
            model_version=model_path,
            evaluation_timestamp=datetime.now().isoformat(),
            dataset_info={"split": split, "data_dir": data_dir},
        )

    def _load_recognition_model(self, model_path: str):
        """Load recognition model from path."""
        import torch

        # Create model architecture
        trainer = MultiOutputTrainer()
        model = trainer._create_recognition_model()

        # Load weights
        model.load_state_dict(torch.load(model_path, map_location="cpu"))
        return model

    def _predict_single(self, model, image_path: str) -> dict | None:
        """Get prediction for a single image.

        Args:
            model: Recognition model.
            image_path: Path to image.

        Returns:
            Prediction dictionary or None.
        """
        try:
            import torch
            import cv2
            import numpy as np

            # Load and preprocess image
            image = cv2.imread(image_path)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image = cv2.resize(image, (64, 64))
            image = image.astype(np.float32) / 255.0
            image = np.transpose(image, (2, 0, 1))
            image = torch.tensor(image).unsqueeze(0)

            # Get prediction
            with torch.no_grad():
                outputs = model(image)

            # Decode outputs
            dice_type_idx = outputs["dice_type"].argmax(dim=1).item()
            value_idx = outputs["value"].argmax(dim=1).item()
            orientation = outputs["orientation"].item() * 360
            has_special = outputs["special"].item() > 0.5

            dice_types = ["D4", "D6", "D8", "D10", "D12", "D20", "D100", "UNKNOWN"]

            return {
                "dice_type": dice_types[dice_type_idx],
                "value": value_idx,
                "orientation": orientation,
                "special_value": "unknown_symbol" if has_special else None,
            }

        except Exception as e:
            print(f"Prediction failed: {e}")
            return None

    def _empty_report(self) -> EvaluationReport:
        """Create empty evaluation report."""
        return EvaluationReport(
            metrics=EvaluationMetrics(
                detection_map50=0.0,
                detection_map50_95=0.0,
                detection_precision=0.0,
                detection_recall=0.0,
                dice_type_accuracy=0.0,
                dice_type_per_class={},
                value_accuracy=0.0,
                value_accuracy_per_type={},
                six_nine_confusion_rate=0.0,
                d4_accuracy=0.0,
                special_symbol_accuracy=0.0,
                d100_accuracy=0.0,
                confirmation_request_rate=0.0,
                false_confirmation_rate=0.0,
                total_samples=0,
                total_dice=0,
            ),
            evaluation_timestamp=datetime.now().isoformat(),
        )

    def generate_report(
        self,
        detection_model: str | None,
        recognition_model: str | None,
        output_path: str,
    ) -> None:
        """Generate complete evaluation report.

        Args:
            detection_model: Path to detection model.
            recognition_model: Path to recognition model.
            output_path: Path to save report.
        """
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "detection": {},
            "recognition": {},
        }

        # Evaluate detection
        if detection_model:
            data_yaml = str(Path(detection_model).parent.parent.parent / "data.yaml")
            if Path(data_yaml).exists():
                report_data["detection"] = self.evaluate_detection(
                    detection_model, data_yaml
                )

        # Evaluate recognition
        if recognition_model:
            # Find recognition data
            recognition_data = str(
                Path(recognition_model).parent.parent.parent / "recognition_data"
            )
            if Path(recognition_data).exists():
                eval_report = self.evaluate_recognition(
                    recognition_model, recognition_data
                )
                report_data["recognition"] = eval_report.model_dump()

        # Save report
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(report_data, f, indent=2)

        print(f"Evaluation report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Multi-output dice model training")
    parser.add_argument("--action", choices=["prepare", "train-detection", "train-recognition", "train-all", "evaluate"], default="train-all")
    parser.add_argument("--dataset", type=str, default="data/dataset_v2")
    parser.add_argument("--output", type=str, default="runs/multi_output")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--model", type=str, default="yolo26n.pt")

    args = parser.parse_args()

    trainer = MultiOutputTrainer(args.dataset, args.output)

    if args.action == "prepare":
        print("Preparing detection data...")
        data_yaml = trainer.prepare_detection_data()
        print(f"Detection data: {data_yaml}")

        print("Preparing recognition data...")
        recog_dir = trainer.prepare_recognition_data()
        print(f"Recognition data: {recog_dir}")

    elif args.action == "train-detection":
        data_yaml = trainer.prepare_detection_data()
        trainer.train_detection_model(
            data_yaml,
            base_model=args.model,
            epochs=args.epochs,
            batch=args.batch,
        )

    elif args.action == "train-recognition":
        recog_dir = trainer.prepare_recognition_data()
        trainer.train_recognition_model(
            recog_dir,
            epochs=args.epochs,
            batch=args.batch,
        )

    elif args.action == "train-all":
        # Train both models
        print("=== Training Detection Model ===")
        data_yaml = trainer.prepare_detection_data()
        det_model = trainer.train_detection_model(
            data_yaml,
            base_model=args.model,
            epochs=args.epochs,
            batch=args.batch,
        )

        print("\n=== Training Recognition Model ===")
        recog_dir = trainer.prepare_recognition_data()
        recog_model = trainer.train_recognition_model(
            recog_dir,
            epochs=args.epochs // 2,
            batch=args.batch * 2,
        )

        print("\n=== Training Complete ===")
        print(f"Detection model: {det_model}")
        print(f"Recognition model: {recog_model}")

    elif args.action == "evaluate":
        evaluator = MultiOutputEvaluator(args.dataset)
        evaluator.generate_report(
            detection_model=None,  # Would need to specify
            recognition_model=None,
            output_path=str(Path(args.output) / "evaluation_report.json"),
        )


if __name__ == "__main__":
    main()
