"""Annotation tool for labeling dice images."""

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class AnnotationTool:
    """Simple annotation tool for labeling dice in images."""

    DICE_CLASSES = ["D4", "D6", "D8", "D10", "D12", "D20", "D100_TENS"]
    MAX_VALUE_BY_CLASS = {
        "D4": 4,
        "D6": 6,
        "D8": 8,
        "D10": 10,
        "D12": 12,
        "D20": 20,
        "D100_TENS": 90,
    }

    def __init__(self, images_dir: str, output_dir: str):
        """Initialize annotation tool.

        Args:
            images_dir: Directory containing images to annotate.
            output_dir: Directory to save annotations.
        """
        self.images_dir = Path(images_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.current_image: Optional[np.ndarray] = None
        self.current_image_path: Optional[Path] = None
        self.annotations: list[dict] = []
        self.current_class_idx = 0
        self.drawing = False
        self.start_point = (0, 0)
        self.end_point = (0, 0)
        self.value_buffer = ""
        self.value_entry_mode = False

    def get_image_list(self) -> list[Path]:
        """Get list of images to annotate.

        Returns:
            List of image paths.
        """
        extensions = [".jpg", ".jpeg", ".png", ".bmp"]
        images = []
        for ext in extensions:
            images.extend(self.images_dir.glob(f"*{ext}"))
            images.extend(self.images_dir.glob(f"*{ext.upper()}"))
        return sorted(images)

    def load_image(self, image_path: Path) -> np.ndarray:
        """Load an image for annotation.

        Args:
            image_path: Path to image.

        Returns:
            Loaded image.
        """
        self.current_image_path = image_path
        self.current_image = cv2.imread(str(image_path))
        self.annotations = []
        self._clear_value_buffer()
        self.value_entry_mode = False

        # Load existing annotations if any
        annotation_path = self.output_dir / f"{image_path.stem}.json"
        if annotation_path.exists():
            with open(annotation_path, "r") as f:
                data = json.load(f)
                self.annotations = data.get("annotations", [])

        return self.current_image

    def add_annotation(
        self,
        bbox: tuple[int, int, int, int],
        class_name: str,
        value: Optional[int] = None,
    ) -> None:
        """Add an annotation.

        Args:
            bbox: Bounding box (x, y, width, height) in pixels.
            class_name: Dice class name.
            value: Optional dice value.
        """
        if self.current_image is None:
            return

        h, w = self.current_image.shape[:2]
        x, y, bw, bh = bbox

        # Convert to normalized YOLO format
        x_center = (x + bw / 2) / w
        y_center = (y + bh / 2) / h
        norm_width = bw / w
        norm_height = bh / h

        annotation = {
            "class_name": class_name,
            "bbox": [x_center, y_center, norm_width, norm_height],
            "bbox_pixels": [x, y, bw, bh],
            "value": value,
        }

        self.annotations.append(annotation)

    def remove_last_annotation(self) -> None:
        """Remove the last annotation."""
        if self.annotations:
            self.annotations.pop()

    def _max_value_for_class(self, class_name: str) -> int:
        return self.MAX_VALUE_BY_CLASS.get(class_name, 20)

    def _parse_value_buffer(self, class_name: str) -> int | None:
        if not self.value_buffer:
            return None
        try:
            value = int(self.value_buffer)
        except ValueError:
            return None
        max_value = self._max_value_for_class(class_name)
        if value < 0 or value > max_value:
            return None
        if class_name == "D100_TENS" and value % 10 != 0:
            return None
        return value

    def _clear_value_buffer(self) -> None:
        self.value_buffer = ""

    def _consume_value_for_class(self, class_name: str) -> int | None:
        value = self._parse_value_buffer(class_name)
        self._clear_value_buffer()
        return value

    def _apply_value_to_last_annotation(self, class_name: str) -> bool:
        if not self.annotations:
            return False
        value = self._parse_value_buffer(class_name)
        if value is None:
            print(f"Invalid value '{self.value_buffer}' for {class_name}")
            return False
        self.annotations[-1]["value"] = value
        self._clear_value_buffer()
        return True

    def save_annotations(self) -> None:
        """Save annotations for current image."""
        if self.current_image_path is None:
            return

        # Save JSON format with full metadata
        json_path = self.output_dir / f"{self.current_image_path.stem}.json"
        with open(json_path, "w") as f:
            json.dump(
                {
                    "image_path": str(self.current_image_path),
                    "image_size": list(self.current_image.shape[:2]),
                    "annotations": self.annotations,
                },
                f,
                indent=2,
            )

        # Save YOLO format
        txt_path = self.output_dir / f"{self.current_image_path.stem}.txt"
        with open(txt_path, "w") as f:
            for ann in self.annotations:
                class_idx = self.DICE_CLASSES.index(ann["class_name"])
                x_center, y_center, width, height = ann["bbox"]
                f.write(f"{class_idx} {x_center} {y_center} {width} {height}\n")

    def draw_annotations(self, image: np.ndarray) -> np.ndarray:
        """Draw annotations on image.

        Args:
            image: Image to draw on.

        Returns:
            Image with annotations drawn.
        """
        result = image.copy()

        colors = {
            "D4": (255, 0, 0),
            "D6": (0, 255, 0),
            "D8": (0, 255, 255),
            "D10": (255, 255, 0),
            "D12": (255, 0, 255),
            "D20": (0, 165, 255),
            "D100_TENS": (128, 0, 128),
        }

        for ann in self.annotations:
            if "bbox_pixels" in ann:
                x, y, w, h = ann["bbox_pixels"]
            else:
                # Convert from normalized
                img_h, img_w = result.shape[:2]
                x_center, y_center, norm_w, norm_h = ann["bbox"]
                w = int(norm_w * img_w)
                h = int(norm_h * img_h)
                x = int(x_center * img_w - w / 2)
                y = int(y_center * img_h - h / 2)

            color = colors.get(ann["class_name"], (128, 128, 128))

            # Draw rectangle
            cv2.rectangle(result, (x, y), (x + w, y + h), color, 2)

            # Draw label
            label = ann["class_name"]
            if ann.get("value") is not None:
                label += f"={ann['value']}"

            cv2.putText(
                result,
                label,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

        return result

    def run_interactive(self) -> None:
        """Run interactive annotation session using OpenCV window."""
        images = self.get_image_list()
        if not images:
            print("No images found to annotate")
            return

        current_idx = 0
        window_name = "Dice Annotator"

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                self.drawing = True
                self.start_point = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
                self.end_point = (x, y)
            elif event == cv2.EVENT_LBUTTONUP:
                self.drawing = False
                self.end_point = (x, y)

                # Calculate bbox
                x1 = min(self.start_point[0], self.end_point[0])
                y1 = min(self.start_point[1], self.end_point[1])
                x2 = max(self.start_point[0], self.end_point[0])
                y2 = max(self.start_point[1], self.end_point[1])

                if x2 - x1 > 10 and y2 - y1 > 10:
                    class_name = self.DICE_CLASSES[self.current_class_idx]
                    value = self._consume_value_for_class(class_name)
                    self.add_annotation(
                        bbox=(x1, y1, x2 - x1, y2 - y1),
                        class_name=class_name,
                        value=value,
                    )
                    if value is not None:
                        print(f"  -> {class_name} = {value}")

        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, mouse_callback)

        print("\nControls:")
        print("  1-7: Select dice class (D4, D6, D8, D10, D12, D20, D100)")
        print("  Click and drag: Draw bounding box")
        print("  v: Toggle value entry (0-9 type digits, Enter apply, c clear)")
        print("  x: Clear value on last box / skip value for next box")
        print("  z: Undo last annotation")
        print("  s: Save annotations")
        print("  n/Right: Next image")
        print("  p/Left: Previous image")
        print("  q/Esc: Quit")

        while True:
            # Load current image
            self.load_image(images[current_idx])

            while True:
                # Draw current state
                display = self.draw_annotations(self.current_image.copy())

                # Draw current drawing box
                if self.drawing:
                    cv2.rectangle(
                        display,
                        self.start_point,
                        self.end_point,
                        (0, 255, 0),
                        1,
                    )

                # Draw status bar
                class_name = self.DICE_CLASSES[self.current_class_idx]
                max_val = self._max_value_for_class(class_name)
                value_hint = (
                    f"Value: {self.value_buffer or '-'} (max {max_val})"
                    if self.value_entry_mode
                    else "Value: press v to enter"
                )
                status = (
                    f"Image {current_idx + 1}/{len(images)} | "
                    f"Class: {class_name} | "
                    f"Annotations: {len(self.annotations)} | {value_hint}"
                )
                cv2.putText(
                    display,
                    status,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                )

                cv2.imshow(window_name, display)
                key = cv2.waitKey(30) & 0xFF

                if key == ord("q") or key == 27:  # q or Esc
                    cv2.destroyAllWindows()
                    return

                elif key == ord("v"):
                    self.value_entry_mode = not self.value_entry_mode
                    if not self.value_entry_mode:
                        self._clear_value_buffer()

                elif key == ord("x"):
                    self._clear_value_buffer()
                    if self.annotations:
                        self.annotations[-1]["value"] = None

                elif self.value_entry_mode and key in [ord(str(i)) for i in range(10)]:
                    if len(self.value_buffer) < 3:
                        self.value_buffer += chr(key)

                elif self.value_entry_mode and key in (13, 10):
                    self._apply_value_to_last_annotation(class_name)

                elif self.value_entry_mode and key == 8:
                    self.value_buffer = self.value_buffer[:-1]

                elif self.value_entry_mode and key == ord("c"):
                    self._clear_value_buffer()

                elif not self.value_entry_mode and key in [ord(str(i)) for i in range(1, 8)]:
                    self.current_class_idx = int(chr(key)) - 1

                elif key == ord("z"):
                    self.remove_last_annotation()

                elif key == ord("s"):
                    self.save_annotations()
                    print(f"Saved annotations for {self.current_image_path.name}")

                elif key == ord("n") or key == 83:  # n or Right arrow
                    self.save_annotations()
                    current_idx = (current_idx + 1) % len(images)
                    break

                elif key == ord("p") or key == 81:  # p or Left arrow
                    self.save_annotations()
                    current_idx = (current_idx - 1) % len(images)
                    break

        cv2.destroyAllWindows()

    def export_to_yolo(self, output_dir: str) -> None:
        """Export all annotations to YOLO format.

        Args:
            output_dir: Output directory.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for json_file in self.output_dir.glob("*.json"):
            with open(json_file, "r") as f:
                data = json.load(f)

            txt_path = output_path / f"{json_file.stem}.txt"
            with open(txt_path, "w") as f:
                for ann in data.get("annotations", []):
                    class_idx = self.DICE_CLASSES.index(ann["class_name"])
                    x_center, y_center, width, height = ann["bbox"]
                    f.write(f"{class_idx} {x_center} {y_center} {width} {height}\n")
