"""
QuickTitles — ffmpeg GPU detection, encoder args, probing, and encode pipeline.
"""

import os
import re
import shlex
import subprocess
import time
from typing import Iterator

import numpy as np

from config import CFG
from utils import _dlog, log, log_progress

# Suppress console windows on Windows when spawning child processes.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _detect_gpu() -> bool:
    """Return True if h264_nvenc is available."""
    try:
        ffmpeg_bin = os.environ.get("FFMPEG_BINARY", "ffmpeg")
        result = subprocess.run(
            [ffmpeg_bin, "-encoders"], capture_output=True, text=True, timeout=5,
            creationflags=_NO_WINDOW,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


_HAS_NVENC: bool = _detect_gpu()


def _build_encoder_args() -> list[str]:
    """Build encoder args from current CFG values."""
    if _HAS_NVENC:
        args = [
            "-c:v", "h264_nvenc",
            "-preset", str(CFG.get("ENCODE_PRESET_NVENC", "p7")),
            "-rc", "vbr",
            "-cq", str(CFG.get("ENCODE_CQ_NVENC", 17)),
            "-b:v", "0",
            "-maxrate", str(CFG.get("ENCODE_MAXRATE", "50M")),
            "-bufsize", str(CFG.get("ENCODE_BUFSIZE", "100M")),
            "-profile:v", "high", "-bf", "2", "-g", "60",
        ]
    else:
        args = [
            "-c:v", "libx264",
            "-preset", str(CFG.get("ENCODE_PRESET_X264", "fast")),
            "-crf", str(CFG.get("ENCODE_CRF", 18)),
        ]
    extra = str(CFG.get("ENCODE_EXTRA_FLAGS", "")).strip()
    if extra:
        args += shlex.split(extra)
    return args


def _probe_video(input_path: str) -> dict:
    """Use ffprobe to get video width, height, fps, duration. No moviepy needed."""
    ffmpeg_bin = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    ffprobe_bin = (
        os.path.join(os.path.dirname(ffmpeg_bin), "ffprobe.exe" if os.name == "nt" else "ffprobe")
        if os.path.isabs(ffmpeg_bin) else "ffprobe"
    )
    if not os.path.exists(ffprobe_bin):
        ffprobe_bin = "ffprobe"

    try:
        r = subprocess.run(
            [ffprobe_bin, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,duration",
             "-of", "csv=p=0", input_path],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        parts = r.stdout.strip().split(",")
        w, h  = int(parts[0]), int(parts[1])
        num, den = parts[2].split("/")
        fps  = float(num) / float(den)
        dur  = float(parts[3])
    except Exception:
        r2 = subprocess.run(
            [ffmpeg_bin, "-i", input_path],
            capture_output=True, text=True,
            creationflags=_NO_WINDOW,
        )
        m_res = re.search(r"(\d{2,5})x(\d{2,5})", r2.stderr)
        m_fps = re.search(r"(\d+(?:\.\d+)?) fps", r2.stderr)
        m_dur = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r2.stderr)
        w   = int(m_res.group(1)) if m_res else 1920
        h   = int(m_res.group(2)) if m_res else 1080
        fps = float(m_fps.group(1)) if m_fps else 30.0
        dur = 0.0
        if m_dur:
            dur = int(m_dur.group(1))*3600 + int(m_dur.group(2))*60 + float(m_dur.group(3))
    return {"w": w, "h": h, "fps": fps, "duration": dur, "total_frames": int(dur * fps)}


def render_with_ffmpeg(
    input_path: str,
    output_path: str,
    frame_iter: Iterator[np.ndarray],
    fps: float,
    video_width: int,
    video_height: int,
    total_frames: int,
) -> float:
    encoder_args = _build_encoder_args()
    audio_br     = str(CFG.get("ENCODE_AUDIO_BITRATE", "320k"))
    ffmpeg_bin   = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    cmd = [ffmpeg_bin, "-y", "-loglevel", "error"]
    if _HAS_NVENC:
        cmd += ["-hwaccel", "cuda"]
    cmd += [
        "-i", input_path,
        "-f", "rawvideo", "-pixel_format", "rgba",
        "-video_size", f"{video_width}x{video_height}",
        "-framerate", str(fps), "-i", "pipe:0",
        "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[vout]",
        "-map", "[vout]", "-map", "0:a",
        *encoder_args,
        "-c:a", "aac", "-b:a", audio_br, output_path,
    ]
    log(f"ffmpeg cmd: {' '.join(cmd[:6])} …  encoder: {encoder_args[1] if len(encoder_args) > 1 else '?'}")
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=_NO_WINDOW,
    )
    t0          = time.time()
    last_report = time.time()
    for i, frame_rgba in enumerate(frame_iter):
        proc.stdin.write(frame_rgba.tobytes())
        if time.time() - last_report >= 0.5:
            elapsed = time.time() - t0
            log_progress("Encoding", i + 1, total_frames, elapsed,
                         pct=0.65 + 0.33 * ((i + 1) / total_frames))
            last_report = time.time()
    proc.stdin.close()
    proc.wait()
    elapsed = time.time() - t0
    if proc.returncode != 0:
        stderr_out = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        log(f"ERROR  ffmpeg exited with code {proc.returncode}  ·  {stderr_out[:300]}")
    else:
        if os.path.exists(output_path):
            out_mb = os.path.getsize(output_path) / 1024 / 1024
            log(f"ffmpeg done  ·  output: {out_mb:.1f} MB  ·  returncode=0")
    return elapsed
