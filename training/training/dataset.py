"""Dataset management for training dice detection models."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class DatasetManager:
    """Manages training dataset for dice detection."""

    def __init__(self, dataset_dir: str = "data/dataset"):
        """Initialize dataset manager.

        Args:
            dataset_dir: Root directory for dataset.
        """
        self.dataset_dir = Path(dataset_dir)
        self.images_dir = self.dataset_dir / "images"
        self.labels_dir = self.dataset_dir / "labels"
        self.metadata_file = self.dataset_dir / "metadata.json"

        self._ensure_dirs()
        self._load_metadata()

    def _ensure_dirs(self) -> None:
        """Ensure dataset directories exist."""
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)

        # Create train/val/test splits
        for split in ["train", "val", "test"]:
            (self.images_dir / split).mkdir(exist_ok=True)
            (self.labels_dir / split).mkdir(exist_ok=True)

    def _load_metadata(self) -> None:
        """Load dataset metadata."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                "created": datetime.now().isoformat(),
                "samples": 0,
                "classes": {
                    "D4": 0,
                    "D6": 1,
                    "D8": 2,
                    "D10": 3,
                    "D12": 4,
                    "D20": 5,
                    "D100": 6,
                },
                "statistics": {
                    "total_images": 0,
                    "total_annotations": 0,
                    "by_class": {},
                    "by_split": {"train": 0, "val": 0, "test": 0},
                },
            }
            self._save_metadata()

    def _save_metadata(self) -> None:
        """Save dataset metadata."""
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2)

    def add_sample(
        self,
        image: np.ndarray,
        annotations: list[dict],
        split: str = "train",
        source: str = "manual",
    ) -> str:
        """Add a sample to the dataset.

        Args:
            image: Image as numpy array.
            annotations: List of annotation dicts with keys:
                - class_name: Dice type (e.g., "D20")
                - bbox: [x_center, y_center, width, height] normalized
                - value: Detected/corrected value
                - confidence: Detection confidence
            split: Dataset split (train/val/test).
            source: Source of the sample.

        Returns:
            Sample ID.
        """
        # Generate sample ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        sample_id = f"{source}_{timestamp}"

        # Save image
        image_path = self.images_dir / split / f"{sample_id}.jpg"
        cv2.imwrite(str(image_path), image)

        # Save YOLO format labels
        label_path = self.labels_dir / split / f"{sample_id}.txt"
        with open(label_path, "w") as f:
            for ann in annotations:
                class_id = self.metadata["classes"].get(ann["class_name"], 0)
                x_center, y_center, width, height = ann["bbox"]
                f.write(f"{class_id} {x_center} {y_center} {width} {height}\n")

        # Save extended annotation metadata
        meta_path = self.labels_dir / split / f"{sample_id}.json"
        with open(meta_path, "w") as f:
            json.dump(
                {
                    "sample_id": sample_id,
                    "source": source,
                    "timestamp": datetime.now().isoformat(),
                    "annotations": annotations,
                },
                f,
                indent=2,
            )

        # Update statistics
        self.metadata["statistics"]["total_images"] += 1
        self.metadata["statistics"]["total_annotations"] += len(annotations)
        self.metadata["statistics"]["by_split"][split] += 1

        for ann in annotations:
            class_name = ann["class_name"]
            if class_name not in self.metadata["statistics"]["by_class"]:
                self.metadata["statistics"]["by_class"][class_name] = 0
            self.metadata["statistics"]["by_class"][class_name] += 1

        self._save_metadata()

        return sample_id

    def add_correction_sample(
        self,
        image: np.ndarray,
        dice_type: str,
        bbox: tuple[int, int, int, int],
        detected_value: int,
        corrected_value: int,
        confidence: float,
    ) -> str:
        """Add a corrected sample for training.

        Args:
            image: Full frame image.
            dice_type: Type of die.
            bbox: Bounding box (x, y, width, height) in pixels.
            detected_value: Originally detected value.
            corrected_value: User-corrected value.
            confidence: Original detection confidence.

        Returns:
            Sample ID.
        """
        h, w = image.shape[:2]

        # Convert bbox to normalized YOLO format
        x, y, bw, bh = bbox
        x_center = (x + bw / 2) / w
        y_center = (y + bh / 2) / h
        norm_width = bw / w
        norm_height = bh / h

        annotation = {
            "class_name": dice_type,
            "bbox": [x_center, y_center, norm_width, norm_height],
            "value": corrected_value,
            "detected_value": detected_value,
            "confidence": confidence,
            "was_corrected": detected_value != corrected_value,
        }

        return self.add_sample(
            image=image,
            annotations=[annotation],
            split="train",
            source="correction",
        )

    def get_statistics(self) -> dict:
        """Get dataset statistics.

        Returns:
            Statistics dictionary.
        """
        return self.metadata["statistics"]

    def export_yolo_format(self, output_dir: str) -> None:
        """Export dataset in YOLO format for training.

        Args:
            output_dir: Output directory.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Copy images and labels
        for split in ["train", "val", "test"]:
            # Images
            src_images = self.images_dir / split
            dst_images = output_path / "images" / split
            dst_images.mkdir(parents=True, exist_ok=True)

            for img_file in src_images.glob("*.jpg"):
                shutil.copy(img_file, dst_images / img_file.name)

            # Labels
            src_labels = self.labels_dir / split
            dst_labels = output_path / "labels" / split
            dst_labels.mkdir(parents=True, exist_ok=True)

            for label_file in src_labels.glob("*.txt"):
                shutil.copy(label_file, dst_labels / label_file.name)

        # Create data.yaml
        data_yaml = {
            "path": str(output_path.absolute()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {v: k for k, v in self.metadata["classes"].items()},
            "nc": len(self.metadata["classes"]),
        }

        import yaml

        with open(output_path / "data.yaml", "w") as f:
            yaml.dump(data_yaml, f, default_flow_style=False)

    def split_dataset(
        self,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
    ) -> None:
        """Redistribute samples across train/val/test splits.

        Args:
            train_ratio: Ratio for training set.
            val_ratio: Ratio for validation set.
            test_ratio: Ratio for test set.
        """
        import random

        # Collect all samples
        all_samples = []
        for split in ["train", "val", "test"]:
            for img_file in (self.images_dir / split).glob("*.jpg"):
                sample_id = img_file.stem
                all_samples.append((sample_id, split))

        # Shuffle
        random.shuffle(all_samples)

        # Calculate split sizes
        total = len(all_samples)
        train_size = int(total * train_ratio)
        val_size = int(total * val_ratio)

        # Assign new splits
        new_splits = (
            ["train"] * train_size
            + ["val"] * val_size
            + ["test"] * (total - train_size - val_size)
        )

        # Move files
        for (sample_id, old_split), new_split in zip(all_samples, new_splits):
            if old_split != new_split:
                # Move image
                old_img = self.images_dir / old_split / f"{sample_id}.jpg"
                new_img = self.images_dir / new_split / f"{sample_id}.jpg"
                if old_img.exists():
                    shutil.move(str(old_img), str(new_img))

                # Move label
                old_label = self.labels_dir / old_split / f"{sample_id}.txt"
                new_label = self.labels_dir / new_split / f"{sample_id}.txt"
                if old_label.exists():
                    shutil.move(str(old_label), str(new_label))

                # Move metadata
                old_meta = self.labels_dir / old_split / f"{sample_id}.json"
                new_meta = self.labels_dir / new_split / f"{sample_id}.json"
                if old_meta.exists():
                    shutil.move(str(old_meta), str(new_meta))

        # Update statistics
        self.metadata["statistics"]["by_split"] = {
            "train": train_size,
            "val": val_size,
            "test": total - train_size - val_size,
        }
        self._save_metadata()

    def get_sample(self, sample_id: str, split: str = "train") -> Optional[dict]:
        """Get a sample by ID.

        Args:
            sample_id: Sample ID.
            split: Dataset split.

        Returns:
            Sample dict or None if not found.
        """
        image_path = self.images_dir / split / f"{sample_id}.jpg"
        meta_path = self.labels_dir / split / f"{sample_id}.json"

        if not image_path.exists():
            return None

        image = cv2.imread(str(image_path))

        metadata = {}
        if meta_path.exists():
            with open(meta_path, "r") as f:
                metadata = json.load(f)

        return {
            "sample_id": sample_id,
            "image": image,
            "metadata": metadata,
        }

    def delete_sample(self, sample_id: str, split: str = "train") -> bool:
        """Delete a sample.

        Args:
            sample_id: Sample ID.
            split: Dataset split.

        Returns:
            True if deleted successfully.
        """
        deleted = False

        for ext in [".jpg", ".txt", ".json"]:
            if ext == ".jpg":
                path = self.images_dir / split / f"{sample_id}{ext}"
            else:
                path = self.labels_dir / split / f"{sample_id}{ext}"

            if path.exists():
                path.unlink()
                deleted = True

        if deleted:
            self.metadata["statistics"]["total_images"] -= 1
            self.metadata["statistics"]["by_split"][split] -= 1
            self._save_metadata()

        return deleted
