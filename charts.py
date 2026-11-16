"""Chart renderer for the digest page. PIL only - matplotlib is NOT installed here.

Everything is fed from the digest's series dump so charts never re-fetch a rate-limited
source. Every chart returns its LIVE NUMBERS and a plain-English "how to use this", because
a chart whose values you cannot read is decoration.

Charts are rendered at roughly the width the page displays them, so label text keeps its
apparent size instead of being scaled down into illegibility.
"""
import json
import math
import os
import statistics
import urllib.request

from PIL import Image, ImageDraw, ImageFont

BG = (13, 17, 23)
GRID = (44, 51, 60)
FG = (230, 237, 243)
DIM = (154, 163, 175)
ACC = (88, 166, 255)
UP = (63, 185, 80)
DN = (248, 81, 73)
AMBER = (210, 153, 34)
PUR = (188, 140, 255)
TEAL = (57, 197, 187)
WHITE = (255, 255, 255)

W, H = 1120, 400                      # near 1:1 with the page's display width
_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_CACHE = {}


def _font(size=17, bold=False):
    key = (size, bold)
    if key in _CACHE:
        return _CACHE[key]
    cands = [p for p in _FONTS if (("Bold" in p) == bold)] or _FONTS
    for p in cands + _FONTS:
        try:
            f = ImageFont.truetype(p, size)
            _CACHE[key] = f
            return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _CACHE[key] = f
    return f


def _fmt(v):
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.0f}M"
    if a >= 1e3:
        return f"{v / 1e3:,.0f}k"
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.1f}"
    # Below 1, %.2f collapsed funding rates (~0.002-0.01) into duplicate "0.00" / "-0.01" axis
    # labels. %g keeps significant digits instead, so small values stay distinct and readable.
    return f"{v:.4g}"


def _usd(v, suffix="B", dec=2, sign=True):
    """Money with the sign BEFORE the symbol: -2245 -> '-$2.25B'.

    The old form f"${v:+,.0f}m" printed "$-2,245m" - a minus stranded after the dollar sign.
    It reads like a typo and buries the scale letter at the end of a long number.

    sign=False for prose where the verb already carries the direction ("fell $0.44B",
    "has come out $2.25B") - otherwise the minus makes it a double negative.
    """
    sgn = ("-" if v < 0 else "+") if sign else ""
    return f"{sgn}${abs(v):,.{dec}f}{suffix}"


def _rank_name(p):
    """A percentile in plain words. '87th pctile' is meaningless to anyone who has not met one."""
    if p >= 95:
        return "the highest in 30 days"
    if p >= 85:
        return "near the top of its 30-day range"
    if p <= 5:
        return "the lowest in 30 days"
    if p <= 15:
        return "near the bottom of its 30-day range"
    return "mid-range for the last 30 days"


def _nice_axis(lo, hi, n=4):
    """Snap [lo, hi] outward to a 1/2/2.5/5 x 10^k grid and return the snapped bounds.

    _grid divides the range into n equal parts and labels each one, so an arbitrary data range
    yields labels like 0.01137 / 0.007834 / 0.0007652. Choosing a round step first makes the axis
    readable; the cost is a little empty space at the ends, which is far cheaper than an axis
    nobody can read.
    """
    if not (hi > lo):
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / max(1, n)
    b = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = 10 * b
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * b:
            step = m * b
            break
    return math.floor(lo / step) * step, math.ceil(hi / step) * step


def _ord(n):
    """41 -> 41st, 43 -> 43rd, 11 -> 11th. Never format 'th' straight onto a number."""
    n = int(round(n))
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _rank_pct(vals):
    """Each value's rank within its own list, 0-100.

    Uses the SAME definition as the digest's percentile (share of the window at or below the
    value), so the chart and the text can never disagree about what a percentile means.
    """
    n = len(vals) or 1
    return [sum(1 for x in vals if x <= v) / n * 100 for v in vals]


def _frame(title, w=W, h=H):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    f = _font(23, True)
    # Keep the title clear of the right-aligned series legend that line_chart draws at y=20.
    # A 59-char title ran straight into it and rendered as unreadable overlap, so truncate here
    # rather than trusting every caller to keep titles short.
    maxw = w - 430
    if d.textlength(title, font=f) > maxw:
        while title and d.textlength(title + "\u2026", font=f) > maxw:
            title = title[:-1]
        title = title.rstrip() + "\u2026"
    d.text((20, 14), title, fill=FG, font=f)
    return img, d


def _grid(d, x0, x1, y0, y1, lo, hi, n=4, deco=None):
    for i in range(n + 1):
        f = i / n
        y = y1 - (y1 - y0) * f
        d.line([(x0, y), (x1, y)], fill=GRID)
        lab = deco(lo + (hi - lo) * f) if deco else _fmt(lo + (hi - lo) * f)
        d.text((x0 - 10, y), lab, fill=DIM, font=_font(16), anchor="rm")


def _xaxis(d, labels, x0, x1, y1, ticks=5):
    if not labels:
        return
    n = len(labels)
    for i in range(ticks + 1):
        idx = min(n - 1, int(i * (n - 1) / ticks))
        x = x0 + (x1 - x0) * (idx / max(1, n - 1))
        d.text((x, y1 + 10), str(labels[idx])[5:], fill=DIM, font=_font(15), anchor="ma")


def _mapx(i, n, x0, x1):
    return x0 + (x1 - x0) * (i / max(1, n - 1))


