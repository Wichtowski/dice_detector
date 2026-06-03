"""Multi-output vision pipeline for dice detection."""

from typing import Optional

import numpy as np

from dice_detector.models import (
    CalibrationSettings,
    DicePrediction,
    FramePrediction,
    frame_prediction_to_detected_dice,
)


class MultiOutputPipeline:
    """Vision pipeline using multi-output model for detection, type, and value."""

    def __init__(
        self,
        model_path: str | None = None,
        settings: CalibrationSettings | None = None,
        device: str | None = None,
    ):
        self.model_path = model_path
        self.settings = settings or CalibrationSettings()
        self.device = device
        self.model = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize the multi-output model."""
        if self.model_path is None:
            print("No model path provided")
            return False

        try:
            from ultralytics import YOLO

            self.model = YOLO(self.model_path)
            self._initialized = True
            return True
        except Exception as e:
            print(f"Failed to load model: {e}")
            return False

    def process_frame(self, frame: np.ndarray, frame_id: str = "0") -> FramePrediction:
        """Process a frame and return predictions.

        Args:
            frame: Input frame (BGR format).
            frame_id: Unique frame identifier.

        Returns:
            FramePrediction with all detected dice.
        """
        import time

        start_time = time.time()

        if not self._initialized:
            self.initialize()

        predictions: list[DicePrediction] = []

        if self.model is not None:
            results = self.model(frame, verbose=False)

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for i in range(len(boxes)):
                    # Extract detection info
                    # This is a simplified version - actual implementation
                    # would depend on the specific model architecture
                    pass

        processing_time = (time.time() - start_time) * 1000

        return FramePrediction(
            frame_id=frame_id,
            predictions=predictions,
            processing_time_ms=processing_time,
        )

    def get_detected_dice(self, frame: np.ndarray):
        """Convenience method to get DetectedDie objects."""
        frame_pred = self.process_frame(frame)
        return frame_prediction_to_detected_dice(frame_pred)
