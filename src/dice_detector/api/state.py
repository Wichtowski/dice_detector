import json
from pathlib import Path

from dice_detector.models import (
    AppConfig,
    DetectedDie,
    ModifierPreset,
    RollResult,
    RollSession,
    RollSessionStatus,
    RollType,
)


class AppState:
    def __init__(self, config: AppConfig):
        self.config = config
        self.current_session: RollSession | None = None
        self.last_result: RollResult | None = None
        self.presets: list[ModifierPreset] = []
        self.connected_clients: set = set()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._load_presets()
        Path(self.config.samples_dir).mkdir(parents=True, exist_ok=True)
        self._initialized = True

    async def shutdown(self) -> None:
        self._save_presets()

    def _load_presets(self) -> None:
        presets_path = Path(self.config.presets_path)
        if presets_path.exists():
            try:
                with open(presets_path) as f:
                    data = json.load(f)
                self.presets = [
                    ModifierPreset.model_validate(p) for p in data.get("presets", [])
                ]
            except Exception as e:
                print(f"Failed to load presets: {e}")
                self.presets = []
        else:
            self.presets = self._default_presets()
            self._save_presets()

    def _save_presets(self) -> None:
        presets_path = Path(self.config.presets_path)
        presets_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(presets_path, "w") as f:
                json.dump(
                    {"presets": [p.model_dump() for p in self.presets]},
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as e:
            print(f"Failed to save presets: {e}")

    def _default_presets(self) -> list[ModifierPreset]:
        from dice_detector.models import Modifier

        return [
            ModifierPreset(
                name="Basic Attack",
                roll_type=RollType.ATTACK,
                dice_formula="1d20",
                modifiers=[
                    Modifier(name="Ability", value=0),
                    Modifier(name="Proficiency", value=0),
                ],
                description="Basic attack roll",
            ),
            ModifierPreset(
                name="Basic Damage",
                roll_type=RollType.DAMAGE,
                dice_formula="1d8",
                modifiers=[Modifier(name="Ability", value=0)],
                description="Basic weapon damage",
            ),
            ModifierPreset(
                name="Ability Check",
                roll_type=RollType.ABILITY_CHECK,
                dice_formula="1d20",
                modifiers=[Modifier(name="Ability", value=0)],
                description="Generic ability check",
            ),
            ModifierPreset(
                name="Saving Throw",
                roll_type=RollType.SAVING_THROW,
                dice_formula="1d20",
                modifiers=[Modifier(name="Save", value=0)],
                description="Generic saving throw",
            ),
        ]

    def start_session(
        self,
        formula: str,
        roll_name: str = "",
        roll_type: RollType = RollType.CUSTOM,
        character_name: str = "",
        preset: ModifierPreset | None = None,
    ) -> RollSession:
        modifiers = list(preset.modifiers) if preset else []

        self.current_session = RollSession.from_formula(
            formula=formula,
            roll_name=roll_name,
            roll_type=roll_type,
            character_name=character_name,
            modifiers=modifiers,
        )
        self.current_session.status = RollSessionStatus.COLLECTING

        return self.current_session

    def accept_dice(self, detected: list[DetectedDie]) -> RollSession | None:
        if self.current_session is None:
            return None

        self.current_session.accept_detected_dice(detected)
        return self.current_session

    def confirm_session(self) -> RollResult | None:
        if self.current_session is None:
            return None

        self.current_session.status = RollSessionStatus.COMPLETE
        self.last_result = RollResult.from_session(self.current_session)
        return self.last_result

    def cancel_session(self) -> None:
        if self.current_session:
            self.current_session.status = RollSessionStatus.CANCELLED
        self.current_session = None

    def add_preset(self, preset: ModifierPreset) -> None:
        self.presets.append(preset)
        self._save_presets()

    def remove_preset(self, name: str) -> bool:
        for i, p in enumerate(self.presets):
            if p.name == name:
                self.presets.pop(i)
                self._save_presets()
                return True
        return False

    def get_preset(self, name: str) -> ModifierPreset | None:
        for p in self.presets:
            if p.name == name:
                return p
        return None
