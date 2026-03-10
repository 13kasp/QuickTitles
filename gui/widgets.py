"""
QuickTitles — reusable GUI widgets: Tooltip and UndoEntry.
"""

import tkinter as tk
import customtkinter as ctk

from gui.theme import C


class Tooltip:
    def __init__(self, widget, text: str):
        self._widget = widget
        self._text   = text
        self._win    = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self._win or not self._text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        outer = tk.Frame(tw, bg=C["border2"], padx=1, pady=1)
        outer.pack()
        tk.Label(outer, text=self._text, justify="left", wraplength=300,
                 bg=C["surface2"], fg=C["text2"], font=("Montserrat", 10),
                 padx=12, pady=8).pack()
        tw.update_idletasks()

    def _hide(self, _event=None):
        if self._win:
            self._win.destroy()
            self._win = None


class UndoEntry(ctk.CTkEntry):
    """
    CTkEntry subclass that adds full Ctrl+Z / Ctrl+Y undo/redo support.
    History is per-widget and stored as a list of string snapshots.
    """

    _MAX_HISTORY = 200

    def __init__(self, master, textvariable: tk.StringVar = None, **kwargs):
        super().__init__(master, textvariable=textvariable, **kwargs)

        self._sv        = textvariable
        self._history   = [textvariable.get() if textvariable else ""]
        self._redo_stack: list[str] = []
        self._ignoring  = False

        if textvariable:
            textvariable.trace_add("write", self._on_change)

        inner = self._entry
        for seq_undo in ("<Control-z>", "<Control-Z>", "<Command-z>", "<Command-Z>"):
            inner.bind(seq_undo, self._undo, add=True)
        for seq_redo in ("<Control-y>", "<Control-Y>", "<Command-y>", "<Command-Y>"):
            inner.bind(seq_redo, self._redo, add=True)

    def _on_change(self, *_):
        if self._ignoring:
            return
        val = self._sv.get() if self._sv else self.get()
        if self._history and self._history[-1] == val:
            return
        if len(self._history) >= self._MAX_HISTORY:
            self._history.pop(0)
        self._history.append(val)
        self._redo_stack.clear()

    def _undo(self, event=None):
        if len(self._history) < 2:
            return "break"
        current = self._history.pop()
        self._redo_stack.append(current)
        prev = self._history[-1]
        self._set_value(prev)
        return "break"

    def _redo(self, event=None):
        if not self._redo_stack:
            return "break"
        val = self._redo_stack.pop()
        self._history.append(val)
        self._set_value(val)
        return "break"

    def _set_value(self, val: str):
        self._ignoring = True
        try:
            if self._sv:
                self._sv.set(val)
            else:
                self.delete(0, "end")
                self.insert(0, val)
        finally:
            self._ignoring = False
