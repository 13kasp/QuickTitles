"""
QuickTitles — configuration, constants, and settings persistence.
"""

import os
import json
import platform

# =============================================================================
# CONSTANTS
# =============================================================================

_EPSILON        = 1e-6
_LUT_SLOTS      = 1000
_MAX_GAP_BRIDGE = 0.5
INPUT_FOLDER    = "input"
SETTINGS_FILE   = "quicktitles_settings.json"

# =============================================================================
# DEFAULTS / CFG
# =============================================================================

DEFAULTS: dict = {
    # Text
    "FONT_PATH"              : (
        "C:/Windows/Fonts/arialbd.ttf" if os.name == "nt" else
        "/System/Library/Fonts/Helvetica.ttc" if platform.system() == "Darwin" else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ),
    "FONT_SIZE"              : 110,
    "TEXT_COLOR"             : (255, 255, 255, 255),
    "MAX_WORDS"              : 4,
    "CHUNK_MODE"             : "words",
    "MAX_LINES"              : 2,
    "VERTICAL_POSITION"      : 0.72,
    "LINE_SPACING"           : 14,
    "MAX_WIDTH_RATIO"        : 0.92,
    "ENABLE_HIGHLIGHT"       : True,
    "HIGHLIGHT_COLOR"        : (122, 43, 226, 255),
    "HIGHLIGHT_PADDING_X"    : 26,
    "HIGHLIGHT_PADDING_Y"    : 18,
    "HIGHLIGHT_CORNER_RADIUS": 18,
    "INK_VERTICAL_NUDGE"     : 8,
    "ENABLE_POP_ANIMATION"   : True,
    "POP_SCALE_START"        : 1.35,
    "POP_DURATION"           : 0.10,
    "POP_STEPS"              : 12,
    "ENABLE_SLIDE_ANIMATION" : True,
    "TRANSITION_DURATION"    : 0.12,
    "TRANSITION_STEPS"       : 24,
    "ENABLE_MOTION_BLUR"     : True,
    "MOTION_BLUR_STRENGTH"   : 2,
    "ENABLE_DROP_SHADOW"     : True,
    "DROP_SHADOW_SPREAD"     : 60,
    "DROP_SHADOW_OPACITY"    : 120,
    "DROP_SHADOW_HOLD"       : 0.30,
    "OUTPUT_FOLDER"          : "output",
    "RENDER_THREADS"         : 4,
    "ENCODE_PRESET_X264"     : "fast",
    "ENCODE_CRF"             : 18,
    "ENCODE_PRESET_NVENC"    : "p7",
    "ENCODE_CQ_NVENC"        : 17,
    "ENCODE_MAXRATE"         : "60M",
    "ENCODE_BUFSIZE"         : "100M",
    "ENCODE_AUDIO_BITRATE"   : "320k",
    "ENCODE_EXTRA_FLAGS"     : "",
    "WHISPER_MODEL"          : "small",
    "WORD_CASE"              : "default",
}

CFG = dict(DEFAULTS)


def _load_settings() -> None:
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        for key, val in saved.items():
            if key in DEFAULTS:
                CFG[key] = tuple(val) if isinstance(DEFAULTS[key], tuple) else val
    except Exception as e:
        print(f"[settings] Could not load: {e}")


def _save_settings() -> None:
    try:
        serialisable = {
            k: list(v) if isinstance(v, tuple) else v
            for k, v in CFG.items()
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(serialisable, f, indent=2)
    except Exception as e:
        print(f"[settings] Could not save: {e}")


_load_settings()
