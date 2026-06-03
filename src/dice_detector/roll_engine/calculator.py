"""Roll calculation engine."""

from typing import Optional

from dice_detector.models import (
    DetectedDie,
    DiceType,
    ExpectedRoll,
    Modifier,
    ModifierPreset,
    RollResult,
    RollType,
)


class RollCalculator:
    """Calculates roll results from detected dice and modifiers."""

    def __init__(self, character_name: str = "Player"):
        """Initialize roll calculator.

        Args:
            character_name: Default character name for rolls.
        """
        self.character_name = character_name

    def calculate(
        self,
        dice: list[DetectedDie],
        modifiers: Optional[list[Modifier]] = None,
        roll_name: str = "Roll",
        roll_type: RollType = RollType.CUSTOM,
        expected_roll: Optional[ExpectedRoll] = None,
    ) -> RollResult:
        """Calculate a roll result from detected dice.

        Args:
            dice: List of detected dice.
            modifiers: Optional list of modifiers to apply.
            roll_name: Name of the roll.
            roll_type: Type of roll.
            expected_roll: Expected roll for formula generation.

        Returns:
            Complete roll result.
        """
        modifiers = modifiers or []

        formula = self._generate_formula(dice, modifiers, expected_roll)

        raw_total = sum(die.final_value or 0 for die in dice)
        modifier_total = sum(m.value for m in modifiers if m.enabled)
        final_total = raw_total + modifier_total
        requires_confirmation = any(die.requires_confirmation for die in dice)
        warnings = []
        for die in dice:
            if die.notes:
                warnings.extend(die.notes)

        return RollResult(
            character_name=self.character_name,
            roll_name=roll_name,
            roll_type=roll_type,
            formula=formula,
            dice=dice,
            modifiers=modifiers,
            raw_total=raw_total,
            modifier_total=modifier_total,
            final_total=final_total,
            requires_confirmation=requires_confirmation,
            warnings=warnings,
        )

    def calculate_from_preset(
        self,
        dice: list[DetectedDie],
        preset: ModifierPreset,
    ) -> RollResult:
        """Calculate a roll result using a modifier preset.

        Args:
            dice: List of detected dice.
            preset: Modifier preset to apply.

        Returns:
            Complete roll result.
        """
        return self.calculate(
            dice=dice,
            modifiers=preset.modifiers,
            roll_name=preset.name,
            roll_type=preset.roll_type,
            expected_roll=ExpectedRoll.parse(preset.dice_formula),
        )

    def _generate_formula(
        self,
        dice: list[DetectedDie],
        modifiers: list[Modifier],
        expected_roll: Optional[ExpectedRoll] = None,
    ) -> str:
        """Generate dice formula string.

        Args:
            dice: Detected dice.
            modifiers: Applied modifiers.
            expected_roll: Expected roll for reference.

        Returns:
            Formula string like "2d6 + 5".
        """
        if expected_roll:
            formula = expected_roll.formula
        else:
            # Generate from detected dice
            dice_counts: dict[DiceType, int] = {}
            for die in dice:
                dice_type = die.final_type
                dice_counts[dice_type] = dice_counts.get(dice_type, 0) + 1

            parts = []
            for dice_type, count in sorted(dice_counts.items(), key=lambda x: -x[1]):
                if dice_type == DiceType.UNKNOWN:
                    continue
                sides = dice_type.sides
                if count == 1:
                    parts.append(f"d{sides}")
                else:
                    parts.append(f"{count}d{sides}")

            formula = " + ".join(parts) if parts else "0"

        # Add modifier total
        modifier_total = sum(m.value for m in modifiers if m.enabled)
        if modifier_total > 0:
            formula += f" + {modifier_total}"
        elif modifier_total < 0:
            formula += f" - {abs(modifier_total)}"

        return formula

    def validate_roll(
        self,
        dice: list[DetectedDie],
        expected_roll: ExpectedRoll,
    ) -> tuple[bool, list[str]]:
        """Validate detected dice against expected roll.

        Args:
            dice: Detected dice.
            expected_roll: Expected roll configuration.

        Returns:
            (is_valid, list of warnings)
        """
        warnings = []

        # Count detected dice by type
        detected_counts: dict[DiceType, int] = {}
        for die in dice:
            dice_type = die.final_type
            detected_counts[dice_type] = detected_counts.get(dice_type, 0) + 1

        # Compare with expected
        for expected_type, expected_count in expected_roll.expected_dice:
            detected_count = detected_counts.get(expected_type, 0)

            if detected_count < expected_count:
                warnings.append(
                    f"Expected {expected_count} {expected_type.value}, "
                    f"detected {detected_count}"
                )
            elif detected_count > expected_count:
                warnings.append(
                    f"Detected extra {expected_type.value} dice "
                    f"({detected_count} vs expected {expected_count})"
                )

        # Check for unexpected dice types
        expected_types = {t for t, _ in expected_roll.expected_dice}
        for dice_type, count in detected_counts.items():
            if dice_type not in expected_types and dice_type != DiceType.UNKNOWN:
                warnings.append(f"Unexpected {dice_type.value} detected ({count})")

        is_valid = len(warnings) == 0
        return is_valid, warnings

    def combine_d100(
        self,
        tens_value: int,
        ones_value: int,
    ) -> int:
        """Combine D100 percentile and digit values.

        Args:
            tens_value: Value from percentile die (0, 10, 20, ..., 90).
            ones_value: Value from digit die (0-9).

        Returns:
            Combined D100 result (1-100).
        """
        if tens_value == 0 and ones_value == 0:
            return 100
        return tens_value + ones_value

    def interpret_percentile_as_d10(self, value: int) -> int:
        """Interpret a percentile die value as a normal D10.

        Args:
            value: Percentile value (0, 10, 20, ..., 90 or 00).

        Returns:
            D10 interpretation (1-10).
        """
        if value == 0 or value == 100:
            return 10
        return value // 10

    def get_advantage_result(
        self,
        dice: list[DetectedDie],
        advantage: bool = True,
    ) -> tuple[DetectedDie, int]:
        """Get the result for advantage/disadvantage rolls.

        Args:
            dice: List of D20 dice (should be 2).
            advantage: True for advantage (take higher), False for disadvantage.

        Returns:
            (selected die, selected value)
        """
        d20_dice = [d for d in dice if d.final_type == DiceType.D20]

        if len(d20_dice) < 2:
            # Not enough dice for advantage
            if d20_dice:
                return d20_dice[0], d20_dice[0].final_value
            raise ValueError("No D20 dice found for advantage roll")

        # Sort by value
        sorted_dice = sorted(d20_dice, key=lambda d: d.final_value, reverse=advantage)
        selected = sorted_dice[0]

        return selected, selected.final_value

    def is_critical(self, die: DetectedDie) -> bool:
        """Check if a die roll is a critical hit (natural 20).

        Args:
            die: Detected die.

        Returns:
            True if natural 20 on D20.
        """
        return die.final_type == DiceType.D20 and die.final_value == 20

    def is_fumble(self, die: DetectedDie) -> bool:
        """Check if a die roll is a fumble (natural 1).

        Args:
            die: Detected die.

        Returns:
            True if natural 1 on D20.
        """
        return die.final_type == DiceType.D20 and die.final_value == 1
