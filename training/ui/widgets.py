"""UI widgets for dice detector."""

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from ..models import DetectedDie, DiceType, Modifier, ModifierPreset


class DiceDisplayWidget(ctk.CTkFrame):
    """Widget for displaying a detected die with its value and confidence."""

    def __init__(
        self,
        parent,
        die: DetectedDie,
        on_correct: Optional[Callable[[DetectedDie, int, DiceType], None]] = None,
        on_confirm: Optional[Callable[[DetectedDie], None]] = None,
        **kwargs,
    ):
        """Initialize dice display widget.

        Args:
            parent: Parent widget.
            die: Detected die to display.
            on_correct: Callback when user corrects the value.
            on_confirm: Callback when user confirms the detection.
        """
        super().__init__(parent, **kwargs)
        self.die = die
        self.on_correct = on_correct
        self.on_confirm = on_confirm

        self._setup_ui()

    def _setup_ui(self):
        """Set up the widget UI."""
        # Determine color based on confidence
        if self.die.is_confirmed:
            bg_color = "#2d5a2d"  # Green
        elif self.die.requires_confirmation:
            bg_color = "#5a4a2d"  # Orange/yellow
        elif self.die.confidence >= 0.8:
            bg_color = "#2d5a2d"  # Green
        elif self.die.confidence >= 0.6:
            bg_color = "#5a5a2d"  # Yellow
        else:
            bg_color = "#5a2d2d"  # Red

        self.configure(fg_color=bg_color, corner_radius=10)

        # Dice type label
        type_label = ctk.CTkLabel(
            self,
            text=self.die.dice_type.value,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        type_label.pack(pady=(10, 5))

        # Value display
        value_frame = ctk.CTkFrame(self, fg_color="transparent")
        value_frame.pack(pady=5)

        self.value_label = ctk.CTkLabel(
            value_frame,
            text=str(self.die.final_value),
            font=ctk.CTkFont(size=32, weight="bold"),
        )
        self.value_label.pack(side="left", padx=5)

        # Confidence indicator
        conf_text = f"{self.die.confidence:.0%}"
        conf_label = ctk.CTkLabel(
            self,
            text=conf_text,
            font=ctk.CTkFont(size=12),
        )
        conf_label.pack(pady=2)

        # Warning indicator
        if self.die.notes:
            warning_label = ctk.CTkLabel(
                self,
                text="⚠️ " + self.die.notes[0][:20],
                font=ctk.CTkFont(size=10),
                text_color="#ffaa00",
            )
            warning_label.pack(pady=2)

        # Correction controls (if needs confirmation)
        if self.die.requires_confirmation or not self.die.is_confirmed:
            self._add_correction_controls()

    def _add_correction_controls(self):
        """Add correction controls to the widget."""
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(pady=10, fill="x", padx=10)

        # Value adjustment
        minus_btn = ctk.CTkButton(
            control_frame,
            text="-",
            width=30,
            command=self._decrease_value,
        )
        minus_btn.pack(side="left", padx=2)

        plus_btn = ctk.CTkButton(
            control_frame,
            text="+",
            width=30,
            command=self._increase_value,
        )
        plus_btn.pack(side="left", padx=2)

        # Confirm button
        confirm_btn = ctk.CTkButton(
            control_frame,
            text="✓",
            width=30,
            fg_color="#2d5a2d",
            command=self._confirm,
        )
        confirm_btn.pack(side="right", padx=2)

    def _decrease_value(self):
        """Decrease the die value."""
        new_value = max(1, self.die.final_value - 1)
        self._update_value(new_value)

    def _increase_value(self):
        """Increase the die value."""
        max_val = self.die.dice_type.max_value
        new_value = min(max_val, self.die.final_value + 1)
        self._update_value(new_value)

    def _update_value(self, new_value: int):
        """Update the displayed value."""
        self.die.user_corrected_value = new_value
        self.value_label.configure(text=str(new_value))
        if self.on_correct:
            self.on_correct(self.die, new_value, self.die.dice_type)

    def _confirm(self):
        """Confirm the detection."""
        self.die.is_confirmed = True
        self.configure(fg_color="#2d5a2d")
        if self.on_confirm:
            self.on_confirm(self.die)


class ModifierPanel(ctk.CTkFrame):
    """Panel for displaying and editing modifiers."""

    def __init__(
        self,
        parent,
        preset: Optional[ModifierPreset] = None,
        on_change: Optional[Callable[[list[Modifier]], None]] = None,
        **kwargs,
    ):
        """Initialize modifier panel.

        Args:
            parent: Parent widget.
            preset: Optional preset to load.
            on_change: Callback when modifiers change.
        """
        super().__init__(parent, **kwargs)
        self.preset = preset
        self.modifiers: list[Modifier] = []
        self.on_change = on_change
        self.modifier_widgets: list[dict] = []

        if preset:
            self.modifiers = [
                Modifier(name=m.name, value=m.value, enabled=m.enabled)
                for m in preset.modifiers
            ]

        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI."""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))

        title = ctk.CTkLabel(
            header_frame,
            text="Modifiers",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title.pack(side="left")

        # Total display
        self.total_label = ctk.CTkLabel(
            header_frame,
            text="Total: +0",
            font=ctk.CTkFont(size=14),
        )
        self.total_label.pack(side="right")

        # Modifier list
        self.modifier_frame = ctk.CTkScrollableFrame(self, height=200)
        self.modifier_frame.pack(fill="both", expand=True, pady=5)

        # Add existing modifiers
        for mod in self.modifiers:
            self._add_modifier_row(mod)

        # Add new modifier button
        add_btn = ctk.CTkButton(
            self,
            text="+ Add Modifier",
            command=self._add_new_modifier,
        )
        add_btn.pack(pady=10)

        self._update_total()

    def _add_modifier_row(self, modifier: Modifier):
        """Add a modifier row to the panel."""
        row_frame = ctk.CTkFrame(self.modifier_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        # Enable checkbox
        enabled_var = tk.BooleanVar(value=modifier.enabled)
        checkbox = ctk.CTkCheckBox(
            row_frame,
            text="",
            variable=enabled_var,
            width=20,
            command=lambda: self._toggle_modifier(modifier, enabled_var.get()),
        )
        checkbox.pack(side="left", padx=5)

        # Name entry
        name_entry = ctk.CTkEntry(row_frame, width=120)
        name_entry.insert(0, modifier.name)
        name_entry.pack(side="left", padx=5)
        name_entry.bind("<FocusOut>", lambda e: self._update_modifier_name(modifier, name_entry.get()))

        # Value entry
        value_entry = ctk.CTkEntry(row_frame, width=50)
        value_entry.insert(0, str(modifier.value))
        value_entry.pack(side="left", padx=5)
        value_entry.bind("<FocusOut>", lambda e: self._update_modifier_value(modifier, value_entry.get()))

        # Remove button
        remove_btn = ctk.CTkButton(
            row_frame,
            text="×",
            width=30,
            fg_color="#5a2d2d",
            command=lambda: self._remove_modifier(modifier, row_frame),
        )
        remove_btn.pack(side="right", padx=5)

        self.modifier_widgets.append({
            "frame": row_frame,
            "modifier": modifier,
            "enabled_var": enabled_var,
        })

    def _toggle_modifier(self, modifier: Modifier, enabled: bool):
        """Toggle modifier enabled state."""
        modifier.enabled = enabled
        self._update_total()
        self._notify_change()

    def _update_modifier_name(self, modifier: Modifier, name: str):
        """Update modifier name."""
        modifier.name = name
        self._notify_change()

    def _update_modifier_value(self, modifier: Modifier, value_str: str):
        """Update modifier value."""
        try:
            modifier.value = int(value_str)
        except ValueError:
            pass
        self._update_total()
        self._notify_change()

    def _remove_modifier(self, modifier: Modifier, row_frame):
        """Remove a modifier."""
        self.modifiers.remove(modifier)
        row_frame.destroy()
        self.modifier_widgets = [w for w in self.modifier_widgets if w["modifier"] != modifier]
        self._update_total()
        self._notify_change()

    def _add_new_modifier(self):
        """Add a new empty modifier."""
        new_mod = Modifier(name="New Modifier", value=0)
        self.modifiers.append(new_mod)
        self._add_modifier_row(new_mod)
        self._notify_change()

    def _update_total(self):
        """Update the total display."""
        total = sum(m.value for m in self.modifiers if m.enabled)
        sign = "+" if total >= 0 else ""
        self.total_label.configure(text=f"Total: {sign}{total}")

    def _notify_change(self):
        """Notify callback of modifier changes."""
        if self.on_change:
            self.on_change(self.modifiers)

    def get_modifiers(self) -> list[Modifier]:
        """Get current modifiers."""
        return self.modifiers

    def set_preset(self, preset: ModifierPreset):
        """Set modifiers from a preset."""
        # Clear existing
        for widget in self.modifier_widgets:
            widget["frame"].destroy()
        self.modifier_widgets.clear()
        self.modifiers.clear()

        # Add from preset
        self.preset = preset
        for mod in preset.modifiers:
            new_mod = Modifier(name=mod.name, value=mod.value, enabled=mod.enabled)
            self.modifiers.append(new_mod)
            self._add_modifier_row(new_mod)

        self._update_total()


class CorrectionDialog(ctk.CTkToplevel):
    """Dialog for correcting a detected die."""

    def __init__(
        self,
        parent,
        die: DetectedDie,
        cropped_image=None,
        on_save: Optional[Callable[[int, DiceType], None]] = None,
        **kwargs,
    ):
        """Initialize correction dialog.

        Args:
            parent: Parent window.
            die: Die to correct.
            cropped_image: Optional cropped image of the die.
            on_save: Callback when correction is saved.
        """
        super().__init__(parent, **kwargs)
        self.die = die
        self.cropped_image = cropped_image
        self.on_save = on_save

        self.title("Correct Detection")
        self.geometry("400x500")
        self.resizable(False, False)

        self._setup_ui()

        # Make modal
        self.transient(parent)
        self.grab_set()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Image display (placeholder)
        if self.cropped_image is not None:
            # Would display the cropped image here
            img_label = ctk.CTkLabel(
                self,
                text="[Die Image]",
                height=150,
            )
            img_label.pack(pady=20)

        # Current detection info
        info_frame = ctk.CTkFrame(self)
        info_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            info_frame,
            text=f"Detected: {self.die.dice_type.value} = {self.die.detected_value}",
            font=ctk.CTkFont(size=14),
        ).pack(pady=5)

        ctk.CTkLabel(
            info_frame,
            text=f"Confidence: {self.die.confidence:.0%}",
            font=ctk.CTkFont(size=12),
        ).pack(pady=2)

        if self.die.notes:
            ctk.CTkLabel(
                info_frame,
                text=f"Notes: {', '.join(self.die.notes)}",
                font=ctk.CTkFont(size=11),
                text_color="#ffaa00",
            ).pack(pady=2)

        # Correction inputs
        correction_frame = ctk.CTkFrame(self)
        correction_frame.pack(fill="x", padx=20, pady=20)

        # Dice type selection
        ctk.CTkLabel(
            correction_frame,
            text="Correct Type:",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(10, 5))

        self.type_var = tk.StringVar(value=self.die.dice_type.value)
        type_options = [dt.value for dt in DiceType if dt != DiceType.UNKNOWN]
        type_menu = ctk.CTkOptionMenu(
            correction_frame,
            values=type_options,
            variable=self.type_var,
        )
        type_menu.pack(fill="x", pady=5)

        # Value input
        ctk.CTkLabel(
            correction_frame,
            text="Correct Value:",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(10, 5))

        self.value_entry = ctk.CTkEntry(correction_frame)
        self.value_entry.insert(0, str(self.die.detected_value))
        self.value_entry.pack(fill="x", pady=5)

        # Quick value buttons
        quick_frame = ctk.CTkFrame(correction_frame, fg_color="transparent")
        quick_frame.pack(fill="x", pady=10)

        max_val = self.die.dice_type.max_value
        common_values = [1, max_val // 2, max_val]
        if self.die.dice_type == DiceType.D20:
            common_values = [1, 6, 9, 20]

        for val in common_values:
            btn = ctk.CTkButton(
                quick_frame,
                text=str(val),
                width=50,
                command=lambda v=val: self._set_value(v),
            )
            btn.pack(side="left", padx=5)

        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=20)

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            fg_color="gray",
            command=self.destroy,
        )
        cancel_btn.pack(side="left", padx=10)

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save Correction",
            fg_color="#2d5a2d",
            command=self._save,
        )
        save_btn.pack(side="right", padx=10)

    def _set_value(self, value: int):
        """Set the value entry."""
        self.value_entry.delete(0, tk.END)
        self.value_entry.insert(0, str(value))

    def _save(self):
        """Save the correction."""
        try:
            value = int(self.value_entry.get())
            dice_type = DiceType(self.type_var.get())

            if self.on_save:
                self.on_save(value, dice_type)

            self.destroy()
        except ValueError:
            # Invalid input
            pass


class PresetSelector(ctk.CTkFrame):
    """Widget for selecting modifier presets."""

    def __init__(
        self,
        parent,
        presets: list[ModifierPreset],
        on_select: Optional[Callable[[ModifierPreset], None]] = None,
        **kwargs,
    ):
        """Initialize preset selector.

        Args:
            parent: Parent widget.
            presets: Available presets.
            on_select: Callback when preset is selected.
        """
        super().__init__(parent, **kwargs)
        self.presets = {p.name: p for p in presets}
        self.on_select = on_select

        self._setup_ui()

    def _setup_ui(self):
        """Set up the selector UI."""
        ctk.CTkLabel(
            self,
            text="Preset:",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=5)

        preset_names = list(self.presets.keys())
        self.preset_var = tk.StringVar(value=preset_names[0] if preset_names else "")

        self.preset_menu = ctk.CTkOptionMenu(
            self,
            values=preset_names,
            variable=self.preset_var,
            command=self._on_preset_selected,
        )
        self.preset_menu.pack(side="left", padx=5, fill="x", expand=True)

    def _on_preset_selected(self, name: str):
        """Handle preset selection."""
        preset = self.presets.get(name)
        if preset and self.on_select:
            self.on_select(preset)

    def update_presets(self, presets: list[ModifierPreset]):
        """Update available presets."""
        self.presets = {p.name: p for p in presets}
        self.preset_menu.configure(values=list(self.presets.keys()))


class RollFormulaInput(ctk.CTkFrame):
    """Widget for inputting expected roll formula."""

    def __init__(
        self,
        parent,
        on_change: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        """Initialize formula input.

        Args:
            parent: Parent widget.
            on_change: Callback when formula changes.
        """
        super().__init__(parent, **kwargs)
        self.on_change = on_change

        self._setup_ui()

    def _setup_ui(self):
        """Set up the input UI."""
        ctk.CTkLabel(
            self,
            text="Expected Roll:",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=5)

        self.formula_entry = ctk.CTkEntry(self, width=150)
        self.formula_entry.insert(0, "1d20")
        self.formula_entry.pack(side="left", padx=5)
        self.formula_entry.bind("<Return>", self._on_change)
        self.formula_entry.bind("<FocusOut>", self._on_change)

        # Quick formula buttons
        quick_formulas = ["1d20", "2d6", "1d12", "d100", "4d6"]
        for formula in quick_formulas:
            btn = ctk.CTkButton(
                self,
                text=formula,
                width=50,
                command=lambda f=formula: self._set_formula(f),
            )
            btn.pack(side="left", padx=2)

    def _set_formula(self, formula: str):
        """Set the formula."""
        self.formula_entry.delete(0, tk.END)
        self.formula_entry.insert(0, formula)
        self._on_change(None)

    def _on_change(self, event):
        """Handle formula change."""
        if self.on_change:
            self.on_change(self.formula_entry.get())

    def get_formula(self) -> str:
        """Get current formula."""
        return self.formula_entry.get()
