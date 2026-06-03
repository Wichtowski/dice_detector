from enum import Enum

from pydantic import BaseModel, Field, computed_field


class RollType(str, Enum):
    ATTACK = "attack"
    DAMAGE = "damage"
    SAVING_THROW = "saving_throw"
    ABILITY_CHECK = "ability_check"
    SKILL_CHECK = "skill_check"
    INITIATIVE = "initiative"
    CUSTOM = "custom"


class Modifier(BaseModel):
    name: str
    value: int
    enabled: bool = True

    def __str__(self) -> str:
        sign = "+" if self.value >= 0 else ""
        return f"{sign}{self.value} {self.name}"


class ModifierPreset(BaseModel):
    name: str
    roll_type: RollType
    dice_formula: str
    modifiers: list[Modifier] = Field(default_factory=list)
    description: str = ""

    @computed_field
    @property
    def total_modifier(self) -> int:
        return sum(m.value for m in self.modifiers if m.enabled)

    @computed_field
    @property
    def full_formula(self) -> str:
        total = self.total_modifier
        if total == 0:
            return self.dice_formula
        sign = "+" if total > 0 else ""
        return f"{self.dice_formula} {sign} {total}"
