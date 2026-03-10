"""
QuickTitles — transcript editor dialog with integrated audio player.
"""

import os
import time
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from utils import _apply_icon
from gui.theme import C, FONT_MONO
from gui.icons import icon_lbl, update_icon, get_icon
from gui.widgets import UndoEntry
from gui.audio_player import AudioPlayer


class TranscriptEditor(ctk.CTkToplevel):
    """
    Modal editor for all transcript chunks with integrated audio preview.

    • Player bar  — play/pause the full audio, scrubber with live position.
    • Per-chunk ▶ — plays just that subtitle segment.
    • Editing     — each line is one subtitle group; blank = delete chunk.
    • Ctrl+Z/Y    — undo/redo per entry field.
    """

    _TICK_MS = 150

    def __init__(self, parent, file_chunks_list: list):
        super().__init__(parent)
        self.title("Edit Transcript")
        self.geometry("900x720")
        self.minsize(640, 480)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.configure(fg_color=C["bg"])
        self.after(300, lambda: _apply_icon(self))

        self._file_chunks_list = file_chunks_list
        self._confirmed = False
        self._result    = None
        self._entries: list[tuple] = []
        self._chunk_btns: list[tk.Label] = []

        self._players: list[Optional[AudioPlayer]] = []
        for _f, _c, audio_path, _m in file_chunks_list:
            self._players.append(
                AudioPlayer(audio_path) if (audio_path and os.path.exists(audio_path)) else None
            )

        self._active_idx    = 0
        self._is_playing    = False
        self._play_wall_t0  = 0.0
        self._play_offset   = 0.0
        self._play_end      = None
        self._tick_job      = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # =========================================================================
    # UI BUILD
    # =========================================================================

    def _build_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(self, bg=C["bg"])
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        hdr.grid_columnconfigure(0, weight=1)
        tk.Label(hdr, text="Review & Edit Transcript",
                 bg=C["bg"], fg=C["text"], font=("Montserrat", 16, "bold")
                 ).grid(row=0, column=0, sticky="w")
        tk.Label(hdr,
                 text="Edit words below, timings auto-adjust   ▶ on each row plays that line   Ctrl+Z / Ctrl+Y to undo/redo",
                 bg=C["bg"], fg=C["text2"], font=("Montserrat", 10)
                 ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self._build_player_bar()

        scroll = ctk.CTkScrollableFrame(
            self, fg_color=C["bg"], corner_radius=0,
            scrollbar_button_color=C["border2"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)

        flat = 0
        srow = 0
        for fi, (fname, chunks, _a, _m) in enumerate(self._file_chunks_list):
            lf = tk.Frame(scroll, bg=C["bg"])
            lf.grid(row=srow, column=0, sticky="ew", pady=(16 if fi else 4, 4))
            lf.grid_columnconfigure(1, weight=1)
            nl = tk.Label(lf, text=fname, bg=C["bg"], fg=C["accent"],
                          font=("Montserrat", 9, "bold"), cursor="hand2")
            nl.grid(row=0, column=0, sticky="w")
            nl.bind("<Button-1>", lambda e, i=fi: self._select_file(i))
            tk.Frame(lf, bg=C["border"], height=1).grid(
                row=0, column=1, sticky="ew", padx=(10, 0), pady=(1, 0))
            srow += 1

            card = tk.Frame(scroll, bg=C["surface"],
                            highlightbackground=C["border"], highlightthickness=1)
            card.grid(row=srow, column=0, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            srow += 1

            for ci, chunk in enumerate(chunks):
                text = " ".join(w["word"] for w in chunk["words"])
                sv   = tk.StringVar(value=text)
                self._entries.append((sv, fi, ci))

                rf = tk.Frame(card, bg=C["surface"])
                rf.grid(row=ci * 2, column=0, sticky="ew", padx=12, pady=6)
                rf.grid_columnconfigure(2, weight=1)

                tk.Label(rf, text=f"{ci+1:>3}.", bg=C["surface"],
                         fg=C["text3"], font=FONT_MONO, width=4
                         ).grid(row=0, column=0, sticky="w")

                btn = icon_lbl(rf, "play", 14, C["accent"], C["surface2"],
                               cursor="hand2", padx=8, pady=4)
                btn.grid(row=0, column=1, padx=(4, 6))
                btn._playing = False
                btn.bind("<Enter>", lambda e, b=btn: update_icon(
                    b, "stop" if b._playing else "play", 14, C["accent_hover"]))
                btn.bind("<Leave>", lambda e, b=btn: update_icon(
                    b, "stop" if b._playing else "play", 14,
                    C["warn"] if b._playing else C["accent"]))
                btn.bind("<Button-1>",
                         lambda e, i=fi, s=chunk["start"], en=chunk["end"], bi=flat:
                         self._play_chunk(i, s, en, bi))
                self._chunk_btns.append(btn)
                UndoEntry(
                    rf, textvariable=sv,
                    fg_color=C["surface2"], border_color=C["border2"],
                    text_color=C["text"], font=FONT_MONO,
                    corner_radius=6, height=36,
                ).grid(row=0, column=2, sticky="ew", padx=(0, 6))

                tk.Label(rf, text=f"{self._ts(chunk['start'])}–{self._ts(chunk['end'])}",
                         bg=C["surface"], fg=C["text3"], font=("Montserrat", 9)
                         ).grid(row=0, column=3, padx=(0, 4))

                if ci < len(chunks) - 1:
                    tk.Frame(card, bg=C["border"], height=1).grid(
                        row=ci * 2 + 1, column=0, columnspan=1, sticky="ew", padx=12)
                flat += 1

        footer = tk.Frame(self, bg=C["bg"])
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 20))
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, text="Tip: leave a line blank to remove that subtitle group",
                 bg=C["bg"], fg=C["text3"], font=("Montserrat", 9)
                 ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        br = tk.Frame(footer, bg=C["bg"])
        br.grid(row=1, column=0, sticky="ew")
        br.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(br, text="Cancel", width=110, height=38, anchor="center",
                      fg_color=C["surface2"], hover_color=C["border2"], text_color=C["text2"],
                      font=("Montserrat", 12), corner_radius=8,
                      command=self._on_close).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(br, text="Confirm & Render",
                      image=get_icon("check", 14, "#ffffff"), compound="left", anchor="center",
                      width=180, height=38,
                      fg_color=C["accent"], hover_color=C["accent_hover"], text_color="#ffffff",
                      font=("Montserrat", 12), corner_radius=8,
                      command=self._confirm).grid(row=0, column=2)

    def _build_player_bar(self):
        bar = tk.Frame(self, bg=C["surface"],
                       highlightbackground=C["border"], highlightthickness=1)
        bar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        bar.grid_columnconfigure(2, weight=1)

        self._pp = icon_lbl(bar, "play", 18, C["accent"], C["surface"],
                            cursor="hand2", padx=14, pady=8)
        self._pp._playing = False
        self._pp.grid(row=0, column=0)
        self._pp.bind("<Button-1>", lambda e: self._toggle_play())
        self._pp.bind("<Enter>",    lambda e: update_icon(
            self._pp, "pause" if self._is_playing else "play", 18, C["accent_hover"]))
        self._pp.bind("<Leave>",    lambda e: update_icon(
            self._pp, "pause" if self._is_playing else "play", 18,
            C["warn"] if self._is_playing else C["accent"]))

        sl = icon_lbl(bar, "stop", 16, C["text3"], C["surface"],
                      cursor="hand2", padx=8, pady=8)
        sl.grid(row=0, column=1)
        sl.bind("<Button-1>", lambda e: self._stop_reset())
        sl.bind("<Enter>",    lambda e: update_icon(sl, "stop", 16, C["error"]))
        sl.bind("<Leave>",    lambda e: update_icon(sl, "stop", 16, C["text3"]))

        self._scrub = tk.Canvas(bar, height=20, bg=C["surface"], highlightthickness=0,
                                cursor="hand2")
        self._scrub.grid(row=0, column=2, sticky="ew", padx=(4, 8))
        self._scrub.bind("<ButtonPress-1>",  self._scrub_press)
        self._scrub.bind("<B1-Motion>",       self._scrub_drag)
        self._scrub.bind("<ButtonRelease-1>", self._scrub_release)
        self._scrubbing = False

        self._time_lbl = tk.Label(bar, text="0:00 / 0:00", bg=C["surface"],
                                  fg=C["text3"], font=("Montserrat", 9), padx=10)
        self._time_lbl.grid(row=0, column=3)

        bar.after(80, self._draw_scrubber)

    # =========================================================================
    # SCRUBBER
    # =========================================================================

    def _cur_pos(self) -> float:
        if not self._is_playing:
            return self._play_offset
        return self._play_offset + (time.time() - self._play_wall_t0)

    def _duration(self) -> float:
        meta = self._file_chunks_list[self._active_idx][3]
        return float(meta.get("total_frames", 0)) / max(float(meta.get("fps", 30)), 1)

    def _draw_scrubber(self, frac: Optional[float] = None):
        c = self._scrub
        W = c.winfo_width()
        H = c.winfo_height()
        if W < 4:
            self.after(80, self._draw_scrubber)
            return
        if frac is None:
            dur  = self._duration()
            frac = min(self._cur_pos() / dur, 1.0) if dur > 0 else 0.0
        c.delete("all")
        cy = H // 2
        c.create_rectangle(0, cy - 2, W, cy + 2, fill=C["border2"], outline="")
        fx = int(frac * W)
        if fx > 0:
            c.create_rectangle(0, cy - 2, fx, cy + 2, fill=C["accent"], outline="")
        tx = max(7, min(W - 7, fx))
        c.create_oval(tx - 7, cy - 7, tx + 7, cy + 7, fill=C["accent"], outline="")
        pos = frac * self._duration()
        self._time_lbl.configure(
            text=f"{self._ts(pos)} / {self._ts(self._duration())}")

    def _scrub_frac(self, event) -> float:
        return max(0.0, min(1.0, event.x / max(self._scrub.winfo_width(), 1)))

    def _scrub_press(self, event):
        self._scrubbing = True
        self._draw_scrubber(self._scrub_frac(event))

    def _scrub_drag(self, event):
        if self._scrubbing:
            self._draw_scrubber(self._scrub_frac(event))

    def _scrub_release(self, event):
        self._scrubbing = False
        frac  = self._scrub_frac(event)
        was   = self._is_playing
        self._do_stop()
        self._play_offset = frac * self._duration()
        self._draw_scrubber(frac)
        if was:
            self._do_play(self._play_offset, None)

    def _start_tick(self):
        self._cancel_tick()
        self._tick_job = self.after(self._TICK_MS, self._tick)

    def _cancel_tick(self):
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None

    def _tick(self):
        if not self._is_playing:
            return
        pos = self._cur_pos()
        dur = self._duration()
        if self._play_end is not None and pos >= self._play_end:
            self._do_stop()
            return
        if dur > 0 and pos >= dur:
            self._do_stop()
            return
        if not self._scrubbing:
            self._draw_scrubber()
        self._start_tick()

    # =========================================================================
    # PLAYBACK PRIMITIVES
    # =========================================================================

    def _do_play(self, start: float, end: Optional[float]):
        player = self._players[self._active_idx] if self._active_idx < len(self._players) else None
        if not player:
            return

        self._is_playing   = True
        self._play_wall_t0 = time.time()
        self._play_offset  = start
        self._play_end     = end
        update_icon(self._pp, "pause", 18, C["warn"])

        def _done():
            self.after(0, self._on_natural_end)

        player.play(start, end, on_done=_done)
        self._start_tick()

    def _do_stop(self):
        self._cancel_tick()
        self._is_playing = False
        self._play_end   = None
        update_icon(self._pp, "play", 18, C["accent"])
        for p in self._players:
            if p:
                p.stop()
        for b in self._chunk_btns:
            b._playing = False
            update_icon(b, "play", 14, C["accent"])

    def _on_natural_end(self):
        if not self._is_playing:
            return
        self._do_stop()
        self._play_offset = 0.0
        self._draw_scrubber(0.0)

    # =========================================================================
    # USER-FACING CONTROLS
    # =========================================================================

    def _toggle_play(self):
        if self._is_playing:
            self._play_offset = self._cur_pos()
            self._do_stop()
            self._draw_scrubber()
        else:
            dur = self._duration()
            if self._play_offset >= dur:
                self._play_offset = 0.0
            self._do_play(self._play_offset, None)

    def _stop_reset(self):
        self._do_stop()
        self._play_offset = 0.0
        self._draw_scrubber(0.0)

    def _play_chunk(self, file_idx: int, start: float, end: float, btn_idx: int):
        self._do_stop()
        self._select_file(file_idx, silent=True)
        if btn_idx < len(self._chunk_btns):
            self._chunk_btns[btn_idx]._playing = True
            update_icon(self._chunk_btns[btn_idx], "stop", 14, C["warn"])

        def _done():
            self.after(0, lambda: (
                (setattr(self._chunk_btns[btn_idx], "_playing", False),
                 update_icon(self._chunk_btns[btn_idx], "play", 14, C["accent"]))
                if btn_idx < len(self._chunk_btns) else None
            ))

        player = self._players[file_idx] if file_idx < len(self._players) else None
        if not player:
            return

        self._is_playing   = True
        self._play_wall_t0 = time.time()
        self._play_offset  = start
        self._play_end     = end
        player.play(start, end, on_done=_done)
        self._start_tick()

    def _select_file(self, idx: int, silent=False):
        if idx == self._active_idx:
            return
        self._do_stop()
        self._active_idx  = idx
        self._play_offset = 0.0
        if not silent:
            self._draw_scrubber(0.0)

    # =========================================================================
    # CONFIRM / CLOSE
    # =========================================================================

    def _on_close(self):
        self._do_stop()
        self.destroy()

    def _confirm(self):
        self._do_stop()
        result = [[] for _ in self._file_chunks_list]
        for sv, fi, ci in self._entries:
            text = sv.get().strip()
            orig = self._file_chunks_list[fi][1][ci]
            if not text:
                continue
            words        = text.split()
            dur_per_word = (orig["end"] - orig["start"]) / len(words)
            new_words    = [
                {"word": w, "start": orig["start"] + i * dur_per_word,
                 "end":  orig["start"] + (i + 1) * dur_per_word}
                for i, w in enumerate(words)
            ]
            new_words[-1]["end"] = orig["end"]
            result[fi].append({"words": new_words, "start": orig["start"], "end": orig["end"]})
        self._result    = result
        self._confirmed = True
        self.destroy()

    def get_result(self) -> Optional[list]:
        return self._result if self._confirmed else None

    @staticmethod
    def _ts(s: float) -> str:
        s = max(0.0, float(s))
        return f"{int(s)//60}:{int(s)%60:02}"