def line_chart(path, series, title, days=None, log=False, hlines=(), dlines=(),
               pad=(104, 26, 52, 44), ylim=None, nice=False):
    """series: list of (values, colour, label).

    dlines: [(value, colour, label)] - dotted reference lines (a series' own median, a balance
    point) labelled at the right edge. PIL has no dash style so these are drawn by hand. The L/S
    medians sit ~11px apart on the canvas, so labels are staggered vertically and boxed on the
    chart background - otherwise they print on top of each other and read as a single number.
    """
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    tf = (lambda v: math.log10(v)) if log else (lambda v: v)
    flat = [v for vals, *_ in series for v in vals if v is not None and (v > 0 if log else True)]
    if not flat:
        return False
    if ylim:
        lo, hi = ylim                          # fixed scale, e.g. 0-100 for a percentile panel
    else:
        lo, hi = min(flat), max(flat)
        if lo == hi:
            lo, hi = lo * 0.99, hi * 1.01
        pad_y = (hi - lo) * 0.08
        lo, hi = lo - pad_y, hi + pad_y
        if nice:
            # Opt-in: snap the axis to round steps. Only for charts read by absolute level
            # (indexed-to-100 overlays); it coarsens tightly-ranged series like OI or premium.
            lo, hi = _nice_axis(lo, hi)
        if not log and min(flat) >= 0 and lo < 0:
            lo = 0.0
    tlo, thi = tf(lo), tf(hi)
    _grid(d, x0, x1, y0, y1, lo, hi)

    for v, col in hlines:
        if hi >= v >= lo:
            y = y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo)
            d.line([(x0, y), (x1, y)], fill=col, width=2)

    # dotted reference lines, hand-drawn (PIL has no dash style). Labels are drawn AFTER the
    # series further down - drawing them here let the series lines print straight through the text.
    tags = []
    for v, col, lbl in dlines:
        if not (hi >= v >= lo):
            continue
        y = y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo)
        x = x0
        while x < x1:
            d.line([(x, y), (min(x + 9, x1), y)], fill=col, width=2)
            x += 16
        tags.append([y, lbl, col])

    for vals, col, *rest in series:
        pts = [(_mapx(i, len(vals), x0, x1), y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo))
               for i, v in enumerate(vals) if v is not None and (v > 0 if log else True)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=3, joint="curve")

    tags.sort(key=lambda r: r[0])
    for i in range(1, len(tags)):                    # push labels apart so none overlap
        if tags[i][0] - tags[i - 1][0] < 18:
            tags[i][0] = tags[i - 1][0] + 18
    ftag = _font(15, True)
    for y, lbl, col in tags:
        y = min(max(y, y0 + 10), y1 - 4)
        tw = d.textlength(lbl, font=ftag)
        d.rectangle([x1 - tw - 14, y - 11, x1 - 2, y + 11], fill=BG)   # box it, or lines show through
        d.text((x1 - 8, y), lbl, fill=col, font=ftag, anchor="rm")

    lx = x1
    for vals, col, *rest in reversed(series):
        lbl = rest[0] if rest else ""
        if lbl:
            d.text((lx, 20), lbl, fill=col, font=_font(17, True), anchor="ra")
            lx -= int(d.textlength(lbl, font=_font(17, True))) + 30
    _xaxis(d, days or [], x0, x1, y1)
    img.save(path)
    return True


def dual_chart(path, primary, secondary, title, days=None, log=True,
               pad=(104, 118, 56, 44), h=430, ylim=None, sdlines=()):
    """Two series, two independent y-axes: price on the left, an index LEVEL on the right.

    Written for BTC vs DXY. Indexing both series to 100 (the earlier approach) made the
    comparison mathematically fair but visually useless: DXY travelled 96-103 over the window,
    so on a shared 40-120 axis it flattened into a line pinned at 100 while BTC's drawdown owned
    the whole panel. You could not see the dollar at all. Here DXY keeps its REAL level on its
    own axis, zoomed to its own range, so its strength is legible.

    The trade-off is that the two slopes are no longer comparable - a 1% DXY move and a 1% BTC
    move are different pixel heights. The on-canvas note and the caption both say so; the
    percentages live in the caption's number line instead.

    pad's right gutter must fit the right-axis labels (118px at 2 decimals).
    """
    pvals, pcol, plbl = primary
    svals, scol, slbl = secondary
    pl, pr, pt, pb = pad
    img, d = _frame(title, h=h)
    x0, x1, y0, y1 = pl, W - pr, pt, h - pb
    tf = (lambda v: math.log10(v)) if log else (lambda v: v)
    pf = [v for v in pvals if v is not None and (v > 0 if log else True)]
    sf = [v for v in svals if v is not None]
    if not pf or not sf:
        return False

    if ylim:
        lo, hi = ylim
    else:
        lo, hi = min(pf), max(pf)
        pad_y = (hi - lo) * 0.08 or abs(hi) * 0.01 or 1
        lo, hi = lo - pad_y, hi + pad_y
    tlo, thi = tf(lo), tf(hi)
    _grid(d, x0, x1, y0, y1, lo, hi,
          deco=lambda v: f"${v / 1000:,.0f}k" if abs(v) >= 1000 else f"${v:,.0f}")

    # Right axis: snap to round levels so the labels read 96 / 98 / 100 / 102 / 104 instead of
    # 96.203 / 97.962 / ... The zoom is the point, so keep all 5 ticks inside the series range.
    slo, shi = min(sf), max(sf)
    sp_y = (shi - slo) * 0.12 or abs(shi) * 0.005 or 1
    slo, shi = _nice_axis(slo - sp_y, shi + sp_y, 4)
    sspan = (shi - slo) or 1
    step = sspan / 4
    # Pick the fewest decimals that print `step` EXACTLY. Snapping produced a 2.5 step, and a
    # naive ">= 1.5 -> 0 decimals" rule then labelled the 97.5 tick "98": a label that lies about
    # where its own gridline sits. Derive it from the step instead of guessing at the size.
    dec = 2
    for cand in (0, 1, 2):
        if abs(round(step, cand) - step) < 1e-9:
            dec = cand
            break

    def sy(v):
        return y1 - (y1 - y0) * (v - slo) / sspan

    for i in range(5):
        v = slo + step * i
        y = sy(v)
        d.line([(x1, y), (x1 + 7, y)], fill=DIM, width=2)
        d.text((x1 + 12, y), f"{v:.{dec}f}", fill=scol, font=_font(16), anchor="lm")
    # No axis-name text at the top: it collided with the top tick and the legend. The legend
    # labels carry "(left)"/"(right)" and the tick colours match the lines instead.

    ftag = _font(15, True)
    for v, col, lbl in sdlines:
        if not (shi >= v >= slo):
            continue
        y = sy(v)
        x = x0
        while x < x1:
            d.line([(x, y), (min(x + 8, x1), y)], fill=col, width=1)
            x += 15
        if lbl:
            tw = d.textlength(lbl, font=ftag)
            d.rectangle([x1 - tw - 14, y - 11, x1 - 2, y + 11], fill=BG)
            d.text((x1 - 8, y), lbl, fill=col, font=ftag, anchor="rm")

    # Primary (price) uses the left/log mapping, secondary (index level) the right/linear one.
    ppts = [(_mapx(i, len(pvals), x0, x1), y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo))
            for i, v in enumerate(pvals) if v is not None and (v > 0 if log else True)]
    spts = [(_mapx(i, len(svals), x0, x1), sy(v))
            for i, v in enumerate(svals) if v is not None]
    for pts, col in ((ppts, pcol), (spts, scol)):
        if len(pts) > 1:
            d.line(pts, fill=col, width=3, joint="curve")

    lx = x1
    for col, lbl in ((scol, slbl), (pcol, plbl)):
        d.text((lx, 20), lbl, fill=col, font=_font(17, True), anchor="ra")
        lx -= int(d.textlength(lbl, font=_font(17, True))) + 30
    _xaxis(d, days or [], x0, x1, y1)
    d.text((20, h - 16),
           "Left axis = BTC price (log). Right axis = DXY, ZOOMED to its own range - read the "
           "direction and the labelled level, not the slope.", fill=DIM, font=_font(15))
    img.save(path)
    return True


