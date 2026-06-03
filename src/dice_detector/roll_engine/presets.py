"""Modifier preset management."""

import json
import os
from typing import Optional

from dice_detector.models import Modifier, ModifierPreset, RollType


class PresetManager:
    """Manages modifier presets for different roll types."""

    def __init__(self, presets_file: str = "data/presets.json"):
        """Initialize preset manager.

        Args:
            presets_file: Path to presets JSON file.
        """
        self.presets_file = presets_file
        self.presets: dict[str, ModifierPreset] = {}
        self._load_presets()

    def _load_presets(self) -> None:
        """Load presets from file."""
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, "r") as f:
                    data = json.load(f)
                    for preset_data in data.get("presets", []):
                        preset = ModifierPreset.model_validate(preset_data)
                        self.presets[preset.name] = preset
            except Exception as e:
                print(f"Failed to load presets: {e}")
                self._create_default_presets()
        else:
            self._create_default_presets()

    def _create_default_presets(self) -> None:
        """Create default presets."""
        defaults = [
            ModifierPreset(
                name="Basic Attack",
                roll_type=RollType.ATTACK,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Strength", value=0),
                    Modifier(name="Proficiency", value=0),
                ],
                description="Basic melee attack roll",
            ),
            ModifierPreset(
                name="Basic Damage",
                roll_type=RollType.DAMAGE,
                dice_formula="1d8",
                modifiers=[
                    Modifier(name="Strength", value=0),
                ],
                description="Basic weapon damage",
            ),
            ModifierPreset(
                name="Ability Check",
                roll_type=RollType.ABILITY_CHECK,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Ability Modifier", value=0),
                ],
                description="Generic ability check",
            ),
            ModifierPreset(
                name="Saving Throw",
                roll_type=RollType.SAVING_THROW,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Save Modifier", value=0),
                ],
                description="Generic saving throw",
            ),
            ModifierPreset(
                name="Initiative",
                roll_type=RollType.INITIATIVE,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Dexterity", value=0),
                ],
                description="Initiative roll",
            ),
            ModifierPreset(
                name="Barbarian Greataxe Attack",
                roll_type=RollType.ATTACK,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Strength", value=4),
                    Modifier(name="Proficiency", value=3),
                    Modifier(name="Magic Weapon", value=1),
                ],
                description="Barbarian greataxe attack with +1 weapon",
            ),
            ModifierPreset(
                name="Raging Greataxe Damage",
                roll_type=RollType.DAMAGE,
                dice_formula="1d12",
                modifiers=[
                    Modifier(name="Strength", value=4),
                    Modifier(name="Rage", value=2),
                    Modifier(name="Magic Weapon", value=1),
                ],
                description="Barbarian raging greataxe damage",
            ),
            ModifierPreset(
                name="Fireball",
                roll_type=RollType.DAMAGE,
                dice_formula="8d6",
                modifiers=[],
                description="Fireball spell damage",
            ),
            ModifierPreset(
                name="Sneak Attack (Rogue 5)",
                roll_type=RollType.DAMAGE,
                dice_formula="3d6",
                modifiers=[
                    Modifier(name="Dexterity", value=4),
                ],
                description="Sneak attack damage for level 5 rogue",
            ),
        ]

        for preset in defaults:
            self.presets[preset.name] = preset

        self.save_presets()

    def save_presets(self) -> None:
        """Save presets to file."""
        os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
        data = {"presets": [p.model_dump(mode="json") for p in self.presets.values()]}
        with open(self.presets_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_preset(self, name: str) -> Optional[ModifierPreset]:
        """Get a preset by name.

        Args:
            name: Preset name.

        Returns:
            Preset or None if not found.
        """
        return self.presets.get(name)

    def add_preset(self, preset: ModifierPreset) -> None:
        """Add or update a preset.

        Args:
            preset: Preset to add.
        """
        self.presets[preset.name] = preset
        self.save_presets()

    def remove_preset(self, name: str) -> bool:
        """Remove a preset.

        Args:
            name: Preset name.

        Returns:
            True if preset was removed.
        """
        if name in self.presets:
            del self.presets[name]
            self.save_presets()
            return True
        return False

    def list_presets(self, roll_type: Optional[RollType] = None) -> list[ModifierPreset]:
        """List all presets, optionally filtered by roll type.

        Args:
            roll_type: Optional roll type filter.

        Returns:
            List of presets.
        """
        if roll_type:
            return [p for p in self.presets.values() if p.roll_type == roll_type]
        return list(self.presets.values())

    def create_preset(
        self,
        name: str,
        roll_type: RollType,
        dice_formula: str,
        modifiers: list[tuple[str, int]],
        description: str = "",
    ) -> ModifierPreset:
        """Create and save a new preset.

        Args:
            name: Preset name.
            roll_type: Type of roll.
            dice_formula: Dice formula (e.g., "1d20", "2d6").
            modifiers: List of (name, value) tuples.
            description: Optional description.

        Returns:
            Created preset.
        """
        preset = ModifierPreset(
            name=name,
            roll_type=roll_type,
            dice_formula=dice_formula,
            modifiers=[Modifier(name=n, value=v) for n, v in modifiers],
            description=description,
        )
        self.add_preset(preset)
        return preset

    def duplicate_preset(self, name: str, new_name: str) -> Optional[ModifierPreset]:
        """Duplicate an existing preset with a new name.

        Args:
            name: Name of preset to duplicate.
            new_name: Name for the new preset.

        Returns:
            New preset or None if original not found.
        """
        original = self.get_preset(name)
        if not original:
            return None

        new_preset = ModifierPreset(
            name=new_name,
            roll_type=original.roll_type,
            dice_formula=original.dice_formula,
            modifiers=[
                Modifier(name=m.name, value=m.value, enabled=m.enabled)
                for m in original.modifiers
            ],
            description=original.description,
        )
        self.add_preset(new_preset)
        return new_preset

    def update_modifier(
        self,
        preset_name: str,
        modifier_name: str,
        new_value: int,
    ) -> bool:
        """Update a modifier value in a preset.

        Args:
            preset_name: Name of the preset.
            modifier_name: Name of the modifier.
            new_value: New value for the modifier.

        Returns:
            True if modifier was updated.
        """
        preset = self.get_preset(preset_name)
        if not preset:
            return False

        for modifier in preset.modifiers:
            if modifier.name == modifier_name:
                modifier.value = new_value
                self.save_presets()
                return True

        return False

    def add_modifier_to_preset(
        self,
        preset_name: str,
        modifier_name: str,
        value: int,
    ) -> bool:
        """Add a new modifier to a preset.

        Args:
            preset_name: Name of the preset.
            modifier_name: Name of the new modifier.
            value: Value for the modifier.

        Returns:
            True if modifier was added.
        """
        preset = self.get_preset(preset_name)
        if not preset:
            return False

        preset.modifiers.append(Modifier(name=modifier_name, value=value))
        self.save_presets()
        return True

    def remove_modifier_from_preset(
        self,
        preset_name: str,
        modifier_name: str,
    ) -> bool:
        """Remove a modifier from a preset.

        Args:
            preset_name: Name of the preset.
            modifier_name: Name of the modifier to remove.

        Returns:
            True if modifier was removed.
        """
        preset = self.get_preset(preset_name)
        if not preset:
            return False

        original_count = len(preset.modifiers)
        preset.modifiers = [m for m in preset.modifiers if m.name != modifier_name]

        if len(preset.modifiers) < original_count:
            self.save_presets()
            return True

        return False
