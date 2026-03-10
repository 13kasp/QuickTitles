"""
QuickTitles — Whisper transcription and transcript processing.
"""

import os
import subprocess
import time
from typing import Optional

from PIL import ImageFont

from config import CFG, _EPSILON, _MAX_GAP_BRIDGE
from utils import _dlog, _quiet_io, log, fmt_time
from core.ffmpeg import _NO_WINDOW, _probe_video
from rendering.layout import split_into_lines


# ---------------------------------------------------------------------------
# Whisper device detection

_WHISPER_DEVICE: Optional[str] = None


def _detect_whisper_device() -> str:
    """Return 'cuda' if a CUDA-capable GPU is available for Whisper, else 'cpu'."""
    try:
        import torch
        if torch.cuda.is_available():
            log("GPU detected — Whisper will use CUDA for transcription")
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def get_whisper_device() -> str:
    global _WHISPER_DEVICE
    if _WHISPER_DEVICE is None:
        _WHISPER_DEVICE = _detect_whisper_device()
    return _WHISPER_DEVICE


# ---------------------------------------------------------------------------
# Transcript helpers

def _apply_word_case(word: str) -> str:
    """Apply the configured capitalisation to a single word."""
    case = CFG.get("WORD_CASE", "default")
    if case == "upper":  return word.upper()
    if case == "title":  return word.capitalize()
    if case == "lower":  return word.lower()
    return word


def get_word_chunks(segments: list, font=None, video_width: int = 1920) -> list:
    """
    Split transcript segments into display chunks.

    CHUNK_MODE == "words"  — groups exactly MAX_WORDS words per chunk.
    CHUNK_MODE == "lines"  — fills MAX_LINES lines per chunk (needs font + video_width).
    """
    mode = CFG.get("CHUNK_MODE", "words")

    if mode == "lines" and font is not None:
        max_lines = max(1, int(CFG.get("MAX_LINES", 2)))
        max_w     = int(video_width * CFG["MAX_WIDTH_RATIO"])

        def _words_for_lines(word_list: list) -> int:
            lo, hi = 1, len(word_list)
            best   = 1
            while lo <= hi:
                mid = (lo + hi) // 2
                dummy = [{"word": w if isinstance(w, str) else w["word"]} for w in word_list[:mid]]
                n_lines = len(split_into_lines(dummy, font, max_w))
                if n_lines <= max_lines:
                    best = mid; lo = mid + 1
                else:
                    hi = mid - 1
            return best

        chunks = []
        for seg in segments:
            words = seg.get("words", [])
            if words:
                i = 0
                while i < len(words):
                    remaining = words[i:]
                    n = max(1, _words_for_lines(remaining))
                    cw = words[i:i + n]
                    chunks.append({
                        "words": [{"word": _apply_word_case(w["word"].strip()), "start": w["start"], "end": w["end"]} for w in cw],
                        "start": cw[0]["start"],
                        "end":   cw[-1]["end"],
                    })
                    i += n
            else:
                word_list = seg["text"].strip().split()
                duration  = seg["end"] - seg["start"]
                dummy_words = [{"word": w} for w in word_list]
                i = 0
                while i < len(word_list):
                    n = max(1, _words_for_lines(dummy_words[i:]))
                    chunk = word_list[i:i + n]
                    s  = seg["start"] + (i / len(word_list)) * duration
                    e  = seg["start"] + (min(i + n, len(word_list)) / len(word_list)) * duration
                    wd = (e - s) / len(chunk)
                    chunks.append({
                        "words": [{"word": _apply_word_case(w), "start": s + j * wd, "end": s + (j + 1) * wd}
                                  for j, w in enumerate(chunk)],
                        "start": s, "end": e,
                    })
                    i += n
        return chunks

    # ---- default "words" mode ----
    max_words = CFG["MAX_WORDS"]
    chunks = []
    for seg in segments:
        words = seg.get("words", [])
        if words:
            for i in range(0, len(words), max_words):
                cw = words[i:i + max_words]
                chunks.append({
                    "words": [{"word": _apply_word_case(w["word"].strip()), "start": w["start"], "end": w["end"]} for w in cw],
                    "start": cw[0]["start"],
                    "end":   cw[-1]["end"],
                })
        else:
            word_list = seg["text"].strip().split()
            duration  = seg["end"] - seg["start"]
            for i in range(0, len(word_list), max_words):
                chunk = word_list[i:i + max_words]
                s  = seg["start"] + (i / len(word_list)) * duration
                e  = seg["start"] + (min(i + max_words, len(word_list)) / len(word_list)) * duration
                wd = (e - s) / len(chunk)
                chunks.append({
                    "words": [{"word": _apply_word_case(w), "start": s + j * wd, "end": s + (j + 1) * wd}
                              for j, w in enumerate(chunk)],
                    "start": s, "end": e,
                })
    return chunks


