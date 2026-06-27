from __future__ import annotations

from pathlib import Path

import cv2
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

from dice_detector.models.dice import DiceType


class DiceInventory(BaseModel):
    D4: int = Field(default=1, ge=0)
    D6: int = Field(default=4, ge=0)
    D8: int = Field(default=1, ge=0)
    D10: int = Field(default=2, ge=0)
    D12: int = Field(default=1, ge=0)
    D20: int = Field(default=1, ge=0)
    D100: int = Field(default=1, ge=0)

    def get_count(self, dice_type: DiceType) -> int:
        mapping = {
            DiceType.D4: self.D4,
            DiceType.D6: self.D6,
            DiceType.D8: self.D8,
            DiceType.D10: self.D10,
            DiceType.D12: self.D12,
            DiceType.D20: self.D20,
            DiceType.D100: self.D100,
        }
        return mapping.get(dice_type, 0)

    def can_roll_in_one_throw(self, required: list[tuple[DiceType, int]]) -> bool:
        return all(self.get_count(dice_type) >= count for dice_type, count in required)

    def calculate_stages(
        self, required: list[tuple[DiceType, int]]
    ) -> list[list[tuple[DiceType, int]]]:
        stages: list[list[tuple[DiceType, int]]] = []
        remaining = {dt: count for dt, count in required}

        while any(count > 0 for count in remaining.values()):
            stage: list[tuple[DiceType, int]] = []
            for dice_type in remaining:
                if remaining[dice_type] > 0:
                    available = self.get_count(dice_type)
                    to_roll = min(remaining[dice_type], available)
                    if to_roll > 0:
                        stage.append((dice_type, to_roll))
                        remaining[dice_type] -= to_roll
            if stage:
                stages.append(stage)
            else:
                break

        return stages


class CameraConfig(BaseModel):
    camera_index: int = Field(default=0, ge=0)
    frame_width: int = Field(default=1280, gt=0)
    frame_height: int = Field(default=720, gt=0)
    fps: int = Field(default=30, gt=0)


class CameraDevice(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    label: str

    @staticmethod
    def _v4l2_name(index: int) -> str | None:
        name_path = Path(f"/sys/class/video4linux/video{index}/name")
        if name_path.is_file():
            return name_path.read_text(encoding="utf-8").strip()
        return None

    @classmethod
    def probe(cls, index: int) -> CameraDevice | None:
        try:
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except AttributeError:
            pass

        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            return None
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        name = cls._v4l2_name(index)
        if name:
            label = f"{index}: {name} ({width}×{height})"
        else:
            label = f"Camera {index} ({width}×{height})"
        return cls(index=index, label=label)

    @classmethod
    def list_available(cls, max_index: int = 10) -> list[CameraDevice]:
        devices: list[CameraDevice] = []
        for index in range(max_index):
            device = cls.probe(index)
            if device is not None:
                devices.append(device)
        return devices


class VisionConfig(BaseModel):
    device: str | None = Field(
        default=None,
        description="Compute device: rocm/amd, cuda, mps, cpu, or None for auto",
    )
    require_gpu: bool = Field(default=True)
    allow_contour_fallback: bool = Field(
        default=False,
        description="Use OpenCV contour heuristics when no trained dice model is loaded",
    )


class CalibrationConfig(BaseModel):
    camera_index: int = Field(default=0, ge=0)
    detection_zone: tuple[int, int, int, int] | None = None
    min_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    auto_post_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    use_expected_roll_mode: bool = True
    save_corrected_samples: bool = True
    lighting_adjustment: float = Field(default=1.0, ge=0.1, le=3.0)
    frame_width: int = Field(default=1280, gt=0)
    frame_height: int = Field(default=720, gt=0)


CalibrationSettings = CalibrationConfig


class FoundryConfig(BaseModel):
    host: str = "localhost"
    port: int = Field(default=30000, ge=1, le=65535)
    websocket_port: int = Field(default=8767, ge=1, le=65535)
    use_websocket: bool = True
    api_key: str | None = None
    default_character: str = ""

    @property
    def websocket_url(self) -> str:
        host = "127.0.0.1" if self.host == "localhost" else self.host
        return f"ws://{host}:{self.websocket_port}"

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def websocket_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"


class AppConfig(BaseSettings):
    camera: CameraConfig = Field(default_factory=CameraConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    dice_inventory: DiceInventory = Field(default_factory=DiceInventory)
    model_path: str | None = None
    presets_path: str = "data/presets.json"
    samples_dir: str = "data/samples"

    model_config = {
        "env_prefix": "DICE_DETECTOR_",
        "env_nested_delimiter": "__",
    }
