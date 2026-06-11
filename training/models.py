from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiceType(Enum):
    D4 = "D4"
    D6 = "D6"
    D8 = "D8"
    D10 = "D10"
    D12 = "D12"
    D20 = "D20"
    D100_TENS = "D100_TENS"  # Percentile die (00, 10, 20, ..., 90)
    D100_ONES = "D100_ONES"  # Single digit die for D100
    UNKNOWN = "UNKNOWN"

    @property
    def max_value(self) -> int:
        mapping = {
            DiceType.D4: 4,
            DiceType.D6: 6,
            DiceType.D8: 8,
            DiceType.D10: 10,
            DiceType.D12: 12,
            DiceType.D20: 20,
            DiceType.D100_TENS: 90,
            DiceType.D100_ONES: 9,
        }
        return mapping.get(self, 0)

    @property
    def sides(self) -> int:
        mapping = {
            DiceType.D4: 4,
            DiceType.D6: 6,
            DiceType.D8: 8,
            DiceType.D10: 10,
            DiceType.D12: 12,
            DiceType.D20: 20,
            DiceType.D100_TENS: 10,
            DiceType.D100_ONES: 10,
        }
        return mapping.get(self, 0)


class RollType(Enum):
    ATTACK = "attack"
    DAMAGE = "damage"
    SAVING_THROW = "saving_throw"
    ABILITY_CHECK = "ability_check"
    SKILL_CHECK = "skill_check"
    INITIATIVE = "initiative"
    CUSTOM = "custom"


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def to_xyxy(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class DetectedDie:
    dice_type: DiceType
    detected_value: int
    confidence: float
    bbox: BoundingBox
    orientation_degrees: float = 0.0
    notes: list[str] = field(default_factory=list)
    cropped_image_path: Optional[str] = None
    is_confirmed: bool = False
    user_corrected_value: Optional[int] = None
    user_corrected_type: Optional[DiceType] = None

    @property
    def final_value(self) -> int:
        return self.user_corrected_value if self.user_corrected_value is not None else self.detected_value

    @property
    def final_type(self) -> DiceType:
            return self.user_corrected_type if self.user_corrected_type is not None else self.dice_type

    @property
    def requires_confirmation(self) -> bool:
        """Check if this die requires user confirmation."""
        if self.is_confirmed:
            return False
        # D4 always requires confirmation due to complexity
        if self.dice_type == DiceType.D4 and self.confidence < 0.85:
            return True
        # Low confidence requires confirmation
        if self.confidence < 0.7:
            return True
        # 6/9 ambiguity
        if self.detected_value in (6, 9) and "6/9 ambiguity" in self.notes:
            return True
        return False


@dataclass
class Modifier:
    name: str
    value: int
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "enabled": self.enabled,
        }


@dataclass
class ModifierPreset:
    name: str
    roll_type: RollType
    dice_formula: str  # e.g., "1d20", "2d6", "1d12"
    modifiers: list[Modifier] = field(default_factory=list)
    description: str = ""

    @property
    def total_modifier(self) -> int:
        return sum(m.value for m in self.modifiers if m.enabled)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "roll_type": self.roll_type.value,
            "dice_formula": self.dice_formula,
            "modifiers": [m.to_dict() for m in self.modifiers],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModifierPreset":
        return cls(
            name=data["name"],
            roll_type=RollType(data["roll_type"]),
            dice_formula=data.get("dice_formula", "1d20"),
            modifiers=[
                Modifier(
                    name=m["name"],
                    value=m["value"],
                    enabled=m.get("enabled", True),
                )
                for m in data.get("modifiers", [])
            ],
            description=data.get("description", ""),
        )


@dataclass
class RollResult:
    """Complete roll result with all dice and modifiers."""
    character_name: str
    roll_name: str
    roll_type: RollType
    formula: str
    dice: list[DetectedDie]
    modifiers: list[Modifier]
    raw_total: int = 0
    modifier_total: int = 0
    final_total: int = 0
    requires_confirmation: bool = False
    warnings: list[str] = field(default_factory=list)
    timestamp: Optional[str] = None

    def calculate_totals(self) -> None:
        """Calculate raw, modifier, and final totals."""
        self.raw_total = sum(die.final_value for die in self.dice)
        self.modifier_total = sum(m.value for m in self.modifiers if m.enabled)
        self.final_total = self.raw_total + self.modifier_total
        self.requires_confirmation = any(die.requires_confirmation for die in self.dice)
        self.warnings = []
        for die in self.dice:
            if die.notes:
                self.warnings.extend(die.notes)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "character_name": self.character_name,
            "roll_name": self.roll_name,
            "roll_type": self.roll_type.value,
            "formula": self.formula,
            "dice": [
                {
                    "dice_type": die.final_type.value,
                    "value": die.final_value,
                    "confidence": die.confidence,
                    "bbox": die.bbox.to_tuple(),
                    "notes": die.notes,
                }
                for die in self.dice
            ],
            "modifiers": [m.to_dict() for m in self.modifiers if m.enabled],
            "raw_total": self.raw_total,
            "modifier_total": self.modifier_total,
            "final_total": self.final_total,
            "requires_confirmation": self.requires_confirmation,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }

    def to_foundry_message(self) -> str:
        """Format as a Foundry VTT chat message."""
        lines = [f"**{self.character_name}** rolls **{self.roll_name}**", ""]

        # Dice formula and results
        lines.append(f"**Dice:** {self.formula}")
        if len(self.dice) == 1:
            lines.append(f"**Result:** {self.dice[0].final_value}")
        else:
            values = ", ".join(str(die.final_value) for die in self.dice)
            lines.append(f"**Results:** {values}")

        # Modifiers
        if self.modifiers:
            lines.append("")
            lines.append("**Modifiers:**")
            for mod in self.modifiers:
                if mod.enabled:
                    sign = "+" if mod.value >= 0 else ""
                    lines.append(f"  {sign}{mod.value} {mod.name}")

        # Total
        lines.append("")
        lines.append(f"**Total: {self.final_total}**")

        # Warnings
        if self.warnings:
            lines.append("")
            lines.append("*⚠️ " + ", ".join(set(self.warnings)) + "*")

        return "\n".join(lines)


