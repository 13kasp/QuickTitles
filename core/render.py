"""
QuickTitles — high-level render pipeline (step 2).
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import ImageFont

from config import CFG
from utils import log, log_progress, fmt_time, _dlog
from core.ffmpeg import _HAS_NVENC, render_with_ffmpeg
from rendering.layout import get_ink_metrics
from rendering.animation import prerender_chunk, iter_frames


def render_file(input_path: str, chunks: list, audio_path: str, video_meta: dict) -> str:
    """Step 2 — pre-render frames and encode. chunks may have been edited by the user."""
    out_dir      = CFG["OUTPUT_FOLDER"]
    output_path  = os.path.join(out_dir, f"sub_{os.path.basename(input_path)}")
    video_w, video_h = video_meta["w"], video_meta["h"]
    fps          = video_meta["fps"]
    total_frames = video_meta["total_frames"]

    log(f"Render start  ·  output: {os.path.basename(output_path)}")
    log(f"Font: {os.path.basename(CFG['FONT_PATH'])}  ·  size: {CFG['FONT_SIZE']}  ·  encoder: {'nvenc' if _HAS_NVENC else 'x264'}")
    try:
        font = ImageFont.truetype(CFG["FONT_PATH"], CFG["FONT_SIZE"])
    except Exception as e:
        log(f"ERROR  Failed to load font '{CFG['FONT_PATH']}': {e}")
        raise
    ink_h, ink_top_offset = get_ink_metrics(font)

    log(f"Pre-rendering subtitles  ·  {CFG['RENDER_THREADS']} threads  ·  {len(chunks)} chunks…", 0.18)
    t0               = time.time()
    all_schedules    = [None] * len(chunks)
    all_shadow_holds = [None] * len(chunks)
    completed        = [0]

    def _render_task(args):
        idx, chunk = args
        sched, hold = prerender_chunk(chunk, font, ink_h, ink_top_offset, video_w, video_h)
        return idx, sched, hold

    with ThreadPoolExecutor(max_workers=CFG["RENDER_THREADS"]) as ex:
        futures = {ex.submit(_render_task, (i, c)): i for i, c in enumerate(chunks)}
        for future in as_completed(futures):
            idx, sched, hold      = future.result()
            all_schedules[idx]    = sched
            all_shadow_holds[idx] = hold
            completed[0]         += 1
            log_progress("Pre-rendering", completed[0], len(chunks),
                         time.time() - t0,
                         pct=0.18 + 0.42 * (completed[0] / len(chunks)))

    total_unique = sum(sum(len(w["unique_frames"]) for w in s) for s in all_schedules)
    log(f"Pre-render done  ·  {total_unique} unique frames  ·  {fmt_time(int(time.time() - t0))}", 0.61)

    log("Encoding…", 0.65)
    frames = iter_frames(all_schedules, all_shadow_holds, total_frames, fps, video_w, video_h)

    try:
        encode_time = render_with_ffmpeg(input_path, output_path, frames, fps, video_w, video_h, total_frames)
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

    avg_fps = total_frames / encode_time if encode_time > 0 else 0
    log(f"Done  ·  {avg_fps:.1f} fps encode  ·  total encode {fmt_time(int(encode_time))}", 1.0)
    return output_path
