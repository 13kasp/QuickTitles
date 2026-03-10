# -*- mode: python ; coding: utf-8 -*-
# QuickTitles PyInstaller spec  —  cross-platform (Windows / macOS / Linux)
#
# ── Project layout expected ───────────────────────────────────────────────────
#   QuickTitles/
#     main.py
#     config.py
#     utils.py
#     core/
#       __init__.py
#       ffmpeg.py
#       fonts.py
#       transcribe.py
#       render.py          (render_file lives here)
#     gui/
#       __init__.py
#       app.py
#       theme.py
#       icons.py
#       widgets.py
#       color_picker.py
#       font_browser.py
#       transcript_editor.py
#       audio_player.py
#       preview.py
#     rendering/
#       __init__.py
#       animation.py
#       layout.py
#       primitives.py
#
# ── Windows ───────────────────────────────────────────────────────────────────
#   Copy ffmpeg.exe + ffprobe.exe next to this spec file, then:
#     pyinstaller QuickTitles.spec
#
# ── macOS ─────────────────────────────────────────────────────────────────────
#   cp $(which ffmpeg)  ./ffmpeg
#   cp $(which ffprobe) ./ffprobe
#   pyinstaller QuickTitles.spec
#
# ── Linux ─────────────────────────────────────────────────────────────────────
#   cp $(which ffmpeg)  ./ffmpeg
#   cp $(which ffprobe) ./ffprobe
#   pyinstaller QuickTitles.spec

import os
import sys
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

block_cipher = None
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# ---------------------------------------------------------------------------
# Windows-only: bundle VC++ 2015-2022 runtime DLLs that PyTorch needs.
# Without these, end-users on a clean Windows install get: WinError 1114
# ---------------------------------------------------------------------------

def _find_vcredist_dlls():
    if not IS_WIN:
        return []
    needed = [
        "vcruntime140.dll", "vcruntime140_1.dll",
        "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
        "concrt140.dll",
    ]
    search_dirs = [
        os.path.dirname(sys.executable),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "SysWOW64"),
    ]
    for pf in [os.environ.get("ProgramFiles", r"C:\Program Files"),
               os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]:
        if pf:
            search_dirs += glob.glob(os.path.join(
                pf, "Microsoft Visual Studio", "*", "*", "VC", "Redist", "MSVC", "*", "x64", "*.CRT"))
    found = {}
    for dll in needed:
        for d in search_dirs:
            p = os.path.join(d, dll)
            if os.path.exists(p) and dll.lower() not in found:
                found[dll.lower()] = p
                break
    print(f"[spec] VC++ DLLs bundled: {sorted(found.keys())}")
    missing = [d for d in needed if d.lower() not in found]
    if missing:
        print(f"[spec] WARNING - VC++ DLLs NOT found: {missing}")
    return [(path, ".") for path in found.values()]

vcredist_binaries = _find_vcredist_dlls()

# ---------------------------------------------------------------------------
# Collect packages
# ---------------------------------------------------------------------------

whisper_datas, whisper_binaries, whisper_hidden = collect_all("whisper")
ctk_datas      = collect_data_files("customtkinter")
torch_binaries = collect_dynamic_libs("torch")
numpy_binaries = collect_dynamic_libs("numpy")
scipy_binaries = collect_dynamic_libs("scipy")

_ffmpeg_name  = "ffmpeg.exe"  if IS_WIN else "ffmpeg"
_ffprobe_name = "ffprobe.exe" if IS_WIN else "ffprobe"
extra_binaries = []
for name in (_ffmpeg_name, _ffprobe_name):
    if os.path.exists(name):
        extra_binaries.append((name, "."))
    else:
        print(f"[spec] WARNING - {name} not found next to spec file — bundle will lack it.")

# Bundle both icon formats when available
_icon_datas = []
for _f in ("icon.ico", "icon.png"):
    if os.path.exists(_f):
        _icon_datas.append((_f, "."))

