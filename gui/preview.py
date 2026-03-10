"""
QuickTitles — animated subtitle preview window.
"""

import random
import threading
import tkinter as tk
from typing import Optional

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageFont, ImageTk

from config import CFG
from utils import _apply_icon, _dlog
from rendering.layout import get_ink_metrics
from rendering.animation import prerender_chunk, _resolve_frame
from core.transcribe import _apply_word_case
from gui.theme import C
from gui.icons import get_icon


_PREVIEW_SENTENCES = [
    ["adjust", "settings", "and", "hit", "refresh"],
    ["just", "keep", "going", "no", "matter", "what", "u", "will", "succeed", "eventually"],
    ["subtitles", "look", "great", "on", "this"],
    ["made", "with", "love", "by", "13kasp", "on", "discord"],
    ["looking", "clean", "keep", "it", "up"],
]
_PREVIEW_SENTENCE_IDX = 0

_PREVIEW_FPS         = 30
_PREVIEW_WORD_DUR    = 0.55
_PREVIEW_FPS_OPTIONS = [15, 30, 60, 120, 240]


def _make_gradient_bg(w: int, h: int) -> np.ndarray:
    """Diagonal dark-to-light greyscale gradient, RGBA."""
    xs = np.linspace(0, 1, w, dtype=np.float32)
    ys = np.linspace(0, 1, h, dtype=np.float32)
    xg, yg = np.meshgrid(xs, ys)
    brightness = ((xg * 0.35 + yg * 0.25) * 160 + 20).astype(np.uint8)
    rgb = np.stack([
        np.clip(brightness.astype(np.int16) + 10, 0, 255).astype(np.uint8),
        brightness,
        brightness,
    ], axis=-1)
    return np.dstack([rgb, np.full((h, w), 255, dtype=np.uint8)])


