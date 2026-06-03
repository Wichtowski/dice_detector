"""Settings management for dice detector."""

import json
import os

import yaml

from ..models import CalibrationSettings, FoundryConfig


class SettingsManager:
    """Manages application settings persistence."""

    def __init__(self, config_dir: str = "config"):
        """Initialize settings manager.

        Args:
            config_dir: Directory for configuration files.
        """
        self.config_dir = config_dir
        self.settings_file = os.path.join(config_dir, "settings.yaml")
        self.calibration: CalibrationSettings = CalibrationSettings()
        self.foundry: FoundryConfig = FoundryConfig()

        self._ensure_config_dir()
        self.load()

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)

    def load(self) -> None:
        """Load settings from file."""
        if not os.path.exists(self.settings_file):
            self._create_default_settings()
            return

        try:
            with open(self.settings_file, "r") as f:
                data = yaml.safe_load(f)

            if data:
                if "calibration" in data:
                    self.calibration = CalibrationSettings.from_dict(data["calibration"])
                if "foundry" in data:
                    self.foundry = FoundryConfig.from_dict(data["foundry"])

        except Exception as e:
            print(f"Failed to load settings: {e}")
            self._create_default_settings()

    def save(self) -> None:
        """Save settings to file."""
        data = {
            "calibration": self.calibration.to_dict(),
            "foundry": self.foundry.to_dict(),
        }

        try:
            with open(self.settings_file, "w") as f:
                yaml.dump(data, f, default_flow_style=False)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def _create_default_settings(self) -> None:
        """Create default settings file."""
        self.calibration = CalibrationSettings()
        self.foundry = FoundryConfig()
        self.save()

    def update_calibration(self, **kwargs) -> None:
        """Update calibration settings.

        Args:
            **kwargs: Settings to update.
        """
        for key, value in kwargs.items():
            if hasattr(self.calibration, key):
                setattr(self.calibration, key, value)
        self.save()

    def update_foundry(self, **kwargs) -> None:
        """Update Foundry settings.

        Args:
            **kwargs: Settings to update.
        """
        for key, value in kwargs.items():
            if hasattr(self.foundry, key):
                setattr(self.foundry, key, value)
        self.save()

    def set_detection_zone(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        """Set the detection zone.

        Args:
            x: X coordinate.
            y: Y coordinate.
            width: Zone width.
            height: Zone height.
        """
        self.calibration.detection_zone = (x, y, width, height)
        self.save()

    def clear_detection_zone(self) -> None:
        """Clear the detection zone."""
        self.calibration.detection_zone = None
        self.save()

    def get_camera_index(self) -> int:
        """Get configured camera index."""
        return self.calibration.camera_index

    def set_camera_index(self, index: int) -> None:
        """Set camera index."""
        self.calibration.camera_index = index
        self.save()

    def export_settings(self, filepath: str) -> bool:
        """Export settings to a file.

        Args:
            filepath: Path to export file.

        Returns:
            True if export successful.
        """
        try:
            data = {
                "calibration": self.calibration.to_dict(),
                "foundry": self.foundry.to_dict(),
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    def import_settings(self, filepath: str) -> bool:
        """Import settings from a file.

        Args:
            filepath: Path to import file.

        Returns:
            True if import successful.
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            if "calibration" in data:
                self.calibration = CalibrationSettings.from_dict(data["calibration"])
            if "foundry" in data:
                self.foundry = FoundryConfig.from_dict(data["foundry"])

            self.save()
            return True
        except Exception:
            return False
