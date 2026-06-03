import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from dice_detector.models import (
    AmbiguityReason,
    BoundingBox,
    DiceAnnotation,
    DiceType,
    ImageAnnotation,
    SpecialValue,
    TrainingSample,
)


class MultiOutputDatasetManager:
    """Manages training dataset with multi-output annotations.

    This replaces the old approach of using merged class labels.
    """

    def __init__(self, dataset_dir: str = "data/dataset_v2"):
        self.dataset_dir = Path(dataset_dir)
        self.images_dir = self.dataset_dir / "images"
        self.annotations_dir = self.dataset_dir / "annotations"
        self.metadata_file = self.dataset_dir / "metadata.json"

        self._ensure_dirs()
        self._load_metadata()

    def _ensure_dirs(self) -> None:
        for split in ["train", "val", "test"]:
            (self.images_dir / split).mkdir(parents=True, exist_ok=True)
            (self.annotations_dir / split).mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> None:
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                "version": "2.0",
                "format": "multi_output",
                "created": datetime.now().isoformat(),
                "statistics": {
                    "total_images": 0,
                    "total_dice": 0,
                    "by_split": {"train": 0, "val": 0, "test": 0},
                    "by_dice_type": {},
                    "by_value": {},
                    "special_symbols": 0,
                    "ambiguous_annotations": 0,
                    "d4_count": 0,
                    "d100_count": 0,
                    "six_nine_cases": 0,
                },
            }
            self._save_metadata()

    def _save_metadata(self) -> None:
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2)

    def add_sample(
        self,
        image: np.ndarray,
        annotation: ImageAnnotation,
        split: Literal["train", "val", "test"] = "train",
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        sample_id = f"{annotation.source}_{timestamp}"

        image_path = self.images_dir / split / f"{sample_id}.jpg"
        cv2.imwrite(str(image_path), image)

        annotation.image_path = str(image_path)

        annotation_path = self.annotations_dir / split / f"{sample_id}.json"
        with open(annotation_path, "w") as f:
            f.write(annotation.model_dump_json(indent=2))

        self._update_statistics(annotation, split)
        self._save_metadata()

        return sample_id

    def add_dice_annotation(
        self,
        image: np.ndarray,
        bbox: BoundingBox,
        dice_type: DiceType,
        value: int | str | None,
        split: Literal["train", "val", "test"] = "train",
        source: str = "manual",
        orientation_degrees: float | None = None,
        special_value: SpecialValue | None = None,
        ambiguous: bool = False,
        ambiguity_reasons: list[AmbiguityReason] | None = None,
    ) -> str:
        """Single-die annotation (convenience method :p)

        Args:
            image: Image as numpy array.
            bbox: Bounding box of the die.
            dice_type: Type of die.
            value: Detected/annotated value.
            split: Dataset split.
            source: Annotation source.
            orientation_degrees: Optional orientation.
            special_value: Optional special symbol.
            ambiguous: Whether annotation is uncertain.
            ambiguity_reasons: List of ambiguity reasons.
        """
        h, w = image.shape[:2]

        dice_annotation = DiceAnnotation(
            bbox=bbox,
            dice_type=dice_type,
            value=value,
            orientation_degrees=orientation_degrees,
            special_value=special_value,
            ambiguous=ambiguous,
            ambiguity_reasons=ambiguity_reasons or [],
        )

        image_annotation = ImageAnnotation(
            image_path="",  # Will be set in add_sample
            image_width=w,
            image_height=h,
            dice=[dice_annotation],
            source=source,
            timestamp=datetime.now().isoformat(),
        )

        return self.add_sample(image, image_annotation, split)

    def add_correction_sample(
        self,
        image: np.ndarray,
        bbox: BoundingBox,
        dice_type: DiceType,
        detected_value: int | None,
        corrected_value: int,
        detection_confidence: float,
        orientation_degrees: float | None = None,
    ) -> str:
        """Add a user-corrected sample for training

        Args:
            image: Full frame image
            bbox: Bounding box of the die
            dice_type: Type of die
            detected_value: Originally detected value
            corrected_value: User-corrected value
            detection_confidence: Original detection confidence
            orientation_degrees: Optional orientation
        """
        h, w = image.shape[:2]

        # Determine if this was a 6/9 (hehe) confusion
        ambiguity_reasons = []
        if detected_value in (6, 9) and corrected_value in (6, 9):
            ambiguity_reasons.append(AmbiguityReason.POSSIBLE_6_9)

        dice_annotation = DiceAnnotation(
            bbox=bbox,
            dice_type=dice_type,
            value=corrected_value,
            orientation_degrees=orientation_degrees,
            ambiguous=detected_value != corrected_value,
            ambiguity_reasons=ambiguity_reasons,
        )

        image_annotation = ImageAnnotation(
            image_path="",
            image_width=w,
            image_height=h,
            dice=[dice_annotation],
            source="correction",
            timestamp=datetime.now().isoformat(),
            metadata={
                "detected_value": detected_value,
                "corrected_value": corrected_value,
                "detection_confidence": detection_confidence,
                "was_corrected": detected_value != corrected_value,
            },
        )

        return self.add_sample(image, image_annotation, "train")

    def _update_statistics(
        self, annotation: ImageAnnotation, split: str
    ) -> None:
        stats = self.metadata["statistics"]
        stats["total_images"] += 1
        stats["total_dice"] += len(annotation.dice)
        stats["by_split"][split] += 1

        for die in annotation.dice:
            dtype = die.dice_type.value
            stats["by_dice_type"][dtype] = stats["by_dice_type"].get(dtype, 0) + 1

            if die.value is not None:
                val_key = f"{dtype}_{die.value}"
                stats["by_value"][val_key] = stats["by_value"].get(val_key, 0) + 1

            if die.special_value is not None:
                stats["special_symbols"] += 1

            if die.ambiguous:
                stats["ambiguous_annotations"] += 1

            if die.dice_type == DiceType.D4:
                stats["d4_count"] += 1

            if die.dice_type in (DiceType.D100, DiceType.D100_TENS):
                stats["d100_count"] += 1

            if AmbiguityReason.POSSIBLE_6_9 in die.ambiguity_reasons:
                stats["six_nine_cases"] += 1

    def get_sample(
        self, sample_id: str, split: str = "train"
    ) -> TrainingSample | None:
        image_path = self.images_dir / split / f"{sample_id}.jpg"
        annotation_path = self.annotations_dir / split / f"{sample_id}.json"

        if not image_path.exists() or not annotation_path.exists():
            return None

        with open(annotation_path, "r") as f:
            annotation = ImageAnnotation.model_validate_json(f.read())

        return TrainingSample(
            image_path=str(image_path),
            annotation=annotation,
            split=split,
        )

    def get_all_samples(
        self, split: str | None = None
    ) -> list[TrainingSample]:
        """Get all samples, optionally filtered by split"""
        samples = []
        splits = [split] if split else ["train", "val", "test"]

        for s in splits:
            annotation_dir = self.annotations_dir / s
            for annotation_file in annotation_dir.glob("*.json"):
                sample_id = annotation_file.stem
                sample = self.get_sample(sample_id, s)
                if sample:
                    samples.append(sample)

        return samples

    def get_statistics(self) -> dict:
        return self.metadata["statistics"]

    def export_yolo_detection(self, output_dir: str) -> None:
        output_path = Path(output_dir)

        # Class mapping for detection
        class_names = {
            DiceType.D4: 0,
            DiceType.D6: 1,
            DiceType.D8: 2,
            DiceType.D10: 3,
            DiceType.D12: 4,
            DiceType.D20: 5,
            DiceType.D100: 6,
            DiceType.D100_TENS: 6,
            DiceType.D100_ONES: 7,
        }

        for split in ["train", "val", "test"]:
            images_out = output_path / "images" / split
            labels_out = output_path / "labels" / split
            images_out.mkdir(parents=True, exist_ok=True)
            labels_out.mkdir(parents=True, exist_ok=True)

            annotation_dir = self.annotations_dir / split
            for annotation_file in annotation_dir.glob("*.json"):
                sample_id = annotation_file.stem
                image_src = self.images_dir / split / f"{sample_id}.jpg"

                if not image_src.exists():
                    continue

                shutil.copy(image_src, images_out / f"{sample_id}.jpg")

                with open(annotation_file, "r") as f:
                    annotation = ImageAnnotation.model_validate_json(f.read())

                label_path = labels_out / f"{sample_id}.txt"
                with open(label_path, "w") as f:
                    for die in annotation.dice:
                        class_id = class_names.get(die.dice_type, 0)

                        x_center = (die.bbox.x + die.bbox.width / 2) / annotation.image_width
                        y_center = (die.bbox.y + die.bbox.height / 2) / annotation.image_height
                        width = die.bbox.width / annotation.image_width
                        height = die.bbox.height / annotation.image_height

                        f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

        data_yaml = {
            "path": str(output_path.absolute()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {
                0: "D4",
                1: "D6",
                2: "D8",
                3: "D10",
                4: "D12",
                5: "D20",
                6: "D100_TENS",
                7: "D100_ONES",
            },
            "nc": 8,
        }

        import yaml
        with open(output_path / "data.yaml", "w") as f:
            yaml.dump(data_yaml, f, default_flow_style=False)

    def export_recognition_crops(self, output_dir: str) -> None:
        output_path = Path(output_dir)

        for split in ["train", "val", "test"]:
            crops_dir = output_path / "crops" / split
            annotations_out = output_path / "annotations" / split
            crops_dir.mkdir(parents=True, exist_ok=True)
            annotations_out.mkdir(parents=True, exist_ok=True)

            annotation_dir = self.annotations_dir / split
            for annotation_file in annotation_dir.glob("*.json"):
                sample_id = annotation_file.stem
                image_path = self.images_dir / split / f"{sample_id}.jpg"

                if not image_path.exists():
                    continue

                image = cv2.imread(str(image_path))
                with open(annotation_file, "r") as f:
                    annotation = ImageAnnotation.model_validate_json(f.read())

                for i, die in enumerate(annotation.dice):
                    crop_id = f"{sample_id}_die{i}"

                    padding = 10
                    h, w = image.shape[:2]
                    x1 = max(0, die.bbox.x - padding)
                    y1 = max(0, die.bbox.y - padding)
                    x2 = min(w, die.bbox.x + die.bbox.width + padding)
                    y2 = min(h, die.bbox.y + die.bbox.height + padding)

                    crop = image[y1:y2, x1:x2]
                    cv2.imwrite(str(crops_dir / f"{crop_id}.jpg"), crop)

                    crop_annotation = {
                        "crop_id": crop_id,
                        "source_image": str(image_path),
                        "dice_type": die.dice_type.value,
                        "value": die.value,
                        "special_value": die.special_value.value if die.special_value else None,
                        "orientation_degrees": die.orientation_degrees,
                        "ambiguous": die.ambiguous,
                        "ambiguity_reasons": [r.value for r in die.ambiguity_reasons],
                        "has_6_9_marker": die.has_6_9_marker,
                        "number_style": die.number_style.value,
                    }

                    with open(annotations_out / f"{crop_id}.json", "w") as f:
                        json.dump(crop_annotation, f, indent=2)

    def split_dataset(
        self,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        seed: int | None = None,
    ) -> None:
        """Redistribute samples across train/val/test splits"""
        import random

        if seed is not None:
            random.seed(seed)

        all_samples = []
        for split in ["train", "val", "test"]:
            for annotation_file in (self.annotations_dir / split).glob("*.json"):
                sample_id = annotation_file.stem
                all_samples.append((sample_id, split))

        random.shuffle(all_samples)

        total = len(all_samples)
        train_size = int(total * train_ratio)
        val_size = int(total * val_ratio)

        new_splits = (
            ["train"] * train_size
            + ["val"] * val_size
            + ["test"] * (total - train_size - val_size)
        )

        for (sample_id, old_split), new_split in zip(all_samples, new_splits):
            if old_split != new_split:
                old_img = self.images_dir / old_split / f"{sample_id}.jpg"
                new_img = self.images_dir / new_split / f"{sample_id}.jpg"
                if old_img.exists():
                    shutil.move(str(old_img), str(new_img))

                old_ann = self.annotations_dir / old_split / f"{sample_id}.json"
                new_ann = self.annotations_dir / new_split / f"{sample_id}.json"
                if old_ann.exists():
                    shutil.move(str(old_ann), str(new_ann))

        self._recalculate_statistics()
        self._save_metadata()

    def _recalculate_statistics(self) -> None:
        self.metadata["statistics"] = {
            "total_images": 0,
            "total_dice": 0,
            "by_split": {"train": 0, "val": 0, "test": 0},
            "by_dice_type": {},
            "by_value": {},
            "special_symbols": 0,
            "ambiguous_annotations": 0,
            "d4_count": 0,
            "d100_count": 0,
            "six_nine_cases": 0,
        }

        for split in ["train", "val", "test"]:
            for annotation_file in (self.annotations_dir / split).glob("*.json"):
                with open(annotation_file, "r") as f:
                    annotation = ImageAnnotation.model_validate_json(f.read())
                self._update_statistics(annotation, split)

    def delete_sample(self, sample_id: str, split: str = "train") -> bool:
        deleted = False

        image_path = self.images_dir / split / f"{sample_id}.jpg"
        annotation_path = self.annotations_dir / split / f"{sample_id}.json"

        if image_path.exists():
            image_path.unlink()
            deleted = True

        if annotation_path.exists():
            annotation_path.unlink()
            deleted = True

        if deleted:
            self._recalculate_statistics()
            self._save_metadata()

        return deleted

    def migrate_from_v1(self, v1_dataset_dir: str) -> int:
        v1_path = Path(v1_dataset_dir)
        migrated = 0

        for split in ["train", "val", "test"]:
            v1_labels = v1_path / "labels" / split
            v1_images = v1_path / "images" / split

            if not v1_labels.exists():
                continue

            for label_file in v1_labels.glob("*.json"):
                sample_id = label_file.stem
                image_path = v1_images / f"{sample_id}.jpg"

                if not image_path.exists():
                    continue

                with open(label_file, "r") as f:
                    v1_data = json.load(f)

                image = cv2.imread(str(image_path))
                if image is None:
                    continue

                h, w = image.shape[:2]

                dice_annotations = []
                for ann in v1_data.get("annotations", []):
                    class_name = ann.get("class_name", "UNKNOWN")
                    try:
                        dice_type = DiceType(class_name)
                    except ValueError:
                        dice_type = DiceType.UNKNOWN

                    x_center, y_center, norm_w, norm_h = ann.get("bbox", [0.5, 0.5, 0.1, 0.1])
                    bbox_w = int(norm_w * w)
                    bbox_h = int(norm_h * h)
                    bbox_x = int(x_center * w - bbox_w / 2)
                    bbox_y = int(y_center * h - bbox_h / 2)

                    bbox = BoundingBox(
                        x=max(0, bbox_x),
                        y=max(0, bbox_y),
                        width=max(1, bbox_w),
                        height=max(1, bbox_h),
                    )

                    dice_annotations.append(
                        DiceAnnotation(
                            bbox=bbox,
                            dice_type=dice_type,
                            value=ann.get("value"),
                        )
                    )

                if dice_annotations:
                    image_annotation = ImageAnnotation(
                        image_path="",
                        image_width=w,
                        image_height=h,
                        dice=dice_annotations,
                        source="migrated_v1",
                        timestamp=datetime.now().isoformat(),
                        metadata={"original_v1_path": str(label_file)},
                    )

                    self.add_sample(image, image_annotation, split)
                    migrated += 1

        return migrated
