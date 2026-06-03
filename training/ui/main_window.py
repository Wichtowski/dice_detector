"""Main application window."""

import time
import tkinter as tk
from typing import Optional

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from ..camera import CameraCapture
from ..foundry import FoundryClient, FoundryWebSocketServer, MessageFormatter
from ..models import (
    CalibrationSettings,
    DetectedDie,
    DiceType,
    ExpectedRoll,
    FoundryConfig,
    Modifier,
    ModifierPreset,
    RollType,
)
from ..roll_engine import PresetManager, RollCalculator
from ..vision import VisionPipeline
from .widgets import (
    DiceDisplayWidget,
    ModifierPanel,
    PresetSelector,
    RollFormulaInput,
)


class MainWindow(ctk.CTk):
    """Main application window for dice detector."""

    def __init__(self):
        """Initialize main window."""
        super().__init__()

        self.title("D&D Dice Detector")
        self.geometry("1400x900")

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Initialize components
        self.settings = CalibrationSettings()
        self.foundry_config = FoundryConfig()

        self.camera = CameraCapture(self.settings)
        self.vision = VisionPipeline(self.settings)
        self.calculator = RollCalculator()
        self.preset_manager = PresetManager()
        self.foundry_client = FoundryClient(self.foundry_config)
        self.foundry_ws_server = FoundryWebSocketServer()
        self.formatter = MessageFormatter()

        # State
        self.detected_dice: list[DetectedDie] = []
        self.current_modifiers: list[Modifier] = []
        self.expected_roll: Optional[ExpectedRoll] = None
        self.auto_detect = True
        self.auto_send = False
        self._running = False
        self._last_detection_time = 0.0
        self._detection_cooldown = 1.0  # seconds

        # Setup UI
        self._setup_ui()

        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_ui(self):
        """Set up the main UI layout."""
        # Main container
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel - Camera and detection
        left_panel = ctk.CTkFrame(main_frame)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self._setup_camera_panel(left_panel)
        self._setup_detection_panel(left_panel)

        # Right panel - Controls and results
        right_panel = ctk.CTkFrame(main_frame, width=400)
        right_panel.pack(side="right", fill="y", padx=(5, 0))
        right_panel.pack_propagate(False)

        self._setup_control_panel(right_panel)
        self._setup_modifier_panel(right_panel)
        self._setup_result_panel(right_panel)
        self._setup_foundry_panel(right_panel)

    def _setup_camera_panel(self, parent):
        """Set up camera preview panel."""
        camera_frame = ctk.CTkFrame(parent)
        camera_frame.pack(fill="both", expand=True, pady=(0, 5))

        # Header
        header = ctk.CTkFrame(camera_frame, fg_color="transparent")
        header.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            header,
            text="Camera Feed",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")

        self.fps_label = ctk.CTkLabel(header, text="FPS: --")
        self.fps_label.pack(side="right")

        # Camera preview
        self.camera_label = ctk.CTkLabel(camera_frame, text="Camera not started")
        self.camera_label.pack(fill="both", expand=True, padx=10, pady=10)

        # Camera controls
        controls = ctk.CTkFrame(camera_frame, fg_color="transparent")
        controls.pack(fill="x", pady=5, padx=10)

        self.start_btn = ctk.CTkButton(
            controls,
            text="Start Camera",
            command=self._toggle_camera,
        )
        self.start_btn.pack(side="left", padx=5)

        self.detect_btn = ctk.CTkButton(
            controls,
            text="Detect Now",
            command=self._detect_now,
            state="disabled",
        )
        self.detect_btn.pack(side="left", padx=5)

        self.auto_detect_var = tk.BooleanVar(value=True)
        auto_check = ctk.CTkCheckBox(
            controls,
            text="Auto Detect",
            variable=self.auto_detect_var,
            command=self._toggle_auto_detect,
        )
        auto_check.pack(side="left", padx=10)

        # Camera selection
        ctk.CTkLabel(controls, text="Camera:").pack(side="right", padx=(10, 5))
        self.camera_var = tk.StringVar(value="0")
        camera_menu = ctk.CTkOptionMenu(
            controls,
            values=["0", "1", "2", "3"],
            variable=self.camera_var,
            width=60,
        )
        camera_menu.pack(side="right")

    def _setup_detection_panel(self, parent):
        """Set up detection results panel."""
        detection_frame = ctk.CTkFrame(parent)
        detection_frame.pack(fill="x", pady=(5, 0))

        # Header
        header = ctk.CTkFrame(detection_frame, fg_color="transparent")
        header.pack(fill="x", pady=5, padx=10)

        ctk.CTkLabel(
            header,
            text="Detected Dice",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            command=self._clear_detections,
        )
        clear_btn.pack(side="right")

        # Dice display area
        self.dice_frame = ctk.CTkScrollableFrame(detection_frame, height=150)
        self.dice_frame.pack(fill="x", padx=10, pady=10)

        self.dice_widgets: list[DiceDisplayWidget] = []

    def _setup_control_panel(self, parent):
        """Set up control panel."""
        control_frame = ctk.CTkFrame(parent)
        control_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            control_frame,
            text="Roll Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=10)

        # Character name
        name_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        name_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(name_frame, text="Character:").pack(side="left")
        self.character_entry = ctk.CTkEntry(name_frame, width=150)
        self.character_entry.insert(0, "Player")
        self.character_entry.pack(side="right")

        # Roll name
        roll_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        roll_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(roll_frame, text="Roll Name:").pack(side="left")
        self.roll_name_entry = ctk.CTkEntry(roll_frame, width=150)
        self.roll_name_entry.insert(0, "Attack Roll")
        self.roll_name_entry.pack(side="right")

        # Expected roll formula
        self.formula_input = RollFormulaInput(
            control_frame,
            on_change=self._on_formula_change,
        )
        self.formula_input.pack(fill="x", padx=10, pady=10)

        # Preset selector
        presets = self.preset_manager.list_presets()
        self.preset_selector = PresetSelector(
            control_frame,
            presets=presets,
            on_select=self._on_preset_select,
        )
        self.preset_selector.pack(fill="x", padx=10, pady=5)

    def _setup_modifier_panel(self, parent):
        """Set up modifier panel."""
        self.modifier_panel = ModifierPanel(
            parent,
            on_change=self._on_modifiers_change,
        )
        self.modifier_panel.pack(fill="x", pady=10)

    def _setup_result_panel(self, parent):
        """Set up result display panel."""
        result_frame = ctk.CTkFrame(parent)
        result_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            result_frame,
            text="Roll Result",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=10)

        # Result display
        self.result_text = ctk.CTkTextbox(result_frame, height=150)
        self.result_text.pack(fill="x", padx=10, pady=5)
        self.result_text.configure(state="disabled")

        # Total display
        self.total_label = ctk.CTkLabel(
            result_frame,
            text="Total: --",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.total_label.pack(pady=10)

    def _setup_foundry_panel(self, parent):
        """Set up Foundry VTT integration panel."""
        foundry_frame = ctk.CTkFrame(parent)
        foundry_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(
            foundry_frame,
            text="Foundry VTT",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=10)

        # Connection status
        status_frame = ctk.CTkFrame(foundry_frame, fg_color="transparent")
        status_frame.pack(fill="x", padx=10, pady=5)

        self.connection_label = ctk.CTkLabel(
            status_frame,
            text="● Disconnected",
            text_color="#ff6666",
        )
        self.connection_label.pack(side="left")

        connect_btn = ctk.CTkButton(
            status_frame,
            text="Connect",
            width=80,
            command=self._connect_foundry,
        )
        connect_btn.pack(side="right")

        # Send controls
        send_frame = ctk.CTkFrame(foundry_frame, fg_color="transparent")
        send_frame.pack(fill="x", padx=10, pady=10)

        self.send_btn = ctk.CTkButton(
            send_frame,
            text="Send to Foundry",
            command=self._send_to_foundry,
            state="disabled",
        )
        self.send_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.auto_send_var = tk.BooleanVar(value=False)
        auto_send_check = ctk.CTkCheckBox(
            send_frame,
            text="Auto",
            variable=self.auto_send_var,
            command=self._toggle_auto_send,
            width=60,
        )
        auto_send_check.pack(side="right")

    def _toggle_camera(self):
        """Toggle camera on/off."""
        if self._running:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        """Start camera capture."""
        camera_idx = int(self.camera_var.get())
        self.settings.camera_index = camera_idx

        if self.camera.start():
            self._running = True
            self.start_btn.configure(text="Stop Camera")
            self.detect_btn.configure(state="normal")

            # Initialize vision pipeline
            self.vision.initialize()

            # Start update loop
            self._update_camera()
        else:
            self.camera_label.configure(text="Failed to start camera")

    def _stop_camera(self):
        """Stop camera capture."""
        self._running = False
        self.camera.stop()
        self.start_btn.configure(text="Start Camera")
        self.detect_btn.configure(state="disabled")
        self.camera_label.configure(text="Camera stopped")

    def _update_camera(self):
        """Update camera preview."""
        if not self._running:
            return

        frame = self.camera.get_frame()
        if frame is not None:
            # Auto detection
            current_time = time.time()
            if (
                self.auto_detect
                and current_time - self._last_detection_time > self._detection_cooldown
            ):
                self._run_detection(frame)
                self._last_detection_time = current_time

            # Draw detections on frame
            if self.detected_dice:
                frame = self.vision.draw_results(frame, self.detected_dice)

            # Convert to display format
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (800, 600))
            img = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(img)

            self.camera_label.configure(image=photo, text="")
            self.camera_label.image = photo

            # Update FPS
            self.fps_label.configure(text=f"FPS: {self.camera.fps:.1f}")

        # Schedule next update
        self.after(33, self._update_camera)  # ~30 FPS

    def _detect_now(self):
        """Run detection immediately."""
        frame = self.camera.get_frame()
        if frame is not None:
            self._run_detection(frame)

    def _run_detection(self, frame: np.ndarray):
        """Run dice detection on frame."""
        # Parse expected roll
        formula = self.formula_input.get_formula()
        expected = ExpectedRoll.parse(formula) if formula else None

        # Run detection
        detected = self.vision.process_frame(frame, expected)

        if detected:
            self.detected_dice = detected
            self._update_dice_display()
            self._calculate_result()

    def _update_dice_display(self):
        """Update the dice display widgets."""
        # Clear existing widgets
        for widget in self.dice_widgets:
            widget.destroy()
        self.dice_widgets.clear()

        # Create new widgets
        for die in self.detected_dice:
            widget = DiceDisplayWidget(
                self.dice_frame,
                die=die,
                on_correct=self._on_die_corrected,
                on_confirm=self._on_die_confirmed,
            )
            widget.pack(side="left", padx=5, pady=5)
            self.dice_widgets.append(widget)

    def _on_die_corrected(self, die: DetectedDie, value: int, dice_type: DiceType):
        """Handle die value correction."""
        die.user_corrected_value = value
        die.user_corrected_type = dice_type
        self._calculate_result()

        # Save sample if configured
        if self.settings.save_corrected_samples:
            frame = self.camera.get_frame()
            if frame is not None:
                self.vision.save_sample(frame, die, value, dice_type)

    def _on_die_confirmed(self, die: DetectedDie):
        """Handle die confirmation."""
        die.is_confirmed = True
        self._calculate_result()

        # Check if all dice confirmed and auto-send enabled
        if self.auto_send and all(d.is_confirmed for d in self.detected_dice):
            self._send_to_foundry()

    def _clear_detections(self):
        """Clear all detections."""
        self.detected_dice.clear()
        self._update_dice_display()
        self._clear_result()

    def _on_formula_change(self, formula: str):
        """Handle formula change."""
        self.expected_roll = ExpectedRoll.parse(formula) if formula else None

    def _on_preset_select(self, preset: ModifierPreset):
        """Handle preset selection."""
        self.modifier_panel.set_preset(preset)
        self.roll_name_entry.delete(0, tk.END)
        self.roll_name_entry.insert(0, preset.name)
        self.formula_input._set_formula(preset.dice_formula)
        self.current_modifiers = self.modifier_panel.get_modifiers()
        self._calculate_result()

    def _on_modifiers_change(self, modifiers: list[Modifier]):
        """Handle modifier changes."""
        self.current_modifiers = modifiers
        self._calculate_result()

    def _calculate_result(self):
        """Calculate and display roll result."""
        if not self.detected_dice:
            self._clear_result()
            return

        # Update calculator character name
        self.calculator.character_name = self.character_entry.get()

        # Calculate result
        result = self.calculator.calculate(
            dice=self.detected_dice,
            modifiers=self.current_modifiers,
            roll_name=self.roll_name_entry.get(),
            roll_type=RollType.CUSTOM,
            expected_roll=self.expected_roll,
        )

        # Format and display
        formatted = self.formatter.format_roll(result)

        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", formatted)
        self.result_text.configure(state="disabled")

        self.total_label.configure(text=f"Total: {result.final_total}")

        # Enable send button if all confirmed or high confidence
        if not result.requires_confirmation:
            self.send_btn.configure(state="normal")
        else:
            self.send_btn.configure(state="disabled")

    def _clear_result(self):
        """Clear result display."""
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.configure(state="disabled")
        self.total_label.configure(text="Total: --")
        self.send_btn.configure(state="disabled")

    def _toggle_auto_detect(self):
        """Toggle auto detection."""
        self.auto_detect = self.auto_detect_var.get()

    def _toggle_auto_send(self):
        """Toggle auto send."""
        self.auto_send = self.auto_send_var.get()

    def _connect_foundry(self):
        """Connect to Foundry VTT via WebSocket server."""
        # Start WebSocket server for Foundry module to connect to
        if self.foundry_ws_server.start():
            self.connection_label.configure(
                text="● Server Running (ws://localhost:8765)",
                text_color="#66ff66",
            )
        else:
            # Fall back to HTTP client
            if self.foundry_client.connect():
                self.connection_label.configure(
                    text="● Connected (HTTP)",
                    text_color="#66ff66",
                )
            else:
                self.connection_label.configure(
                    text="● Connection Failed",
                    text_color="#ff6666",
                )

    def _send_to_foundry(self):
        """Send roll result to Foundry VTT."""
        if not self.detected_dice:
            return

        # Calculate final result
        self.calculator.character_name = self.character_entry.get()
        result = self.calculator.calculate(
            dice=self.detected_dice,
            modifiers=self.current_modifiers,
            roll_name=self.roll_name_entry.get(),
            roll_type=RollType.CUSTOM,
            expected_roll=self.expected_roll,
        )

        # Send to Foundry via WebSocket server (preferred) or HTTP client
        if self.foundry_ws_server.is_running and self.foundry_ws_server.client_count > 0:
            success = self.foundry_ws_server.send_roll(result)
        else:
            success = self.foundry_client.send_roll(result)

        if success:
            # Clear after successful send
            self._clear_detections()
        else:
            # Show error
            self.connection_label.configure(
                text="● Send Failed",
                text_color="#ffaa00",
            )

    def _on_close(self):
        """Handle window close."""
        self._running = False
        self.camera.stop()
        self.foundry_client.disconnect()
        self.foundry_ws_server.stop()
        self.destroy()

    def run(self):
        """Run the application."""
        self.mainloop()