def normalise_timestamps(chunks: list) -> list:
    if not chunks:
        return chunks
    out = []
    for chunk in chunks:
        words, c_start, c_end = chunk["words"], chunk["start"], chunk["end"]
        raw_durs = [max(w["end"] - w["start"], _EPSILON) for w in words]
        total    = sum(raw_durs)
        cursor   = c_start
        new_words = []
        for w, d in zip(words, raw_durs):
            span = (d / total) * (c_end - c_start)
            new_words.append({"word": w["word"], "start": cursor, "end": cursor + span})
            cursor += span
        new_words[-1]["end"] = c_end
        out.append({"words": new_words, "start": c_start, "end": c_end})

    for i in range(len(out) - 1):
        gap = out[i + 1]["start"] - out[i]["end"]
        if gap == 0:
            continue
        if abs(gap) < _MAX_GAP_BRIDGE or gap < 0:
            mid = (out[i]["end"] + out[i + 1]["start"]) / 2
            out[i]["words"][-1]["end"]      = mid
            out[i]["end"]                   = mid
            out[i + 1]["words"][0]["start"] = mid
            out[i + 1]["start"]             = mid
    return out


# ---------------------------------------------------------------------------
# High-level transcription step

def transcribe_file(input_path: str, model) -> tuple:
    """Step 1 — extract audio and run Whisper. Returns (chunks, audio_path, video_meta)."""
    out_dir = CFG["OUTPUT_FOLDER"]
    tmp_dir = os.path.join(out_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    ffmpeg_bin = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    log(f"File: {os.path.basename(input_path)}  ·  path: {input_path}")

    log("Probing video…", 0.0)
    meta         = _probe_video(input_path)
    video_w      = meta["w"]
    video_h      = meta["h"]
    fps          = meta["fps"]
    duration     = meta["duration"]
    total_frames = meta["total_frames"]

    size_mb = os.path.getsize(input_path) / 1024 / 1024
    log(f"Video  {video_w}×{video_h}  ·  {int(duration//60)}m {int(duration%60)}s  ·  {fps:.2f} fps  ·  {size_mb:.1f} MB  ·  {total_frames} frames", 0.02)

    log(f"Extracting audio  ·  ffmpeg: {ffmpeg_bin}  ·  output: {os.path.basename(tmp_dir)}/audio.wav", 0.04)
    t0         = time.time()
    audio_path = os.path.join(tmp_dir, "audio.wav")
    extract_result = subprocess.run(
        [ffmpeg_bin, "-y", "-loglevel", "error",
         "-i", input_path,
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
         audio_path],
        capture_output=True, text=True,
        creationflags=_NO_WINDOW,
    )
    if extract_result.returncode != 0:
        log(f"ERROR  ffmpeg stderr: {extract_result.stderr[:300]}")
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{extract_result.stderr}")
    audio_mb = os.path.getsize(audio_path) / 1024 / 1024 if os.path.exists(audio_path) else 0
    log(f"Audio extracted  ·  {audio_mb:.1f} MB  ·  {fmt_time(int(time.time() - t0))}", 0.07)

    device = get_whisper_device()
    log(f"Transcribing with Whisper…  ·  device={device}", 0.08)
    t0 = time.time()
    with _quiet_io():
        result = model.transcribe(audio_path, word_timestamps=True, verbose=None)
    segments = result.get("segments", [])

    _chunk_font = None
    if CFG.get("CHUNK_MODE", "words") == "lines":
        try:
            _chunk_font = ImageFont.truetype(CFG["FONT_PATH"], CFG["FONT_SIZE"])
        except Exception:
            _chunk_font = None
    chunks       = normalise_timestamps(get_word_chunks(segments, font=_chunk_font, video_width=video_w))
    total_words  = sum(len(c["words"]) for c in chunks)
    detected_lang = result.get("language", "unknown")
    log(f"Transcribed  ·  lang={detected_lang}  ·  {len(segments)} segments  ·  {len(chunks)} groups  ·  {total_words} words  ·  {fmt_time(int(time.time() - t0))}", 0.15)
    if total_words == 0:
        log("WARNING  No words detected — audio may be silent or unsupported language")

    video_meta = {"w": video_w, "h": video_h, "fps": fps, "total_frames": total_frames}
    return chunks, audio_path, video_meta
