"""
QuickTitles — searchable font browser dialog with live preview.
"""

import tkinter as tk
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from utils import _apply_icon
from core.fonts import get_system_fonts
from gui.theme import C, FONT_MONO


class FontBrowserDialog(ctk.CTkToplevel):
    """
    Lists all installed system fonts in a searchable scrollable list with a
    live preview of the font rendering.  Confirms the chosen font file path.
    """

    PREVIEW_TEXT = "The quick brown fox jumps"
    PREVIEW_SIZE = 22

    def __init__(self, parent, current_path: str = ""):
        super().__init__(parent)
        self.title("Font Browser")
        self.geometry("660x540")
        self.minsize(500, 400)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.configure(fg_color=C["bg"])
        self.after(300, lambda: _apply_icon(self))

        self._fonts    = get_system_fonts()
        self._names    = list(self._fonts.keys())
        self._result   = None
        self._sel_path = current_path
        self._preview_after: Optional[str] = None

        self._build_ui()
        self._populate(self._names)
        self._preselect(current_path)

    def _build_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(self, bg=C["bg"])
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        hdr.grid_columnconfigure(0, weight=1)
        tk.Label(hdr, text="Font Browser", bg=C["bg"], fg=C["text"],
                 font=("Montserrat", 15, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(hdr, text=f"{len(self._fonts)} fonts found",
                 bg=C["bg"], fg=C["text3"], font=("Montserrat", 9)).grid(row=0, column=1, sticky="e")

        search_frame = tk.Frame(self, bg=C["bg"])
        search_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        search_frame.grid_columnconfigure(0, weight=1)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        ctk.CTkEntry(search_frame, textvariable=self._search_var, placeholder_text="Search fonts…",
                     height=34, corner_radius=8, fg_color=C["surface2"],
                     border_color=C["border2"], text_color=C["text"],
                     font=("Montserrat", 12)).grid(row=0, column=0, sticky="ew")

        list_frame = tk.Frame(self, bg=C["bg"])
        list_frame.grid(row=2, column=0, sticky="nsew", padx=20)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_frame, bg=C["surface"], fg=C["text"], font=("Montserrat", 11),
            selectbackground=C["accent_dim"], selectforeground=C["accent"],
            activestyle="none", relief="flat", bd=0,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"],
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview,
                          bg=C["surface2"], troughcolor=C["surface"])
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<Double-Button-1>", lambda e: self._ok())

        preview_card = tk.Frame(self, bg=C["surface"],
                                highlightbackground=C["border"], highlightthickness=1)
        preview_card.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 0))
        preview_card.grid_columnconfigure(0, weight=1)

        self._preview_canvas = tk.Canvas(preview_card, height=64, bg=C["surface"],
                                         highlightthickness=0)
        self._preview_canvas.grid(row=0, column=0, sticky="ew", padx=12, pady=8)

        self._path_lbl = tk.Label(preview_card, text="", bg=C["surface"],
                                  fg=C["text3"], font=("Consolas", 9), anchor="w")
        self._path_lbl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        btn_row = tk.Frame(self, bg=C["bg"])
        btn_row.grid(row=4, column=0, sticky="ew", padx=20, pady=(10, 18))
        btn_row.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(btn_row, text="Cancel", width=100, height=34, anchor="center",
                      fg_color=C["surface2"], hover_color=C["border2"], text_color=C["text2"],
                      font=("Montserrat", 12), corner_radius=8,
                      command=self.destroy).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(btn_row, text="Select Font", width=130, height=34, anchor="center",
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      font=("Montserrat", 12), corner_radius=8,
                      command=self._ok).grid(row=0, column=2)

    def _populate(self, names: list[str]):
        self._listbox.delete(0, "end")
        for name in names:
            self._listbox.insert("end", name)

    def _on_search(self, *_):
        q = self._search_var.get().lower()
        filtered = [n for n in self._names if q in n.lower()]
        self._populate(filtered)

    def _on_select(self, _event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        name = self._listbox.get(sel[0])
        path = self._fonts.get(name, "")
        self._sel_path = path
        self._path_lbl.configure(text=path)
        if self._preview_after:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(120, lambda p=path: self._render_preview(p))

    def _render_preview(self, path: str):
        self._preview_canvas.delete("all")
        W = self._preview_canvas.winfo_width() or 580
        H = 64
        try:
            font = ImageFont.truetype(path, self.PREVIEW_SIZE)
            img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((12, (H - self.PREVIEW_SIZE) // 2), self.PREVIEW_TEXT,
                      font=font, fill=C["text"])
            self._prev_tk = ImageTk.PhotoImage(img)
            self._preview_canvas.create_image(0, 0, anchor="nw", image=self._prev_tk)
        except Exception:
            self._preview_canvas.create_text(
                12, H // 2, anchor="w", text="(preview not available)",
                fill=C["text3"], font=("Montserrat", 10))

    def _preselect(self, path: str):
        for i, name in enumerate(self._listbox.get(0, "end")):
            if self._fonts.get(name, "") == path:
                self._listbox.selection_set(i)
                self._listbox.see(i)
                self._on_select()
                break

    def _ok(self):
        if self._sel_path:
            self._result = self._sel_path
            self.destroy()

    def get_path(self) -> Optional[str]:
        return self._result
