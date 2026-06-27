from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from dice_detector.models.dice import BoundingBox, DiceType


class AmbiguityReason(str, Enum):
    POSSIBLE_6_9 = "possible_6_9_confusion"
    LOW_CONFIDENCE_VALUE = "low_confidence_value"
    LOW_CONFIDENCE_TYPE = "low_confidence_type"
    D4_AMBIGUOUS_FACE = "d4_ambiguous_face"
    SPECIAL_SYMBOL_UNCERTAIN = "special_symbol_uncertain"
    D20_SYMBOL_UNCERTAIN = "d20_symbol_uncertain"
    OCCLUDED = "occluded"
    MOTION_BLUR = "motion_blur"
    PARTIAL_VISIBILITY = "partial_visibility"
    LOW_CONTRAST = "low_contrast"
    UNUSUAL_ORIENTATION = "unusual_orientation"


class SpecialValue(str, Enum):
    NAT20_SYMBOL = "nat20_symbol"
    MIN_VALUE_SYMBOL = "min_value_symbol"
    MAX_VALUE_SYMBOL = "max_value_symbol"
    CUSTOM_SYMBOL = "custom_symbol"
    UNKNOWN_SYMBOL = "unknown_symbol"
    SKULL_SYMBOL = "skull_symbol"
    STAR_SYMBOL = "star_symbol"
    LOGO_SYMBOL = "logo_symbol"


class D4Style(str, Enum):
    TOP_VERTEX = "top_vertex"
    BOTTOM_EDGE = "bottom_edge"
    BARREL = "barrel"
    FLOOR = "floor"
    STANDARD = "standard"
    UNKNOWN = "unknown"


class NumberStyle(str, Enum):
    PAINTED = "painted"
    ENGRAVED = "engraved"
    RAISED = "raised"
    TEXTURED = "textured"
    PIPS = "pips"
    UNKNOWN = "unknown"


class DiceMaterial(str, Enum):
    OPAQUE = "opaque"
    TRANSPARENT = "transparent"
    TRANSLUCENT = "translucent"
    METALLIC = "metallic"
    GLOSSY = "glossy"
    MATTE = "matte"


class DiceAnnotation(BaseModel):
    bbox: BoundingBox
    dice_type: DiceType
    value: int | str | None = Field(
        default=None,
        description="Numeric value or string for special cases like D100 '00'",
    )
    special_value: SpecialValue | None = Field(
        default=None,
        description="Special symbol on the face, if any",
    )
    ambiguous: bool = Field(
        default=False,
        description="Whether the annotation is uncertain",
    )
    ambiguity_reasons: list[AmbiguityReason] = Field(default_factory=list)
    d4_style: D4Style | None = Field(
        default=None,
        description="D4 interpretation style (top vertex vs bottom edge)",
    )
    visibility: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Visibility ratio (1.0 = fully visible, <1.0 = partially occluded)",
    )
    number_style: NumberStyle = Field(default=NumberStyle.UNKNOWN)

    @computed_field
    @property
    def is_6_or_9_value(self) -> bool:
        """True when the face value is 6 or 9 (potential confusion pair)."""
        return self.value in (6, 9)

    @computed_field
    @property
    def has_special_symbol(self) -> bool:
        return self.special_value is not None


class ImageAnnotation(BaseModel):
    image_path: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    dice: list[DiceAnnotation] = Field(default_factory=list)
    source: str = Field(
        default="unknown",
        description="Source of the annotation: manual, synthetic, blender, auto",
    )
    timestamp: str | None = None
    is_verified: bool = Field(
        default=False,
        description="Whether annotations have been human-verified",
    )
    metadata: dict = Field(default_factory=dict)

    @computed_field
    @property
    def dice_count(self) -> int:
        return len(self.dice)

    @computed_field
    @property
    def dice_types_present(self) -> list[DiceType]:
        return sorted(set(d.dice_type for d in self.dice), key=lambda t: t.value)


class DicePrediction(BaseModel):
    bbox: BoundingBox
    dice_type: DiceType | None = None
    value: int | str | None = None
    dice_type_confidence: float = Field(ge=0.0, le=1.0)
    value_confidence: float = Field(ge=0.0, le=1.0)
    detection_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Objectness/detection confidence",
    )
    orientation_degrees: float | None = Field(default=None, ge=0.0, lt=360.0)
    orientation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    special_value: SpecialValue | None = None
    special_value_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[AmbiguityReason] = Field(default_factory=list)
    requires_confirmation: bool = False

    @computed_field
    @property
    def overall_confidence(self) -> float:
        return self.detection_confidence * self.dice_type_confidence * self.value_confidence

    @computed_field
    @property
    def is_high_confidence(self) -> bool:
        return (
            self.overall_confidence >= 0.8
            and not self.requires_confirmation
            and len(self.warnings) == 0
        )


