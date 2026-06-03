from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

from dice_detector.camera import CameraCapture
from dice_detector.models import CalibrationSettings, CameraDevice

if TYPE_CHECKING:
    from dice_detector.training.annotator import AnnotationTool


class CaptureWindow(ctk.CTk):
    def __init__(self, tool: AnnotationTool, camera_index: int) -> None:
        super().__init__()
        self.tool = tool
        self.captured_count = 0
        self.cancelled = False
        self.active_index = camera_index
        self.device_list = CameraDevice.list_available() or [
            CameraDevice(index=camera_index, label=f"Camera {camera_index}")
        ]

        settings = CalibrationSettings(camera_index=camera_index)
        self.camera = CameraCapture(settings)
        if not self.camera.start():
            self._show_camera_error()
            self.cancelled = True
            self.captured_count = -1
            self.after(0, self.destroy)
            return

        self.title("Dice Capture")
        self.geometry("960x720")
        ctk.set_appearance_mode("dark")

        self.preview_label = ctk.CTkLabel(self, text="")
        self.preview_label.pack(fill="both", expand=True, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(0, 5))

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(button_row, text="Save photo (Space)", command=self._save_frame).pack(
            side="left", padx=5
        )
        ctk.CTkButton(button_row, text="Annotate", command=self._finish).pack(side="left", padx=5)
        ctk.CTkButton(
            button_row, text="Prev camera [", width=100, command=lambda: self._switch_camera(-1)
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            button_row, text="Next camera ]", width=100, command=lambda: self._switch_camera(1)
        ).pack(side="left", padx=5)
        ctk.CTkButton(button_row, text="Quit", fg_color="#5a2d2d", command=self._quit).pack(
            side="right", padx=5
        )

        self.bind("<space>", lambda _e: self._save_frame())
        self.bind("<KeyPress-s>", lambda _e: self._save_frame())
        self.bind("<KeyPress-a>", lambda _e: self._finish())
        self.bind("<KeyPress-q>", lambda _e: self._quit())
        self.bind("<Escape>", lambda _e: self._quit())
        self.bind("<KeyPress-bracketleft>", lambda _e: self._switch_camera(-1))
        self.bind("<KeyPress-bracketright>", lambda _e: self._switch_camera(1))

        self._preview_image: ctk.CTkImage | None = None
        self._update_preview()

    def _show_camera_error(self) -> None:
        print(f"Failed to open camera index {self.active_index}")
        for device in CameraDevice.list_available():
            print(f"  [{device.index}] {device.label}")

    def _camera_label(self) -> str:
        return next(
            (d.label for d in self.device_list if d.index == self.active_index),
            f"Camera {self.active_index}",
        )

    def _update_preview(self) -> None:
        if not self.camera.is_running:
            return
        frame = self.camera.get_frame()
        if frame is None:
            self.after(33, self._update_preview)
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        max_size = (900, 600)
        pil.thumbnail(max_size, Image.Resampling.LANCZOS)
        self._preview_image = ctk.CTkImage(light_image=pil, dark_image=pil, size=pil.size)
        self.preview_label.configure(image=self._preview_image, text="")
        self.status_label.configure(
            text=(
                f"{self._camera_label()} | Saved: {self.captured_count} | "
                "Space=save | a=annotate | [/]=camera | q=quit"
            )
        )
        self._last_frame = frame
        self.after(33, self._update_preview)

    def _save_frame(self) -> None:
        if not hasattr(self, "_last_frame"):
            return
        filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        path = self.tool.images_dir / filename
        cv2.imwrite(str(path), self._last_frame)
        self.captured_count += 1
        print(f"Saved {path.name}")

    def _switch_camera(self, step: int) -> None:
        if len(self.device_list) < 2:
            return
        current_pos = next(
            (i for i, d in enumerate(self.device_list) if d.index == self.active_index),
            0,
        )
        next_pos = (current_pos + step) % len(self.device_list)
        self.active_index = self.device_list[next_pos].index
        self.camera.stop()
        settings = CalibrationSettings(camera_index=self.active_index)
        self.camera = CameraCapture(settings)
        if self.camera.start():
            print(f"Switched to [{self.active_index}] {self.device_list[next_pos].label}")
        else:
            print(f"Failed to switch to camera {self.active_index}")

    def _finish(self) -> None:
        self.camera.stop()
        self.destroy()

    def _quit(self) -> None:
        self.cancelled = True
        self.captured_count = -1
        self.camera.stop()
        self.destroy()