def bars_chart(path, values, title, days=None, pad=(104, 26, 52, 44), pos=UP, neg=DN,
               cum=False, unit="", cum_scale=1.0, deco=None, symmetric=True):
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    if not values:
        return False
    if symmetric:
        # Centred on zero so the +/- balance reads correctly, with 12% headroom so the tallest bar
        # never ends exactly on the top gridline (which read as chopped off at the axis limit).
        ext = (max(abs(min(values)), abs(max(values))) or 1) * 1.12
        lo_v, hi_v = -ext, ext
    else:
        # One-sided data (funding is positive 99% of the time). Scaling symmetrically wasted half
        # the panel on empty negative space; fit the data instead. Snap to a round step here
        # because these magnitudes (~0.002-0.01) otherwise label as 0.01137 / 0.0007652.
        lo_v, hi_v = min(min(values), 0.0), max(max(values), 0.0)
        sp = (hi_v - lo_v) or 1.0
        lo_v, hi_v = _nice_axis(lo_v - sp * 0.08, hi_v + sp * 0.08)
    _grid(d, x0, x1, y0, y1, lo_v, hi_v, deco=deco)

    vspan = (hi_v - lo_v) or 1.0

    def _yof(v):
        return y1 - (y1 - y0) * (v - lo_v) / vspan

    zero = _yof(0.0)
    n = len(values)
    bw = int(max(2, (x1 - x0) / n * 0.7))
    for i, v in enumerate(values):
        d.line([(_mapx(i, n, x0, x1), zero), (_mapx(i, n, x0, x1), _yof(v))],
               fill=pos if v > 0 else neg, width=bw)
    d.line([(x0, zero), (x1, zero)], fill=DIM)
    if cum:
        run, tot = [], 0.0
        for v in values:
            tot += v
            run.append(tot)
        cmin, cmax = min(run), max(run)
        cspan = (cmax - cmin) or 1
        pts = [(_mapx(i, n, x0, x1), y1 - (y1 - y0) * 0.9 * ((v - cmin) / cspan) - (y1 - y0) * 0.05)
               for i, v in enumerate(run)]
        d.line(pts, fill=AMBER, width=3, joint="curve")
        d.text((x1, 20), f"cumulative {_fmt(tot * cum_scale)}{unit}", fill=AMBER,
                font=_font(17, True), anchor="ra")
    _xaxis(d, days or [], x0, x1, y1)
    img.save(path)
    return True


def urpd_chart(path, buckets, spot, title):
    """Horizontal supply ladder: price on Y, share of supply on X. Tall - it has many rows."""
    h = 620
    img, d = _frame(title, h=h)
    n = len(buckets)
    if not n:
        return False
    pl, pr, pt, pb = 104, 150, 56, 44
    x0, x1, y0, y1 = pl, W - pr, pt, h - pb
    lo = min(b["lo"] for b in buckets)
    hi = max(b["hi"] for b in buckets)
    pmax = max(b["pct"] for b in buckets) or 1
    for i in range(5):
        f = i / 4
        y = y1 - (y1 - y0) * f
        d.line([(x0, y), (x1, y)], fill=GRID)
        d.text((x0 - 10, y), f"${(lo + (hi - lo) * f) / 1000:,.0f}k", fill=DIM, font=_font(16), anchor="rm")
    bh = max(3, (y1 - y0) / n * 0.72)
    for b in buckets:
        mid_p = (b["lo"] + b["hi"]) / 2
        y = y1 - (y1 - y0) * (mid_p - lo) / (hi - lo)
        w = (x1 - x0) * (b["pct"] / pmax)
        d.line([(x0, y), (x0 + w, y)], fill=(DN if b["lo"] >= spot else ACC), width=int(bh))
        if b["pct"] >= pmax * 0.30:
            d.text((x0 + w + 8, y), f"{b['pct']:.1f}%", fill=WHITE, font=_font(16), anchor="lm")
    if lo <= spot <= hi:
        ys = y1 - (y1 - y0) * (spot - lo) / (hi - lo)
        d.line([(x0, ys), (x1, ys)], fill=AMBER, width=2)
        d.text((x1 + 6, ys), f"spot ${spot / 1000:,.1f}k", fill=AMBER, font=_font(17, True), anchor="lm")
    d.text((20, h - 30), "red bars = supply ABOVE spot (overhead resistance)   blue = below spot (support)",
           fill=DIM, font=_font(16))
    img.save(path)
    return True


