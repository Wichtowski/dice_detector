import math
from typing import Optional

import cv2
import numpy as np

from ..models import BoundingBox, DiceType, DetectedDie


class DiceRecognizer:
    def __init__(self):
        self.ocr_reader = None
        self._ocr_loaded = False

    def load_ocr(self) -> bool:
        try:
            import easyocr

            self.ocr_reader = easyocr.Reader(["en"], gpu=False)
            self._ocr_loaded = True
            return True
        except Exception as e:
            print(f"Failed to load OCR: {e}")
            return False

    def recognize(
        self,
        cropped_image: np.ndarray,
        dice_type: DiceType,
        detection_confidence: float,
        bbox: BoundingBox,
    ) -> DetectedDie:
        """Recognize the value of a cropped die image

        Args:
            cropped_image: Cropped image of the die
            dice_type: Detected type of the die
            detection_confidence: Confidence from object detection
            bbox: Original bounding box

        Returns:
            DetectedDie with recognized value and confidence
        """
        processed = self._preprocess(cropped_image)

        orientation = self._estimate_orientation(processed)

        if abs(orientation) > 10:
            processed = self._rotate_image(processed, -orientation)

        if dice_type == DiceType.D4:
            value, conf, notes = self._recognize_d4(processed)
        elif dice_type == DiceType.D6:
            value, conf, notes = self._recognize_d6(processed)
        elif dice_type in (DiceType.D100_TENS, DiceType.D100_ONES):
            value, conf, notes = self._recognize_d100(processed, dice_type)
        else:
            value, conf, notes = self._recognize_numeric(processed, dice_type)

        final_confidence = detection_confidence * conf

        return DetectedDie(
            dice_type=dice_type,
            detected_value=value,
            confidence=final_confidence,
            bbox=bbox,
            orientation_degrees=orientation,
            notes=notes,
        )

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for better recognition"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)

        return denoised

    def _estimate_orientation(self, image: np.ndarray) -> float:
        """Estimate the orientation of text/numbers in the image"""

        # Use edge detection and Hough lines to estimate orientation
        edges = cv2.Canny(image, 50, 150)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 30, minLineLength=20, maxLineGap=10)

        if lines is None or len(lines) == 0:
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            angles.append(angle)

        # Find dominant angle
        if angles:
            # Normalize angles to -45 to 45 range
            normalized = [(a % 90) - 45 if (a % 90) > 45 else (a % 90) for a in angles]
            return np.median(normalized)

        return 0.0

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """Rotate image by given angle"""
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
        return rotated

    def _recognize_d4(self, image: np.ndarray) -> tuple[int, float, list[str]]:
        """Recognize D4 value - special handling for tetrahedron

        D4 values can appear in different positions depending on design:
        - Near top vertex
        - Along bottom edge
        - On multiple faces"""
        notes = []

        value, conf = self._ocr_read_number(image, max_value=4)

        if value is not None and 1 <= value <= 4:
            if conf < 0.7:
                notes.append("D4 detection may be unreliable")
            return value, conf * 0.8, notes  # Reduce confidence for D4

        # Try reading from different regions
        h, w = image.shape[:2]

        # Try top region
        top_region = image[: h // 3, :]
        value, conf = self._ocr_read_number(top_region, max_value=4)
        if value is not None and 1 <= value <= 4:
            notes.append("Value read from top region")
            return value, conf * 0.7, notes

        # Try bottom region
        bottom_region = image[2 * h // 3 :, :]
        value, conf = self._ocr_read_number(bottom_region, max_value=4)
        if value is not None and 1 <= value <= 4:
            notes.append("Value read from bottom region")
            return value, conf * 0.7, notes

        notes.append("D4 value unclear - manual confirmation required")
        return 1, 0.3, notes

    def _recognize_d6(self, image: np.ndarray) -> tuple[int, float, list[str]]:
        """Recognize D6 value - handles both pips and numbers.

        Args:
            image: Preprocessed image.

        Returns:
            (value, confidence, notes)
        """
        notes = []

        # First try to detect pips (dots)
        pip_count, pip_conf = self._count_pips(image)
        if pip_count is not None and 1 <= pip_count <= 6 and pip_conf > 0.6:
            return pip_count, pip_conf, notes

        # Fall back to OCR for numbered D6
        value, conf = self._ocr_read_number(image, max_value=6)
        if value is not None and 1 <= value <= 6:
            return value, conf, notes

        # If pip detection had some result, use it
        if pip_count is not None and 1 <= pip_count <= 6:
            notes.append("Pip count uncertain")
            return pip_count, pip_conf, notes

        notes.append("D6 value unclear")
        return 1, 0.3, notes

    def _count_pips(self, image: np.ndarray) -> tuple[Optional[int], float]:
        """Count pips (dots) on a D6.

        Args:
            image: Preprocessed image.

        Returns:
            (pip_count, confidence)
        """
        # Apply threshold
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by circularity and size
        h, w = image.shape[:2]
        min_area = (min(h, w) * 0.05) ** 2
        max_area = (min(h, w) * 0.3) ** 2

        pip_candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                perimeter = cv2.arcLength(contour, True)
                if perimeter > 0:
                    circularity = 4 * np.pi * area / (perimeter**2)
                    if circularity > 0.6:  # Reasonably circular
                        pip_candidates.append(contour)

        pip_count = len(pip_candidates)
        if 1 <= pip_count <= 6:
            confidence = 0.7 + (0.05 * min(pip_count, 3))  # Higher confidence for common values
            return pip_count, confidence

        return None, 0.0

    def _recognize_d100(
        self, image: np.ndarray, dice_type: DiceType
    ) -> tuple[int, float, list[str]]:
        """Recognize D100 component value.

        Args:
            image: Preprocessed image.
            dice_type: D100_TENS or D100_ONES.

        Returns:
            (value, confidence, notes)
        """
        notes = []

        if dice_type == DiceType.D100_TENS:
            # Percentile die: 00, 10, 20, ..., 90
            value, conf = self._ocr_read_number(image, max_value=90)
            if value is not None:
                # Round to nearest 10
                rounded = (value // 10) * 10
                if rounded == 0:
                    rounded = 0  # 00
                if rounded > 90:
                    rounded = 90
                return rounded, conf, notes
            notes.append("Percentile die value unclear")
            return 0, 0.3, notes
        else:
            # Single digit die: 0-9
            value, conf = self._ocr_read_number(image, max_value=9)
            if value is not None and 0 <= value <= 9:
                return value, conf, notes
            notes.append("D100 ones digit unclear")
            return 0, 0.3, notes

    def _recognize_numeric(
        self, image: np.ndarray, dice_type: DiceType
    ) -> tuple[int, float, list[str]]:
        """Recognize numeric value for D8, D10, D12, D20.

        Args:
            image: Preprocessed image.
            dice_type: Type of die.

        Returns:
            (value, confidence, notes)
        """
        notes = []
        max_value = dice_type.max_value

        # Try OCR
        value, conf = self._ocr_read_number(image, max_value=max_value)

        if value is not None:
            # Handle 6/9 ambiguity
            if value in (6, 9):
                is_six, six_conf = self._disambiguate_6_9(image, value)
                if six_conf < 0.7:
                    notes.append("6/9 ambiguity")
                value = 6 if is_six else 9
                conf = conf * six_conf

            # Handle D20 special symbol for 20
            if dice_type == DiceType.D20 and value == 20:
                is_symbol, symbol_conf = self._check_d20_symbol(image)
                if is_symbol:
                    notes.append("D20 symbol detected as 20")
                    conf = conf * symbol_conf

            if 1 <= value <= max_value:
                return value, conf, notes

        # Check for D20 symbol if OCR failed
        if dice_type == DiceType.D20:
            is_symbol, symbol_conf = self._check_d20_symbol(image)
            if is_symbol:
                notes.append("D20 symbol detected - treating as 20")
                return 20, symbol_conf * 0.7, notes

        notes.append(f"{dice_type.value} value unclear")
        return 1, 0.3, notes

    def _ocr_read_number(
        self, image: np.ndarray, max_value: int
    ) -> tuple[Optional[int], float]:
        """Read a number from image using OCR.

        Args:
            image: Preprocessed image.
            max_value: Maximum expected value.

        Returns:
            (value, confidence) or (None, 0.0)
        """
        if not self._ocr_loaded or self.ocr_reader is None:
            return self._fallback_read_number(image, max_value)

        try:
            # Convert grayscale to BGR for EasyOCR
            if len(image.shape) == 2:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            else:
                image_bgr = image

            results = self.ocr_reader.readtext(
                image_bgr,
                allowlist="0123456789",
                paragraph=False,
            )

            best_value = None
            best_conf = 0.0

            for bbox, text, conf in results:
                try:
                    value = int(text)
                    if 0 <= value <= max_value and conf > best_conf:
                        best_value = value
                        best_conf = conf
                except ValueError:
                    continue

            return best_value, best_conf

        except Exception:
            return self._fallback_read_number(image, max_value)

    def _fallback_read_number(
        self, image: np.ndarray, max_value: int
    ) -> tuple[Optional[int], float]:
        """Fallback number reading using template matching or contour analysis.

        Args:
            image: Preprocessed image.
            max_value: Maximum expected value.

        Returns:
            (value, confidence) or (None, 0.0)
        """
        # Simple contour-based digit detection
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, 0.0

        # Count significant contours as rough digit estimate
        h, w = image.shape[:2]
        min_area = (min(h, w) * 0.1) ** 2

        digit_contours = [c for c in contours if cv2.contourArea(c) > min_area]
        num_digits = len(digit_contours)

        if num_digits == 1:
            # Single digit: 1-9
            return min(5, max_value), 0.4  # Return middle value with low confidence
        elif num_digits == 2:
            # Two digits: 10-99
            return min(15, max_value), 0.3

        return None, 0.0

    def _disambiguate_6_9(self, image: np.ndarray, detected: int) -> tuple[bool, float]:
        """Disambiguate between 6 and 9.

        Looks for orientation markers like dots or underlines.

        Args:
            image: Preprocessed image.
            detected: Initially detected value (6 or 9).

        Returns:
            (is_six, confidence)
        """
        h, w = image.shape[:2]

        # Look for underline/dot marker
        # Check bottom region for marker (indicates 6)
        bottom_region = image[int(h * 0.8) :, :]
        _, bottom_binary = cv2.threshold(
            bottom_region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        bottom_white = np.sum(bottom_binary > 0)

        # Check top region for marker (indicates 9)
        top_region = image[: int(h * 0.2), :]
        _, top_binary = cv2.threshold(
            top_region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        top_white = np.sum(top_binary > 0)

        # Compare marker presence
        total_pixels = h * w * 0.2
        bottom_ratio = bottom_white / total_pixels if total_pixels > 0 else 0
        top_ratio = top_white / total_pixels if total_pixels > 0 else 0

        if bottom_ratio > 0.1 and bottom_ratio > top_ratio * 1.5:
            # Marker at bottom - likely 6
            return True, 0.75
        elif top_ratio > 0.1 and top_ratio > bottom_ratio * 1.5:
            # Marker at top - likely 9
            return False, 0.75
        else:
            # No clear marker - use detected value with lower confidence
            return detected == 6, 0.5

    def _check_d20_symbol(self, image: np.ndarray) -> tuple[bool, float]:
        """Check if image contains a D20 special symbol instead of "20".

        Args:
            image: Preprocessed image.

        Returns:
            (is_symbol, confidence)
        """
        # Look for non-numeric content that could be a symbol
        # This is a simplified check - a proper implementation would use
        # a trained classifier for common D20 symbols

        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return False, 0.0

        # Analyze contour complexity
        total_area = sum(cv2.contourArea(c) for c in contours)
        total_perimeter = sum(cv2.arcLength(c, True) for c in contours)

        if total_perimeter > 0:
            complexity = total_area / (total_perimeter**2)
            # Symbols tend to have different complexity than numbers
            if complexity < 0.01 or complexity > 0.1:
                return True, 0.5  # Possibly a symbol

        return False, 0.0
