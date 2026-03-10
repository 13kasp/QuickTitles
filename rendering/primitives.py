"""
QuickTitles — numpy/PIL rendering primitives (pill, shadow, text layer, compositing).
"""

import numpy as np
from PIL import Image, ImageDraw

from config import CFG


def make_drop_shadow_np(line_texts, line_widths, block_top, ink_h, video_width, video_height) -> np.ndarray:
    num_lines     = len(line_texts)
    total_block_h = ink_h * num_lines + CFG["LINE_SPACING"] * (num_lines - 1)
    cx     = video_width  / 2.0
    cy     = block_top + total_block_h / 2.0
    half_w = max(line_widths) / 2.0
    half_h = total_block_h   / 2.0
    spread = float(CFG["DROP_SHADOW_SPREAD"])
    ys = np.arange(video_height, dtype=np.float32)
    xs = np.arange(video_width,  dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    nx    = (gx - cx) / (half_w + spread)
    ny    = (gy - cy) / (half_h + spread)
    alpha = CFG["DROP_SHADOW_OPACITY"] * np.exp(-0.5 * (nx * nx + ny * ny))
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)
    rgba          = np.zeros((video_height, video_width, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return rgba


def render_pill_np(video_width, video_height, box_x1, box_y1, box_x2, box_y2, pop_scale=1.0) -> np.ndarray:
    out = np.zeros((video_height, video_width, 4), dtype=np.uint8)
    if not CFG["ENABLE_HIGHLIGHT"]:
        return out
    cx     = (box_x1 + box_x2) / 2
    cy     = (box_y1 + box_y2) / 2
    half_w = (box_x2 - box_x1) / 2 * pop_scale + CFG["HIGHLIGHT_PADDING_X"]
    half_h = (box_y2 - box_y1) / 2 * pop_scale + CFG["HIGHLIGHT_PADDING_Y"]
    x1 = round(cx - half_w);  y1 = round(cy - half_h)
    x2 = round(cx + half_w);  y2 = round(cy + half_h)
    cx1 = max(0, x1);  cy1 = max(0, y1)
    cx2 = min(video_width, x2);  cy2 = min(video_height, y2)
    if cx2 <= cx1 or cy2 <= cy1:
        return out
    pw, ph = cx2 - cx1, cy2 - cy1
    crop = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(crop).rounded_rectangle(
        [x1 - cx1, y1 - cy1, x2 - cx1 - 1, y2 - cy1 - 1],
        radius=CFG["HIGHLIGHT_CORNER_RADIUS"], fill=CFG["HIGHLIGHT_COLOR"],
    )
    out[cy1:cy2, cx1:cx2] = np.array(crop)
    return out


def composite_np(base: np.ndarray, pill: np.ndarray) -> np.ndarray:
    pill_alpha = pill[:, :, 3]
    rows = np.any(pill_alpha > 0, axis=1)
    if not rows.any():
        return base.copy()
    out = base.copy()
    r0, r1 = np.where(rows)[0][[0, -1]]
    cols = np.any(pill_alpha[r0:r1+1, :] > 0, axis=0)
    c0, c1 = np.where(cols)[0][[0, -1]]
    src = pill[r0:r1+1, c0:c1+1].astype(np.float32) / 255.0
    dst = base[r0:r1+1, c0:c1+1].astype(np.float32) / 255.0
    a_s   = src[:, :, 3:4];  a_d = dst[:, :, 3:4]
    a_out = a_s + a_d * (1.0 - a_s)
    safe  = np.where(a_out > 0, a_out, 1.0)
    c_out = (src[:, :, :3] * a_s + dst[:, :, :3] * a_d * (1.0 - a_s)) / safe
    region           = out[r0:r1+1, c0:c1+1]
    region[:, :, :3] = np.clip(c_out * 255, 0, 255).astype(np.uint8)
    region[:, :, 3]  = np.clip(a_out[:, :, 0] * 255, 0, 255).astype(np.uint8)
    return out


def make_text_layer_np(video_width, video_height, line_texts, line_widths,
                       block_top, ink_h, ink_top_offset, font) -> np.ndarray:
    """Pre-render just the text (no background) as an RGBA numpy array."""
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)
    for li, text in enumerate(line_texts):
        tx = (video_width - line_widths[li]) // 2
        ty = block_top + li * (ink_h + CFG["LINE_SPACING"]) - ink_top_offset
        draw.text((tx, ty), text, font=font, fill=CFG["TEXT_COLOR"])
    return np.array(canvas)


def stamp_text_layer(base_np: np.ndarray, text_layer: np.ndarray) -> np.ndarray:
    """Composite a pre-rendered text layer (RGBA) onto base_np using alpha-over."""
    out  = base_np.copy()
    rows = np.any(text_layer[:, :, 3] > 0, axis=1)
    if not rows.any():
        return out
    r0, r1 = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    src = text_layer[r0:r1+1].astype(np.float32) / 255.0
    dst = base_np[r0:r1+1].astype(np.float32) / 255.0
    a_s = src[:, :, 3:4];  a_d = dst[:, :, 3:4]
    a_out = a_s + a_d * (1.0 - a_s)
    safe  = np.where(a_out > 0, a_out, 1.0)
    c_out = (src[:, :, :3] * a_s + dst[:, :, :3] * a_d * (1.0 - a_s)) / safe
    region = out[r0:r1+1]
    region[:, :, :3] = np.clip(c_out * 255, 0, 255).astype(np.uint8)
    region[:, :, 3]  = np.clip(a_out[:, :, 0] * 255, 0, 255).astype(np.uint8)
    return out