def stablecoin_series(days=120):
    out = {}
    for cid in (1, 2):
        u = f"https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={cid}"
        raw = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
        for r in json.loads(raw.decode()):
            v = (r.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if v:
                out.setdefault(r["date"], {}).setdefault(cid, v)
    rows = sorted((int(d), v) for d, v in out.items() if len(v) == 2)[-days:]
    from datetime import datetime, timezone
    labels = [datetime.fromtimestamp(d, timezone.utc).strftime("%Y-%m-%d") for d, _ in rows]
    return labels, [v[1] / 1e9 for _, v in rows], [v[2] / 1e9 for _, v in rows]


def build_all(outdir, series_path):
    """Render every chart. Returns metadata for the page. Never raises."""
    with open(series_path) as fh:
        S = json.load(fh)
    os.makedirs(outdir, exist_ok=True)
    out = []

    def add(fn, title, now, use, verdict, cls=""):
        out.append({"file": fn, "title": title, "now": now, "use": use,
                    "verdict": verdict, "cls": cls})

    days = S.get("days", [])
    close = S.get("cb_close", [])
    spot = S.get("spot") or (close[-1] if close else 0)

    def ma(vals, n):
        r = [None] * len(vals)
        for i in range(n - 1, len(vals)):
            r[i] = sum(vals[i - n + 1:i + 1]) / n
        return r

    # 1. price + MAs --------------------------------------------------------
    try:
        p = os.path.join(outdir, "c_price.png")
        m10, m50, m200 = ma(close, 10), ma(close, 50), ma(close, 200)
        if line_chart(p, [(close[-400:], FG, "price"), (m10[-400:], TEAL, "10-day"),
                          (m50[-400:], ACC, "50-day"), (m200[-400:], PUR, "200-day")],
                      "Price vs its 10 / 50 / 200-day averages (log)",
                      days=days[-400:], log=True):
            a200 = m200[-1] or spot
            gap = (spot - a200) / a200 * 100
            above = [n for n, m in (("10-day", m10[-1]), ("50-day", m50[-1]), ("200-day", m200[-1]))
                     if m and spot > m]
            if not above:
                pv = (f"Price is BELOW all three averages, so anyone who bought in the last ten "
                      f"months is sitting on a loss and every rally runs into sellers trying to "
                      f"get out even. The 200-day average is at ${m200[-1]:,.0f}, {abs(gap):.1f}% "
                      f"above today's ${spot:,.0f}: that is the level a bounce has to reclaim "
                      f"before this is anything but a downtrend.")
            elif len(above) == 3:
                pv = (f"Price is ABOVE all three averages, so each one acts as a floor and dips "
                      f"into them get bought. The nearest floor is the 10-day at "
                      f"${m10[-1]:,.0f}, {abs(gap):.1f}% below spot.")
            else:
                pv = (f"Price is above the {' and '.join(above)} average but below the rest, so "
                      f"it is wedged: floors underneath from the averages already reclaimed, "
                      f"sellers overhead from the ones still above it. No clean trend either way.")
            add("c_price.png", "Price vs its 10, 50 and 200-day averages",
                [f"price now ${spot:,.0f}", f"10-day avg ${m10[-1]:,.0f}",
                 f"50-day avg ${m50[-1]:,.0f}", f"200-day avg ${m200[-1]:,.0f}",
                 f"{abs(gap):.1f}% below the 200-day" if gap < 0 else f"{gap:+.1f}% above the 200-day"],
                "A moving average is simply the average closing price over the last N days, "
                "drawn as a line so the trend shows through the daily noise. The 10-day line is "
                "the last two weeks, the 50-day the last two months, the 200-day the last ten "
                "months. Rule of thumb: price above an average means that average is support, "
                "price below means it is resistance, and a bounce inside a downtrend usually "
                "stalls at the FIRST average overhead. The 200-day is the line the short-fade "
                "signal waits for.",
                pv, "wide")
    except Exception:
        pass

    # 1b. BTC vs dollar strength (DXY) ---------------------------------------
    try:
        dxy = S.get("dxy", [])
        if dxy and close and len(dxy) >= 2:
            n = min(len(dxy), len(close))
            dxy, px, dys = dxy[-n:], close[-n:], (days or [])[-n:]
            # DXY at its REAL level on its own right-hand axis, zoomed to its own range.
            # An indexed overlay of both series (the previous version) is fair maths and a
            # useless chart: DXY's 96->103 range compressed to a flat line at 100 and you could
            # not see the dollar at all. Levels on their own axis; % moves in the number line.
            b = [v / px[0] * 100 for v in px]
            q = [v / dxy[0] * 100 for v in dxy]
            p = os.path.join(outdir, "c_dxy.png")
            if dual_chart(p, (px, AMBER, "BTC price (left)"), (dxy, ACC, "DXY (right)"),
                          "BTC price vs DXY - actual levels, separate axes",
                          days=dys, log=True, sdlines=[(100.0, DIM, "")]):
                # Correlate DAILY RETURNS, not price levels. Two series can both trend hard and
                # "correlate" strongly as levels while having no day-to-day link at all - that is
                # spurious correlation. Returns are what answer "does the dollar move BTC?".
                rb = [b[i] / b[i - 1] - 1 for i in range(1, n)]
                rq = [q[i] / q[i - 1] - 1 for i in range(1, n)]
                m = len(rb)
                mb, md = sum(rb) / m, sum(rq) / m
                cov = sum((x - mb) * (y - md) for x, y in zip(rb, rq))
                sb = math.sqrt(sum((x - mb) ** 2 for x in rb))
                sd = math.sqrt(sum((y - md) ** 2 for y in rq))
                r = cov / (sb * sd) if sb and sd else 0.0
                dpts = dxy[-1] - dxy[0]
                dpc = dpts / dxy[0] * 100
                # Where today's level sits inside the window. Written for a reader who does not
                # know what a percentile is: "P100" and "103.24 vs 96.2-103.2" are MY shorthand,
                # not the reader's - Ben's rule, if a term needs a glossary it does not ship.
                # Say the plain fact instead: highest / lowest / middle of the months shown.
                rank = sum(1 for v in dxy if v <= dxy[-1]) / len(dxy) * 100
                wm = max(1, round(n / 30.44))                 # window length in months
                lo_d, hi_d = min(dxy), max(dxy)
                btc_pc = b[-1] - 100
                btc_verb = f"fallen {abs(btc_pc):.0f}%" if btc_pc < 0 else f"gained {btc_pc:.0f}%"
                if rank >= 95:
                    where = f"the highest level in the {wm} months shown"
                elif rank >= 80:
                    where = f"near the top of the {wm}-month range"
                elif rank <= 5:
                    where = f"the lowest level in the {wm} months shown"
                elif rank <= 20:
                    where = f"near the bottom of the {wm}-month range"
                else:
                    where = f"the middle of the {wm}-month range"
                # Every verdict states the same three things in the same order: where the dollar
                # is, what that means for BTC, and what to do about it.
                tail = ("A stronger dollar pulls money out of risk assets, so treat BTC rallies as "
                        "fades while this holds." if rank >= 80 and dpc > 0 else
                        "A weaker dollar is a tailwind, so the macro is not what is holding BTC "
                        "down right now." if rank <= 20 else
                        "No strong push either way, so the dollar is not the reason to take or "
                        "skip a trade today.")
                add("c_dxy.png", "Dollar strength - macro headwind or tailwind",
                    [f"DXY now {dxy[-1]:.1f}", f"{dpc:+.1f}% in {wm} months",
                     f"{wm}-month range {lo_d:.1f}-{hi_d:.1f}",
                     f"BTC {btc_pc:+.0f}% same window", f"move-together {r:+.2f}"],
                    "DXY is the dollar measured against six major currencies. It is an INDEX, "
                    "not a price: it was set to 100 when the basket started, so 103.2 means the "
                    "dollar is a bit stronger than that starting point - the number only means "
                    "something next to its own range, which is the 96.2-103.2 band in the chips "
                    "above. Orange line = BTC price on the LEFT axis (in $, log scale). Blue line "
                    "= DXY on the RIGHT axis. Each axis is zoomed to its own data, so the two "
                    "lines' heights and steepness are NOT comparable - read direction, and use "
                    "the percentages above to compare. Usual relationship: dollar up, BTC down. "
                    "'Move-together' measures whether their DAILY changes went the same way: +1 "
                    "= always together, -1 = always opposite, 0 = no link. Below about -0.3 is a "
                    "real day-to-day link; -0.12 means almost none, so this is slow pressure, "
                    "not a trigger. Rebuilt from ECB reference rates, so it can sit ~0.1-0.2% "
                    "off the official ICE print.",
                    (f"The dollar is at {where}: {dxy[-1]:.1f} today against a low of {lo_d:.1f} "
                     f"in the same stretch, so it has risen {dpc:.1f}% while BTC has {btc_verb}. "
                     f"{tail}"),
                    "wide")
    except Exception:
        pass

    # 2. premium ------------------------------------------------------------
    try:
        prem = S.get("premium", [])
        p = os.path.join(outdir, "c_premium.png")
        m30 = [sum(prem[max(0, i - 29):i + 1]) / len(prem[max(0, i - 29):i + 1]) for i in range(len(prem))]
        if line_chart(p, [(prem[-240:], ACC, "daily gap"), (m30[-240:], AMBER, "30-day avg")],
                      "US vs global BTC price, % - who pays more?", days=days[-240:],
                      hlines=[(0, DIM)]):
            streak = 0
            for v in reversed(prem):
                if v < 0:
                    streak += 1
                else:
                    break
            add("c_premium.png", "US vs global premium - is America paying up?",
                # prem[-1] is the last SETTLED daily close - the series excludes the forming
                # day. Calling it "right now" (as this chip did) claimed a live tick that it is
                # not, and disagreed with the digest's live line on the same screen.
                [f"last close {prem[-1]:+.3f}%", f"30-day average {m30[-1]:+.3f}%",
                 f"below zero for {streak} days straight"],
                "The premium is Coinbase's BTC price minus Binance's, in percent: it answers "
                "'are US buyers paying more or less than the rest of the world?'. Above zero = "
                "US demand is leading. A run of 20+ days below zero is not noise, it is a "
                "regime - the deepest pool of buyers is simply not there.",
                (f"US buyers have paid LESS than the rest of the world for {streak} days in a "
                 f"row. That is the structural buyer - US institutions - simply absent, so there "
                 f"is no American bid to lift this market. A few days would be noise; {streak} "
                 f"days is the regime, and it stays bearish until it flips back above zero."
                 if streak >= 20 else
                 "US buyers are paying roughly the same as the rest of the world, so there is no "
                 "US signal here either way - look at the other flow cards instead."))
    except Exception:
        pass

    # 3. RSI ----------------------------------------------------------------
    try:
        def rsi(vals, n=14):
            if len(vals) < n + 1:
                return [None] * len(vals)
            r = [None] * len(vals)
            g = l = 0.0
            for i in range(1, n + 1):
                ch = vals[i] - vals[i - 1]
                g += max(ch, 0); l += max(-ch, 0)
            g /= n; l /= n
            r[n] = 100 - 100 / (1 + (g / l if l else 1e9))
            for i in range(n + 1, len(vals)):
                ch = vals[i] - vals[i - 1]
                g = (g * (n - 1) + max(ch, 0)) / n
                l = (l * (n - 1) + max(-ch, 0)) / n
                r[i] = 100 - 100 / (1 + (g / l if l else 1e9))
            return r
        r6, r14, r24 = rsi(close, 6), rsi(close, 14), rsi(close, 24)
        p = os.path.join(outdir, "c_rsi.png")
        if line_chart(p, [(r6[-240:], TEAL, "6-day"), (r14[-240:], ACC, "14-day"),
                          (r24[-240:], PUR, "24-day")],
                      "Momentum score, 0-100 (6 / 14 / 24-day)", days=days[-240:],
                      hlines=[(70, DN), (30, UP)]):
            v6, v14, v24 = r6[-1], r14[-1], r24[-1]
            tail = [x for x in r14 if x is not None]
            pct = sum(1 for x in tail if x <= v14) / len(tail) * 100
            if v14 <= 30:
                state = ("oversold - below 30 out of 100, the zone where bounces have "
                         "historically started")
            elif v14 >= 70:
                state = "overbought - above 70 out of 100, stretched and prone to snapping back"
            else:
                state = "neutral - between 30 and 70, no momentum extreme"
            slows = v6 < v24
            add("c_rsi.png", "Momentum score (RSI) - how hard is it moving?",
                [f"momentum {v14:.1f} out of 100", f"6-day reading {v6:.1f}",
                 f"24-day reading {v24:.1f}", f"lower than {100 - pct:.0f}% of the last year"],
                "RSI (relative strength index) scores momentum 0-100 by comparing the size of "
                "average up-days with down-days. Below 30 = oversold, above 70 = overbought. "
                "Three speeds are drawn: 6-day (fast), 14-day (middle) and 24-day (slow). Fast "
                "above slow = momentum improving; fast BELOW slow = momentum deteriorating and "
                "bounces are being sold into. This describes force - it does not trigger a trade "
                "on its own.",
                (f"Momentum scores {v14:.1f} out of 100, which is {state}. The fast 6-day "
                 f"reading ({v6:.1f}) is still weaker than the slow 24-day ({v24:.1f}), so "
                 f"selling pressure is still building rather than easing - rallies are being "
                 f"sold. Oversold means do not chase a short into fresh lows; it is not a buy "
                 f"signal either."
                 if slows else
                 f"Momentum scores {v14:.1f} out of 100, which is {state}. The fast 6-day "
                 f"reading ({v6:.1f}) is now stronger than the slow 24-day ({v24:.1f}), so "
                 f"short-term momentum is turning up ahead of the longer trend."))
    except Exception:
        pass

    # 4. URPD ---------------------------------------------------------------
    try:
        ub = S.get("urpd", [])
        p = os.path.join(outdir, "c_urpd.png")
        stale = "  [cached - bitcoin-data quota]" if S.get("urpd_stale") else ""
        if ub and urpd_chart(p, ub, spot, f"Where supply sits by purchase price - {S.get('urpd_day','')}{stale}"):
            top = sorted(ub, key=lambda b: -b["pct"])[:3]
            below = sum(b["pct"] for b in ub if b["hi"] <= spot)
            above = sum(b["pct"] for b in ub if b["lo"] >= spot)
            add("c_urpd.png", "Where supply sits by purchase price",
                [f"biggest cluster ${top[0]['lo']//1000}k-${top[0]['hi']//1000}k "
                 f"= {top[0]['pct']:.1f}% of all coins",
                 f"{above:.1f}% of coins were bought ABOVE today's price",
                 f"{below:.1f}% were bought BELOW it"],
                "Every bar is how much bitcoin last changed hands at that price - in other "
                "words, where holders' purchase prices sit. Bars ABOVE today's price are holders "
                "sitting on a loss: they sell into rallies to get out even and cap them. Bars "
                "BELOW are holders in profit, who tend to sit still. The amber line is today's "
                "price.",
                (f"Only {below:.1f}% of all coins were last bought below today's price, while "
                 f"{above:.1f}% were bought above it. So the market is mostly underwater: there "
                 f"is heavy overhead supply to chew through as trapped holders sell to break "
                 f"even, and very little bought-in-profit support underneath. Thin floor, thick "
                 f"ceiling."))
    except Exception:
        pass

    # 5. ETF flows ----------------------------------------------------------
    try:
        ef = S.get("etf_flow", [])
        ed = S.get("etf_days", [])
        p = os.path.join(outdir, "c_etf.png")
        if ef and bars_chart(p, ef[-60:], "US spot bitcoin ETF flows, $ per day",
                             days=ed[-60:],
                             cum=True, unit="", cum_scale=1e6):
            s5 = sum(ef[-5:]); s30 = sum(ef[-30:]); last = ef[-1]
            add("c_etf.png", "US spot ETF flows - are institutions buying?",
                ([f"latest day not published yet", f"last 5 days {_usd(s5 / 1000)}",
                  f"last 30 days {_usd(s30 / 1000)}"] if abs(last) < 0.5 else
                 [f"latest day {_usd(last / 1000)}", f"last 5 days {_usd(s5 / 1000)}",
                  f"last 30 days {_usd(s30 / 1000)}"]),
                "US spot bitcoin ETFs are how most institutions buy. Green bars = money going in "
                "(new shares created), red bars = money coming out (shares redeemed). Read the "
                "SUMS, never a single day: one day is noise, the 30-day total is the trend. The "
                "amber line is the running total.",
                (f"Institutions are still selling: {_usd(s30 / 1000, sign=False)} has come out "
                 f"of the US spot ETFs over the last 30 days, and "
                 f"{_usd(s5 / 1000, sign=False)} of that in the last "
                 f"week alone. That is the single biggest buyer of 2024-25 going backwards, so "
                 f"there is nothing here to catch the falling price."
                 if s30 < 0 else
                 f"Institutions are buying again: {_usd(s30 / 1000)} has gone into the US spot "
                 f"ETFs over the last 30 days. Persistent ETF inflows have been what put a floor "
                 f"under every dip this cycle."))
    except Exception:
        pass

    # 6. stablecoins --------------------------------------------------------
    try:
        sd, usdt, usdc = stablecoin_series(120)
        p = os.path.join(outdir, "c_stables.png")
        if line_chart(p, [(usdt, TEAL, "USDT"), (usdc, ACC, "USDC")],
                      "Stablecoin supply, $bn - is cash coming back?", days=sd):
            comb = usdt[-1] + usdc[-1]
            d7 = comb - (usdt[-8] + usdc[-8]) if len(usdt) > 8 else 0
            d30 = comb - (usdt[-31] + usdc[-31]) if len(usdt) > 31 else 0
            add("c_stables.png", "Stablecoin supply - is cash waiting to buy?",
                [f"total stablecoin supply ${comb:,.1f}B", f"7-day change {_usd(d7)}",
                 f"30-day change {_usd(d30)}"],
                "Stablecoins (USDT, USDC) are the cash pile of crypto - what you hold when you "
                "want out of bitcoin but stay inside the system. Growing supply = new fiat "
                "arriving, dry powder building. Shrinking supply = people redeeming for real "
                "dollars and leaving crypto altogether. It is NOT money parked on the sidelines "
                "waiting to buy - a shrinking pile means it is gone.",
                (f"Stablecoin supply is shrinking by {_usd(d7, sign=False)} in a week and "
                 f"{_usd(d30, sign=False)} in a "
                 f"month, down to ${comb:,.1f}B. Money is being redeemed and leaving crypto "
                 f"entirely, so there is no cash pile building up to buy this dip. That is the "
                 f"opposite of the setup that ends a downtrend."
                 if d30 < 0 and d7 < 0 else
                 f"Stablecoin supply is growing by {_usd(d7, sign=False)} in a week and "
                 f"{_usd(d30, sign=False)} in a month. "
                 f"Fresh cash is arriving and sitting ready to buy - dry powder is building, "
                 f"which is what bottoms are made of."
                 if d30 > 0 and d7 > 0 else
                 f"Mixed: the week says {_usd(d7)} and the month says {_usd(d30)}, so the cash "
                 f"pile is not clearly growing or shrinking. No signal until both agree."))
    except Exception:
        pass

    # 7. funding ------------------------------------------------------------
    try:
        fr = S.get("funding", [])
        p = os.path.join(outdir, "c_funding.png")
        if fr and bars_chart(p, [x * 100 for x in fr],
                             "Funding rate, % paid every 8 hours (30 days)",
                             symmetric=False):
            now_r = fr[-1] * 100
            avg = sum(fr) / len(fr) * 100
            ann = avg * 3 * 365
            posn = sum(1 for x in fr if x > 0) / len(fr) * 100
            add("c_funding.png", "Funding rate - what it costs to hold a bet",
                [f"right now {now_r:+.4f}% every 8 hours",
                 f"30-day average {ann:+.1f}% a year",
                 f"positive in {posn:.0f}% of the last 30 days"],
                "Funding is the small payment leveraged traders make to each other every 8 "
                "hours. Positive funding = LONGS pay shorts, meaning the crowd is leaning long "
                "and the long side is crowded (bearish tilt - dips get flushed out). Negative "
                "funding = SHORTS pay longs, meaning shorts are crowded and are squeeze fuel "
                "upward (hostile to a new short). The yearly figure just compounds the "
                "8-hourly rate - three payments a day.",
                (f"Funding averages {ann:+.1f}% a year and has been positive in {posn:.0f}% of "
                 f"the last 30 days: longs are paying to keep their bets open. That means the "
                 f"crowded long side has NOT given up yet, so there is still fuel for another "
                 f"flush lower. Funding only turns bullish for BTC once it goes negative and "
                 f"stays there - that is when the weak longs have actually been cleared."
                 if avg > 0 else
                 f"Funding averages {ann:+.1f}% a year, so shorts are paying longs to stay "
                 f"short. Crowded short positioning is squeeze fuel upward - a bad place to open "
                 f"a fresh short."))
    except Exception:
        pass

    # 8. long/short ratios --------------------------------------------------
    try:
        ra = S.get("ratios_all", []); rt = S.get("ratios_topacct", []); rp = S.get("ratios_toppos", [])
        p = os.path.join(outdir, "c_ratios.png")
        # Draw each series' OWN median, because the three answers to "is this crowded?" differ -
        # a bare 1.8 means nothing until you know that series' normal. Plus the 1.00 balance line,
        # the only hard reference: everything above it is net long, whatever "normal" happens to be.
        med = lambda v: (statistics.median(v) if v else 0.0)
        refs = [(1.0, WHITE, "1.00 = balanced"),
                (med(ra), ACC, f"ordinary median {med(ra):.2f}"),
                (med(rt), PUR, f"big-account median {med(rt):.2f}"),
                (med(rp), TEAL, f"big-money median {med(rp):.2f}")]
        if line_chart(p, [(ra, ACC, "ordinary"), (rt, PUR, "big accounts"),
                          (rp, TEAL, "big money")],
                      "Longs per short on Binance futures", dlines=refs):
            pa = sum(1 for x in ra if x <= ra[-1]) / len(ra) * 100
            pt = sum(1 for x in rt if x <= rt[-1]) / len(rt) * 100
            pp = sum(1 for x in rp if x <= rp[-1]) / len(rp) * 100
            add("c_ratios.png", "Long/short ratios - who is betting which way",
                [f"ordinary accounts {ra[-1]:.2f} longs per short",
                 f"big traders' accounts {rt[-1]:.2f} longs per short",
                 f"big traders' position size {rp[-1]:.2f} longs per short",
                 f"the crowd is {_rank_name(pa)}"],
                "Each line counts how many long positions exist for every short on Binance "
                "futures. Above 1.00 = more longs. 'Ordinary accounts' counts people, 'big "
                "traders accounts' counts only the largest accounts, and 'big traders position "
                "size' weights those big traders by how much money they have on rather than "
                "how many accounts they hold. Read all of it CONTRARIAN: a crowded long book is "
                "fuel for a squeeze DOWN, a crowded short book is fuel for a squeeze UP. When "
                "ordinary traders are long but big traders' money is shrinking, the informed "
                "side is handing risk to the crowd.",
                (f"The crowd is CROWDED long: ordinary accounts hold {ra[-1]:.2f} longs for "
                 f"every short, which is {_rank_name(pa)} - past the 85-of-100 line we treat as "
                 f"crowded. Crowded longs are fuel for a squeeze DOWN. Big traders' position "
                 f"size is {rp[-1]:.2f} ({_rank_name(pp)}), so the money is not adding to that "
                 f"long either way. The pain trade is lower."
                 if pa >= 85 else
                 f"The crowd is CROWDED short: ordinary accounts hold only {ra[-1]:.2f} longs per "
                 f"short, which is {_rank_name(pa)} - below the 15-of-100 line we treat as "
                 f"crowded. Crowded shorts are fuel for a squeeze UP, so a fresh short here is "
                 f"fighting the positioning."
                 if pa <= 15 else
                 f"No crowding signal: ordinary accounts lean long at {ra[-1]:.2f} longs per "
                 f"short, but that is {_rank_name(pa)} - and we only call it crowded past 85 of "
                 f"100. Big traders' position size is {rp[-1]:.2f} ({_rank_name(pp)}). So the "
                 f"book leans long without being stretched, which gives no contrarian squeeze to "
                 f"trade - this is a background condition, not a reason to take a side."))
    except Exception:
        pass

    # 8b. the SAME three ratios as own-window percentiles -------------------
    # Raw levels are not comparable: the headcount series sits near 2.3 by construction and the
    # size series near 1.85, so a "normal" 2.0 reads as long-heavy and a crowded 3.0 reads as
    # average. Re-scored against each series' OWN 30-day window, all three land on one 0-100
    # scale and "how crowded is this, really?" becomes answerable at a glance.
    try:
        ra = S.get("ratios_all", []); rt = S.get("ratios_topacct", []); rp = S.get("ratios_toppos", [])
        if ra and rt and rp:
            p = os.path.join(outdir, "c_ratio_pct.png")
            qa, qt, qp = _rank_pct(ra), _rank_pct(rt), _rank_pct(rp)
            if line_chart(p, [(qa, ACC, "ordinary"), (qt, PUR, "big accounts"),
                              (qp, TEAL, "big money")],
                          "Crowding score 0-100 vs each series' own month",
                          dlines=[(85, DN, "85 = crowded long"), (15, UP, "15 = crowded short")],
                          ylim=(0, 100)):
                add("c_ratio_pct.png", "Crowding score - all three ratios on one scale",
                    [f"ordinary accounts {qa[-1]:.0f} out of 100",
                     f"big traders' accounts {qt[-1]:.0f} out of 100",
                     f"big traders' position size {qp[-1]:.0f} out of 100"],
                    "The three ratios in the chart above each have a different 'normal' level, "
                    "so their raw numbers cannot be compared with each other. Here each one is "
                    "re-scored from 0 to 100 against its OWN last 30 days: 100 = the most "
                    "long-heavy it has been in a month, 0 = the least. Above 85 = crowded long "
                    "(bearish); below 15 = crowded short (squeeze fuel up).",
                    (f"All three sit high - {qa[-1]:.0f}, {qt[-1]:.0f} and {qp[-1]:.0f} out of "
                     f"100. Every group is leaning long at once, so the squeeze risk downward is "
                     f"broad rather than concentrated in one type of trader."
                     if min(qa[-1], qt[-1], qp[-1]) >= 85 else
                     # A headcount/size SPLIT is only a squeeze setup when the crowd is actually
                     # stretched. At 83 of 100 it is not, and calling that "setup for a squeeze
                     # down" contradicted the tile saying "no crowding signal" one inch away.
                     f"Ordinary accounts score {qa[-1]:.0f} out of 100 while big traders' "
                     f"position size scores {qp[-1]:.0f} - "
                     + (("lots of small longs with big money not behind them. Retail is long and "
                         "stretched, the money is not: that is the setup for a squeeze down."
                         if qa[-1] >= 85 else
                         f"lots of small longs with big money not behind them. But at "
                         f"{qa[-1]:.0f} of 100 the crowd is not stretched yet - under the 85 "
                         f"line - so this is a tilt to watch, not a squeeze setup.")
                        if qa[-1] > qp[-1] + 20 else
                        "no wide split between the crowd and the money, so there is no standout "
                        "contrarian read here.")))
    except Exception:
        pass

    # 9. open interest ------------------------------------------------------
    try:
        oi = S.get("oi_bn", [])
        p = os.path.join(outdir, "c_oi.png")
        if oi and line_chart(p, [(oi, AMBER, "open positions $bn")],
                             "Value of open leveraged positions, $bn (30 days)"):
            d1 = oi[-1] - oi[-2]
            add("c_oi.png", "Open interest - how much leverage is in the system",
                [f"${oi[-1]:.2f}B of positions open", f"1-day change {_usd(d1)}",
                 f"30-day range ${min(oi):.2f}B-${max(oi):.2f}B"],
                "Open interest is the total value of leveraged perpetual positions still open - "
                "in plain terms, how much borrowed money is sitting in the market right now. "
                "RISING = new positions opening (fuel for the current move). FALLING = positions "
                "closing, usually forced liquidation, which is deleveraging and not new shorts "
                "being opened.",
                (f"Open positions fell {_usd(d1, sign=False)} in a day to ${oi[-1]:.2f}B. Positions being "
                 f"closed - usually forced - is deleveraging, not new money betting on lower "
                 f"prices. That kind of flush usually marks a short-term bounce rather than a "
                 f"fresh leg down, so this is not the place to chase a short."
                 if d1 < 0 else
                 f"Open positions rose {_usd(d1, sign=False)} in a day to ${oi[-1]:.2f}B. Fresh leverage is "
                 f"entering, which adds fuel to the current move in whichever direction it is "
                 f"going - and makes the eventual liquidation bigger."))
    except Exception:
        pass

    # 10. volume ------------------------------------------------------------
    try:
        def klines(url):
            raw = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
            rows = json.loads(raw.decode())
            return [float(r[7]) / 1e9 for r in rows], [r[0] for r in rows]
        spt, _ = klines("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=60")
        per, ts = klines("https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1d&limit=60")
        from datetime import datetime as _dt, timezone as _tz
        lbl = [_dt.fromtimestamp(t / 1000, _tz.utc).strftime("%Y-%m-%d") for t in ts]
        p = os.path.join(outdir, "c_volume.png")
        if line_chart(p, [(spt, TEAL, "real spot"), (per, AMBER, "leveraged")],
                      "BTC volume per day, $bn - real vs leveraged", days=lbl):
            ratio = per[-1] / spt[-1] if spt[-1] else 0
            add("c_volume.png", "Volume - real trading vs leveraged betting",
                [f"real spot trading ${spt[-1]:.1f}B a day",
                 f"leveraged betting ${per[-1]:.1f}B a day",
                 f"{ratio:.1f}x more leveraged than real"],
                "Spot volume is coins actually bought and sold - delivery. Perpetual (perp) "
                "volume is leveraged bets on the price where nobody takes delivery. When perp "
                "dwarfs spot, price is being moved by borrowed money rather than by real "
                "demand, so moves are faster and fade quicker.",
                (f"For every $1 of real spot trading there is ${ratio:.1f} of leveraged betting. "
                 f"Price is being set by borrowed money, not by people buying coins - expect fast "
                 f"moves that fade, liquidation wicks that overshoot, and fakeouts through levels. "
                 f"Size positions down in this regime."
                 if ratio > 3 else
                 f"Leverage is unusually light: perp volume is only {ratio:.1f}x spot, so real "
                 f"buying and selling is driving price. Moves carry more weight here and are "
                 f"less likely to be a liquidation wick."))
    except Exception:
        pass

    return out


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    s = sys.argv[2] if len(sys.argv) > 2 else "/root/.hermes/state/digest_series.json"
    for m in build_all(d, s):
        print("rendered", m["file"], "-", m["title"])