def render_preview_animation(preview_width: int = 854,
                              preview_height: int = 480,
                              fps: int = 30) -> tuple[list, int]:
    """
    Render a full animated preview using current CFG settings.
    Returns (frames, fps) where frames is a list of PIL RGB Images.
    Returns ([], fps) on error.
    """
    try:
        words_str = _PREVIEW_SENTENCES[_PREVIEW_SENTENCE_IDX % len(_PREVIEW_SENTENCES)]
        n         = len(words_str)
        dur       = _PREVIEW_WORD_DUR
        chunk = {
            "words": [{"word": _apply_word_case(w), "start": i * dur, "end": (i + 1) * dur}
                      for i, w in enumerate(words_str)],
            "start": 0.0, "end": float(n) * dur,
        }

        scale       = preview_height / 1080
        scaled_size = max(16, int(CFG["FONT_SIZE"] * scale))
        try:
            font = ImageFont.truetype(CFG["FONT_PATH"], scaled_size)
        except Exception:
            font = ImageFont.load_default()

        ink_h, ink_top_offset = get_ink_metrics(font)

        scale_keys = [
            "HIGHLIGHT_PADDING_X", "HIGHLIGHT_PADDING_Y",
            "HIGHLIGHT_CORNER_RADIUS", "DROP_SHADOW_SPREAD",
            "LINE_SPACING", "INK_VERTICAL_NUDGE",
        ]
        orig_vals = {k: CFG[k] for k in scale_keys}
        for k in scale_keys:
            CFG[k] = max(1, int(CFG[k] * scale))

        bg_rgba = _make_gradient_bg(preview_width, preview_height)

        word_schedule, shadow_hold = prerender_chunk(
            chunk, font, ink_h, ink_top_offset, preview_width, preview_height
        )

        for k, v in orig_vals.items():
            CFG[k] = v

        all_words = word_schedule
        all_holds = [shadow_hold] if shadow_hold else []
        blank     = np.zeros((preview_height, preview_width, 4), dtype=np.uint8)

        w_starts = np.array([w["start"] for w in all_words], dtype=np.float64)
        w_ends   = np.array([w["end"]   for w in all_words], dtype=np.float64)
        h_starts = np.array([h["start"] for h in all_holds], dtype=np.float64) if all_holds else None
        h_ends   = np.array([h["end"]   for h in all_holds], dtype=np.float64) if all_holds else None

        total_dur    = chunk["end"] + (CFG["DROP_SHADOW_HOLD"] if CFG["ENABLE_DROP_SHADOW"] else 0)
        total_frames = max(1, int(total_dur * fps))

        bg_rgb = bg_rgba[:, :, :3].astype(np.float32)

        frames = []
        for fi in range(total_frames):
            t       = fi / fps
            overlay = _resolve_frame(t, all_words, all_holds, blank,
                                     w_starts, w_ends, h_starts, h_ends)
            a = overlay[:, :, 3:4].astype(np.float32) / 255.0
            rgb = overlay[:, :, :3].astype(np.float32) * a + bg_rgb * (1.0 - a)
            frames.append(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB"))

        return frames, fps

    except Exception as e:
        _dlog(f"[preview] Error: {e}")
        return [], fps


class PreviewWindow(ctk.CTkToplevel):
    """
    Non-modal, animated subtitle style preview window.
    Stays open while you adjust settings; Refresh re-renders with new values.
    """

    PW = 854
    PH = 480

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Subtitle Preview")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.after(300, lambda: _apply_icon(self))
        parent._preview_window = self
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._frames: list        = []
        self._frame_idx: int      = 0
        self._anim_job            = None
        self._fps_var             = tk.IntVar(value=_PREVIEW_FPS)
        self._frame_ms: int       = max(1, int(1000 / _PREVIEW_FPS))

        self._canvas = tk.Canvas(self, width=self.PW, height=self.PH,
                                 bg="#111111", highlightthickness=0)
        self._canvas.pack(padx=0, pady=0)
        self._canvas_img_id = self._canvas.create_image(0, 0, anchor="nw")

        btn_bar = tk.Frame(self, bg=C["bg"])
        btn_bar.pack(fill="x", padx=20, pady=12)
        btn_bar.columnconfigure(0, weight=1)

        self._status = tk.Label(btn_bar, text="Rendering preview…",
                                bg=C["bg"], fg=C["text3"], font=("Montserrat", 9))
        self._status.grid(row=0, column=0, sticky="w")

        tk.Label(btn_bar, text="FPS:", bg=C["bg"], fg=C["text3"],
                 font=("Montserrat", 10)).grid(row=0, column=1, padx=(0, 4))
        ctk.CTkOptionMenu(
            btn_bar,
            values=[str(f) for f in _PREVIEW_FPS_OPTIONS],
            variable=tk.StringVar(value=str(_PREVIEW_FPS)),
            width=72, height=30, corner_radius=7,
            fg_color=C["surface2"], button_color=C["surface2"],
            button_hover_color=C["border2"], text_color=C["text"],
            dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
            dropdown_hover_color=C["accent_dim"],
            command=self._on_fps_change,
        ).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(btn_bar, text="Refresh", image=get_icon("refresh", 14, "#ffffff"),
                      compound="left", width=100, height=30, anchor="center",
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      font=("Montserrat", 11), corner_radius=7,
                      command=self._next_and_render).grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(btn_bar, text="Close", width=80, height=30, anchor="center",
                      fg_color=C["surface2"], hover_color=C["border2"],
                      text_color=C["text2"], font=("Montserrat", 11), corner_radius=7,
                      command=self._on_close).grid(row=0, column=4)

        self.after(300, self._bring_to_front)
        self._start_render()

    def _bring_to_front(self):
        self.attributes("-topmost", True)
        self.update()
        self.attributes("-topmost", False)
        self.focus_force()

    def _on_close(self):
        self._stop_anim()
        try:
            self.master._preview_window = None
        except Exception:
            pass
        self.destroy()

    def _next_and_render(self):
        global _PREVIEW_SENTENCE_IDX
        n = len(_PREVIEW_SENTENCES)
        current = _PREVIEW_SENTENCE_IDX % n
        choices = [i for i in range(n) if i != current]
        _PREVIEW_SENTENCE_IDX = random.choice(choices)
        self._start_render()

    def _on_fps_change(self, value: str):
        try:
            new_fps = int(value)
        except ValueError:
            return
        self._fps_var.set(new_fps)
        self._frame_ms = max(1, int(1000 / new_fps))
        self._start_render()

    def _start_render(self):
        self._stop_anim()
        self._status.configure(text="Rendering preview…", fg=C["text3"])
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        fps = self._fps_var.get()
        frames, fps = render_preview_animation(self.PW, self.PH, fps=fps)
        self.after(0, lambda f=frames: self._on_render_done(f))

    def _on_render_done(self, pil_frames: list):
        if not pil_frames:
            self._status.configure(text="Render failed — check font path.", fg=C["error"])
            return
        self._frames    = [ImageTk.PhotoImage(img) for img in pil_frames]
        self._frame_idx = 0
        sentence = " ".join(_PREVIEW_SENTENCES[_PREVIEW_SENTENCE_IDX % len(_PREVIEW_SENTENCES)])
        self._status.configure(
            text=f'"{sentence}"  ·  Refresh to cycle sentence or apply new settings',
            fg=C["success"])
        self._play_anim()

    def _play_anim(self):
        if not self._frames:
            return
        self._canvas.itemconfigure(self._canvas_img_id,
                                   image=self._frames[self._frame_idx])
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)
        self._anim_job  = self.after(self._frame_ms, self._play_anim)

    def _stop_anim(self):
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._frames = []