_icon_file = ("icon.ico" if (IS_WIN and os.path.exists("icon.ico")) else
              "icon.png" if os.path.exists("icon.png") else None)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["main.py"],                        # ← corrected entry point (was gen_titles.py)
    pathex=["."],                       # ensure local packages (gui/, core/, rendering/) resolve
    binaries=[
        *torch_binaries,
        *numpy_binaries,
        *scipy_binaries,
        *whisper_binaries,
        *vcredist_binaries,
        *extra_binaries,
    ],
    datas=[
        *whisper_datas,
        *ctk_datas,
        *_icon_datas,
    ],
    hiddenimports=[
        # ---- whisper (auto-collected, but belt-and-braces) ----
        *whisper_hidden,
        "whisper", "whisper.audio", "whisper.decoding", "whisper.model",
        "whisper.tokenizer", "whisper.transcribe", "whisper.utils",

        # ---- torch ----
        "torch", "torch.nn", "torch.jit", "torch.jit.frontend",
        "torch.utils", "torch.utils.data",
        "torch._C", "torch.backends", "torch.backends.cpu", "torch.backends.cuda",

        # ---- tiktoken (used by whisper) ----
        "tiktoken", "tiktoken_ext", "tiktoken_ext.openai_public",

        # ---- scipy / numpy ----
        "scipy", "scipy.signal", "scipy.fftpack", "scipy.signal.windows",
        "numpy", "numpy.core", "numpy.core._methods",

        # ---- PIL / Pillow ----
        "PIL", "PIL.Image", "PIL.ImageTk", "PIL.ImageDraw", "PIL.ImageFont",

        # ---- GUI stack ----
        "tkinter", "tkinter.filedialog",
        "customtkinter",

        # ---- first-party packages ----
        # config / utils (top-level modules)
        "config", "utils",
        # core sub-package
        "core", "core.ffmpeg", "core.fonts", "core.transcribe", "core.render",
        # gui sub-package
        "gui", "gui.app", "gui.theme", "gui.icons", "gui.widgets",
        "gui.color_picker", "gui.font_browser",
        "gui.transcript_editor", "gui.audio_player", "gui.preview",
        # rendering sub-package
        "rendering", "rendering.animation", "rendering.layout", "rendering.primitives",

        # ---- stdlib extras that get missed on some builds ----
        "multiprocessing", "multiprocessing.spawn", "multiprocessing.forkserver",
        "multiprocessing.reduction", "multiprocessing.pool",
        "packaging", "packaging.version", "packaging.specifiers", "packaging.requirements",
        "pathlib", "re", "json", "shutil", "colorsys",
        "ctypes", "ctypes.util",
        "concurrent.futures", "concurrent.futures.thread",
        "dataclasses", "enum", "abc", "copy",
        "struct", "gzip", "zlib", "base64",
        "unicodedata", "textwrap", "inspect",
        "tempfile", "io", "contextlib", "functools",
        "logging", "logging.handlers",
        "threading", "queue",
        "urllib", "urllib.request", "urllib.parse", "urllib.error",
        "http", "http.client",
        "ssl", "socket",
        "email", "email.message", "email.parser",
        "html", "html.parser",
        "hashlib", "webbrowser",
        "pyaudio",          # optional — AudioPlayer tries to import this at runtime
    ],
    hookspath=["."],
    runtime_hooks=["hook_ffmpeg.py"] if os.path.exists("hook_ffmpeg.py") else [],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_upx_exclude = ["*.npz", "*.tiktoken"]
if IS_WIN:
    _upx_exclude += [
        "vcruntime140.dll", "vcruntime140_1.dll",
        "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll",
        "python3*.dll",
        "torch*.dll", "c10.dll", "libiomp*.dll", "mkl*.dll", "fbgemm.dll",
        "ffmpeg.exe", "ffprobe.exe",
    ]
else:
    _upx_exclude += ["torch*.so", "libiomp*.so", "ffmpeg", "ffprobe"]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="QuickTitles",
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=_upx_exclude,
    runtime_tmpdir=None,
    console=False,          # no console window — keep False for a GUI app
    icon=_icon_file,
    uac_admin=False,
)

# macOS: wrap the exe in a proper .app bundle
if IS_MAC:
    app = BUNDLE(
        exe,
        name="QuickTitles.app",
        icon="icon.png" if os.path.exists("icon.png") else None,
        bundle_identifier="com.quicktitles.app",
        info_plist={
            "CFBundleName":               "QuickTitles",
            "CFBundleDisplayName":        "QuickTitles",
            "CFBundleVersion":            "1.0.0",
            "CFBundleShortVersionString": "1.0",
            "NSHighResolutionCapable":    True,
            "LSMinimumSystemVersion":     "10.14",
        },
    )
