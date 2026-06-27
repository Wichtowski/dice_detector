import re
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field

from dice_detector.models.dice import DetectedDie, DiceType
from dice_detector.models.modifiers import Modifier, RollType


class RollSessionStatus(str, Enum):
    PENDING = "pending"
    COLLECTING = "collecting"
    NEEDS_CONFIRMATION = "needs_confirmation"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class RequiredDiceGroup(BaseModel):
    dice_type: DiceType
    required_count: int = Field(ge=1)
    collected_values: list[int] = Field(default_factory=list)

    @computed_field
    @property
    def remaining_count(self) -> int:
        return max(self.required_count - len(self.collected_values), 0)

    @computed_field
    @property
    def is_complete(self) -> bool:
        return len(self.collected_values) >= self.required_count

    def accept_value(self, value: int) -> bool:
        if self.remaining_count > 0:
            self.collected_values.append(value)
            return True
        return False

    @computed_field
    @property
    def total(self) -> int:
        return sum(self.collected_values)


class RollStage(BaseModel):
    stage_index: int = Field(ge=0)
    detected_dice: list[DetectedDie] = Field(default_factory=list)
    accepted_dice: list[DetectedDie] = Field(default_factory=list)
    rejected_dice: list[DetectedDie] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def requires_confirmation(self) -> bool:
        return any(die.requires_confirmation for die in self.accepted_dice)


class RollSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    formula: str
    roll_name: str = ""
    roll_type: RollType = RollType.CUSTOM
    character_name: str = ""
    required_dice: list[RequiredDiceGroup] = Field(default_factory=list)
    stages: list[RollStage] = Field(default_factory=list)
    modifiers: list[Modifier] = Field(default_factory=list)
    static_bonus: int = 0
    status: RollSessionStatus = RollSessionStatus.PENDING
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def is_complete(self) -> bool:
        return all(group.is_complete for group in self.required_dice)

    @computed_field
    @property
    def raw_total(self) -> int:
        return sum(group.total for group in self.required_dice)

    @computed_field
    @property
    def modifier_total(self) -> int:
        return sum(m.value for m in self.modifiers if m.enabled)

    @computed_field
    @property
    def final_total(self) -> int:
        return self.raw_total + self.modifier_total + self.static_bonus

    @computed_field
    @property
    def requires_confirmation(self) -> bool:
        return any(stage.requires_confirmation for stage in self.stages)

    @computed_field
    @property
    def progress_summary(self) -> dict[str, str]:
        return {
            group.dice_type.value: f"{len(group.collected_values)}/{group.required_count}"
            for group in self.required_dice
        }

    def get_next_required(self) -> list[tuple[DiceType, int]]:
        return [
            (group.dice_type, group.remaining_count)
            for group in self.required_dice
            if group.remaining_count > 0
        ]

    def accept_detected_dice(self, detected: list[DetectedDie]) -> RollStage:
        stage = RollStage(stage_index=len(self.stages))
        stage.detected_dice = detected

        for die in detected:
            accepted = False
            for group in self.required_dice:
                if (
                    group.dice_type == die.final_type
                    and group.remaining_count > 0
                    and die.final_value is not None
                ):
                    group.accept_value(die.final_value)
                    stage.accepted_dice.append(die)
                    accepted = True
                    break

            if not accepted:
                stage.rejected_dice.append(die)

        self.stages.append(stage)

        if self.is_complete:
            if self.requires_confirmation:
                self.status = RollSessionStatus.NEEDS_CONFIRMATION
            else:
                self.status = RollSessionStatus.COMPLETE
        else:
            self.status = RollSessionStatus.COLLECTING

        return stage

    @classmethod
    def from_formula(
        cls,
        formula: str,
        roll_name: str = "",
        roll_type: RollType = RollType.CUSTOM,
        character_name: str = "",
        modifiers: list[Modifier] | None = None,
    ) -> "RollSession":
        required_dice, static_bonus = cls.parse_formula(formula)

        return cls(
            formula=formula,
            roll_name=roll_name,
            roll_type=roll_type,
            character_name=character_name,
            required_dice=required_dice,
            modifiers=modifiers or [],
            static_bonus=static_bonus,
            status=RollSessionStatus.PENDING,
        )

    @staticmethod
    def parse_formula(formula: str) -> tuple[list[RequiredDiceGroup], int]:
        formula = formula.lower().strip()
        required_dice: list[RequiredDiceGroup] = []
        static_bonus = 0

        if "d100" in formula:
            required_dice.append(
                RequiredDiceGroup(dice_type=DiceType.D100, required_count=1)
            )
            # Add 1 of every other dice type for D100 rolls
            for dt in (DiceType.D4, DiceType.D6, DiceType.D8, DiceType.D12, DiceType.D20):
                required_dice.append(
                    RequiredDiceGroup(dice_type=dt, required_count=1)
                )
            formula = formula.replace("d100", "").replace("1", "", 1)

        dice_pattern = r"(\d*)d(\d+)"
        for match in re.finditer(dice_pattern, formula):
            count_str, sides_str = match.groups()
            count = int(count_str) if count_str else 1
            sides = int(sides_str)

            if sides == 100:
                continue

            dice_type = DiceType.from_sides(sides)
            if dice_type != DiceType.UNKNOWN:
                existing = next(
                    (g for g in required_dice if g.dice_type == dice_type), None
                )
                if existing:
                    existing.required_count += count
                else:
                    required_dice.append(
                        RequiredDiceGroup(dice_type=dice_type, required_count=count)
                    )

        bonus_str = re.sub(dice_pattern, "", formula)
        bonus_pattern = r"([+-]?\s*\d+)"
        for match in re.finditer(bonus_pattern, bonus_str):
            try:
                bonus = int(match.group(1).replace(" ", ""))
                static_bonus += bonus
            except ValueError:
                pass

        return required_dice, static_bonus


