"""
QuickTitles — text measurement, word-wrap, and layout computation.
"""

import numpy as np
from PIL import Image, ImageDraw

from config import CFG

# Shared dummy draw for text measurement (avoid repeated object creation)
_MEASURE_IMG  = Image.new("RGBA", (1, 1))
_MEASURE_DRAW = ImageDraw.Draw(_MEASURE_IMG)


def _bbox_w(text: str, font) -> int:
    b = _MEASURE_DRAW.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def get_ink_metrics(font) -> tuple[int, int]:
    ref = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    b   = _MEASURE_DRAW.textbbox((0, 0), ref, font=font)
    w, h = b[2] - b[0] + 4, b[3] - b[1] + 4
    img  = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((-b[0] + 2, -b[1] + 2), ref, font=font, fill=255)
    arr  = np.array(img)
    rows = np.any(arr > 10, axis=1)
    top, bottom = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))

    cap_ref = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    bc  = _MEASURE_DRAW.textbbox((0, 0), cap_ref, font=font)
    wc, hc = bc[2] - bc[0] + 4, bc[3] - bc[1] + 4
    img_c  = Image.new("L", (wc, hc), 0)
    ImageDraw.Draw(img_c).text((-bc[0] + 2, -bc[1] + 2), cap_ref, font=font, fill=255)
    arr_c    = np.array(img_c)
    rows_c   = np.any(arr_c > 10, axis=1)
    cap_top  = int(np.argmax(rows_c))
    cap_bottom = int(len(rows_c) - 1 - np.argmax(rows_c[::-1]))

    font._pill_cap_top    = cap_top    - top + 2
    font._pill_cap_bottom = cap_bottom - top + 2

    return bottom - top + 1, top - 2


def split_into_lines(words: list, font, max_width: int) -> list:
    """
    Greedy word-wrap: pack words left-to-right, starting a new line when adding
    the next word would exceed max_width.
    """
    if not words:
        return []
    lines: list = []
    current_line: list = []
    for w in words:
        candidate = current_line + [w]
        candidate_text = " ".join(ww["word"] for ww in candidate)
        if _bbox_w(candidate_text, font) <= max_width:
            current_line = candidate
        else:
            if current_line:
                lines.append(current_line)
            current_line = [w]
    if current_line:
        lines.append(current_line)
    return lines if lines else [words]


def word_offsets_in_line(line_words: list, font) -> tuple[list, list]:
    offsets, widths = [], []
    for i, w in enumerate(line_words):
        prefix_w = 0
        if i > 0:
            pb = _MEASURE_DRAW.textbbox((0, 0), " ".join(ww["word"] for ww in line_words[:i]) + " ", font=font)
            prefix_w = pb[2] - pb[0]
        wb = _MEASURE_DRAW.textbbox((0, 0), w["word"], font=font)
        offsets.append(prefix_w); widths.append(wb[2] - wb[0])
    return offsets, widths


def compute_layout(words, font, ink_h, ink_top_offset, video_width, video_height):
    max_w       = int(video_width * CFG["MAX_WIDTH_RATIO"])
    lines       = split_into_lines(words, font, max_w)
    line_texts  = [" ".join(w["word"] for w in line) for line in lines]
    line_widths = [_bbox_w(t, font) for t in line_texts]
    num_lines   = len(lines)
    total_block_h = ink_h * num_lines + CFG["LINE_SPACING"] * (num_lines - 1)
    center_y    = int(video_height * CFG["VERTICAL_POSITION"])
    block_top   = center_y - total_block_h // 2
    cap_top    = getattr(font, "_pill_cap_top",    0)
    cap_bottom = getattr(font, "_pill_cap_bottom", ink_h)
    nudge      = CFG["INK_VERTICAL_NUDGE"]
    word_boxes  = []
    for li, line in enumerate(lines):
        text_x     = (video_width - line_widths[li]) // 2
        ink_y      = block_top + li * (ink_h + CFG["LINE_SPACING"])
        offs, wids = word_offsets_in_line(line, font)
        for j in range(len(line)):
            word_boxes.append((
                text_x + offs[j],
                ink_y + cap_top  + nudge,
                text_x + offs[j] + wids[j],
                ink_y + cap_bottom + nudge,
            ))
    return lines, line_texts, line_widths, block_top, word_boxes