class FramePrediction(BaseModel):
    frame_id: str
    predictions: list[DicePrediction] = Field(default_factory=list)
    processing_time_ms: float | None = None
    model_version: str | None = None

    @computed_field
    @property
    def dice_count(self) -> int:
        return len(self.predictions)

    @computed_field
    @property
    def requires_confirmation(self) -> bool:
        return any(p.requires_confirmation for p in self.predictions)

    @computed_field
    @property
    def all_warnings(self) -> list[AmbiguityReason]:
        warnings = []
        for p in self.predictions:
            warnings.extend(p.warnings)
        return warnings


class SyntheticDiceConfig(BaseModel):
    dice_type: DiceType
    value: int | str
    special_value: SpecialValue | None = None
    orientation_degrees: float = Field(default=0.0, ge=0.0, lt=360.0)
    scale: float = Field(default=1.0, gt=0.0, le=3.0)
    material: DiceMaterial = DiceMaterial.OPAQUE
    d4_style: D4Style | None = None
    has_6_9_marker: bool = True


class SyntheticGenerationConfig(BaseModel):
    output_dir: str = "data/generated"
    num_images: int = Field(default=1000, gt=0)
    image_width: int = Field(default=1280, gt=0)
    image_height: int = Field(default=720, gt=0)
    min_dice_per_image: int = Field(default=1, ge=1)
    max_dice_per_image: int = Field(default=8, ge=1)
    dice_types: list[DiceType] = Field(
        default_factory=lambda: [
            DiceType.D4,
            DiceType.D6,
            DiceType.D8,
            DiceType.D10,
            DiceType.D12,
            DiceType.D20,
            DiceType.D100,
        ]
    )

    enable_blur: bool = True
    enable_noise: bool = True
    enable_perspective_transform: bool = True
    enable_occlusion: bool = True
    enable_shadows: bool = True
    enable_lighting_variation: bool = True
    enable_compression_artifacts: bool = False

    enable_6_9_ambiguity_cases: bool = True
    enable_special_symbol_cases: bool = True
    enable_d4_difficult_cases: bool = True
    enable_d100_percentile_cases: bool = True
    enable_low_contrast_cases: bool = True
    enable_transparent_dice: bool = False
    enable_metallic_dice: bool = False

    special_symbol_ratio: float = Field(default=0.1, ge=0.0, le=1.0)
    ambiguity_case_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    difficult_d4_ratio: float = Field(default=0.2, ge=0.0, le=1.0)

    background_images_dir: str | None = None
    use_solid_backgrounds: bool = True
    use_noise_backgrounds: bool = True

    random_seed: int | None = None


class BlenderGenerationConfig(BaseModel):
    output_dir: str = "data/generated/blender"
    num_images: int = Field(default=1000, gt=0)
    image_width: int = Field(default=1280, gt=0)
    image_height: int = Field(default=720, gt=0)
    min_dice_per_image: int = Field(default=1, ge=1)
    max_dice_per_image: int = Field(default=8, ge=1)

    dice_assets_dir: str = "synthetic/blender/assets/dice"
    materials_dir: str = "synthetic/blender/assets/materials"
    backgrounds_dir: str = "synthetic/blender/assets/backgrounds"
    hdri_dir: str = "synthetic/blender/assets/hdri"

    dice_types: list[DiceType] = Field(
        default_factory=lambda: [
            DiceType.D4,
            DiceType.D6,
            DiceType.D8,
            DiceType.D10,
            DiceType.D12,
            DiceType.D20,
            DiceType.D100,
        ]
    )

    camera_distance_min: float = Field(default=0.3, gt=0.0)
    camera_distance_max: float = Field(default=1.0, gt=0.0)
    camera_angle_min: float = Field(default=30.0, ge=0.0, lt=90.0)
    camera_angle_max: float = Field(default=80.0, ge=0.0, le=90.0)

    render_samples: int = Field(default=64, gt=0)
    enable_motion_blur: bool = False
    enable_depth_of_field: bool = True
    enable_denoising: bool = True

    enable_random_lighting: bool = True
    enable_random_materials: bool = True
    enable_random_backgrounds: bool = True
    enable_dice_touching: bool = True
    enable_partial_occlusion: bool = True

    enable_6_9_ambiguity_cases: bool = True
    enable_special_symbol_cases: bool = True
    enable_d4_difficult_cases: bool = True
    enable_d100_percentile_cases: bool = True

    random_seed: int | None = None


class DiceFaceMapping(BaseModel):
    face_id: str
    value: int | str
    special_value: SpecialValue | None = None
    normal_vector: tuple[float, float, float] | None = Field(
        default=None,
        description="Face normal in local coordinates",
    )