@dataclass
class ExpectedRoll:
    """Expected roll configuration to help detection."""
    formula: str  # e.g., "1d20", "2d6+3", "d100"
    expected_dice: list[tuple[DiceType, int]] = field(default_factory=list)  # [(DiceType, count), ...]
    is_d100: bool = False

    @classmethod
    def parse(cls, formula: str) -> "ExpectedRoll":
        """Parse a dice formula into expected roll configuration."""
        import re

        formula = formula.lower().strip()
        expected_dice = []
        is_d100 = "d100" in formula

        if is_d100:
            expected_dice = [
                (DiceType.D100_TENS, 1),
                (DiceType.D100_ONES, 1),
                (DiceType.D4, 1),
                (DiceType.D6, 1),
                (DiceType.D8, 1),
                (DiceType.D12, 1),
                (DiceType.D20, 1),
            ]
        else:
            # Parse patterns like "2d6", "1d20", "4d8"
            pattern = r"(\d*)d(\d+)"
            matches = re.findall(pattern, formula)
            for count_str, sides_str in matches:
                count = int(count_str) if count_str else 1
                sides = int(sides_str)
                dice_type = {
                    4: DiceType.D4,
                    6: DiceType.D6,
                    8: DiceType.D8,
                    10: DiceType.D10,
                    12: DiceType.D12,
                    20: DiceType.D20,
                }.get(sides, DiceType.UNKNOWN)
                if dice_type != DiceType.UNKNOWN:
                    expected_dice.append((dice_type, count))

        return cls(formula=formula, expected_dice=expected_dice, is_d100=is_d100)


@dataclass
class CalibrationSettings:
    """Camera and detection calibration settings."""
    camera_index: int = 0
    detection_zone: Optional[tuple[int, int, int, int]] = None  # (x, y, width, height)
    min_confidence_threshold: float = 0.5
    auto_post_threshold: float = 0.9
    use_expected_roll_mode: bool = True
    save_corrected_samples: bool = True
    lighting_adjustment: float = 1.0
    frame_width: int = 1280
    frame_height: int = 720

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "camera_index": self.camera_index,
            "detection_zone": self.detection_zone,
            "min_confidence_threshold": self.min_confidence_threshold,
            "auto_post_threshold": self.auto_post_threshold,
            "use_expected_roll_mode": self.use_expected_roll_mode,
            "save_corrected_samples": self.save_corrected_samples,
            "lighting_adjustment": self.lighting_adjustment,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationSettings":
        """Create from dictionary."""
        return cls(
            camera_index=data.get("camera_index", 0),
            detection_zone=data.get("detection_zone"),
            min_confidence_threshold=data.get("min_confidence_threshold", 0.5),
            auto_post_threshold=data.get("auto_post_threshold", 0.9),
            use_expected_roll_mode=data.get("use_expected_roll_mode", True),
            save_corrected_samples=data.get("save_corrected_samples", True),
            lighting_adjustment=data.get("lighting_adjustment", 1.0),
            frame_width=data.get("frame_width", 1280),
            frame_height=data.get("frame_height", 720),
        )


@dataclass
class FoundryConfig:
    """Foundry VTT connection configuration."""
    host: str = "localhost"
    port: int = 30000
    use_websocket: bool = True
    api_key: Optional[str] = None
    default_character: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "use_websocket": self.use_websocket,
            "api_key": self.api_key,
            "default_character": self.default_character,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FoundryConfig":
        """Create from dictionary."""
        return cls(
            host=data.get("host", "localhost"),
            port=data.get("port", 30000),
            use_websocket=data.get("use_websocket", True),
            api_key=data.get("api_key"),
            default_character=data.get("default_character", ""),
        )

    @property
    def websocket_url(self) -> str:
        """Get WebSocket URL."""
        return f"ws://{self.host}:{self.port}/socket.io/"

    @property
    def http_url(self) -> str:
        """Get HTTP URL."""
        return f"http://{self.host}:{self.port}"
