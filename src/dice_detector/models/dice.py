from enum import Enum

from pydantic import BaseModel, Field, computed_field


class DiceType(str, Enum):

    D4 = "D4"
    D6 = "D6"
    D8 = "D8"
    D10 = "D10"
    D12 = "D12"
    D20 = "D20"
    D100 = "D100"
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
            DiceType.D100: 100,
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
            DiceType.D100: 100,
        }
        return mapping.get(self, 0)

    @classmethod
    def from_sides(cls, sides: int) -> "DiceType":
        mapping = {
            4: cls.D4,
            6: cls.D6,
            8: cls.D8,
            10: cls.D10,
            12: cls.D12,
            20: cls.D20,
            100: cls.D100,
        }
        return mapping.get(sides, cls.UNKNOWN)


class BoundingBox(BaseModel):

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def to_xyxy(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height


class DetectedDie(BaseModel):

    dice_type: DiceType
    value: int | None = Field(default=None, alias="detected_value")
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox
    orientation_degrees: float | None = None
    notes: list[str] = Field(default_factory=list)
    cropped_image_path: str | None = None
    is_confirmed: bool = False
    corrected_value: int | None = Field(default=None, alias="user_corrected_value")
    corrected_type: DiceType | None = Field(default=None, alias="user_corrected_type")

    model_config = {"populate_by_name": True}

    @property
    def detected_value(self) -> int | None:
        return self.value

    @computed_field
    @property
    def final_value(self) -> int | None:
        if self.corrected_value is not None:
            return self.corrected_value
        return self.value

    @computed_field
    @property
    def final_type(self) -> DiceType:
        if self.corrected_type is not None:
            return self.corrected_type
        return self.dice_type

    @computed_field
    @property
    def requires_confirmation(self) -> bool:
        if self.is_confirmed:
            return False
        if self.dice_type == DiceType.D4 and self.confidence < 0.85:
            return True
        if self.confidence < 0.7:
            return True
        return self.value in (6, 9) and "6/9 ambiguity" in self.notes
