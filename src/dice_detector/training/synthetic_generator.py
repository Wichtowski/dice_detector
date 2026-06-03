import json
import random
from datetime import datetime
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from dice_detector.models import (
    AmbiguityReason,
    BoundingBox,
    D4Style,
    DiceAnnotation,
    DiceMaterial,
    DiceType,
    ImageAnnotation,
    NumberStyle,
    SpecialValue,
    SyntheticGenerationConfig,
)


class SyntheticDiceGenerator:
    DICE_VALUES: dict[DiceType, list[int | str]] = {
        DiceType.D4: [1, 2, 3, 4],
        DiceType.D6: [1, 2, 3, 4, 5, 6],
        DiceType.D8: [1, 2, 3, 4, 5, 6, 7, 8],
        DiceType.D10: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        DiceType.D12: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        DiceType.D20: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        DiceType.D100: ["00", "10", "20", "30", "40", "50", "60", "70", "80", "90"],
        DiceType.D100_TENS: ["00", "10", "20", "30", "40", "50", "60", "70", "80", "90"],
    }

    DICE_SHAPES: dict[DiceType, str] = {
        DiceType.D4: "triangle",
        DiceType.D6: "square",
        DiceType.D8: "diamond",
        DiceType.D10: "kite",
        DiceType.D12: "pentagon",
        DiceType.D20: "triangle",
        DiceType.D100: "kite",
        DiceType.D100_TENS: "kite",
    }

    def __init__(self, config: SyntheticGenerationConfig | None = None):
        self.config = config or SyntheticGenerationConfig()
        self.output_dir = Path(self.config.output_dir)
        self.images_dir = self.output_dir / "images"
        self.annotations_dir = self.output_dir / "annotations"

        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)
            np.random.seed(self.config.random_seed)

    def generate_dataset(self, progress_callback: Callable[[int, int], None] | None = None) -> int:
        self._ensure_dirs()

        generated = 0
        for i in range(self.config.num_images):
            try:
                self._generate_single_image(i)
                generated += 1

                if progress_callback:
                    progress_callback(i + 1, self.config.num_images)

            except Exception as e:
                print(f"Error generating image {i}: {e}")

        # Save generation metadata
        self._save_generation_metadata(generated)

        return generated

    def _ensure_dirs(self) -> None:
        """Create output directories."""
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.annotations_dir.mkdir(parents=True, exist_ok=True)

    def _generate_single_image(self, index: int) -> None:
        """Generate a single synthetic image with annotations.

        Args:
            index: Image index for naming.
        """
        # Create background
        image = self._create_background()

        # Determine number of dice
        num_dice = random.randint(
            self.config.min_dice_per_image,
            self.config.max_dice_per_image,
        )

        # Generate dice placements
        dice_annotations = []
        occupied_regions: list[tuple[int, int, int, int]] = []

        for _ in range(num_dice):
            # Select dice type
            dice_type = random.choice(self.config.dice_types)

            # Generate die annotation
            annotation = self._generate_die(
                image, dice_type, occupied_regions
            )

            if annotation:
                dice_annotations.append(annotation)
                # Mark region as occupied
                bbox = annotation.bbox
                occupied_regions.append(
                    (bbox.x, bbox.y, bbox.x + bbox.width, bbox.y + bbox.height)
                )

        # Apply global augmentations
        if self.config.enable_blur and random.random() < 0.3:
            image = self._apply_blur(image)

        if self.config.enable_noise and random.random() < 0.3:
            image = self._apply_noise(image)

        if self.config.enable_compression_artifacts and random.random() < 0.2:
            image = self._apply_compression_artifacts(image)

        # Save image and annotation
        image_id = f"synthetic_{index:06d}"
        image_path = self.images_dir / f"{image_id}.jpg"
        cv2.imwrite(str(image_path), image)

        image_annotation = ImageAnnotation(
            image_path=str(image_path),
            image_width=self.config.image_width,
            image_height=self.config.image_height,
            dice=dice_annotations,
            source="synthetic",
            timestamp=datetime.now().isoformat(),
            metadata={
                "generator_version": "1.0",
                "config_hash": hash(str(self.config.model_dump())),
            },
        )

        annotation_path = self.annotations_dir / f"{image_id}.json"
        with open(annotation_path, "w") as f:
            f.write(image_annotation.model_dump_json(indent=2))

    def _create_background(self) -> np.ndarray:
        """Create a background image.

        Returns:
            Background image as numpy array.
        """
        h, w = self.config.image_height, self.config.image_width

        # Try to load a background image
        if self.config.background_images_dir:
            bg_dir = Path(self.config.background_images_dir)
            if bg_dir.exists():
                bg_files = list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png"))
                if bg_files:
                    bg_path = random.choice(bg_files)
                    bg = cv2.imread(str(bg_path))
                    if bg is not None:
                        return cv2.resize(bg, (w, h))

        # Generate synthetic background
        if self.config.use_solid_backgrounds and random.random() < 0.5:
            # Solid color with slight variation
            base_color = np.array([
                random.randint(20, 200),
                random.randint(20, 200),
                random.randint(20, 200),
            ], dtype=np.uint8)
            image = np.full((h, w, 3), base_color, dtype=np.uint8)

            # Add subtle gradient
            gradient = np.linspace(0.9, 1.1, h).reshape(-1, 1, 1)
            image = np.clip(image * gradient, 0, 255).astype(np.uint8)

        elif self.config.use_noise_backgrounds:
            # Noise texture
            image = np.random.randint(50, 150, (h, w, 3), dtype=np.uint8)
            image = cv2.GaussianBlur(image, (15, 15), 0)

        else:
            # Default gray
            image = np.full((h, w, 3), 128, dtype=np.uint8)

        return image

    def _generate_die(
        self,
        image: np.ndarray,
        dice_type: DiceType,
        occupied: list[tuple[int, int, int, int]],
    ) -> DiceAnnotation | None:
        """Generate a single die on the image.

        Args:
            image: Image to draw on.
            dice_type: Type of die to generate.
            occupied: List of occupied regions (x1, y1, x2, y2).

        Returns:
            DiceAnnotation or None if placement failed.
        """
        h, w = image.shape[:2]

        # Determine die size
        base_size = random.randint(40, 100)
        die_w = int(base_size * random.uniform(0.9, 1.1))
        die_h = int(base_size * random.uniform(0.9, 1.1))

        # Find valid placement
        max_attempts = 50
        for _ in range(max_attempts):
            x = random.randint(10, w - die_w - 10)
            y = random.randint(10, h - die_h - 10)

            # Check overlap with occupied regions
            overlaps = False
            for ox1, oy1, ox2, oy2 in occupied:
                if not (x + die_w < ox1 or x > ox2 or y + die_h < oy1 or y > oy2):
                    overlaps = True
                    break

            if not overlaps:
                break
        else:
            return None

        # Select value
        value = self._select_value(dice_type)

        # Determine if this should be a special case
        special_value = None
        ambiguous = False
        ambiguity_reasons = []

        # Special symbol cases
        if self.config.enable_special_symbol_cases:
            if dice_type == DiceType.D20 and random.random() < self.config.special_symbol_ratio:
                if value == 20:
                    special_value = random.choice([
                        SpecialValue.NAT20_SYMBOL,
                        SpecialValue.MAX_VALUE_SYMBOL,
                        SpecialValue.STAR_SYMBOL,
                        SpecialValue.LOGO_SYMBOL,
                    ])
                elif value == 1:
                    special_value = random.choice([
                        SpecialValue.MIN_VALUE_SYMBOL,
                        SpecialValue.SKULL_SYMBOL,
                    ])

        # 6/9 ambiguity cases
        if self.config.enable_6_9_ambiguity_cases:
            if value in (6, 9) and random.random() < self.config.ambiguity_case_ratio:
                ambiguous = True
                ambiguity_reasons.append(AmbiguityReason.POSSIBLE_6_9)

        # D4 difficult cases
        d4_style = None
        if dice_type == DiceType.D4:
            d4_style = random.choice([D4Style.TOP_VERTEX, D4Style.BOTTOM_EDGE])
            if self.config.enable_d4_difficult_cases and random.random() < self.config.difficult_d4_ratio:
                ambiguous = True
                ambiguity_reasons.append(AmbiguityReason.D4_AMBIGUOUS_FACE)

        # Generate orientation
        orientation = random.uniform(0, 360)

        # Determine material/style
        material = DiceMaterial.OPAQUE
        if self.config.enable_transparent_dice and random.random() < 0.1:
            material = DiceMaterial.TRANSPARENT
        elif self.config.enable_metallic_dice and random.random() < 0.1:
            material = DiceMaterial.METALLIC

        # Draw the die
        self._draw_die(
            image, x, y, die_w, die_h,
            dice_type, value, orientation,
            special_value, material,
        )

        # Create annotation
        bbox = BoundingBox(x=x, y=y, width=die_w, height=die_h)

        return DiceAnnotation(
            bbox=bbox,
            dice_type=dice_type,
            value=value,
            special_value=special_value,
            orientation_degrees=orientation,
            ambiguous=ambiguous,
            ambiguity_reasons=ambiguity_reasons,
            d4_style=d4_style,
            has_6_9_marker=value in (6, 9) and not ambiguous,
            number_style=NumberStyle.PAINTED,
        )

    def _select_value(self, dice_type: DiceType) -> int | str:
        """Select a value for the given dice type.

        Args:
            dice_type: Type of die.

        Returns:
            Selected value.
        """
        values = self.DICE_VALUES.get(dice_type, [1])
        return random.choice(values)

    def _draw_die(
        self,
        image: np.ndarray,
        x: int, y: int,
        w: int, h: int,
        dice_type: DiceType,
        value: int | str,
        orientation: float,
        special_value: SpecialValue | None,
        material: DiceMaterial,
    ) -> None:
        """Draw a die on the image.

        Args:
            image: Image to draw on.
            x, y: Top-left position.
            w, h: Size.
            dice_type: Type of die.
            value: Value to display.
            orientation: Rotation angle.
            special_value: Optional special symbol.
            material: Die material.
        """
        # Generate die colors
        if material == DiceMaterial.METALLIC:
            die_color = (180, 180, 200)
            text_color = (40, 40, 40)
        elif material == DiceMaterial.TRANSPARENT:
            die_color = (200, 200, 220)
            text_color = (60, 60, 80)
        else:
            # Random opaque color
            die_color = (
                random.randint(50, 230),
                random.randint(50, 230),
                random.randint(50, 230),
            )
            # Contrasting text color
            brightness = sum(die_color) / 3
            text_color = (20, 20, 20) if brightness > 128 else (235, 235, 235)

        # Draw die shape
        shape = self.DICE_SHAPES.get(dice_type, "square")
        center = (x + w // 2, y + h // 2)

        if shape == "triangle":
            pts = self._get_triangle_points(center, w, h, orientation)
            cv2.fillPoly(image, [pts], die_color)
            cv2.polylines(image, [pts], True, self._darken(die_color), 2)

        elif shape == "square":
            pts = self._get_rotated_rect_points(center, w, h, orientation)
            cv2.fillPoly(image, [pts], die_color)
            cv2.polylines(image, [pts], True, self._darken(die_color), 2)

        elif shape == "diamond":
            pts = self._get_diamond_points(center, w, h, orientation)
            cv2.fillPoly(image, [pts], die_color)
            cv2.polylines(image, [pts], True, self._darken(die_color), 2)

        elif shape == "pentagon":
            pts = self._get_pentagon_points(center, w, h, orientation)
            cv2.fillPoly(image, [pts], die_color)
            cv2.polylines(image, [pts], True, self._darken(die_color), 2)

        elif shape == "kite":
            pts = self._get_kite_points(center, w, h, orientation)
            cv2.fillPoly(image, [pts], die_color)
            cv2.polylines(image, [pts], True, self._darken(die_color), 2)

        else:
            # Default rectangle
            cv2.rectangle(image, (x, y), (x + w, y + h), die_color, -1)
            cv2.rectangle(image, (x, y), (x + w, y + h), self._darken(die_color), 2)

        # Draw value or symbol
        if special_value:
            self._draw_symbol(image, center, min(w, h) // 2, special_value, text_color)
        else:
            self._draw_value(image, center, value, text_color, orientation)

        # Add shadow
        if self.config.enable_shadows and random.random() < 0.5:
            self._add_shadow(image, x, y, w, h)

    def _draw_value(
        self,
        image: np.ndarray,
        center: tuple[int, int],
        value: int | str,
        color: tuple[int, int, int],
        orientation: float,
    ) -> None:
        """Draw the value text on the die"""
        text = str(value)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8 if len(text) == 1 else 0.6
        thickness = 2

        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        text_x = center[0] - text_w // 2
        text_y = center[1] + text_h // 2

        cv2.putText(image, text, (text_x, text_y), font, font_scale, color, thickness)

        if text in ("6", "9"):
            marker_y = text_y + 5
            marker_x1 = text_x
            marker_x2 = text_x + text_w
            cv2.line(image, (marker_x1, marker_y), (marker_x2, marker_y), color, 1)

    def _draw_symbol(
        self,
        image: np.ndarray,
        center: tuple[int, int],
        size: int,
        symbol: SpecialValue,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a special symbol on the die"""
        if symbol in (SpecialValue.STAR_SYMBOL, SpecialValue.NAT20_SYMBOL, SpecialValue.MAX_VALUE_SYMBOL):
            # Draw star
            self._draw_star(image, center, size, color)
        elif symbol in (SpecialValue.SKULL_SYMBOL, SpecialValue.MIN_VALUE_SYMBOL):
            # Draw skull-like shape
            self._draw_skull(image, center, size, color)
        elif symbol == SpecialValue.LOGO_SYMBOL:
            # Draw generic logo shape
            self._draw_logo(image, center, size, color)
        else:
            # Draw question mark for unknown
            cv2.putText(image, "?", (center[0] - 10, center[1] + 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    def _draw_star(
        self,
        image: np.ndarray,
        center: tuple[int, int],
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        pts = []
        for i in range(10):
            angle = np.pi / 2 + i * np.pi / 5
            r = size if i % 2 == 0 else size // 2
            px = int(center[0] + r * np.cos(angle))
            py = int(center[1] - r * np.sin(angle))
            pts.append([px, py])
        pts = np.array(pts, dtype=np.int32)
        cv2.fillPoly(image, [pts], color)

    def _draw_skull(
        self,
        image: np.ndarray,
        center: tuple[int, int],
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        # Head circle
        cv2.circle(image, center, size // 2, color, -1)
        # Eyes
        eye_y = center[1] - size // 6
        cv2.circle(image, (center[0] - size // 4, eye_y), size // 8, (0, 0, 0), -1)
        cv2.circle(image, (center[0] + size // 4, eye_y), size // 8, (0, 0, 0), -1)
        # Nose
        cv2.circle(image, (center[0], center[1] + size // 8), size // 12, (0, 0, 0), -1)

    def _draw_logo(
        self,
        image: np.ndarray,
        center: tuple[int, int],
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        pts = np.array([
            [center[0], center[1] - size],
            [center[0] + size // 2, center[1]],
            [center[0] + size // 4, center[1] + size // 2],
            [center[0], center[1] + size // 4],
            [center[0] - size // 4, center[1] + size // 2],
            [center[0] - size // 2, center[1]],
        ], dtype=np.int32)
        cv2.fillPoly(image, [pts], color)

    def _get_triangle_points(
        self,
        center: tuple[int, int],
        w: int, h: int,
        angle: float,
    ) -> np.ndarray:
        pts = np.array([
            [0, -h // 2],
            [-w // 2, h // 2],
            [w // 2, h // 2],
        ], dtype=np.float32)
        return self._rotate_points(pts, center, angle)

    def _get_rotated_rect_points(
        self,
        center: tuple[int, int],
        w: int, h: int,
        angle: float,
    ) -> np.ndarray:
        pts = np.array([
            [-w // 2, -h // 2],
            [w // 2, -h // 2],
            [w // 2, h // 2],
            [-w // 2, h // 2],
        ], dtype=np.float32)
        return self._rotate_points(pts, center, angle)

    def _get_diamond_points(
        self,
        center: tuple[int, int],
        w: int, h: int,
        angle: float,
    ) -> np.ndarray:
        pts = np.array([
            [0, -h // 2],
            [w // 2, 0],
            [0, h // 2],
            [-w // 2, 0],
        ], dtype=np.float32)
        return self._rotate_points(pts, center, angle)

    def _get_pentagon_points(
        self,
        center: tuple[int, int],
        w: int, h: int,
        angle: float,
    ) -> np.ndarray:
        pts = []
        for i in range(5):
            a = np.pi / 2 + i * 2 * np.pi / 5
            px = w // 2 * np.cos(a)
            py = h // 2 * np.sin(a)
            pts.append([px, -py])
        return self._rotate_points(np.array(pts, dtype=np.float32), center, angle)

    def _get_kite_points(
        self,
        center: tuple[int, int],
        w: int, h: int,
        angle: float,
    ) -> np.ndarray:
        pts = np.array([
            [0, -h // 2],
            [w // 2, -h // 6],
            [w // 3, h // 2],
            [-w // 3, h // 2],
            [-w // 2, -h // 6],
        ], dtype=np.float32)
        return self._rotate_points(pts, center, angle)

    def _rotate_points(
        self,
        pts: np.ndarray,
        center: tuple[int, int],
        angle: float,
    ) -> np.ndarray:
        rad = np.radians(angle)
        cos_a, sin_a = np.cos(rad), np.sin(rad)
        rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
        rotated = pts @ rotation.T
        rotated[:, 0] += center[0]
        rotated[:, 1] += center[1]
        return rotated.astype(np.int32)

    def _darken(self, color: tuple[int, int, int], factor: float = 0.7) -> tuple[int, int, int]:
        return tuple(int(c * factor) for c in color)

    def _add_shadow(
        self,
        image: np.ndarray,
        x: int, y: int,
        w: int, h: int,
    ) -> None:
        shadow_offset = 5
        shadow_color = (30, 30, 30)

        sx = x + shadow_offset
        sy = y + shadow_offset
        sw = min(w, image.shape[1] - sx)
        sh = min(h, image.shape[0] - sy)

        if sw > 0 and sh > 0:
            roi = image[sy:sy + sh, sx:sx + sw]
            shadow = np.full_like(roi, shadow_color)
            cv2.addWeighted(roi, 0.7, shadow, 0.3, 0, roi)

    def _apply_blur(self, image: np.ndarray) -> np.ndarray:
        if random.random() < 0.5:
            ksize = random.choice([3, 5, 7])
            return cv2.GaussianBlur(image, (ksize, ksize), 0)
        else:
            size = random.randint(5, 15)
            kernel = np.zeros((size, size))
            kernel[size // 2, :] = 1
            kernel = kernel / size
            angle = random.uniform(0, 180)
            M = cv2.getRotationMatrix2D((size // 2, size // 2), angle, 1)
            kernel = cv2.warpAffine(kernel, M, (size, size))
            return cv2.filter2D(image, -1, kernel)

    def _apply_noise(self, image: np.ndarray) -> np.ndarray:
        """Apply gaussian noise."""
        noise = np.random.normal(0, random.uniform(5, 20), image.shape)
        noisy = image.astype(np.float32) + noise
        return np.clip(noisy, 0, 255).astype(np.uint8)

    def _apply_compression_artifacts(self, image: np.ndarray) -> np.ndarray:
        """Apply JPEG compression artifacts."""
        quality = random.randint(30, 70)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, encoded = cv2.imencode(".jpg", image, encode_param)
        return cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    def _save_generation_metadata(self, num_generated: int) -> None:
        """Save metadata about the generation run."""
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "num_images": num_generated,
            "config": self.config.model_dump(),
        }

        metadata_path = self.output_dir / "generation_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)


def generate_synthetic_dataset(
    config: SyntheticGenerationConfig | None = None,
    output_dir: str | None = None,
    num_images: int | None = None,
) -> int:
    """Convenience function to generate a synthetic dataset"""
    if config is None:
        config = SyntheticGenerationConfig()

    if output_dir:
        config.output_dir = output_dir

    if num_images:
        config.num_images = num_images

    generator = SyntheticDiceGenerator(config)

    def progress(current: int, total: int) -> None:
        if current % 100 == 0 or current == total:
            print(f"Generated {current}/{total} images")

    return generator.generate_dataset(progress_callback=progress)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic dice training data")
    parser.add_argument("--output", type=str, default="data/generated/synthetic",
                       help="Output directory")
    parser.add_argument("--num-images", type=int, default=1000,
                       help="Number of images to generate")
    parser.add_argument("--seed", type=int, default=None,
                       help="Random seed for reproducibility")

    args = parser.parse_args()

    config = SyntheticGenerationConfig(
        output_dir=args.output,
        num_images=args.num_images,
        random_seed=args.seed,
    )

    print(f"Generating {args.num_images} synthetic images to {args.output}")
    generated = generate_synthetic_dataset(config)
    print(f"Done! Generated {generated} images.")
