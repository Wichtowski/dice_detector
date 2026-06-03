from pathlib import Path

import cv2
import numpy as np

from dice_detector.models import BoundingBox, DiceType


class DiceDetector:
    """Detects dice objects in images using YOLO26."""

    CLASS_NAMES = {
        0: DiceType.D4,
        1: DiceType.D6,
        2: DiceType.D8,
        3: DiceType.D10,
        4: DiceType.D12,
        5: DiceType.D20,
        6: DiceType.D100_TENS,
    }

    def __init__(self, model_path: str | None = None, confidence_threshold: float = 0.5):
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.model_path = model_path
        self._use_fallback = False

    def load_model(self) -> bool:
        try:
            from ultralytics import YOLO

            if self.model_path and Path(self.model_path).exists():
                self.model = YOLO(self.model_path)
            else:
                # Use YOLO26 - latest mainline model with NMS-free inference
                self.model = YOLO("yolo26n.pt")
                self._use_fallback = True
            return True
        except Exception as e:
            print(f"Failed to load YOLO model: {e}")
            self._use_fallback = True
            return False

    def detect(self, frame: np.ndarray) -> list[tuple[BoundingBox, DiceType, float]]:
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

                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                bbox = BoundingBox(
                    x=int(x1),
                    y=int(y1),
                    width=int(x2 - x1),
                    height=int(y2 - y1),
                )

                cls_id = int(boxes.cls[i])
                dice_type = self.CLASS_NAMES.get(cls_id, DiceType.UNKNOWN)

                detections.append((bbox, dice_type, conf))

        return detections

    def _fallback_detect(self, frame: np.ndarray) -> list[tuple[BoundingBox, DiceType, float]]:
        """Fallback detection using traditional CV when YOLO model not available."""
        detections = []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            if area < 500 or area > 50000:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 0.5 or aspect_ratio > 2.0:
                continue

            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            num_vertices = len(approx)

            dice_type = DiceType.UNKNOWN
            confidence = 0.6

            if num_vertices == 3:
                dice_type = DiceType.D4
                confidence = 0.5
            elif num_vertices == 4:
                dice_type = DiceType.D6
                confidence = 0.65
            elif 5 <= num_vertices <= 6:
                dice_type = DiceType.D8
                confidence = 0.55
            elif 7 <= num_vertices <= 10:
                dice_type = DiceType.D10
                confidence = 0.5
            elif num_vertices > 10:
                dice_type = DiceType.D20
                confidence = 0.5

            if dice_type != DiceType.UNKNOWN:
                bbox = BoundingBox(x=x, y=y, width=w, height=h)
                detections.append((bbox, dice_type, confidence))

        return detections

    def crop_die(self, frame: np.ndarray, bbox: BoundingBox, padding: int = 10) -> np.ndarray:
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
        result = frame.copy()

        colors = {
            DiceType.D4: (255, 0, 0),
            DiceType.D6: (0, 255, 0),
            DiceType.D8: (0, 255, 255),
            DiceType.D10: (255, 255, 0),
            DiceType.D12: (255, 0, 255),
            DiceType.D20: (0, 165, 255),
            DiceType.D100_TENS: (128, 0, 128),
            DiceType.UNKNOWN: (128, 128, 128),
        }

        for bbox, dice_type, conf in detections:
            color = colors.get(dice_type, (128, 128, 128))
            x1, y1, x2, y2 = bbox.to_xyxy()

            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)

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
