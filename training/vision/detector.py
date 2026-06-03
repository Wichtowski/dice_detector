import os
from typing import Optional

import cv2
import numpy as np

from ..models import BoundingBox, DiceType


class DiceDetector:
    """Detects dice objects in images using YOLOv8."""

    # Class mapping for dice types
    CLASS_NAMES = {
        0: DiceType.D4,
        1: DiceType.D6,
        2: DiceType.D8,
        3: DiceType.D10,
        4: DiceType.D12,
        5: DiceType.D20,
        6: DiceType.D100_TENS,  # Percentile die
    }

    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = 0.5):
        """Initialize dice detector.

        Args:
            model_path: Path to custom YOLO model. If None, uses default.
            confidence_threshold: Minimum confidence for detections.
        """
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.model_path = model_path
        self._use_fallback = False

    def load_model(self) -> bool:
        """Load the YOLO model.

        Returns:
            True if model loaded successfully.
        """
        try:
            from ultralytics import YOLO

            if self.model_path and os.path.exists(self.model_path):
                self.model = YOLO(self.model_path)
            else:
                # Use pretrained YOLOv8 as base - will need fine-tuning for dice
                self.model = YOLO("yolov8n.pt")
                self._use_fallback = True
            return True
        except Exception as e:
            print(f"Failed to load YOLO model: {e}")
            self._use_fallback = True
            return False

    def detect(self, frame: np.ndarray) -> list[tuple[BoundingBox, DiceType, float]]:
        """Detect dice in a frame.

        Args:
            frame: Input image as numpy array (BGR format).

        Returns:
            List of (bounding_box, dice_type, confidence) tuples.
        """
        if self._use_fallback or self.model is None:
            return self._fallback_detect(frame)

        results = self.model(frame, verbose=False)
        detections = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for i in range(len(boxes)):
                conf = float(boxes.conf[i])
                if conf < self.confidence_threshold:
                    continue

                # Get bounding box
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                bbox = BoundingBox(
                    x=int(x1),
                    y=int(y1),
                    width=int(x2 - x1),
                    height=int(y2 - y1),
                )

                # Get class
                cls_id = int(boxes.cls[i])
                dice_type = self.CLASS_NAMES.get(cls_id, DiceType.UNKNOWN)

                detections.append((bbox, dice_type, conf))

        return detections

    def _fallback_detect(self, frame: np.ndarray) -> list[tuple[BoundingBox, DiceType, float]]:
        """Fallback detection using traditional CV when YOLO model not available.

        Uses contour detection to find dice-like objects.

        Args:
            frame: Input image as numpy array.

        Returns:
            List of (bounding_box, dice_type, confidence) tuples.
        """
        detections = []

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Edge detection
        edges = cv2.Canny(blurred, 50, 150)

        # Dilate to close gaps
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by area (dice should be reasonably sized)
            if area < 500 or area > 50000:
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)

            # Filter by aspect ratio (dice are roughly square-ish)
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.5 or aspect_ratio > 2.0:
                continue

            # Approximate contour to polygon
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            num_vertices = len(approx)

            # Estimate dice type based on shape
            dice_type = DiceType.UNKNOWN
            confidence = 0.6  # Base confidence for fallback detection

            if num_vertices == 3:
                # Triangle - likely D4
                dice_type = DiceType.D4
                confidence = 0.5  # Lower confidence for D4
            elif num_vertices == 4:
                # Square/rectangle - likely D6
                dice_type = DiceType.D6
                confidence = 0.65
            elif 5 <= num_vertices <= 6:
                # Pentagon/hexagon - could be D8 or D10
                dice_type = DiceType.D8
                confidence = 0.55
            elif 7 <= num_vertices <= 10:
                # More complex shape - could be D10, D12
                dice_type = DiceType.D10
                confidence = 0.5
            elif num_vertices > 10:
                # Many vertices - likely D20 or D12
                dice_type = DiceType.D20
                confidence = 0.5

            if dice_type != DiceType.UNKNOWN:
                bbox = BoundingBox(x=x, y=y, width=w, height=h)
                detections.append((bbox, dice_type, confidence))

        return detections

    def crop_die(self, frame: np.ndarray, bbox: BoundingBox, padding: int = 10) -> np.ndarray:
        """Crop a detected die from the frame with padding.

        Args:
            frame: Input image.
            bbox: Bounding box of the die.
            padding: Padding around the bounding box.

        Returns:
            Cropped image of the die.
        """
        h, w = frame.shape[:2]
        x1 = max(0, bbox.x - padding)
        y1 = max(0, bbox.y - padding)
        x2 = min(w, bbox.x + bbox.width + padding)
        y2 = min(h, bbox.y + bbox.height + padding)

        return frame[y1:y2, x1:x2].copy()

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: list[tuple[BoundingBox, DiceType, float]],
        show_confidence: bool = True,
    ) -> np.ndarray:
        """Draw detection boxes on frame.

        Args:
            frame: Input image.
            detections: List of detections.
            show_confidence: Whether to show confidence scores.

        Returns:
            Frame with drawn detections.
        """
        result = frame.copy()

        colors = {
            DiceType.D4: (255, 0, 0),  # Blue
            DiceType.D6: (0, 255, 0),  # Green
            DiceType.D8: (0, 255, 255),  # Yellow
            DiceType.D10: (255, 255, 0),  # Cyan
            DiceType.D12: (255, 0, 255),  # Magenta
            DiceType.D20: (0, 165, 255),  # Orange
            DiceType.D100_TENS: (128, 0, 128),  # Purple
            DiceType.UNKNOWN: (128, 128, 128),  # Gray
        }

        for bbox, dice_type, conf in detections:
            color = colors.get(dice_type, (128, 128, 128))
            x1, y1, x2, y2 = bbox.to_xyxy()

            # Draw rectangle
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = dice_type.value
            if show_confidence:
                label += f" {conf:.2f}"

            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(
                result,
                (x1, y1 - label_size[1] - 10),
                (x1 + label_size[0], y1),
                color,
                -1,
            )
            cv2.putText(
                result,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2,
            )

        return result
