"""
QuickTitles — system font discovery.
"""

import os
from typing import Optional


def _find_system_fonts() -> dict[str, str]:
    """
    Return {display_name: file_path} for every .ttf / .otf font found on the system.
    """
    font_dirs = []
    if os.name == "nt":
        win_fonts  = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
        user_fonts = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
        font_dirs  = [win_fonts, user_fonts]
    else:
        font_dirs = [
            "/usr/share/fonts", "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/Library/Fonts"),
            "/Library/Fonts", "/System/Library/Fonts",
        ]

    found: dict[str, str] = {}
    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fname in files:
                if fname.lower().endswith((".ttf", ".otf")):
                    full = os.path.join(root, fname)
                    display = os.path.splitext(fname)[0]
                    found[display] = full
    return dict(sorted(found.items(), key=lambda x: x[0].lower()))


_SYSTEM_FONTS: Optional[dict[str, str]] = None


def get_system_fonts() -> dict[str, str]:
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is None:
        _SYSTEM_FONTS = _find_system_fonts()
    return _SYSTEM_FONTS
