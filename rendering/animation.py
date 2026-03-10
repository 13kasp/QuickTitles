"""
QuickTitles — chunk pre-rendering, frame resolution, and frame iterator.
"""

import numpy as np

from config import CFG, _EPSILON, _LUT_SLOTS
from rendering.layout import compute_layout
from rendering.primitives import (
    make_drop_shadow_np, render_pill_np, composite_np,
    make_text_layer_np, stamp_text_layer,
)


# ---------------------------------------------------------------------------
# Easing functions

def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    p = -2 * t + 2
    return 1 - p * p * p / 2


# ---------------------------------------------------------------------------
# Pre-rendering

def prerender_chunk(chunk, font, ink_h, ink_top_offset, video_width, video_height):
    words     = chunk["words"]
    chunk_end = chunk["end"]
    lines, line_texts, line_widths, block_top, word_boxes = compute_layout(
        words, font, ink_h, ink_top_offset, video_width, video_height)

    shadow_np   = make_drop_shadow_np(line_texts, line_widths, block_top, ink_h, video_width, video_height) \
                  if CFG["ENABLE_DROP_SHADOW"] else None
    shadow_base = shadow_np.copy() if shadow_np is not None \
                  else np.zeros((video_height, video_width, 4), dtype=np.uint8)

    text_layer = make_text_layer_np(video_width, video_height, line_texts, line_widths,
                                    block_top, ink_h, ink_top_offset, font)

    def make_frame(box, scale=1.0):
        pill      = render_pill_np(video_width, video_height, box[0], box[1], box[2], box[3], pop_scale=scale)
        with_pill = composite_np(shadow_base, pill)
        return stamp_text_layer(with_pill, text_layer)

    hold_frame    = stamp_text_layer(shadow_base, text_layer)
    num_words     = len(words)
    word_schedule = []

    for wi, word in enumerate(words):
        w_start, w_end = word["start"], word["end"]
        w_dur    = max(w_end - w_start, _EPSILON)
        box      = word_boxes[wi]
        has_next = wi < num_words - 1
        use_slide = has_next and CFG["ENABLE_SLIDE_ANIMATION"] and CFG["ENABLE_HIGHLIGHT"]
        segments_frac = []

        # Pop animation
        pop_dur   = min(CFG["POP_DURATION"], w_dur * 0.5) if CFG["ENABLE_POP_ANIMATION"] and CFG["ENABLE_HIGHLIGHT"] else 0.0
        pop_frac  = pop_dur / w_dur
        if pop_frac > 0:
            for fi in range(CFG["POP_STEPS"]):
                t     = fi / max(CFG["POP_STEPS"] - 1, 1)
                scale = CFG["POP_SCALE_START"] - (CFG["POP_SCALE_START"] - 1.0) * ease_out_cubic(t)
                segments_frac.append((pop_frac / CFG["POP_STEPS"], make_frame(box, scale)))

        # Steady hold
        trans_dur   = min(CFG["TRANSITION_DURATION"], w_dur * 0.4) if use_slide else 0.0
        trans_frac  = trans_dur / w_dur
        steady_frac = max(1.0 - pop_frac - trans_frac, 0.0)
        if steady_frac > _EPSILON:
            segments_frac.append((steady_frac, make_frame(box, 1.0)))

        # Slide transition
        if trans_frac > 0:
            next_box   = word_boxes[wi + 1]
            raw_frames = []
            for fi in range(CFG["TRANSITION_STEPS"]):
                t  = fi / max(CFG["TRANSITION_STEPS"] - 1, 1)
                et = ease_in_out_cubic(t)
                interp = (
                    box[0] + (next_box[0] - box[0]) * et, box[1] + (next_box[1] - box[1]) * et,
                    box[2] + (next_box[2] - box[2]) * et, box[3] + (next_box[3] - box[3]) * et,
                )
                raw_frames.append(make_frame(interp, 1.0))

            if CFG["ENABLE_MOTION_BLUR"] and CFG["MOTION_BLUR_STRENGTH"] > 0:
                half    = CFG["MOTION_BLUR_STRENGTH"]
                blurred = [
                    np.mean(raw_frames[max(0, fi - half):min(CFG["TRANSITION_STEPS"], fi + half + 1)], axis=0).astype(np.uint8)
                    for fi in range(CFG["TRANSITION_STEPS"])
                ]
            else:
                blurred = raw_frames

            for frame in blurred:
                segments_frac.append((trans_frac / CFG["TRANSITION_STEPS"], frame))

        # Build phase→frame LUT
        unique_frames = [f for _, f in segments_frac]
        fracs         = [frac for frac, _ in segments_frac]
        phase_to_idx  = np.empty(_LUT_SLOTS, dtype=np.int16)
        seg_idx, cursor = 0, 0.0
        for slot in range(_LUT_SLOTS):
            while seg_idx < len(fracs) - 1 and (slot / _LUT_SLOTS) >= cursor + fracs[seg_idx]:
                cursor += fracs[seg_idx]; seg_idx += 1
            phase_to_idx[slot] = seg_idx

        word_schedule.append({
            "start": w_start, "end": w_end,
            "unique_frames": unique_frames,
            "phase_to_idx":  phase_to_idx,
            "hold_frame":    hold_frame,
        })

    shadow_hold = None
    if CFG["ENABLE_DROP_SHADOW"] and CFG["DROP_SHADOW_HOLD"] > 0 and word_schedule:
        shadow_hold = {"start": chunk_end, "end": chunk_end + CFG["DROP_SHADOW_HOLD"], "hold_frame": hold_frame}

    return word_schedule, shadow_hold


# ---------------------------------------------------------------------------
# Frame resolution

def _resolve_frame(t, all_words, all_holds, blank, w_starts, w_ends, h_starts, h_ends):
    idx = int(np.searchsorted(w_starts, t, side="right")) - 1
    if idx >= 0 and t < w_ends[idx]:
        word  = all_words[idx]
        phase = max(0.0, min((t - word["start"]) / max(word["end"] - word["start"], _EPSILON), 1.0 - _EPSILON))
        fi    = int(word["phase_to_idx"][min(int(phase * _LUT_SLOTS), _LUT_SLOTS - 1)])
        return word["unique_frames"][fi]
    if h_starts is not None:
        idx = int(np.searchsorted(h_starts, t, side="right")) - 1
        if idx >= 0 and t < h_ends[idx]:
            return all_holds[idx]["hold_frame"]
    return blank


def iter_frames(all_schedules, all_shadow_holds, total_frames, fps, video_width, video_height):
    blank     = np.zeros((video_height, video_width, 4), dtype=np.uint8)
    all_words = sorted([w for s in all_schedules for w in s], key=lambda w: w["start"])
    all_holds = sorted([h for h in all_shadow_holds if h is not None], key=lambda h: h["start"])
    if not all_words:
        for _ in range(total_frames):
            yield blank
        return

    w_starts = np.array([w["start"] for w in all_words], dtype=np.float64)
    w_ends   = np.array([w["end"]   for w in all_words], dtype=np.float64)
    h_starts = np.array([h["start"] for h in all_holds], dtype=np.float64) if all_holds else None
    h_ends   = np.array([h["end"]   for h in all_holds], dtype=np.float64) if all_holds else None

    for i in range(total_frames):
        yield _resolve_frame(i / fps, all_words, all_holds, blank, w_starts, w_ends, h_starts, h_ends)
