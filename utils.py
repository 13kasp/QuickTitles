"""
QuickTitles — logging, debug, and miscellaneous helpers.
"""

import os
import sys
import io
import time
import contextlib
import platform
import subprocess
from typing import Optional

from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Debug log

_DEBUG_LOG = os.path.join(
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__)),
    "quicktitles_debug.log",
)


def _dlog(msg: str) -> None:
    """Append a timestamped line to the debug log file."""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


_dlog(f"--- App start  frozen={getattr(sys, 'frozen', False)} ---")
_dlog(f"FFMPEG_BINARY={os.environ.get('FFMPEG_BINARY', 'NOT SET')}")
_dlog(f"PATH prefix={os.environ.get('PATH', '')[:120]}")


# ---------------------------------------------------------------------------
# Frozen-exe I/O suppression

def _quiet_io():
    """Suppress stdout/stderr when running as a frozen exe."""
    if not getattr(sys, "frozen", False):
        return contextlib.nullcontext()
    null = io.StringIO()

    class _Both:
        def __enter__(self):
            self._a = contextlib.redirect_stdout(null)
            self._b = contextlib.redirect_stderr(null)
            self._a.__enter__(); self._b.__enter__()

        def __exit__(self, *args):
            self._b.__exit__(*args); self._a.__exit__(*args)

    return _Both()


# ---------------------------------------------------------------------------
# Window icon

def _apply_icon(window) -> None:
    """Apply the app icon to any Tk/CTk window or Toplevel."""
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico_path = os.path.join(base, "icon.ico")
        png_path = os.path.join(base, "icon.png")
        if os.name == "nt" and os.path.exists(ico_path):
            window.iconbitmap(ico_path)
            return
        if os.path.exists(png_path):
            img = Image.open(png_path).resize((32, 32), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            window._icon_ref = photo
            window.iconphoto(True, photo)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Logging

_log_cb = None


def _timestamp() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str, pct: Optional[float] = None) -> None:
    line = f"[{_timestamp()}]  {msg}"
    if _log_cb:
        _log_cb(line, pct)
    else:
        print(line)


def log_progress(label: str, current: int, total: int, elapsed: float, pct: float) -> None:
    rate = current / elapsed if elapsed > 0 else 0
    eta  = (total - current) / rate if rate > 0 else 0
    log(f"{label}  {current}/{total}  ·  {fmt_time(int(elapsed))} elapsed  ·  ETA {fmt_time(int(eta))}", pct)


# ---------------------------------------------------------------------------
# General helpers

def fmt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h: return f"{h}h {m:02}m {s:02}s"
    if m: return f"{m}m {s:02}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Cross-platform open

def xdg_open(path: str) -> None:
    """Open a file or folder in the system default app — cross-platform."""
    path = os.path.abspath(path)
    if os.name == "nt":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
