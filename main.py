"""
QuickTitles — entry point.
"""

import multiprocessing
import os
import sys
import warnings
import logging

# Suppress noisy library output before any imports trigger them
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# Taskbar icon on Windows
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QuickTitles.App.1")
    except Exception:
        pass

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from gui.app import App


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required first in __main__ for PyInstaller
    App().mainloop()
