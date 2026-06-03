"""Vision pipeline for dice detection and recognition."""

from typing import Optional

import cv2
import numpy as np

from dice_detector.models import CalibrationSettings, DetectedDie, ExpectedRoll, VisionConfig
from dice_detector.vision.detector import DiceDetector
from dice_detector.vision.recognizer import DiceRecognizer


class VisionPipeline:
    """Complete vision pipeline for dice detection and recognition."""

    def __init__(
        self,
        settings: CalibrationSettings | None = None,
        model_path: str | None = None,
        vision_config: VisionConfig | None = None,
    ):
        self.settings = settings or CalibrationSettings()
        self.vision_config = vision_config or VisionConfig()
        self.detector = DiceDetector(
            model_path=model_path,
            confidence_threshold=self.settings.min_confidence_threshold,
        )
        self.recognizer = DiceRecognizer()
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the vision pipeline."""
        detector_ok = self.detector.load_model()
        ocr_ok = self.recognizer.load_ocr()
        self._initialized = detector_ok
        return self._initialized

    def process_frame(
        self,
        frame: np.ndarray,
        expected_roll: ExpectedRoll | None = None,
    ) -> list[DetectedDie]:
        """Process a frame and return detected dice.

        Args:
            frame: Input frame (BGR format).
            expected_roll: Optional expected roll for filtering.

        Returns:
            List of detected dice with values.
        """
        if not self._initialized:
            self.initialize()

        # Apply detection zone if configured
        if self.settings.detection_zone:
            x, y, w, h = self.settings.detection_zone
            frame = frame[y : y + h, x : x + w]

        # Detect dice
        detections = self.detector.detect(frame)

        # Recognize values
        detected_dice = []
        for bbox, dice_type, confidence in detections:
            cropped = self.detector.crop_die(frame, bbox)
            die = self.recognizer.recognize(cropped, dice_type, confidence, bbox)
            detected_dice.append(die)

        # Filter by expected roll if provided
        if expected_roll:
            detected_dice = self._filter_by_expected(detected_dice, expected_roll)

        return detected_dice

    def _filter_by_expected(
        self,
        detected: list[DetectedDie],
        expected: ExpectedRoll,
    ) -> list[DetectedDie]:
        """Filter detected dice by expected roll."""
        expected_types = {dt for dt, _ in expected.expected_dice}

        # Keep dice that match expected types, or all if no filter
        if not expected_types:
            return detected

        return [d for d in detected if d.dice_type in expected_types]

    def draw_results(
        self,
        frame: np.ndarray,
        detected_dice: list[DetectedDie],
    ) -> np.ndarray:
        """Draw detection results on frame."""
        result = frame.copy()

        colors = {
            "D4": (255, 0, 0),
            "D6": (0, 255, 0),
            "D8": (0, 255, 255),
            "D10": (255, 255, 0),
            "D12": (255, 0, 255),
            "D20": (0, 165, 255),
            "D100": (128, 0, 128),
            "D100_TENS": (128, 0, 128),
            "D100_ONES": (128, 0, 128),
        }

        for die in detected_dice:
            color = colors.get(die.dice_type.value, (128, 128, 128))
            x1, y1, x2, y2 = die.bbox.to_xyxy()

            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)

            label = f"{die.dice_type.value}={die.final_value}"
            if die.confidence < 0.7:
                label += " ?"

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

    def save_sample(
        self,
        frame: np.ndarray,
        die: DetectedDie,
        corrected_value: int,
        corrected_type,
    ) -> None:
        """Save a corrected sample for training."""
        # This would save to the training dataset
        pass
