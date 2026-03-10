"""
QuickTitles — vector icon system drawn with PIL, cached as ImageTk.PhotoImage.
"""

import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from gui.theme import C

_icon_cache: dict = {}


def _rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _draw_icon(name: str, size: int, color: str) -> Image.Image:
    SCALE = 6
    R   = size * SCALE
    img = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img, "RGBA")
    c   = _rgb(color)
    mid = R / 2
    sw  = max(2, round(R * 0.115))
    p   = round(R * 0.08)

    if name == "play":
        d.polygon([(round(R*.20), round(R*.12)),
                   (round(R*.20), round(R*.88)),
                   (round(R*.84), mid)], fill=c)

    elif name == "pause":
        bw = round(R*.22); gap = round(R*.10)
        d.rectangle([round(mid-gap-bw), round(R*.12), round(mid-gap), round(R*.88)], fill=c)
        d.rectangle([round(mid+gap), round(R*.12), round(mid+gap+bw), round(R*.88)], fill=c)

    elif name == "stop":
        d.rectangle([p, p, R-p, R-p], fill=c)

    elif name == "refresh":
        r             = round(R * 0.35)
        arc_start_deg = 60
        arc_end_deg   = 60 + 270
        pts = [(mid + r*math.cos(math.radians(a - 90)),
                mid + r*math.sin(math.radians(a - 90))) for a in range(arc_start_deg, arc_end_deg + 1)]
        d.line(pts, fill=c, width=sw, joint="curve")
        end_rad = math.radians(arc_end_deg - 90)
        cx = mid + r * math.cos(end_rad);  cy = mid + r * math.sin(end_rad)
        tan_rad = end_rad + math.pi / 2;   perp = tan_rad + math.pi / 2
        aw = sw * 2.2;  hw = sw * 1.3
        tip_x = cx + aw*math.cos(tan_rad); tip_y = cy + aw*math.sin(tan_rad)
        bx1 = cx + hw*math.cos(perp);      by1 = cy + hw*math.sin(perp)
        bx2 = cx - hw*math.cos(perp);      by2 = cy - hw*math.sin(perp)
        d.polygon([(round(tip_x),round(tip_y)),(round(bx1),round(by1)),(round(bx2),round(by2))], fill=c)

    elif name == "check":
        pts = [(round(R*.12), round(R*.52)),
               (round(R*.40), round(R*.80)),
               (round(R*.88), round(R*.20))]
        d.line(pts, fill=c, width=sw, joint="curve")

    elif name in ("x_close", "x_small"):
        d.line([p, p, R-p, R-p], fill=c, width=sw)
        d.line([R-p, p, p, R-p], fill=c, width=sw)

    elif name == "reset":
        r             = round(R * 0.35)
        arc_start_deg = 120
        arc_end_deg   = 120 - 270
        pts = [(mid + r*math.cos(math.radians(a - 90)),
                mid + r*math.sin(math.radians(a - 90))) for a in range(arc_start_deg, arc_end_deg - 1, -1)]
        d.line(pts, fill=c, width=sw, joint="curve")
        end_rad = math.radians(arc_end_deg - 90)
        cx = mid + r * math.cos(end_rad);  cy = mid + r * math.sin(end_rad)
        tan_rad = end_rad - math.pi / 2;   perp = tan_rad + math.pi / 2
        aw = sw * 2.2;  hw = sw * 1.3
        tip_x = cx + aw*math.cos(tan_rad); tip_y = cy + aw*math.sin(tan_rad)
        bx1 = cx + hw*math.cos(perp);      by1 = cy + hw*math.sin(perp)
        bx2 = cx - hw*math.cos(perp);      by2 = cy - hw*math.sin(perp)
        d.polygon([(round(tip_x),round(tip_y)),(round(bx1),round(by1)),(round(bx2),round(by2))], fill=c)

    elif name == "plus":
        thick = round(sw * 1.0)
        d.rectangle([round(mid - thick/2), round(R*0.15), round(mid + thick/2), round(R*0.85)], fill=c)
        d.rectangle([round(R*0.15), round(mid - thick/2), round(R*0.85), round(mid + thick/2)], fill=c)

    elif name == "info":
        r  = round(R * .40)
        d.ellipse([mid-r, mid-r, mid+r, mid+r], outline=c, width=sw)
        dr = max(sw//2+1, round(R*.07)); dy = round(R*.28)
        d.ellipse([mid-dr, dy-dr, mid+dr, dy+dr], fill=c)
        d.line([round(mid), round(R*.43), round(mid), round(R*.73)], fill=c, width=sw)

    elif name == "queue":
        sx = round(mid)
        d.line([sx, round(R*.84), sx, round(R*.32)], fill=c, width=sw)
        aw = round(R * .28)
        d.polygon([(sx, round(R*.12)), (sx-aw//2, round(R*.36)), (sx+aw//2, round(R*.36))], fill=c)
        d.line([round(R*.18), round(R*.84), round(R*.82), round(R*.84)], fill=c, width=sw)

    elif name == "output":
        sx = round(mid)
        d.line([sx, round(R*.16), sx, round(R*.68)], fill=c, width=sw)
        aw = round(R * .28)
        d.polygon([(sx, round(R*.88)), (sx-aw//2, round(R*.64)), (sx+aw//2, round(R*.64))], fill=c)
        d.line([round(R*.18), round(R*.88), round(R*.82), round(R*.88)], fill=c, width=sw)

    elif name == "settings":
        teeth = 8; ro = round(R*.44); rm2 = round(R*.34); rh = round(R*.17)
        gear  = []
        for i in range(teeth * 2):
            a = math.radians(i * 360 / (teeth*2) - 90)
            r = ro if i % 2 == 0 else rm2
            gear.append((mid + r*math.cos(a), mid + r*math.sin(a)))
        d.polygon(gear, fill=c)
        hole = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        ImageDraw.Draw(hole).ellipse([mid-rh, mid-rh, mid+rh, mid+rh], fill=(0,0,0,255))
        img  = Image.composite(Image.new("RGBA", (R, R), (0,0,0,0)), img, hole.split()[3])
        return img.resize((size, size), Image.LANCZOS)

    elif name == "discord":
        bm = round(R * .06)
        d.rounded_rectangle([bm, round(R*.18), R-bm, R-bm], radius=round(R*.24), fill=c)
        er = round(R * .14)
        d.ellipse([round(R*.08), round(R*.04), round(R*.08)+er*2, round(R*.04)+er*2], fill=c)
        d.ellipse([R-round(R*.08)-er*2, round(R*.04), R-round(R*.08), round(R*.04)+er*2], fill=c)
        ew = round(R*.16); eh = round(R*.20)
        ex1 = round(R*.18); ex2 = round(R*.66); ey = round(R*.42)
        eyes = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        ed   = ImageDraw.Draw(eyes)
        ed.ellipse([ex1, ey, ex1+ew, ey+eh], fill=(0,0,0,255))
        ed.ellipse([ex2, ey, ex2+ew, ey+eh], fill=(0,0,0,255))
        img  = Image.composite(Image.new("RGBA", (R, R), (0,0,0,0)), img, eyes.split()[3])
        return img.resize((size, size), Image.LANCZOS)

    return img.resize((size, size), Image.LANCZOS)


def get_icon(name: str, size: int, color: str) -> ImageTk.PhotoImage:
    key = (name, size, color)
    if key not in _icon_cache:
        _icon_cache[key] = ImageTk.PhotoImage(_draw_icon(name, size, color))
    return _icon_cache[key]


def icon_lbl(parent, name: str, size: int, color: str, bg: str, **kw) -> tk.Label:
    """Create a tk.Label displaying a crisp antialiased vector icon."""
    photo = get_icon(name, size, color)
    lbl   = tk.Label(parent, image=photo, bg=bg, **kw)
    lbl._icon_ref = photo
    return lbl


def update_icon(widget: tk.Label, name: str, size: int, color: str):
    """Swap the displayed icon on an existing Label."""
    photo = get_icon(name, size, color)
    widget.configure(image=photo)
    widget._icon_ref = photo
