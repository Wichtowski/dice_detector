import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from dice_detector.models import CalibrationSettings, CameraDevice


class CameraCapture:
    """Handles webcam capture and frame processing."""

    def __init__(self, settings: Optional[CalibrationSettings] = None):
        """Initialize camera capture.

        Args:
            settings: Calibration settings for camera configuration.
        """
        self.settings = settings or CalibrationSettings()
        self.cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._frame_callbacks: list[Callable[[np.ndarray], None]] = []
        self._last_frame_time = 0.0
        self._fps = 0.0

    def start(self) -> bool:
        """Start camera capture.

        Returns:
            True if camera started successfully, False otherwise.
        """
        if self._running:
            return True

        self.cap = cv2.VideoCapture(self.settings.camera_index)
        if not self.cap.isOpened():
            return False

        # Configure camera
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.frame_height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop camera capture."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self.cap:
            self.cap.release()
            self.cap = None

    def _capture_loop(self) -> None:
        """Main capture loop running in separate thread."""
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                continue

            if self.settings.lighting_adjustment != 1.0:
                frame = cv2.convertScaleAbs(
                    frame, alpha=self.settings.lighting_adjustment, beta=0
                )

            if self.settings.detection_zone:
                x, y, w, h = self.settings.detection_zone
                # Store full frame but mark detection zone
                frame_with_zone = frame.copy()
                cv2.rectangle(frame_with_zone, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Calculate FPS
            current_time = time.time()
            if self._last_frame_time > 0:
                self._fps = 1.0 / (current_time - self._last_frame_time)
            self._last_frame_time = current_time

            with self._frame_lock:
                self._frame = frame

            for callback in self._frame_callbacks:
                try:
                    callback(frame)
                except Exception:
                    pass

    def get_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._frame.copy() if self._frame is not None else None

    def get_detection_frame(self) -> Optional[np.ndarray]:
        frame = self.get_frame()
        if frame is None:
            return None

        if self.settings.detection_zone:
            x, y, w, h = self.settings.detection_zone
            return frame[y : y + h, x : x + w]
        return frame

    def add_frame_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        self._frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def is_running(self) -> bool:
        return self._running

    def list_cameras(self) -> list[int]:
        return [device.index for device in CameraDevice.list_available()]

    @staticmethod
    def list_devices() -> list[CameraDevice]:
        return CameraDevice.list_available()

    def set_detection_zone(self, x: int, y: int, width: int, height: int) -> None:
        self.settings.detection_zone = (x, y, width, height)

    def clear_detection_zone(self) -> None:
        self.settings.detection_zone = None

    def capture_snapshot(self, filepath: str) -> bool:
        frame = self.get_frame()
        if frame is None:
            return False
        return cv2.imwrite(filepath, frame)