class AnnotateWindow(ctk.CTk):
    def __init__(self, tool: AnnotationTool) -> None:
        super().__init__()
        self.tool = tool
        self.images = tool.get_image_list()
        if not self.images:
            print("No images found to annotate")
            self.destroy()
            return

        self.current_idx = 0
        self.disp_w = 900
        self.disp_h = 600
        self.scale = 1.0
        self.drawing = False
        self.start_canvas = (0, 0)
        self.end_canvas = (0, 0)
        self._photo: ImageTk.PhotoImage | None = None

        self.title("Dice Annotator")
        self.geometry("980x760")
        ctk.set_appearance_mode("dark")

        self.status_label = ctk.CTkLabel(self, text="", anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(10, 0))

        canvas_frame = ctk.CTkFrame(self)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        nav_row = ctk.CTkFrame(self, fg_color="transparent")
        nav_row.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(nav_row, text="Previous", command=self._prev_image).pack(side="left", padx=5)
        ctk.CTkButton(nav_row, text="Save", command=self._save).pack(side="left", padx=5)
        ctk.CTkButton(nav_row, text="Next", command=self._next_image).pack(side="left", padx=5)
        ctk.CTkButton(nav_row, text="Quit", fg_color="#5a2d2d", command=self.destroy).pack(
            side="right", padx=5
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Key>", self._on_key)

        self._load_current_image()

    def _load_current_image(self) -> None:
        self.tool.load_image(self.images[self.current_idx])
        self._redraw()

    def _redraw(self) -> None:
        if self.tool.current_image is None:
            return

        display = self.tool.draw_annotations(self.tool.current_image.copy())
        if self.drawing:
            x1, y1 = self.start_canvas
            x2, y2 = self.end_canvas
            cv2.rectangle(display, self._canvas_to_image(x1, y1), self._canvas_to_image(x2, y2), (0, 255, 0), 2)

        h, w = display.shape[:2]
        self.scale = min(self.disp_w / w, self.disp_h / h, 1.0)
        self.disp_w = int(w * self.scale)
        self.disp_h = int(h * self.scale)

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb).resize((self.disp_w, self.disp_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(pil)

        self.canvas.delete("all")
        self.canvas.configure(width=self.disp_w, height=self.disp_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        class_name = self.tool.DICE_CLASSES[self.tool.current_class_idx]
        max_val = self.tool._max_value_for_class(class_name)
        value_hint = (
            f"Value: {self.tool.value_buffer or '-'} (max {max_val})"
            if self.tool.value_entry_mode
            else "Value: press v"
        )
        self.status_label.configure(
            text=(
                f"Image {self.current_idx + 1}/{len(self.images)} | "
                f"Class: {class_name} | Boxes: {len(self.tool.annotations)} | {value_hint} | "
                "Drag=box 1-7=class v=value z=undo n/p=nav"
            )
        )

    def _canvas_to_image(self, cx: int, cy: int) -> tuple[int, int]:
        return int(cx / self.scale), int(cy / self.scale)

    def _on_press(self, event: tk.Event) -> None:
        self.drawing = True
        self.start_canvas = (event.x, event.y)
        self.end_canvas = (event.x, event.y)

    def _on_drag(self, event: tk.Event) -> None:
        if not self.drawing:
            return
        self.end_canvas = (event.x, event.y)
        self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        if not self.drawing:
            return
        self.drawing = False
        self.end_canvas = (event.x, event.y)

        x1, y1 = self._canvas_to_image(*self.start_canvas)
        x2, y2 = self._canvas_to_image(*self.end_canvas)
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)

        if width > 10 and height > 10:
            class_name = self.tool.DICE_CLASSES[self.tool.current_class_idx]
            value = self.tool._consume_value_for_class(class_name)
            self.tool.add_annotation(
                bbox=(left, top, width, height),
                class_name=class_name,
                value=value,
            )
        self._redraw()

    def _on_key(self, event: tk.Event) -> None:
        keysym = event.keysym.lower()
        class_name = self.tool.DICE_CLASSES[self.tool.current_class_idx]

        if keysym in ("q", "escape"):
            self.destroy()
            return

        if keysym == "v":
            self.tool.value_entry_mode = not self.tool.value_entry_mode
            if not self.tool.value_entry_mode:
                self.tool._clear_value_buffer()
        elif keysym == "x":
            self.tool._clear_value_buffer()
            if self.tool.annotations:
                self.tool.annotations[-1]["value"] = None
        elif keysym == "z":
            self.tool.remove_last_annotation()
        elif keysym == "s":
            self._save()
        elif keysym in ("n", "right"):
            self._next_image()
        elif keysym in ("p", "left"):
            self._prev_image()
        elif keysym == "c" and self.tool.value_entry_mode:
            self.tool._clear_value_buffer()
        elif keysym == "return" and self.tool.value_entry_mode:
            self.tool._apply_value_to_last_annotation(class_name)
        elif keysym == "backspace" and self.tool.value_entry_mode:
            self.tool.value_buffer = self.tool.value_buffer[:-1]
        elif self.tool.value_entry_mode and len(keysym) == 1 and keysym.isdigit():
            if len(self.tool.value_buffer) < 3:
                self.tool.value_buffer += keysym
        elif not self.tool.value_entry_mode and keysym in "1234567":
            self.tool.current_class_idx = int(keysym) - 1

        self._redraw()

    def _save(self) -> None:
        self.tool.save_annotations()
        if self.tool.current_image_path:
            print(f"Saved annotations for {self.tool.current_image_path.name}")

    def _next_image(self) -> None:
        self._save()
        self.current_idx = (self.current_idx + 1) % len(self.images)
        self._load_current_image()

    def _prev_image(self) -> None:
        self._save()
        self.current_idx = (self.current_idx - 1) % len(self.images)
        self._load_current_image()


def run_session_gui(tool: AnnotationTool, camera_index: int, skip_capture: bool) -> None:
    if not skip_capture:
        print("\n=== Camera capture ===")
        print("Roll dice on the tray, then save a still frame.")
        print(f"Images save to: {tool.images_dir.resolve()}\n")
        capture = CaptureWindow(tool, camera_index)
        capture.mainloop()
        if capture.captured_count < 0:
            print("Capture cancelled.")
            return
        print(f"\nCaptured {capture.captured_count} image(s).")

    annotate = AnnotateWindow(tool)
    if tool.get_image_list():
        annotate.mainloop()