class RollResult(BaseModel):
    character_name: str = ""
    roll_name: str = ""
    roll_type: RollType = RollType.CUSTOM
    formula: str
    dice: list[DetectedDie]
    modifiers: list[Modifier] = Field(default_factory=list)
    raw_total: int
    modifier_total: int = 0
    static_bonus: int = 0
    final_total: int
    requires_confirmation: bool = False
    warnings: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str | None = None

    @classmethod
    def from_session(cls, session: RollSession) -> "RollResult":
        all_dice: list[DetectedDie] = []
        for stage in session.stages:
            all_dice.extend(stage.accepted_dice)

        return cls(
            character_name=session.character_name,
            roll_name=session.roll_name,
            roll_type=session.roll_type,
            formula=session.formula,
            dice=all_dice,
            modifiers=session.modifiers,
            raw_total=session.raw_total,
            modifier_total=session.modifier_total,
            static_bonus=session.static_bonus,
            final_total=session.final_total,
            requires_confirmation=session.requires_confirmation,
            warnings=session.warnings,
            session_id=session.session_id,
        )

    def to_markdown(self) -> str:
        """Format roll result as markdown message."""
        lines = []

        if self.character_name:
            lines.append(f"**{self.character_name}** rolls **{self.roll_name}**")
        else:
            lines.append(f"**{self.roll_name}**")

        lines.append("")
        lines.append(f"**Dice:** {self.formula}")

        if len(self.dice) == 1:
            lines.append(f"**Result:** {self.dice[0].final_value}")
        else:
            values = ", ".join(str(die.final_value) for die in self.dice)
            lines.append(f"**Results:** {values}")

        if self.modifiers:
            lines.append("")
            lines.append("**Modifiers:**")
            for mod in self.modifiers:
                if mod.enabled:
                    lines.append(f"  {mod}")

        if self.static_bonus != 0:
            sign = "+" if self.static_bonus > 0 else ""
            lines.append(f"  {sign}{self.static_bonus} (formula)")

        lines.append("")
        lines.append(f"**Total: {self.final_total}**")

        if self.warnings:
            lines.append("")
            lines.append("*⚠️ " + ", ".join(set(self.warnings)) + "*")

        return "\n".join(lines)


class ExpectedRoll(BaseModel):
    formula: str
    expected_dice: list[tuple[DiceType, int]] = Field(default_factory=list)
    is_d100: bool = False

    @classmethod
    def parse(cls, formula: str) -> "ExpectedRoll":
        formula_lower = formula.lower().strip()
        expected_dice: list[tuple[DiceType, int]] = []
        is_d100 = "d100" in formula_lower

        if is_d100:
            expected_dice = [
                (DiceType.D100, 1),
                (DiceType.D4, 1),
                (DiceType.D6, 1),
                (DiceType.D8, 1),
                (DiceType.D12, 1),
                (DiceType.D20, 1),
            ]
        else:
            pattern = r"(\d*)d(\d+)"
            matches = re.findall(pattern, formula_lower)
            for count_str, sides_str in matches:
                count = int(count_str) if count_str else 1
                sides = int(sides_str)
                dice_type = DiceType.from_sides(sides)
                if dice_type != DiceType.UNKNOWN:
                    expected_dice.append((dice_type, count))

        return cls(formula=formula, expected_dice=expected_dice, is_d100=is_d100)
