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
        if line_chart(p, [(close[-400:], FG, "BTC"), (m10[-400:], TEAL, "MA10"),
                          (m50[-400:], ACC, "MA50"), (m200[-400:], PUR, "MA200")],
                      "BTC price vs MA10 / MA50 / MA200  (log scale)", days=days[-400:], log=True):
            a200 = m200[-1] or spot
            gap = (spot - a200) / a200 * 100
            above = [n for n, m in (("MA10", m10[-1]), ("MA50", m50[-1]), ("MA200", m200[-1]))
                     if m and spot > m]
            add("c_price.png", "Price vs moving averages",
                [f"spot ${spot:,.0f}", f"MA10 ${m10[-1]:,.0f}", f"MA50 ${m50[-1]:,.0f}",
                 f"MA200 ${m200[-1]:,.0f}", f"vs MA200 {gap:+.1f}%"],
                "A bounce in a downtrend stalls at the FIRST moving average above it. "
                "MA200 is the line the short-fade block waits for. Price above an MA = "
                "that MA is support; below = it is resistance.",
                (f"Spot is below all three MAs ({', '.join(above) if above else 'none above'}), "
                 f"so every rally runs into overhead supply. MA200 is {abs(gap):.1f}% away."),
                "wide")
    except Exception:
        pass

    # 1b. BTC vs dollar strength (DXY) ---------------------------------------
    try:
        dxy = S.get("dxy", [])
        if dxy and close and len(dxy) >= 2:
            n = min(len(dxy), len(close))
            dxy, px, dys = dxy[-n:], close[-n:], (days or [])[-n:]
            # Index BOTH to 100 at the left edge. A dual axis (BTC ~$65k vs DXY ~99) invents
            # crossovers that look meaningful and are pure scale artefacts; comparing percentage
            # moves from a common base is the honest way to show correlation.
            b = [v / px[0] * 100 for v in px]
            q = [v / dxy[0] * 100 for v in dxy]
            p = os.path.join(outdir, "c_dxy.png")
            if line_chart(p, [(b, AMBER, "BTC"), (q, ACC, "DXY (ECB-reconstructed)")],
                          "BTC vs DXY - both indexed to 100 at start",
                          days=dys, dlines=[(100, DIM, "start = 100")], nice=True):
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
                add("c_dxy.png", "Dollar strength - macro headwind or tailwind",
                    [f"DXY {dxy[-1]:.2f}", f"DXY {q[-1] - 100:+.1f}%", f"BTC {b[-1] - 100:+.1f}%",
                     f"daily corr {r:+.2f}"],
                    "DXY is the US dollar against six currencies; EUR alone is 57.6% of it. Both "
                    "lines are indexed to 100 at the left edge, so this compares PERCENTAGE moves, "
                    "not price levels. The usual regime relationship is inverse - dollar up, BTC "
                    "down. The correlation shown is on DAILY RETURNS, not price levels: two "
                    "trending series can look tightly linked while having no day-to-day link at "
                    "all. A headwind/tailwind gauge, not a timing trigger. Rebuilt from ECB "
                    "reference rates, so it can sit ~0.1-0.2% off the ICE print.",
                    (f"Inverse and tight (daily corr {r:+.2f}): dollar moves are pressuring BTC "
                     f"day to day." if r <= -0.3 else
                     f"Moving together (daily corr {r:+.2f}): the usual inverse has broken - BTC "
                     f"is trading on its own flows." if r >= 0.3 else
                     f"Weak day-to-day link (corr {r:+.2f}) even though BTC is {b[-1] - 100:+.0f}% "
                     f"and DXY {q[-1] - 100:+.0f}% over the window - so the inverse is a slow "
                     f"regime drift, not a signal you can trade off."),
                    "wide")
    except Exception:
        pass

    # 2. premium ------------------------------------------------------------
    try:
        prem = S.get("premium", [])
        p = os.path.join(outdir, "c_premium.png")
        m30 = [sum(prem[max(0, i - 29):i + 1]) / len(prem[max(0, i - 29):i + 1]) for i in range(len(prem))]
        if line_chart(p, [(prem[-240:], ACC, "daily"), (m30[-240:], AMBER, "30d mean")],
                      "Coinbase premium % - is the US paying up?", days=days[-240:],
                      hlines=[(0, DIM)]):
            streak = 0
            for v in reversed(prem):
                if v < 0:
                    streak += 1
                else:
                    break
            add("c_premium.png", "Coinbase premium (US vs global bid)",
                [f"live {prem[-1]:+.3f}%", f"30d mean {m30[-1]:+.3f}%", f"{streak}d negative"],
                "Above the zero line = US buyers paying more than global = US demand leading. "
                "A run of 20+ days below zero is a REGIME, not noise - it means the deepest "
                "pool of buyers is simply absent.",
                ("US bid missing for %d straight days - the structural buyer is not there."
                 % streak) if streak >= 20 else "Premium near neutral - no strong US signal.")
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
        if line_chart(p, [(r6[-240:], TEAL, "RSI6"), (r14[-240:], ACC, "RSI14"), (r24[-240:], PUR, "RSI24")],
                      "RSI(6 / 14 / 24) on daily closes", days=days[-240:],
                      hlines=[(70, DN), (30, UP)]):
            v6, v14, v24 = r6[-1], r14[-1], r24[-1]
            tail = [x for x in r14 if x is not None]
            pct = sum(1 for x in tail if x <= v14) / len(tail) * 100
            if v14 <= 30:
                state = "oversold - capitulation zone, where bounces historically start"
            elif v14 >= 70:
                state = "overbought - stretched, mean-reversion risk"
            else:
                state = "neutral - no momentum extreme"
            add("c_rsi.png", "RSI momentum",
                [f"RSI6 {v6:.1f}", f"RSI14 {v14:.1f}", f"RSI24 {v24:.1f}",
                 f"RSI14 1y pctile {pct:.0f}%"],
                "Red 70 / green 30. Fast line above slow = momentum improving; fast BELOW slow = "
                "momentum deteriorating and bounces are being sold. This describes force - it "
                "does not trigger a trade on its own.",
                f"RSI14 {v14:.1f} is {state}. " +
                ("Fast < slow: momentum still deteriorating." if v6 < v24
                 else "Fast > slow: short-term momentum leading."))
    except Exception:
        pass

    # 4. URPD ---------------------------------------------------------------
    try:
        ub = S.get("urpd", [])
        p = os.path.join(outdir, "c_urpd.png")
        stale = "  [cached - bitcoin-data quota]" if S.get("urpd_stale") else ""
        if ub and urpd_chart(p, ub, spot, f"URPD - where supply sits by cost basis ({S.get('urpd_day','')}){stale}"):
            top = sorted(ub, key=lambda b: -b["pct"])[:3]
            below = sum(b["pct"] for b in ub if b["hi"] <= spot)
            above = sum(b["pct"] for b in ub if b["lo"] >= spot)
            add("c_urpd.png", "URPD / cost-basis ladder",
                [f"top cluster ${top[0]['lo']//1000}k-{top[0]['hi']//1000}k ({top[0]['pct']:.1f}%)",
                 f"above spot {above:.1f}%", f"below spot {below:.1f}%"],
                "Each bar is how much supply last moved at that price. Bars ABOVE spot are "
                "holders who are underwater - they sell into rallies and cap them. Bars BELOW "
                "spot are holders in profit who tend to hold. The amber line is today's price.",
                f"Only {below:.1f}% of supply sits below spot versus {above:.1f}% above it - "
                "thin support underneath, heavy overhead supply to chew through.")
    except Exception:
        pass

    # 5. ETF flows ----------------------------------------------------------
    try:
        ef = S.get("etf_flow", [])
        ed = S.get("etf_days", [])
        p = os.path.join(outdir, "c_etf.png")
        if ef and bars_chart(p, ef[-60:], "US spot BTC ETF net flow, daily ($m)", days=ed[-60:],
                             cum=True, unit="", cum_scale=1e6):
            s5 = sum(ef[-5:]); s30 = sum(ef[-30:]); last = ef[-1]
            add("c_etf.png", "ETF net flows",
                [f"latest ${last:+,.0f}m", f"5d ${s5:+,.0f}m", f"30d ${s30:+,.0f}m"],
                "Green bars = creations (money in), red = redemptions (money out). Read the "
                "SUMS, never a single day - one day is noise, the 30d line is the trend. The "
                "amber line is cumulative.",
                (f"Money still leaving: ${s30:+,.0f}m over 30 days." if s30 < 0
                 else f"Money returning: ${s30:+,.0f}m over 30 days."))
    except Exception:
        pass

    # 6. stablecoins --------------------------------------------------------
    try:
        sd, usdt, usdc = stablecoin_series(120)
        p = os.path.join(outdir, "c_stables.png")
        if line_chart(p, [(usdt, TEAL, "USDT"), (usdc, ACC, "USDC")],
                      "Stablecoin supply, $bn - is capital coming back?", days=sd):
            comb = usdt[-1] + usdc[-1]
            d7 = comb - (usdt[-8] + usdc[-8]) if len(usdt) > 8 else 0
            d30 = comb - (usdt[-31] + usdc[-31]) if len(usdt) > 31 else 0
            add("c_stables.png", "Stablecoin supply",
                [f"combined ${comb:,.1f}bn", f"7d {d7:+,.2f}bn", f"30d {d30:+,.2f}bn"],
                "Stablecoins are the dry powder of crypto. Expanding supply = fresh fiat "
                "entering the system. Contracting = capital leaving crypto entirely - it is "
                "NOT money sitting on the sidelines waiting.",
                (f"Contracting on both windows ({d30:+,.2f}bn over 30d) - capital is exiting, "
                 "not waiting." if d30 < 0 and d7 < 0 else
                 ("Expanding on both windows - capital returning." if d30 > 0 and d7 > 0
                  else "Mixed: 7d and 30d disagree, no clean signal yet.")))
    except Exception:
        pass

    # 7. funding ------------------------------------------------------------
    try:
        fr = S.get("funding", [])
        p = os.path.join(outdir, "c_funding.png")
        if fr and bars_chart(p, [x * 100 for x in fr], "Perp funding rate, % per 8h (30d)",
                             symmetric=False):
            now_r = fr[-1] * 100
            avg = sum(fr) / len(fr) * 100
            ann = avg * 3 * 365
            posn = sum(1 for x in fr if x > 0) / len(fr) * 100
            add("c_funding.png", "Funding rate - what leverage costs",
                [f"now {now_r:+.4f}%/8h", f"30d avg -> {ann:+.1f}% APR", f"positive {posn:.0f}% of time"],
                "Funding is the 8-hourly payment between longs and shorts. Positive = LONGS pay "
                "shorts = leveraged longs are the crowded side (bearish tilt, dips get flushed). "
                "Negative = shorts pay, meaning crowded shorts and squeeze fuel UP - hostile to "
                "a short.",
                ("Longs still paying - leveraged longs have NOT capitulated, so dips get "
                 "flushed." if avg > 0 else
                 "Shorts are paying - crowded short positioning is squeeze fuel upward."))
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
                (med(ra), ACC, f"all-acct median {med(ra):.2f}"),
                (med(rt), PUR, f"top-acct median {med(rt):.2f}"),
                (med(rp), TEAL, f"top-pos median {med(rp):.2f}")]
        if line_chart(p, [(ra, ACC, "all accounts"), (rt, PUR, "top acct"), (rp, TEAL, "top positions")],
                      "Binance long/short ratios (contrarian)", dlines=refs):
            pa = sum(1 for x in ra if x <= ra[-1]) / len(ra) * 100
            pt = sum(1 for x in rt if x <= rt[-1]) / len(rt) * 100
            add("c_ratios.png", "Long/short ratios - who is crowded",
                [f"all acct {ra[-1]:.2f} ({_ord(pa)} pctile)", f"top acct {rt[-1]:.2f} ({_ord(pt)} pctile)",
                 f"top positions {rp[-1]:.2f}"],
                "Above 1 = more longs than shorts. Read it CONTRARIAN: a crowded long book is "
                "squeeze fuel DOWN; a crowded short book is squeeze fuel UP. When retail is "
                "long but top-trader POSITIONS are falling, smart money is exiting into retail "
                "strength. Mid-range percentile = no signal.",
                ("Crowd is crowded LONG (%s pctile) - squeeze fuel down. Top-trader "
                 "positions at %.2f, so smart money is not adding." % (_ord(pa), rp[-1]) if pa >= 80
                 else ("Crowd crowded SHORT - squeeze fuel up." if pa <= 20
                       else "Positioning mid-range - no contrarian signal.")))
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
            if line_chart(p, [(qa, ACC, "all accounts"), (qt, PUR, "top acct"), (qp, TEAL, "top positions")],
                          "Long/short ratios as own-window percentiles",
                          dlines=[(85, DN, "85 = crowded long"), (15, UP, "15 = crowded short")],
                          ylim=(0, 100)):
                add("c_ratio_pct.png", "Long/short crowding - apples to apples",
                    [f"all acct {_ord(qa[-1])} pctile", f"top acct {_ord(qt[-1])} pctile",
                     f"top pos {_ord(qp[-1])} pctile"],
                    "Same data as the chart above, re-scored so the three are comparable. 100 means "
                    "that series is at its most crowded in 30 days, 0 its least. Above 85 = crowded "
                    "long (contrarian bearish); below 15 = crowded short (squeeze fuel up).",
                    ("All three pinned high - the whole book is leaning long, squeeze risk is broad."
                     if min(qa[-1], qt[-1], qp[-1]) >= 80 else
                     f"Headcount {_ord(qa[-1])} vs position size {_ord(qp[-1])} - "
                     + ("many small longs, not big conviction." if qa[-1] > qp[-1] + 20
                        else "no wide split between crowd and size.")))
    except Exception:
        pass

    # 9. open interest ------------------------------------------------------
    try:
        oi = S.get("oi_bn", [])
        p = os.path.join(outdir, "c_oi.png")
        if oi and line_chart(p, [(oi, AMBER, "OI $bn")], "Binance BTC perp open interest, $bn (30d)"):
            d1 = oi[-1] - oi[-2]
            add("c_oi.png", "Open interest - how much leverage exists",
                [f"${oi[-1]:.2f}bn", f"1d {d1:+.2f}bn", f"30d range {min(oi):.2f}-{max(oi):.2f}"],
                "Total value of open perp positions. RISING = fresh positions entering (trend "
                "fuel). FALLING = positions closing, usually forced liquidation - that is "
                "deleveraging, not new shorts, and it often marks a local bounce.",
                (f"OI draining ({d1:+.2f}bn) - deleveraging/liquidation, not fresh shorts."
                 if d1 < 0 else f"OI building ({d1:+.2f}bn) - fresh leverage entering."))
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
        if line_chart(p, [(spt, TEAL, "spot"), (per, AMBER, "perp")],
                      "BTC volume, $bn/day - spot vs perpetual", days=lbl):
            ratio = per[-1] / spt[-1] if spt[-1] else 0
            add("c_volume.png", "Volume: spot vs perp",
                [f"spot ${spt[-1]:.1f}bn", f"perp ${per[-1]:.1f}bn", f"perp/spot {ratio:.1f}x"],
                "Spot volume is real buying and selling. Perp volume is leveraged bets on "
                "price. When perp dwarfs spot, price is being moved by leverage rather than "
                "by people taking delivery - moves are faster and less durable.",
                (f"Perp is {ratio:.1f}x spot - leverage-dominated tape, expect fragile moves "
                 "and liquidation wicks." if ratio > 3 else
                 f"Perp {ratio:.1f}x spot - unusually spot-led, moves carry more weight."))
    except Exception:
        pass

    return out


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    s = sys.argv[2] if len(sys.argv) > 2 else "/root/.hermes/state/digest_series.json"
    for m in build_all(d, s):
        print("rendered", m["file"], "-", m["title"])
