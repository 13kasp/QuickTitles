"""
QuickTitles — fully custom HSV + alpha color picker dialog.
"""

import colorsys
import tkinter as tk
from typing import Optional

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from utils import _apply_icon


class ColorPickerDialog(ctk.CTkToplevel):
    """A fully custom HSV + alpha color picker with hex input."""

    SV_SIZE = 220
    HUE_W   = 22
    ALPHA_H = 22
    PAD     = 12

    def __init__(self, parent, initial_color=(255, 255, 255, 255), title="Pick colour"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.after(300, lambda: _apply_icon(self))

        r, g, b, a = (int(x) for x in initial_color)
        h, s, v    = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._h    = h
        self._s    = s
        self._v    = v
        self._a    = a
        self._updating = False
        self._result   = None

        self._build_ui()
        self._draw_all()
        self._update_fields()

    def _build_ui(self):
        P, SS, HW, AH = self.PAD, self.SV_SIZE, self.HUE_W, self.ALPHA_H

        y_sv      = P
        y_alpha   = y_sv + SS + P
        y_swatch  = y_alpha + AH + P
        y_rgba    = y_swatch + 38
        y_entries = y_rgba + 16
        y_buttons = y_entries + 36
        total_h   = y_buttons + 42

        x_hue   = P + SS + P
        total_w = x_hue + HW + P

        self.configure(fg_color="#1e1e1e")

        self._sv_canvas = tk.Canvas(self, width=SS, height=SS, bd=0, highlightthickness=0, bg="#1e1e1e")
        self._sv_canvas.place(x=P, y=y_sv)
        self._sv_canvas.bind("<ButtonPress-1>", self._on_sv_drag)
        self._sv_canvas.bind("<B1-Motion>",     self._on_sv_drag)

        self._hue_canvas = tk.Canvas(self, width=HW, height=SS, bd=0, highlightthickness=0, bg="#1e1e1e")
        self._hue_canvas.place(x=x_hue, y=y_sv)
        self._hue_canvas.bind("<ButtonPress-1>", self._on_hue_drag)
        self._hue_canvas.bind("<B1-Motion>",     self._on_hue_drag)

        self._alpha_canvas = tk.Canvas(self, width=SS, height=AH, bd=0, highlightthickness=0, bg="#1e1e1e")
        self._alpha_canvas.place(x=P, y=y_alpha)
        self._alpha_canvas.bind("<ButtonPress-1>", self._on_alpha_drag)
        self._alpha_canvas.bind("<B1-Motion>",     self._on_alpha_drag)

        self._swatch = tk.Label(self, width=4, height=2, bg="#ffffff", relief="flat", bd=0)
        self._swatch.place(x=P, y=y_swatch)

        self._hex_var = tk.StringVar()
        ctk.CTkEntry(self, textvariable=self._hex_var, width=130, height=28,
                     font=("Consolas", 12)).place(x=P + 50, y=y_swatch + 2)
        self._hex_var.trace_add("write", self._on_hex_change)

        for i, ch in enumerate(("R", "G", "B", "A")):
            tk.Label(self, text=ch, fg="#888888", bg="#1e1e1e",
                     font=("Consolas", 10)).place(x=P + i * 50, y=y_rgba)

        self._rgba_vars = [tk.StringVar() for _ in range(4)]
        for i, sv in enumerate(self._rgba_vars):
            ctk.CTkEntry(self, textvariable=sv, width=44, height=28,
                         font=("Consolas", 11)).place(x=P + i * 50, y=y_entries)
            sv.trace_add("write", lambda *_, idx=i: self._on_rgba_change(idx))

        ctk.CTkButton(self, text="OK", width=95, height=32, anchor="center",
                      command=self._ok).place(x=P, y=y_buttons)
        ctk.CTkButton(self, text="Cancel", width=95, height=32, anchor="center",
                      fg_color="#3a3a3a", hover_color="#555",
                      command=self.destroy).place(x=P + 103, y=y_buttons)
        self.geometry(f"{total_w}x{total_h}")

    def _draw_sv(self):
        SS = self.SV_SIZE
        s_vals = np.linspace(0, 1, SS, dtype=np.float32)
        v_vals = np.linspace(1, 0, SS, dtype=np.float32)
        s_grid, v_grid = np.meshgrid(s_vals, v_vals)
        hr, hg, hb = colorsys.hsv_to_rgb(self._h, 1.0, 1.0)
        r = v_grid * (1 - s_grid + s_grid * hr)
        g = v_grid * (1 - s_grid + s_grid * hg)
        b = v_grid * (1 - s_grid + s_grid * hb)
        img_arr = (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)
        img = Image.fromarray(img_arr, "RGB")
        self._sv_tk = ImageTk.PhotoImage(img)
        self._sv_canvas.delete("all")
        self._sv_canvas.create_image(0, 0, anchor="nw", image=self._sv_tk)
        cx, cy = int(self._s * (SS - 1)), int((1 - self._v) * (SS - 1))
        self._sv_canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, outline="white", width=2)

    def _draw_hue(self):
        SS, HW = self.SV_SIZE, self.HUE_W
        h_vals = np.linspace(0, 1, SS, dtype=np.float32)
        rgb    = np.array([colorsys.hsv_to_rgb(h, 1.0, 1.0) for h in h_vals], dtype=np.float32)
        strip  = (rgb[:, None, :] * 255).astype(np.uint8).repeat(HW, axis=1)
        self._hue_tk = ImageTk.PhotoImage(Image.fromarray(strip, "RGB"))
        self._hue_canvas.delete("all")
        self._hue_canvas.create_image(0, 0, anchor="nw", image=self._hue_tk)
        cy = int(self._h * (SS - 1))
        self._hue_canvas.create_line(0, cy, HW, cy, fill="white", width=2)

    def _draw_alpha(self):
        SS, AH  = self.SV_SIZE, self.ALPHA_H
        checker = 6
        r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(self._h, self._s, self._v))
        xs = np.arange(SS); ys = np.arange(AH)
        xg, yg   = np.meshgrid(xs, ys)
        bg_arr   = np.where(((xg // checker) + (yg // checker)) % 2 == 0, 200, 120).astype(np.float32)
        a_arr    = xs / (SS - 1)
        alpha_f  = a_arr[None, :].repeat(AH, axis=0)
        pr = (r * alpha_f + bg_arr * (1 - alpha_f)).astype(np.uint8)
        pg = (g * alpha_f + bg_arr * (1 - alpha_f)).astype(np.uint8)
        pb = (b * alpha_f + bg_arr * (1 - alpha_f)).astype(np.uint8)
        img_arr = np.stack([pr, pg, pb], axis=-1)
        self._alpha_tk = ImageTk.PhotoImage(Image.fromarray(img_arr, "RGB"))
        self._alpha_canvas.delete("all")
        self._alpha_canvas.create_image(0, 0, anchor="nw", image=self._alpha_tk)
        ax = int((self._a / 255) * (SS - 1))
        self._alpha_canvas.create_line(ax, 0, ax, AH, fill="white", width=2)

    def _draw_all(self):
        self._draw_sv()
        self._draw_hue()
        self._draw_alpha()
        r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(self._h, self._s, self._v))
        self._swatch.configure(bg=f"#{r:02x}{g:02x}{b:02x}")

    def _on_sv_drag(self, event):
        SS = self.SV_SIZE
        self._s = max(0.0, min(1.0, event.x / (SS - 1)))
        self._v = max(0.0, min(1.0, 1.0 - event.y / (SS - 1)))
        self._draw_all(); self._update_fields()

    def _on_hue_drag(self, event):
        self._h = max(0.0, min(1.0, event.y / (self.SV_SIZE - 1)))
        self._draw_all(); self._update_fields()

    def _on_alpha_drag(self, event):
        self._a = int(max(0, min(255, (event.x / (self.SV_SIZE - 1)) * 255)))
        self._draw_alpha(); self._update_fields()

    def _update_fields(self):
        r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(self._h, self._s, self._v))
        self._updating = True
        self._hex_var.set(f"#{r:02x}{g:02x}{b:02x}{self._a:02x}")
        for sv, val in zip(self._rgba_vars, (r, g, b, self._a)):
            sv.set(str(val))
        self._updating = False

    def _on_hex_change(self, *_):
        if self._updating:
            return
        raw = self._hex_var.get().strip().lstrip("#")
        try:
            if len(raw) == 6:
                r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
                a = self._a
            elif len(raw) == 8:
                r, g, b, a = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), int(raw[6:8], 16)
            else:
                return
            self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            self._a = a
            self._draw_all()
        except ValueError:
            pass

    def _on_rgba_change(self, _idx):
        if self._updating:
            return
        try:
            vals = [int(sv.get()) for sv in self._rgba_vars]
            if not all(0 <= v <= 255 for v in vals):
                return
            r, g, b, a = vals
            self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            self._a = a
            self._draw_all()
        except ValueError:
            pass

    def _ok(self):
        r, g, b = (int(x * 255) for x in colorsys.hsv_to_rgb(self._h, self._s, self._v))
        self._result = (r, g, b, self._a)
        self.destroy()

    def get_color(self) -> Optional[tuple]:
        return self._result