class DiceAssetMetadata(BaseModel):
    asset_id: str
    asset_path: str
    dice_type: DiceType
    faces: list[DiceFaceMapping]
    has_6_9_marker: bool = False
    number_style: NumberStyle = NumberStyle.PAINTED
    d4_style: D4Style | None = None
    default_material: DiceMaterial = DiceMaterial.OPAQUE
    scale_factor: float = Field(default=1.0, gt=0.0)
    origin_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def get_face_value(self, face_id: str) -> int | str | None:
        for face in self.faces:
            if face.face_id == face_id:
                return face.value
        return None

    def get_face_by_value(self, value: int | str) -> DiceFaceMapping | None:
        for face in self.faces:
            if face.value == value:
                return face
        return None


class TrainingSample(BaseModel):
    image_path: str
    annotation: ImageAnnotation
    split: Literal["train", "val", "test"] = "train"
    weight: float = Field(default=1.0, ge=0.0)
    tags: list[str] = Field(default_factory=list)


class EvaluationMetrics(BaseModel):
    detection_map50: float = Field(ge=0.0, le=1.0)
    detection_map50_95: float = Field(ge=0.0, le=1.0)
    detection_precision: float = Field(ge=0.0, le=1.0)
    detection_recall: float = Field(ge=0.0, le=1.0)

    dice_type_accuracy: float = Field(ge=0.0, le=1.0)
    dice_type_per_class: dict[str, float] = Field(default_factory=dict)

    value_accuracy: float = Field(ge=0.0, le=1.0)
    value_accuracy_per_type: dict[str, float] = Field(default_factory=dict)

    six_nine_confusion_rate: float = Field(ge=0.0, le=1.0)
    d4_accuracy: float = Field(ge=0.0, le=1.0)
    special_symbol_accuracy: float = Field(ge=0.0, le=1.0)
    d100_accuracy: float = Field(ge=0.0, le=1.0)

    orientation_mae: float | None = Field(
        default=None,
        description="Mean absolute error in degrees",
    )

    confidence_ece: float | None = Field(
        default=None,
        description="Expected calibration error",
    )

    confirmation_request_rate: float = Field(ge=0.0, le=1.0)
    false_confirmation_rate: float = Field(ge=0.0, le=1.0)

    total_samples: int = Field(ge=0)
    total_dice: int = Field(ge=0)


class ConfusionMatrixData(BaseModel):
    labels: list[str]
    matrix: list[list[int]]
    task: Literal["dice_type", "value", "special_symbol"]

    @computed_field
    @property
    def total_predictions(self) -> int:
        return sum(sum(row) for row in self.matrix)


class EvaluationReport(BaseModel):
    metrics: EvaluationMetrics
    dice_type_confusion: ConfusionMatrixData | None = None
    value_confusion_per_type: dict[str, ConfusionMatrixData] = Field(default_factory=dict)
    failed_examples: list[dict] = Field(default_factory=list)
    low_confidence_examples: list[dict] = Field(default_factory=list)
    model_version: str | None = None
    evaluation_timestamp: str | None = None
    dataset_info: dict = Field(default_factory=dict)


def prediction_to_detected_die(prediction: DicePrediction) -> "DetectedDie":
    from dice_detector.models.dice import DetectedDie

    notes = []
    for warning in prediction.warnings:
        if warning == AmbiguityReason.POSSIBLE_6_9:
            notes.append("6/9 ambiguity")
        elif warning == AmbiguityReason.D4_AMBIGUOUS_FACE:
            notes.append("D4 detection may be unreliable")
        elif warning == AmbiguityReason.LOW_CONFIDENCE_VALUE:
            notes.append("Low confidence value")
        elif warning == AmbiguityReason.LOW_CONFIDENCE_TYPE:
            notes.append("Low confidence type")
        elif warning == AmbiguityReason.SPECIAL_SYMBOL_UNCERTAIN:
            notes.append("Special symbol uncertain")
        else:
            notes.append(warning.value)

    if prediction.special_value:
        notes.append(f"Special symbol: {prediction.special_value.value}")

    return DetectedDie(
        dice_type=prediction.dice_type or DiceType.UNKNOWN,
        detected_value=prediction.value if isinstance(prediction.value, int) else None,
        confidence=prediction.overall_confidence,
        bbox=prediction.bbox,
        orientation_degrees=prediction.orientation_degrees,
        notes=notes,
    )


def frame_prediction_to_detected_dice(
    frame_prediction: FramePrediction,
) -> list["DetectedDie"]:
    return [
        prediction_to_detected_die(pred)
        for pred in frame_prediction.predictions
    ]
