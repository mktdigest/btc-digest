#!/usr/bin/env python3
"""Two explanatory diagrams for the Guide and Evidence tabs.

1. img_divergence_types.png - the 2x2 grid: price makes one thing, RSI makes another. The table stays;
   this just removes the need to visualise it from words.
2. img_evidence_divergence.png - win rate and forward return for the four divergence variants, with the
   baseline drawn as a reference line, so the "only the oversold variant has an edge" claim is visible.

Numbers are read from the same EVIDENCE dict the tables print, so picture and table cannot disagree.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
BG = (13, 17, 23)
PANEL = (17, 22, 29)
LINE = (48, 56, 66)
TXT = (201, 209, 217)
DIM = (139, 148, 158)
PRICE = (190, 199, 209)
RSI = (88, 166, 255)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
AMBER = (210, 153, 34)

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONTS_B = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def font(size, bold=False):
    cands = FONTS_B if bold else FONTS
    for p in cands + FONTS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ---------------------------------------------------------------- diagram 1: the four types
def divergence_types(path, scale=2):
    W, H = 900 * scale, 580 * scale
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # price series (5 points) and rsi series, per type
    #                       price y values (higher = higher price on chart, we invert when drawing)
    types = [
        {
            "title": "Regular bullish",
            "sub": "lower low in price, higher low in RSI",
            "colour": GREEN,
            "price": [0.66, 0.36, 0.52, 0.18, 0.44],
            "rsi":   [0.30, 0.20, 0.34, 0.48, 0.56],
            "pivots": (1, 3),
        },
        {
            "title": "Regular bearish",
            "sub": "higher high in price, lower high in RSI",
            "colour": RED,
            "price": [0.28, 0.58, 0.44, 0.84, 0.60],
            "rsi":   [0.70, 0.80, 0.60, 0.50, 0.42],
            "pivots": (1, 3),
        },
        {
            "title": "Hidden bullish",
            "sub": "higher low in price, lower low in RSI",
            "colour": GREEN,
            "price": [0.50, 0.26, 0.42, 0.46, 0.68],
            "rsi":   [0.52, 0.44, 0.46, 0.18, 0.58],
            "pivots": (1, 3),
        },
        {
            "title": "Hidden bearish",
            "sub": "lower high in price, higher high in RSI",
            "colour": RED,
            "price": [0.58, 0.82, 0.60, 0.54, 0.32],
            "rsi":   [0.40, 0.52, 0.44, 0.82, 0.46],
            "pivots": (1, 3),
        },
    ]

    pw, ph = 405 * scale, 258 * scale
    origins = [(16 * scale, 16 * scale), (451 * scale, 16 * scale),
               (16 * scale, 296 * scale), (451 * scale, 296 * scale)]

    for t, (ox, oy) in zip(types, origins):
        d.rounded_rectangle([ox, oy, ox + pw, oy + ph], radius=10 * scale, fill=PANEL, outline=LINE)
        d.text((ox + 16 * scale, oy + 12 * scale), t["title"], font=font(15 * scale, True), fill=t["colour"])
        d.text((ox + 16 * scale, oy + 34 * scale), t["sub"], font=font(11 * scale), fill=DIM)

        inner_x = ox + 18 * scale
        inner_w = pw - 36 * scale

        # price band
        py0, pyh = oy + 76 * scale, 92 * scale
        # rsi band
        ry0, ryh = oy + 194 * scale, 48 * scale

        for band_y, band_h in ((py0, pyh), (ry0, ryh)):
            d.line([(inner_x, band_y + band_h), (inner_x + inner_w, band_y + band_h)],
                   fill=(30, 36, 44), width=1 * scale)

        def poly(vals, y0, h, colour, width):
            pts = []
            n = len(vals)
            for i, v in enumerate(vals):
                x = inner_x + inner_w * i / (n - 1)
                y = y0 + h * (1 - v)
                pts.append((x, y))
            d.line(pts, fill=colour, width=width, joint="curve")
            return pts

        ppts = poly(t["price"], py0, pyh, PRICE, 2 * scale)
        rpts = poly(t["rsi"], ry0, ryh, RSI, 2 * scale)

        # mark the two pivots on both lines
        for idx in t["pivots"]:
            for pts, colour in ((ppts, PRICE), (rpts, RSI)):
                x, y = pts[idx]
                r = 3.5 * scale
                d.ellipse([x - r, y - r, x + r, y + r], fill=BG, outline=colour, width=2 * scale)

        # the disagreement arrow between the two pivots
        a, b = t["pivots"]
        for pts, colour in ((ppts, PRICE), (rpts, RSI)):
            d.line([pts[a], pts[b]], fill=colour, width=1 * scale)

        d.text((inner_x, py0 - 15 * scale), "PRICE", font=font(9 * scale, True), fill=DIM)
        d.text((inner_x, ry0 - 15 * scale), "RSI", font=font(9 * scale, True), fill=DIM)

    img.save(path, optimize=True)
    return path


# ---------------------------------------------------------------- diagram 2: the evidence
def evidence_divergence(path, rows, scale=2):
    """rows: (label, n, forward, winrate) straight from EVIDENCE['divergence']."""
    W, H = 900 * scale, 340 * scale
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    parsed = []
    for label, n, fwd, win in rows:
        parsed.append((label.replace("&lt;", "<"), n, float(fwd.strip("%+")), float(win.strip("%"))))

    base_win = parsed[0][3]
    left, right = 300 * scale, W - 60 * scale
    top, row_h = 34 * scale, 58 * scale
    lo, hi = 40.0, 75.0

    def x_of(v):
        return left + (right - left) * (v - lo) / (hi - lo)

    # baseline reference line
    bx = x_of(base_win)
    d.line([(bx, top - 12 * scale), (bx, top + row_h * len(parsed))], fill=AMBER, width=2 * scale)
    d.text((bx + 8 * scale, top - 30 * scale), f"baseline {base_win:.0f}%",
           font=font(11 * scale, True), fill=AMBER)

    for i, (label, n, fwd, win) in enumerate(parsed):
        y = top + i * row_h
        colour = DIM if i == 0 else (RED if "Bearish divergence" == label else
                                     (GREEN if "RSI14" in label else (150, 160, 172)))
        d.text((28 * scale, y + 4 * scale), label, font=font(13 * scale, i > 0), fill=TXT)
        d.text((28 * scale, y + 24 * scale), f"n={n}", font=font(11 * scale), fill=DIM)

        bar_h = 20 * scale
        x1 = x_of(win)
        d.rounded_rectangle([left, y + 8 * scale, max(x1, left + 2 * scale), y + 8 * scale + bar_h],
                            radius=4 * scale, fill=colour)
        d.text((max(x1, left) + 8 * scale, y + 9 * scale), f"{win:.0f}% win  ·  {fwd:+.2f}% fwd",
               font=font(12 * scale, i > 0), fill=TXT if i else DIM)

    # axis ticks
    for v in (40, 50, 60, 70):
        x = x_of(v)
        d.line([(x, top - 6 * scale), (x, top + row_h * len(parsed))], fill=(28, 34, 42), width=1)
        d.text((x - 8 * scale, top + row_h * len(parsed) + 6 * scale), f"{v}%",
               font=font(10 * scale), fill=DIM)

    d.text((28 * scale, H - 22 * scale),
           "Forward return is the price change after the signal. On the bearish row price rose, "
           "so that signal failed.",
           font=font(11 * scale), fill=DIM)
    img.save(path, optimize=True)
    return path


if __name__ == "__main__":
    sys.path.insert(0, OUT)
    import build_site as bs

    p1 = divergence_types(os.path.join(OUT, "img_divergence_types.png"))
    p2 = evidence_divergence(os.path.join(OUT, "img_evidence_divergence.png"),
                             bs.EVIDENCE["divergence"])
    print("wrote", p1)
    print("wrote", p2)
