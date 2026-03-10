"""
QuickTitles — main application window (App).
"""

import os
import platform
import shutil
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from config import CFG, DEFAULTS, INPUT_FOLDER, _save_settings
from utils import _apply_icon, _dlog, _quiet_io, log, xdg_open
from core.ffmpeg import _HAS_NVENC
from core.transcribe import transcribe_file
from core.render import render_file
from gui.theme import C, FONT_UI, FONT_UI_SM, FONT_MONO
from gui.icons import get_icon, icon_lbl, update_icon
from gui.widgets import Tooltip
from gui.color_picker import ColorPickerDialog
from gui.font_browser import FontBrowserDialog
from gui.transcript_editor import TranscriptEditor
from gui.preview import PreviewWindow


class App(ctk.CTk):

    PAGES      = ["Queue", "Output", "Settings"]
    PAGE_ICONS = {"Queue": "queue", "Output": "output", "Settings": "settings"}

    def __init__(self):
        super().__init__()
        self.withdraw()

        self.title("QuickTitles")
        self.geometry("1020x740")
        self.minsize(860, 600)
        self.configure(fg_color=C["bg"])

        _apply_icon(self)

        self._files                = []
        self._outputs              = []
        self._running              = False
        self._model                = None
        self._sv                   = {}
        self._current_page         = tk.StringVar(value="Queue")
        self._pending_transcripts  = []
        self._output_sizes         = {}
        self._last_input_mtime     = -1.0
        self._last_output_mtime    = -1.0
        self._batch_total     = 0
        self._batch_done      = 0
        self._batch_phase     = ""

        os.makedirs(INPUT_FOLDER, exist_ok=True)

        self._build_ui()

        import utils as _utils_mod
        _utils_mod._log_cb = self._gui_log

        self._refresh_input()
        self._refresh_output()
        self._start_folder_polling()

        self.after(10, self.deiconify)
        self.after(300, self._log_startup_info)

    def _log_startup_info(self):
        log(f"QuickTitles started  ·  frozen={getattr(sys, 'frozen', False)}  ·  Python {sys.version.split()[0]}")
        log(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
        ffmpeg_bin   = os.environ.get("FFMPEG_BINARY", "ffmpeg")
        ffmpeg_found = shutil.which(ffmpeg_bin) or (os.path.exists(ffmpeg_bin) and ffmpeg_bin) or None
        log(f"ffmpeg: {ffmpeg_found if ffmpeg_found else 'NOT FOUND in PATH'}  ·  nvenc={'yes' if _HAS_NVENC else 'no'}")
        log(f"Whisper model cfg: '{CFG.get('WHISPER_MODEL', 'base')}'  ·  font: {os.path.basename(CFG.get('FONT_PATH', '?'))}")
        if not os.path.exists(CFG.get("FONT_PATH", "")):
            log(f"WARNING  Font file not found: {CFG.get('FONT_PATH', '')}")
        log(f"Output: {os.path.abspath(CFG.get('OUTPUT_FOLDER', 'output'))}  ·  threads: {CFG.get('RENDER_THREADS', '?')}")

    # =========================================================================
    # SHELL
    # =========================================================================

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._sidebar = tk.Frame(self, bg=C["surface"], width=C["sidebar_w"])
        self._sidebar.grid(row=0, column=0, sticky="nsew")
        self._sidebar.grid_propagate(False)
        self._build_sidebar()

        self._content = tk.Frame(self, bg=C["bg"])
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._pages = {}
        for name in self.PAGES:
            f = tk.Frame(self._content, bg=C["bg"])
            f.grid(row=0, column=0, sticky="nsew")
            self._pages[name] = f

        self._build_queue_page()
        self._build_output_page()
        self._build_settings_page()
        self._show_page("Queue")

    def _build_sidebar(self):
        sb = self._sidebar
        title_frame = tk.Frame(sb, bg=C["surface"])
        title_frame.pack(fill="x", pady=(24, 6), padx=20)
        tk.Label(title_frame, text="Quick", bg=C["surface"],
                 fg=C["text"], font=("Montserrat", 17, "bold")).pack(side="left")
        tk.Label(title_frame, text="Titles", bg=C["surface"],
                 fg=C["accent"], font=("Montserrat", 17, "bold")).pack(side="left")
        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(10, 16))

        self._nav_btns = {}
        for page in self.PAGES:
            btn = self._make_nav_btn(sb, page)
            btn["frame"].pack(fill="x", padx=10, pady=2)
            self._nav_btns[page] = btn

        tk.Frame(sb, bg=C["surface"]).pack(expand=True, fill="both")

        disc_frame = tk.Frame(sb, bg=C["surface2"], cursor="hand2")
        disc_frame.pack(fill="x", padx=10, pady=(0, 8))
        disc_frame.bind("<Button-1>", lambda e: self._open_discord())
        disc_inner = tk.Frame(disc_frame, bg=C["surface2"])
        disc_inner.pack(padx=12, pady=10, anchor="w")
        disc_inner.bind("<Button-1>", lambda e: self._open_discord())
        disc_text_frame = tk.Frame(disc_inner, bg=C["surface2"])
        disc_text_frame.pack(side="left")
        disc_text_frame.bind("<Button-1>", lambda e: self._open_discord())
        tk.Label(disc_text_frame, text="Join Discord", bg=C["surface2"],
                 fg=C["text"], font=("Montserrat", 10, "bold")).pack(anchor="w")
        tk.Label(disc_text_frame, text="Support & updates", bg=C["surface2"],
                 fg=C["text3"], font=("Montserrat", 9)).pack(anchor="w")
        for w in disc_text_frame.winfo_children():
            w.bind("<Button-1>", lambda e: self._open_discord())

        def _disc_enter(e):
            disc_frame.configure(bg=C["border2"])
            for w in (disc_frame.winfo_children()
                      + disc_inner.winfo_children()
                      + disc_text_frame.winfo_children()):
                try: w.configure(bg=C["border2"])
                except Exception: pass

        def _disc_leave(e):
            disc_frame.configure(bg=C["surface2"])
            for w in (disc_frame.winfo_children()
                      + disc_inner.winfo_children()
                      + disc_text_frame.winfo_children()):
                try: w.configure(bg=C["surface2"])
                except Exception: pass

        for w in ([disc_frame, disc_inner, disc_text_frame]
                  + disc_text_frame.winfo_children()):
            w.bind("<Enter>", _disc_enter)
            w.bind("<Leave>", _disc_leave)

        tk.Label(sb, text="v1.0  ·  by 13kasp", bg=C["surface"],
                 fg=C["text3"], font=("Montserrat", 9)).pack(pady=(0, 14))

    def _make_nav_btn(self, parent, page: str) -> dict:
        icon_name = self.PAGE_ICONS.get(page, "")
        frame     = tk.Frame(parent, bg=C["surface"], cursor="hand2")
        icon_widget = icon_lbl(frame, icon_name, 16, C["text2"], C["surface"],
                               width=24, height=24)
        icon_widget.pack(side="left", padx=(12, 6), pady=10)
        text_lbl = tk.Label(frame, text=page, bg=C["surface"],
                            fg=C["text2"], font=("Montserrat", 12))
        text_lbl.pack(side="left", pady=10)

        def _on_click(_e=None):    self._show_page(page)
        def _on_enter(_e=None):
            if self._current_page.get() != page:
                self._set_nav_colors(page, C["surface2"], C["surface2"], C["text2"])
        def _on_leave(_e=None):
            if self._current_page.get() != page:
                self._set_nav_colors(page, C["surface"], C["surface"], C["text2"])

        for w in (frame, icon_widget, text_lbl):
            w.bind("<Button-1>", _on_click)
            w.bind("<Enter>",    _on_enter)
            w.bind("<Leave>",    _on_leave)

        return {"frame": frame, "icon": icon_widget, "text": text_lbl}

    def _set_nav_colors(self, page: str, frame_bg: str, lbl_bg: str, fg: str):
        btn = self._nav_btns[page]
        btn["frame"].configure(bg=frame_bg)
        btn["icon"].configure(bg=lbl_bg)
        update_icon(btn["icon"], self.PAGE_ICONS[page], 16, fg)
        btn["text"].configure(bg=lbl_bg, fg=fg)

    def _show_page(self, page: str):
        old = self._current_page.get()
        if old in self._nav_btns:
            self._set_nav_colors(old, C["surface"], C["surface"], C["text2"])
        self._current_page.set(page)
        btn = self._nav_btns[page]
        btn["frame"].configure(bg=C["accent_dim"])
        btn["icon"].configure(bg=C["accent_dim"])
        update_icon(btn["icon"], self.PAGE_ICONS[page], 16, C["accent"])
        btn["text"].configure(bg=C["accent_dim"], fg=C["text"])
        self._pages[page].tkraise()

    # =========================================================================
    # QUEUE PAGE
    # =========================================================================

    def _build_queue_page(self):
        p = self._pages["Queue"]
        p.grid_rowconfigure(1, weight=1)
        p.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(p, bg=C["bg"])
        hdr.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 16))
        hdr.grid_columnconfigure(3, weight=1)
        tk.Label(hdr, text="Queue", bg=C["bg"],
                 fg=C["text"], font=("Montserrat", 20, "bold")).grid(row=0, column=0, sticky="w")
        self._make_btn(hdr, " Add files",   self._add_files,         accent=True, icon=get_icon("plus", 12, "#ffffff")).grid(row=0, column=1, padx=(24, 6))
        self._make_btn(hdr, " Refresh",      self._refresh_input,     icon=get_icon("refresh", 12, C["text2"])).grid(row=0, column=2, padx=(0, 6))
        self._make_btn(hdr, "Open folder",   self._open_input_folder).grid(row=0, column=3, padx=(0, 6))
        self._make_btn(hdr, "Clear all",     self._clear_files,       danger=True).grid(row=0, column=4, sticky="w")

        list_frame = tk.Frame(p, bg=C["bg"])
        list_frame.grid(row=1, column=0, sticky="nsew", padx=28)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._file_list = ctk.CTkScrollableFrame(
            list_frame, fg_color=C["surface"], corner_radius=12,
            scrollbar_button_color=C["border2"],
            scrollbar_button_hover_color=C["accent"],
        )
        self._file_list.grid(row=0, column=0, sticky="nsew")
        self._file_list.grid_columnconfigure(0, weight=1)

        self._queue_empty_lbl = tk.Label(
            self._file_list, text="Drop MP4 files into the  input/  folder\nor click  + Add files  above",
            bg=C["surface"], fg=C["text3"], font=("Montserrat", 12), justify="center",
        )

        bottom = tk.Frame(p, bg=C["bg"])
        bottom.grid(row=2, column=0, sticky="ew", padx=28, pady=(16, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self._batch_banner = tk.Frame(bottom, bg=C["surface2"],
                                       highlightbackground=C["border"], highlightthickness=1)
        self._batch_banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._batch_banner.grid_columnconfigure(1, weight=1)
        self._batch_banner.grid_remove()

        tk.Label(self._batch_banner, text="Batch:", bg=C["surface2"],
                 fg=C["text3"], font=("Montserrat", 9, "bold"), padx=12
                 ).grid(row=0, column=0, sticky="w", pady=6)

        self._batch_counter_lbl = tk.Label(
            self._batch_banner, text="", bg=C["surface2"],
            fg=C["accent"], font=("Montserrat", 11, "bold"))
        self._batch_counter_lbl.grid(row=0, column=1, sticky="w")

        self._batch_phase_lbl = tk.Label(
            self._batch_banner, text="", bg=C["surface2"],
            fg=C["text3"], font=("Montserrat", 9), padx=12)
        self._batch_phase_lbl.grid(row=0, column=2, sticky="e", pady=6)

        self._batch_bar = ctk.CTkProgressBar(
            self._batch_banner, height=3, corner_radius=0,
            fg_color=C["border"], progress_color=C["success"],
        )
        self._batch_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._batch_bar.set(0)

        log_card = tk.Frame(bottom, bg=C["surface"],
                            highlightbackground=C["border"], highlightthickness=1)
        log_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        log_card.grid_columnconfigure(0, weight=1)

        log_hdr = tk.Frame(log_card, bg=C["surface"])
        log_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        log_hdr.grid_columnconfigure(0, weight=1)
        tk.Label(log_hdr, text="Activity", bg=C["surface"],
                 fg=C["text3"], font=("Montserrat", 9, "bold")).grid(row=0, column=0, sticky="w")
        self._make_btn(log_hdr, "Copy",  self._copy_log,  small=True).grid(row=0, column=1, sticky="e", padx=(0, 4))
        self._make_btn(log_hdr, "Clear", self._clear_log, small=True).grid(row=0, column=2, sticky="e")

        self._log_box = ctk.CTkTextbox(
            log_card, height=90, font=FONT_MONO, fg_color=C["surface"],
            text_color=C["text2"], scrollbar_button_color=C["border2"],
            activate_scrollbars=True, wrap="word", state="disabled",
        )
        self._log_box.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 4))
        for tag, color in (("progress", C["text3"]), ("done", C["success"]),
                           ("error", C["error"]), ("header", C["accent"])):
            self._log_box._textbox.tag_configure(tag, foreground=color)

        self._progress = ctk.CTkProgressBar(
            bottom, height=4, corner_radius=2,
            fg_color=C["surface2"], progress_color=C["accent"],
        )
        self._progress.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self._progress.set(0)

        self._step_lbl = tk.Label(bottom, text="", bg=C["bg"], fg=C["text3"], font=("Montserrat", 9))
        self._step_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))

        btn_row = tk.Frame(bottom, bg=C["bg"])
        btn_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 28))
        btn_row.grid_columnconfigure(0, weight=1)

        self._run_btn = ctk.CTkButton(
            btn_row, text="1. Transcribe", height=40, anchor="center",
            image=get_icon("play", 14, "#ffffff"), compound="left",
            font=("Montserrat", 14), fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#ffffff", corner_radius=10, command=self._start_transcribe,
        )
        self._run_btn.grid(row=0, column=0, sticky="ew")

        self._edit_btn = ctk.CTkButton(
            btn_row, text="2. Review & Edit Transcript", height=40, anchor="center",
            image=get_icon("check", 14, C["text2"]), compound="left",
            font=("Montserrat", 14), fg_color=C["surface2"], hover_color=C["border2"],
            text_color=C["text2"], corner_radius=10,
            command=self._open_transcript_editor, state="disabled",
        )
        self._edit_btn.grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _show_batch_banner(self, total: int, phase: str):
        self._batch_total = total
        self._batch_done  = 0
        self._batch_phase = phase
        self._batch_banner.grid()
        self._update_batch_banner()

    def _update_batch_banner(self):
        frac = self._batch_done / max(self._batch_total, 1)
        self._batch_counter_lbl.configure(text=f"{self._batch_done} / {self._batch_total} files done")
        phase_text = {"transcribe": "Transcribing…", "render": "Rendering…"}.get(self._batch_phase, "")
        self._batch_phase_lbl.configure(text=phase_text)
        self._batch_bar.set(frac)

    def _hide_batch_banner(self):
        self._batch_banner.grid_remove()

    def _update_queue_empty(self):
        try:
            if self._files:
                self._queue_empty_lbl.place_forget()
            else:
                self._queue_empty_lbl.place(relx=0.5, rely=0.4, anchor="center")
        except Exception:
            pass

    # =========================================================================
    # OUTPUT PAGE
    # =========================================================================

    def _build_output_page(self):
        p = self._pages["Output"]
        p.grid_rowconfigure(1, weight=1)
        p.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(p, bg=C["bg"])
        hdr.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 16))
        hdr.grid_columnconfigure(2, weight=1)
        tk.Label(hdr, text="Output", bg=C["bg"],
                 fg=C["text"], font=("Montserrat", 20, "bold")).grid(row=0, column=0, sticky="w")
        self._make_btn(hdr, " Refresh",     self._refresh_output,    icon=get_icon("refresh", 12, C["text2"])).grid(row=0, column=1, padx=(20, 6))
        self._make_btn(hdr, "Open folder", self._open_output_folder, accent=True).grid(row=0, column=2, sticky="w")

        lf = tk.Frame(p, bg=C["bg"])
        lf.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        self._output_list = ctk.CTkScrollableFrame(
            lf, fg_color=C["surface"], corner_radius=12,
            scrollbar_button_color=C["border2"],
            scrollbar_button_hover_color=C["accent"],
        )
        self._output_list.grid(row=0, column=0, sticky="nsew")
        self._output_list.grid_columnconfigure(0, weight=1)

        self._output_empty_lbl = tk.Label(
            self._output_list, text="Finished videos will appear here",
            bg=C["surface"], fg=C["text3"], font=("Montserrat", 12),
        )

    def _update_output_empty(self):
        try:
            if self._outputs:
                self._output_empty_lbl.place_forget()
            else:
                self._output_empty_lbl.place(relx=0.5, rely=0.4, anchor="center")
        except Exception:
            pass

    # =========================================================================
    # SETTINGS PAGE
    # =========================================================================

    def _build_settings_page(self):
        p = self._pages["Settings"]
        p.grid_rowconfigure(1, weight=1)
        p.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(p, bg=C["bg"])
        hdr.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 16))
        hdr.grid_columnconfigure(0, weight=1)
        tk.Label(hdr, text="Settings", bg=C["bg"],
                 fg=C["text"], font=("Montserrat", 20, "bold")).grid(row=0, column=0, sticky="w")
        self._make_btn(hdr, " Preview", self._open_preview_from_settings,
                       accent=True, icon=get_icon("play", 12, "#ffffff")).grid(row=0, column=1, sticky="e", padx=(0, 8))
        self._make_btn(hdr, "Reset to defaults", self._reset_settings).grid(row=0, column=2, sticky="e")

        scroll = ctk.CTkScrollableFrame(
            p, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["border2"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        scroll.grid_columnconfigure(0, weight=1)

        TOOLTIPS = {
            "FONT_PATH":              "Font file for subtitle text. Must be .ttf or .otf. Use the Browse button to pick from installed fonts.",
            "FONT_SIZE":              "Subtitle text size. 80–120 is a good range for most videos.",
            "TEXT_COLOR":             "Colour of the subtitle text. White is most readable on most backgrounds.",
            "VERTICAL_POSITION":      "Vertical placement: 0 = top, 1 = bottom. 0.75 keeps text near the bottom.",
            "LINE_SPACING":           "Extra space between lines when text wraps.",
            "MAX_WIDTH_RATIO":        "Max subtitle width as fraction of video width. 0.9 = 90% of screen.",
            "ENABLE_HIGHLIGHT":       "Show a coloured bubble behind each spoken word.",
            "HIGHLIGHT_COLOR":        "Colour of the word highlight bubble.",
            "HIGHLIGHT_PADDING_X":    "Left/right padding inside the highlight bubble.",
            "HIGHLIGHT_PADDING_Y":    "Top/bottom padding inside the highlight bubble.",
            "HIGHLIGHT_CORNER_RADIUS":"Corner roundness of the bubble. 0 = sharp, higher = pill-shaped.",
            "INK_VERTICAL_NUDGE":     "Shift the highlight bubble up or down in pixels. Positive = down, negative = up. Use to fine-tune vertical centering for your font.",
            "ENABLE_POP_ANIMATION":   "Bubble briefly pops larger on each new word for a punchy feel.",
            "POP_SCALE_START":        "How big the bubble is at the start of the pop. 1.3 = 30% bigger.",
            "POP_DURATION":           "Pop animation duration in seconds. 0.05–0.15 feels snappy.",
            "POP_STEPS":              "Frames used for the pop. Higher = smoother.",
            "ENABLE_SLIDE_ANIMATION": "Highlight smoothly slides from word to word instead of jumping.",
            "TRANSITION_DURATION":    "Slide duration in seconds. Shorter = snappier.",
            "TRANSITION_STEPS":       "Frames used for the slide. 20–30 is a good balance.",
            "ENABLE_MOTION_BLUR":     "Adds blur during slide for a more natural look.",
            "MOTION_BLUR_STRENGTH":   "Blur strength. 1–2 is subtle and natural.",
            "ENABLE_DROP_SHADOW":     "Soft dark glow behind subtitles for readability over busy backgrounds.",
            "DROP_SHADOW_SPREAD":     "How far the shadow spreads from the text.",
            "DROP_SHADOW_OPACITY":    "Shadow darkness. 0 = invisible, 255 = solid black.",
            "DROP_SHADOW_HOLD":       "Seconds the shadow lingers after a group ends.",
            "OUTPUT_FOLDER":          "Folder where finished videos are saved.",
            "RENDER_THREADS":         "Parallel subtitle chunks processed at once. Keep below CPU core count.",
            "ENCODE_PRESET_X264":     "libx264 speed/quality preset. ultrafast=fastest, slow=best quality. Only used when no NVIDIA GPU is detected.",
            "ENCODE_CRF":             "libx264 quality. 0=lossless, 18=visually lossless, 23=default, 28=low quality. Lower = larger file.",
            "ENCODE_PRESET_NVENC":    "NVIDIA NVENC quality preset. p1=fastest, p7=best quality. Only used when an NVIDIA GPU is detected.",
            "ENCODE_CQ_NVENC":        "NVIDIA NVENC constant quality level. 0=best, 17=high quality, 28=low quality.",
            "ENCODE_MAXRATE":         "NVENC max bitrate cap e.g. 50M, 20M, 8M. Higher = better quality on fast scenes.",
            "ENCODE_BUFSIZE":         "NVENC VBV buffer size. Usually 2× maxrate. e.g. 100M for 50M maxrate.",
            "ENCODE_AUDIO_BITRATE":   "AAC audio bitrate. 320k=high quality, 192k=standard, 128k=small file.",
            "ENCODE_EXTRA_FLAGS":     "Extra ffmpeg flags appended verbatim, e.g. -pix_fmt yuv420p. Advanced use only.",
            "WHISPER_MODEL":          "AI model for transcription. Larger = more accurate but slower.",
            "CHUNK_MODE":             "How subtitle groups are sized: 'words' shows a fixed number of words; 'lines' fills a fixed number of lines.",
            "MAX_WORDS":              "Words shown at once (used when mode is 'Words per group'). Lower = faster pace. 3–5 is typical.",
            "MAX_LINES":              "Lines shown at once (used when mode is 'Lines per group'). Words are packed to fill this many lines.",
            "WORD_CASE":              "Capitalisation applied to every word: Default = as Whisper transcribes it; UPPERCASE = all caps; Title Case = first letter of each word; lowercase = all lower.",
        }

        sections = [
            ("Transcription", [
                ("WHISPER_MODEL", "Whisper model",   "whisper_model"),
                ("CHUNK_MODE",    "Group mode",       "chunk_mode"),
                ("MAX_WORDS",     "Words per group",  "int"),
                ("MAX_LINES",     "Lines per group",  "int"),
                ("WORD_CASE",     "Word case",        "word_case"),
            ]),
            ("Text", [
                ("FONT_PATH",         "Font file",         "font"),
                ("FONT_SIZE",         "Font size",         "int"),
                ("TEXT_COLOR",        "Text colour",       "color"),
                ("VERTICAL_POSITION", "Vertical position", "float"),
                ("LINE_SPACING",      "Line spacing",      "int"),
                ("MAX_WIDTH_RATIO",   "Max line width",    "float"),
            ]),
            ("Highlight bubble", [
                ("ENABLE_HIGHLIGHT",        "Enable highlight",     "bool"),
                ("HIGHLIGHT_COLOR",         "Highlight colour",     "color"),
                ("HIGHLIGHT_PADDING_X",     "Padding left / right", "int"),
                ("HIGHLIGHT_PADDING_Y",     "Padding top / bottom", "int"),
                ("HIGHLIGHT_CORNER_RADIUS", "Corner roundness",     "int"),
                ("INK_VERTICAL_NUDGE",      "Vertical nudge",       "int"),
            ]),
            ("Animations", [
                ("ENABLE_POP_ANIMATION",   "Pop on new word",     "bool"),
                ("POP_SCALE_START",        "Pop size",            "float"),
                ("POP_DURATION",           "Pop speed",           "float"),
                ("POP_STEPS",              "Pop smoothness",      "int"),
                ("ENABLE_SLIDE_ANIMATION", "Slide between words", "bool"),
                ("TRANSITION_DURATION",    "Slide speed",         "float"),
                ("TRANSITION_STEPS",       "Slide smoothness",    "int"),
                ("ENABLE_MOTION_BLUR",     "Motion blur",         "bool"),
                ("MOTION_BLUR_STRENGTH",   "Blur strength",       "int"),
            ]),
            ("Drop shadow", [
                ("ENABLE_DROP_SHADOW",  "Enable shadow",     "bool"),
                ("DROP_SHADOW_SPREAD",  "Shadow size",       "int"),
                ("DROP_SHADOW_OPACITY", "Shadow darkness",   "int"),
                ("DROP_SHADOW_HOLD",    "Shadow fade delay", "float"),
            ]),
            ("Output & performance", [
                ("OUTPUT_FOLDER",  "Output folder",  "folder"),
                ("RENDER_THREADS", "Render threads", "int"),
            ]),
            ("Encoding — " + ("NVIDIA NVENC (GPU detected)" if _HAS_NVENC else "libx264 (no NVIDIA GPU)"), [
                *(([
                    ("ENCODE_PRESET_NVENC",  "NVENC preset",       "nvenc_preset"),
                    ("ENCODE_CQ_NVENC",      "CQ quality",         "int"),
                    ("ENCODE_MAXRATE",       "Max bitrate",        "str"),
                    ("ENCODE_BUFSIZE",       "Buffer size",        "str"),
                ] if _HAS_NVENC else [
                    ("ENCODE_PRESET_X264",   "x264 preset",        "x264_preset"),
                    ("ENCODE_CRF",           "CRF quality",        "int"),
                ])),
                ("ENCODE_AUDIO_BITRATE",  "Audio bitrate",          "str"),
                ("ENCODE_EXTRA_FLAGS",    "Extra ffmpeg flags",      "str"),
            ]),
        ]

        srow = 0
        for section_title, fields in sections:
            self._settings_section(scroll, srow, section_title, fields, TOOLTIPS)
            srow += len(fields) + 2

    def _settings_section(self, parent, start_row, title, fields, tooltips):
        hdr_frame = tk.Frame(parent, bg=C["bg"])
        hdr_frame.grid(row=start_row, column=0, sticky="ew", pady=(20, 4), padx=4)
        hdr_frame.grid_columnconfigure(1, weight=1)
        tk.Label(hdr_frame, text=title.upper(), bg=C["bg"],
                 fg=C["accent"], font=("Montserrat", 9, "bold")).grid(row=0, column=0, sticky="w")
        tk.Frame(hdr_frame, bg=C["border"], height=1).grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=(1, 0))

        card = tk.Frame(parent, bg=C["surface"],
                        highlightbackground=C["border"], highlightthickness=1)
        card.grid(row=start_row + 1, column=0, sticky="ew", padx=4)
        card.grid_columnconfigure(0, weight=1)

        for i, (key, label, kind) in enumerate(fields):
            self._add_setting_row(card, i, key, label, kind, tooltips.get(key, ""))
            if i < len(fields) - 1:
                divider = tk.Frame(card, bg=C["border"], height=1)
                divider.grid(row=i * 2 + 1, column=0, sticky="ew", padx=16)
                if not hasattr(self, "_setting_dividers"):
                    self._setting_dividers = {}
                self._setting_dividers[key] = divider

    def _add_setting_row(self, parent, row, key, label, kind, tooltip=""):
        val        = CFG[key]
        actual_row = row * 2

        row_frame = tk.Frame(parent, bg=C["surface"])
        row_frame.grid(row=actual_row, column=0, sticky="ew", padx=16, pady=10)
        row_frame.grid_columnconfigure(1, weight=1)
        if not hasattr(self, "_setting_rows"):
            self._setting_rows = {}
        self._setting_rows[key] = row_frame

        left_frame = tk.Frame(row_frame, bg=C["surface"])
        left_frame.grid(row=0, column=0, sticky="w")

        lbl_frame = tk.Frame(left_frame, bg=C["surface"])
        lbl_frame.pack(side="left", padx=(0, 12))
        tk.Label(lbl_frame, text=label, bg=C["surface"], fg=C["text"], font=FONT_UI,
                 width=22, anchor="w").pack(side="left")
        if tooltip:
            tip_lbl = icon_lbl(lbl_frame, "info", 14, C["text3"], C["surface"],
                               cursor="question_arrow")
            tip_lbl.pack(side="left", padx=(4, 0))
            Tooltip(tip_lbl, tooltip)

        ctrl_frame = tk.Frame(left_frame, bg=C["surface"])
        ctrl_frame.pack(side="left")

        if kind == "whisper_model":
            sv = tk.StringVar(value=str(CFG.get("WHISPER_MODEL", "base")))
            sv.trace_add("write", lambda *_, s=sv: (
                self._apply_setting("WHISPER_MODEL", s.get()),
                setattr(self, "_model", None),
            ))
            ctk.CTkOptionMenu(
                ctrl_frame, values=["tiny", "base", "small", "medium", "large"],
                variable=sv, width=130, height=30, corner_radius=8,
                fg_color=C["surface2"], button_color=C["surface2"],
                button_hover_color=C["border2"], text_color=C["text"],
                dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
                dropdown_hover_color=C["accent_dim"],
            ).pack()

        elif kind == "chunk_mode":
            sv = tk.StringVar(value=str(CFG.get("CHUNK_MODE", "words")))
            def _on_chunk_mode_change(*_, s=sv):
                self._apply_setting("CHUNK_MODE", s.get())
                self._update_chunk_mode_visibility(s.get())
            sv.trace_add("write", _on_chunk_mode_change)
            ctk.CTkOptionMenu(
                ctrl_frame, values=["words", "lines"],
                variable=sv, width=130, height=30, corner_radius=8,
                fg_color=C["surface2"], button_color=C["surface2"],
                button_hover_color=C["border2"], text_color=C["text"],
                dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
                dropdown_hover_color=C["accent_dim"],
            ).pack()
            row_frame.after(0, lambda: self._update_chunk_mode_visibility(CFG.get("CHUNK_MODE", "words")))

        elif kind == "word_case":
            _CASE_OPTIONS = ["default", "UPPERCASE", "Title Case", "lowercase"]
            _CASE_VALUES  = {"default": "default", "UPPERCASE": "upper",
                             "Title Case": "title", "lowercase": "lower"}
            _CASE_LABELS  = {v: k for k, v in _CASE_VALUES.items()}
            current_label = _CASE_LABELS.get(CFG.get("WORD_CASE", "default"), "default")
            sv = tk.StringVar(value=current_label)
            sv.trace_add("write", lambda *_, s=sv: self._apply_setting(
                "WORD_CASE", _CASE_VALUES.get(s.get(), "default")))
            ctk.CTkOptionMenu(
                ctrl_frame, values=_CASE_OPTIONS,
                variable=sv, width=130, height=30, corner_radius=8,
                fg_color=C["surface2"], button_color=C["surface2"],
                button_hover_color=C["border2"], text_color=C["text"],
                dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
                dropdown_hover_color=C["accent_dim"],
            ).pack()

        elif kind == "bool":
            sv = tk.BooleanVar(value=bool(val))
            ctk.CTkSwitch(
                ctrl_frame, text="", variable=sv, width=44, height=22,
                fg_color=C["border2"], progress_color=C["accent"],
                button_color=C["text"], button_hover_color="#ffffff",
                command=lambda k=key, v=sv: self._apply_setting(k, v.get()),
            ).pack()

        elif kind == "color":
            sv      = tk.StringVar(value=str(val))
            cf      = tk.Frame(ctrl_frame, bg=C["surface"])
            cf.pack()
            preview = tk.Label(cf, text="  ", width=3, bg=self._rgba_to_hex(val),
                               relief="flat", cursor="hand2")
            preview.pack(side="left", padx=(0, 8), ipady=10)
            hex_lbl = tk.Label(cf, text=self._rgba_to_hex(val),
                               bg=C["surface"], fg=C["text2"], font=FONT_MONO)
            hex_lbl.pack(side="left", padx=(0, 10))
            self._make_btn(cf, "Change",
                           lambda k=key, s=sv, p=preview, h=hex_lbl: self._pick_color(k, s, p, h)
                           ).pack(side="left")
            sv._hex_lbl = hex_lbl
            sv._preview = preview

        elif kind == "font":
            sv  = tk.StringVar(value=str(val))
            pf  = tk.Frame(ctrl_frame, bg=C["surface"])
            pf.pack()
            name_lbl = tk.Label(pf, text=os.path.basename(val), bg=C["surface"],
                                fg=C["text2"], font=FONT_MONO, width=22, anchor="w")
            name_lbl.pack(side="left", padx=(0, 8))
            sv._name_lbl = name_lbl
            self._make_btn(pf, "Browse Fonts",
                           lambda k=key, s=sv: self._browse_font(k, s)).pack(side="left", padx=(0, 4))
            self._make_btn(pf, "File…",
                           lambda k=key, s=sv: self._browse(k, s, "path")).pack(side="left")
            sv.trace_add("write", lambda *_, k=key, s=sv: self._apply_setting(k, s.get()))

        elif kind in ("path", "folder"):
            sv  = tk.StringVar(value=str(val))
            pf  = tk.Frame(ctrl_frame, bg=C["surface"])
            pf.pack()
            ctk.CTkEntry(pf, textvariable=sv, width=240, height=30,
                         fg_color=C["surface2"], border_color=C["border2"],
                         text_color=C["text"], corner_radius=6).pack(side="left", padx=(0, 8))
            self._make_btn(pf, "Browse",
                           lambda k=key, s=sv, kd=kind: self._browse(k, s, kd)).pack(side="left")
            sv.trace_add("write", lambda *_, k=key, s=sv: self._apply_setting(k, s.get()))

        elif kind == "str":
            sv = tk.StringVar(value=str(val))
            ctk.CTkEntry(ctrl_frame, textvariable=sv, width=140, height=30,
                         fg_color=C["surface2"], border_color=C["border2"],
                         text_color=C["text"], corner_radius=6).pack()
            sv.trace_add("write", lambda *_, k=key, s=sv: self._apply_setting(k, s.get()))

        elif kind == "nvenc_preset":
            sv = tk.StringVar(value=str(val))
            ctk.CTkOptionMenu(
                ctrl_frame, values=["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
                variable=sv, width=100, height=30, corner_radius=8,
                fg_color=C["surface2"], button_color=C["surface2"],
                button_hover_color=C["border2"], text_color=C["text"],
                dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
                dropdown_hover_color=C["accent_dim"],
                command=lambda v, k=key: self._apply_setting(k, v),
            ).pack()

        elif kind == "x264_preset":
            sv = tk.StringVar(value=str(val))
            ctk.CTkOptionMenu(
                ctrl_frame,
                values=["ultrafast", "superfast", "veryfast", "faster",
                        "fast", "medium", "slow", "slower", "veryslow"],
                variable=sv, width=140, height=30, corner_radius=8,
                fg_color=C["surface2"], button_color=C["surface2"],
                button_hover_color=C["border2"], text_color=C["text"],
                dropdown_fg_color=C["surface2"], dropdown_text_color=C["text"],
                dropdown_hover_color=C["accent_dim"],
                command=lambda v, k=key: self._apply_setting(k, v),
            ).pack()

        else:  # int / float
            sv = tk.StringVar(value=str(val))
            ctk.CTkEntry(ctrl_frame, textvariable=sv, width=90, height=30,
                         fg_color=C["surface2"], border_color=C["border2"],
                         text_color=C["text"], corner_radius=6).pack()
            sv.trace_add("write", lambda *_, k=key, s=sv, kd=kind: self._apply_typed(k, s, kd))

        self._sv[key] = sv

        reset_btn = icon_lbl(row_frame, "reset", 14, C["text3"], C["surface"],
                             cursor="hand2", padx=6)
        reset_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))
        reset_btn.bind("<Enter>",    lambda e, b=reset_btn: update_icon(b, "reset", 14, C["accent"]))
        reset_btn.bind("<Leave>",    lambda e, b=reset_btn: update_icon(b, "reset", 14, C["text3"]))
        reset_btn.bind("<Button-1>", lambda e, k=key, kd=kind: self._reset_one_setting(k, kd))

    def _browse_font(self, key: str, sv: tk.StringVar):
        dialog = FontBrowserDialog(self, current_path=CFG.get(key, ""))
        self.wait_window(dialog)
        path = dialog.get_path()
        if path:
            sv.set(path)
            CFG[key] = path
            if hasattr(sv, "_name_lbl"):
                sv._name_lbl.configure(text=os.path.basename(path))
            _save_settings()

    # =========================================================================
    # SHARED WIDGET FACTORY
    # =========================================================================

    def _make_btn(self, parent, text: str, cmd, accent=False, danger=False, small=False, icon=None):
        h  = 26 if small else 32
        fs = 9  if small else 11
        if accent:   bg, hbg, fg = C["accent"],   C["accent_hover"], "#ffffff"
        elif danger: bg, hbg, fg = C["surface2"],  "#6b2020",         C["error"]
        else:        bg, hbg, fg = C["surface2"],  C["border2"],       C["text2"]
        kw = dict(image=icon, compound="left") if icon is not None else {}
        return ctk.CTkButton(parent, text=text.strip(), height=h, command=cmd,
                             fg_color=bg, hover_color=hbg, text_color=fg,
                             font=("Montserrat", fs), corner_radius=7, anchor="center", **kw)

    # =========================================================================
    # FOLDER POLLING
    # =========================================================================

    def _start_folder_polling(self):
        self._poll_once()
        self.after(2000, self._start_folder_polling)

    def _poll_once(self):
        if os.path.isdir(INPUT_FOLDER):
            mt = os.path.getmtime(INPUT_FOLDER)
            if mt != self._last_input_mtime:
                self._last_input_mtime = mt
                self._refresh_input()

        out_dir = CFG["OUTPUT_FOLDER"]
        if os.path.isdir(out_dir):
            mt = os.path.getmtime(out_dir)
            if mt != self._last_output_mtime:
                self._last_output_mtime = mt
                self._refresh_output()
        elif any(
            os.path.exists(p) and os.path.getsize(p) != self._output_sizes.get(p, -1)
            for p in self._outputs
        ):
            self._refresh_output()

    def _refresh_input(self):
        disk = set()
        if os.path.isdir(INPUT_FOLDER):
            for fname in os.listdir(INPUT_FOLDER):
                if fname.lower().endswith(".mp4"):
                    disk.add(os.path.abspath(os.path.join(INPUT_FOLDER, fname)))
        current = set(self._files)
        for p in sorted(disk - current):
            self._files.append(p)
            self._add_file_row(p)
        removed = current - disk
        if removed:
            self._files = [p for p in self._files if p not in removed]
            self._redraw_file_list()
        self._update_queue_empty()

    def _refresh_output(self):
        out_dir = CFG["OUTPUT_FOLDER"]
        disk    = set()
        if os.path.isdir(out_dir):
            for fname in os.listdir(out_dir):
                if fname.lower().endswith(".mp4") and fname.startswith("sub_"):
                    disk.add(os.path.abspath(os.path.join(out_dir, fname)))
        self._outputs = sorted(disk, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        self._output_sizes = {p: os.path.getsize(p) for p in self._outputs if os.path.exists(p)}
        self._redraw_output_list()
        self._update_output_empty()

    # =========================================================================
    # FILE ROWS — QUEUE
    # =========================================================================

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        os.makedirs(INPUT_FOLDER, exist_ok=True)
        copied = 0
        for src in paths:
            dst = os.path.join(INPUT_FOLDER, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                copied += 1
        self._refresh_input()
        if copied:
            log(f"Added {copied} file(s)")

    def _remove_file(self, path: str, frame: tk.Frame):
        if path in self._files:
            self._files.remove(path)
        frame.destroy()
        if os.path.abspath(path).startswith(os.path.abspath(INPUT_FOLDER)):
            try: os.remove(path)
            except Exception: pass
        self._update_queue_empty()

    def _clear_files(self):
        for p in list(self._files):
            if os.path.abspath(p).startswith(os.path.abspath(INPUT_FOLDER)):
                try: os.remove(p)
                except Exception: pass
        self._files.clear()
        for w in self._file_list.winfo_children():
            w.destroy()
        self._update_queue_empty()

    def _redraw_file_list(self):
        for w in self._file_list.winfo_children():
            w.destroy()
        for p in self._files:
            self._add_file_row(p)

    def _add_file_row(self, path: str):
        row_idx = len(self._files) - 1
        frame   = tk.Frame(self._file_list, bg=C["surface"],
                           highlightbackground=C["border"], highlightthickness=0)
        frame.grid(row=row_idx, column=0, sticky="ew", pady=(0, 1))
        frame.grid_columnconfigure(1, weight=1)

        tk.Frame(frame, bg=C["accent"], width=3).grid(row=0, column=0, sticky="ns", pady=1)
        size = os.path.getsize(path) / 1024 / 1024 if os.path.exists(path) else 0
        tk.Label(frame, text=os.path.basename(path), bg=C["surface"], fg=C["text"],
                 font=FONT_UI, anchor="w").grid(row=0, column=1, sticky="w", padx=(12, 8), pady=11)
        tk.Label(frame, text=f"{size:.1f} MB", bg=C["surface"],
                 fg=C["text3"], font=FONT_UI_SM).grid(row=0, column=2, padx=(0, 8))

        rm = icon_lbl(frame, "x_small", 13, C["text3"], C["surface"],
                      cursor="hand2", padx=10, pady=11)
        rm.grid(row=0, column=3, padx=(0, 4))
        rm.bind("<Enter>",    lambda e, b=rm: update_icon(b, "x_small", 13, C["error"]))
        rm.bind("<Leave>",    lambda e, b=rm: update_icon(b, "x_small", 13, C["text3"]))
        rm.bind("<Button-1>", lambda e, p=path, f=frame: self._remove_file(p, f))

    def _open_preview_from_settings(self):
        existing = getattr(self, "_preview_window", None)
        if existing is not None:
            try:
                existing.lift()
                existing.focus_force()
                return
            except Exception:
                self._preview_window = None
        self._preview_window = PreviewWindow(self)

    # =========================================================================
    # FILE ROWS — OUTPUT
    # =========================================================================

    def _redraw_output_list(self):
        for w in self._output_list.winfo_children():
            w.destroy()
        for i, p in enumerate(self._outputs):
            self._add_output_row(p, i)

    def _add_output_row(self, path: str, row: int):
        frame = tk.Frame(self._output_list, bg=C["surface"])
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 1))
        frame.grid_columnconfigure(1, weight=1)

        tk.Frame(frame, bg=C["success"], width=3).grid(row=0, column=0, sticky="ns", pady=1)
        size = os.path.getsize(path) / 1024 / 1024 if os.path.exists(path) else 0
        tk.Label(frame, text=os.path.basename(path), bg=C["surface"], fg=C["text"],
                 font=FONT_UI, anchor="w").grid(row=0, column=1, sticky="w", padx=(12, 8), pady=11)
        tk.Label(frame, text=f"{size:.1f} MB", bg=C["surface"],
                 fg=C["text3"], font=FONT_UI_SM).grid(row=0, column=2, padx=(0, 12))

        btn_frame = tk.Frame(frame, bg=C["surface"])
        btn_frame.grid(row=0, column=3, padx=(0, 8))
        self._make_btn(btn_frame, "Open",      lambda p=path: self._open_file(p),      accent=True, small=True).pack(side="left", padx=(0, 4))
        self._make_btn(btn_frame, "Open with", lambda p=path: self._open_with(p),      small=True).pack(side="left", padx=(0, 4))
        self._make_btn(btn_frame, "Folder",    lambda p=path: self._reveal_file(p),    small=True).pack(side="left", padx=(0, 4))

        rm = icon_lbl(frame, "x_small", 13, C["text3"], C["surface"],
                      cursor="hand2", padx=10, pady=11)
        rm.grid(row=0, column=4, padx=(0, 4))
        rm.bind("<Enter>",    lambda e, b=rm: update_icon(b, "x_small", 13, C["error"]))
        rm.bind("<Leave>",    lambda e, b=rm: update_icon(b, "x_small", 13, C["text3"]))
        rm.bind("<Button-1>", lambda e, p=path, f=frame: self._delete_output(p, f))

    def _delete_output(self, path: str, frame: tk.Frame):
        if os.path.exists(path):
            try:
                os.remove(path)
                log(f"Deleted  {os.path.basename(path)}")
            except Exception as e:
                log(f"ERROR  {e}")
        if path in self._outputs:
            self._outputs.remove(path)
        frame.destroy()
        self._update_output_empty()

    # =========================================================================
    # PROCESSING PIPELINE
    # =========================================================================

    def _start_transcribe(self):
        if self._running or not self._files:
            if not self._files:
                log("No files in queue.")
            return
        self._running = True
        self._pending_transcripts = []
        self._run_btn.configure(state="disabled", text="Transcribing…")
        self._edit_btn.configure(state="disabled")
        self._step_lbl.configure(text="Step 1 of 2 — Transcribing audio…", fg=C["text3"])
        self._show_batch_banner(len(self._files), "transcribe")
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

    def _transcribe_worker(self):
        _dlog("_transcribe_worker started")
        try:
            _dlog("importing whisper…")
            import whisper as _whisper
            _dlog("whisper imported OK")
        except Exception as e:
            _dlog(f"FAILED to import whisper: {e}\n{traceback.format_exc()}")
            log(f"ERROR  Cannot load Whisper: {e}")
            self._running = False
            self.after(0, lambda: self._on_transcribe_done([]))
            return

        model_name = CFG.get("WHISPER_MODEL", "base")
        if self._model is None or getattr(self._model, "_name", "") != model_name:
            try:
                _dlog(f"loading whisper model={model_name}")
                from core.transcribe import get_whisper_device
                device = "cpu" if getattr(sys, "frozen", False) else get_whisper_device()
                _dlog(f"device={device}")
                log(f"Loading Whisper model '{model_name}'…  (this may take a moment)")
                with _quiet_io():
                    self._model = _whisper.load_model(model_name, device=device)
                self._model._name = model_name
                _dlog("model loaded OK")
                log(f"Whisper '{model_name}' ready  ·  device={device}")
            except Exception as e:
                _dlog(f"FAILED to load model: {e}\n{traceback.format_exc()}")
                log(f"ERROR  Cannot load Whisper model: {e}")
                self._running = False
                self.after(0, lambda: self._on_transcribe_done([]))
                return

        results = []
        total   = len(self._files)
        for i, path in enumerate(list(self._files)):
            log(f"── Transcribing {i+1}/{total}  —  {os.path.basename(path)}")
            try:
                _dlog(f"transcribe_file: {path}")
                chunks, audio_path, video_meta = transcribe_file(path, self._model)
                results.append((path, chunks, audio_path, video_meta))
                _dlog(f"transcribe_file done: {len(chunks)} chunks")
            except Exception as e:
                _dlog(f"ERROR in transcribe_file: {e}\n{traceback.format_exc()}")
                log(f"ERROR  {e}")
                log(f"  → {traceback.format_exc().strip().splitlines()[-1]}")
            self.after(0, self._on_batch_file_done)

        failed = total - len(results)
        _dlog(f"_transcribe_worker done, {len(results)}/{total} succeeded")
        if failed:
            log(f"WARNING  {failed}/{total} file(s) failed transcription")
        self._running = False
        self.after(0, lambda r=results: self._on_transcribe_done(r))

    def _on_batch_file_done(self):
        self._batch_done += 1
        self._update_batch_banner()

    def _on_transcribe_done(self, results):
        self._pending_transcripts = results
        self._progress.set(0.15)
        self._hide_batch_banner()
        if results:
            self._run_btn.configure(state="normal", text="1. Transcribe")
            self._edit_btn.configure(
                state="normal",
                fg_color=C["accent"], hover_color=C["accent_hover"],
                text_color="#ffffff", text="2. Review & Edit Transcript",
                image=get_icon("check", 14, "#ffffff"),
            )
            self._step_lbl.configure(
                text="Transcription done — review before rendering.",
                fg=C["success"],
            )
            log(f"Transcription complete  ·  {len(results)} file(s) ready to review")
        else:
            self._run_btn.configure(state="normal", text="1. Transcribe")
            self._step_lbl.configure(text="", fg=C["text3"])
            self._progress.set(0)

    def _open_transcript_editor(self):
        if not self._pending_transcripts:
            return
        editor_data = [
            (os.path.basename(path), chunks, audio_path, video_meta)
            for path, chunks, audio_path, video_meta in self._pending_transcripts
        ]
        editor = TranscriptEditor(self, editor_data)
        self.wait_window(editor)
        result = editor.get_result()
        if result is None:
            return
        for i, new_chunks in enumerate(result):
            path, _, audio_path, video_meta = self._pending_transcripts[i]
            self._pending_transcripts[i] = (path, new_chunks, audio_path, video_meta)
        self._start_render()

    def _start_render(self):
        if self._running:
            return
        self._running = True
        self._edit_btn.configure(state="disabled", text="Rendering…")
        self._run_btn.configure(state="disabled")
        self._step_lbl.configure(text="Step 2 of 2 — Rendering video…", fg=C["text3"])
        self._show_batch_banner(len(self._pending_transcripts), "render")
        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        total   = len(self._pending_transcripts)
        failed  = 0
        for i, (path, chunks, audio_path, video_meta) in enumerate(self._pending_transcripts):
            log(f"── Rendering {i+1}/{total}  —  {os.path.basename(path)}")
            try:
                render_file(path, chunks, audio_path, video_meta)
            except Exception as e:
                failed += 1
                log(f"ERROR  {e}")
                log(f"  → {traceback.format_exc().strip().splitlines()[-1]}")
                _dlog(f"ERROR in render_file: {e}\n{traceback.format_exc()}")
            self.after(0, self._on_batch_file_done)

        if failed:
            log(f"WARNING  {failed}/{total} file(s) failed to render")
        self._running = False
        self._pending_transcripts = []
        self.after(0, self._on_render_done)

    def _on_render_done(self):
        self._run_btn.configure(state="normal", text="1. Transcribe")
        self._edit_btn.configure(
            state="disabled",
            fg_color=C["surface2"], hover_color=C["border2"],
            text_color=C["text2"], text="2. Review & Edit Transcript",
            image=get_icon("check", 14, C["text2"]),
        )
        self._progress.set(0)
        self._step_lbl.configure(text="", fg=C["text3"])
        self._hide_batch_banner()
        log("All done")

    # =========================================================================
    # MISC ACTIONS
    # =========================================================================

    def _open_discord(self):
        import webbrowser
        webbrowser.open("https://discord.gg/np4XWvqgQ4")

    def _open_output_folder(self):
        folder = os.path.abspath(CFG["OUTPUT_FOLDER"])
        os.makedirs(folder, exist_ok=True)
        xdg_open(folder)

    def _open_input_folder(self):
        folder = os.path.abspath(INPUT_FOLDER)
        os.makedirs(folder, exist_ok=True)
        xdg_open(folder)

    def _open_file(self, path: str):
        if os.path.exists(path):
            xdg_open(path)

    def _open_with(self, path: str):
        if not os.path.exists(path):
            return
        if os.name == "nt":
            subprocess.Popen(["rundll32", "shell32.dll,OpenAs_RunDLL", os.path.abspath(path)])
        else:
            xdg_open(path)

    def _reveal_file(self, path: str):
        xdg_open(os.path.dirname(os.path.abspath(path)))

    # =========================================================================
    # LOG
    # =========================================================================

    def _gui_log(self, line: str, pct: Optional[float]):
        self.after(0, lambda l=line, p=pct: self._append_log(l, p))

    def _append_log(self, line: str, pct: Optional[float]):
        box = self._log_box._textbox
        box.configure(state="normal")
        low = line.lower()
        tag = ("error"    if "error" in low else
               "done"     if ("done" in low or "ready" in low) else
               "progress" if ("pre-rendering" in low or "encoding" in low) else
               None)
        is_progress = "eta" in low and "·" in low
        if is_progress:
            box.delete("end-2l", "end-1l")
        if tag:
            box.insert("end", line + "\n", tag)
        else:
            box.insert("end", line + "\n")
        box.see("end")
        box.configure(state="disabled")
        if pct is not None:
            self._progress.set(max(0.0, min(1.0, pct)))

    def _clear_log(self):
        self._log_box._textbox.configure(state="normal")
        self._log_box._textbox.delete("1.0", "end")
        self._log_box._textbox.configure(state="disabled")

    def _copy_log(self):
        text = self._log_box._textbox.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)

    # =========================================================================
    # SETTINGS HELPERS
    # =========================================================================

    def _apply_setting(self, key: str, value):
        CFG[key] = value
        _save_settings()

    def _apply_typed(self, key: str, sv: tk.StringVar, kind: str):
        try:
            raw = sv.get()
            CFG[key] = int(raw) if kind == "int" else float(raw)
            _save_settings()
        except ValueError:
            pass

    def _reset_one_setting(self, key: str, kind: str):
        if key not in DEFAULTS:
            return
        default = DEFAULTS[key]
        CFG[key] = default
        _save_settings()

        sv = self._sv.get(key)
        if sv is None:
            return

        if kind == "bool":
            sv.set(bool(default))
        elif kind == "color":
            sv.set(str(default))
            hex_str = self._rgba_to_hex(default)
            if hasattr(sv, "_hex_lbl"):
                sv._hex_lbl.configure(text=hex_str)
            if hasattr(sv, "_preview"):
                sv._preview.configure(bg=hex_str)
        elif kind == "font":
            sv.set(str(default))
            if hasattr(sv, "_name_lbl"):
                sv._name_lbl.configure(text=os.path.basename(str(default)))
        elif kind == "word_case":
            _CASE_LABELS = {"default": "default", "upper": "UPPERCASE",
                            "title": "Title Case", "lower": "lowercase"}
            sv.set(_CASE_LABELS.get(str(default), "default"))
        elif kind == "chunk_mode":
            sv.set(str(default))
            self._update_chunk_mode_visibility(str(default))
        elif kind == "whisper_model":
            sv.set(str(default))
            self._model = None
        else:
            sv.set(str(default))

    def _update_chunk_mode_visibility(self, mode: str):
        rows     = getattr(self, "_setting_rows",     {})
        dividers = getattr(self, "_setting_dividers", {})
        for key, show in (("MAX_WORDS", mode == "words"), ("MAX_LINES", mode == "lines")):
            row = rows.get(key)
            div = dividers.get(key)
            if row:
                row.grid() if show else row.grid_remove()
            if div:
                div.grid() if show else div.grid_remove()

    def _browse(self, key: str, sv: tk.StringVar, kind: str):
        p = (filedialog.askopenfilename(title="Select font file",
                                        filetypes=[("Font files", "*.ttf *.otf"), ("All", "*.*")])
             if kind == "path" else
             filedialog.askdirectory(title="Select output folder"))
        if p:
            sv.set(p); CFG[key] = p; _save_settings()
            if hasattr(sv, "_name_lbl"):
                sv._name_lbl.configure(text=os.path.basename(p))

    def _pick_color(self, key: str, sv: tk.StringVar, preview_label: tk.Label, hex_lbl: tk.Label = None):
        dialog = ColorPickerDialog(self, initial_color=CFG[key], title=f"Pick colour — {key}")
        self.wait_window(dialog)
        result = dialog.get_color()
        if result:
            CFG[key] = result
            sv.set(str(result))
            hex_str = self._rgba_to_hex(result)
            preview_label.configure(bg=hex_str)
            if hex_lbl:
                hex_lbl.configure(text=hex_str)
            _save_settings()

    def _reset_settings(self):
        for key, val in DEFAULTS.items():
            CFG[key] = val
        _save_settings()
        for key, sv in self._sv.items():
            if isinstance(sv, tk.BooleanVar):
                sv.set(bool(CFG[key]))
            else:
                sv.set(str(CFG[key]))
            if hasattr(sv, "_hex_lbl"):
                sv._hex_lbl.configure(text=self._rgba_to_hex(CFG[key]))
            if hasattr(sv, "_preview"):
                sv._preview.configure(bg=self._rgba_to_hex(CFG[key]))
            if hasattr(sv, "_name_lbl"):
                sv._name_lbl.configure(text=os.path.basename(str(CFG[key])))

    @staticmethod
    def _rgba_to_hex(val) -> str:
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            return "#{:02x}{:02x}{:02x}".format(int(val[0]), int(val[1]), int(val[2]))
        return "#888888"
