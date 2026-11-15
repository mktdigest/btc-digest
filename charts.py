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
    return f"{v:.2f}"


def _frame(title, w=W, h=H):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.text((20, 14), title, fill=FG, font=_font(23, True))
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


def line_chart(path, series, title, days=None, log=False, hlines=(), pad=(104, 26, 52, 44)):
    """series: list of (values, colour, label)."""
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    tf = (lambda v: math.log10(v)) if log else (lambda v: v)
    flat = [v for vals, *_ in series for v in vals if v is not None and (v > 0 if log else True)]
    if not flat:
        return False
    lo, hi = min(flat), max(flat)
    if lo == hi:
        lo, hi = lo * 0.99, hi * 1.01
    pad_y = (hi - lo) * 0.08
    lo, hi = lo - pad_y, hi + pad_y
    if not log and min(flat) >= 0 and lo < 0:
        lo = 0.0
    tlo, thi = tf(lo), tf(hi)
    _grid(d, x0, x1, y0, y1, lo, hi)

    for v, col in hlines:
        if hi >= v >= lo:
            y = y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo)
            d.line([(x0, y), (x1, y)], fill=col, width=2)

    for vals, col, *rest in series:
        pts = [(_mapx(i, len(vals), x0, x1), y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo))
               for i, v in enumerate(vals) if v is not None and (v > 0 if log else True)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=3, joint="curve")

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
               cum=False, unit="", cum_scale=1.0, deco=None):
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    if not values:
        return False
    vmax = max(abs(min(values)), abs(max(values))) or 1
    _grid(d, x0, x1, y0, y1, -vmax, vmax, deco=deco)
    mid = (y0 + y1) / 2
    n = len(values)
    for i, v in enumerate(values):
        h = (y1 - y0) / 2 * (abs(v) / vmax)
        x = _mapx(i, n, x0, x1)
        d.line([(x, mid), (x, mid - h if v > 0 else mid + h)],
               fill=pos if v > 0 else neg, width=int(max(2, (x1 - x0) / n * 0.7)))
    d.line([(x0, mid), (x1, mid)], fill=DIM)
    if cum:
        run, tot = [], 0.0
        for v in values:
            tot += v
            run.append(tot)
        cmin, cmax = min(run), max(run)
        span = (cmax - cmin) or 1
        pts = [(_mapx(i, n, x0, x1), y1 - (y1 - y0) * 0.9 * ((v - cmin) / span) - (y1 - y0) * 0.05)
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
                "MA200 is the line the short-fade in block [8] waits for. Price above an MA = "
                "that MA is support; below = it is resistance.",
                (f"Spot is below all three MAs ({', '.join(above) if above else 'none above'}), "
                 f"so every rally runs into overhead supply. MA200 is {abs(gap):.1f}% away."),
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
        if fr and bars_chart(p, [x * 100 for x in fr], "Perp funding rate, % per 8h (30d)"):
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
        if line_chart(p, [(ra, ACC, "all accounts"), (rt, PUR, "top acct"), (rp, TEAL, "top positions")],
                      "Binance long/short ratios (contrarian)", hlines=[(1, DIM)]):
            pa = sum(1 for x in ra if x <= ra[-1]) / len(ra) * 100
            pt = sum(1 for x in rt if x <= rt[-1]) / len(rt) * 100
            add("c_ratios.png", "Long/short ratios - who is crowded",
                [f"all acct {ra[-1]:.2f} ({pa:.0f}th pctile)", f"top acct {rt[-1]:.2f} ({pt:.0f}th pctile)",
                 f"top positions {rp[-1]:.2f}"],
                "Above 1 = more longs than shorts. Read it CONTRARIAN: a crowded long book is "
                "squeeze fuel DOWN; a crowded short book is squeeze fuel UP. When retail is "
                "long but top-trader POSITIONS are falling, smart money is exiting into retail "
                "strength. Mid-range percentile = no signal.",
                ("Crowd is crowded LONG (%.0fth pctile) - squeeze fuel down. Top-trader "
                 "positions at %.2f, so smart money is not adding." % (pa, rp[-1]) if pa >= 80
                 else ("Crowd crowded SHORT - squeeze fuel up." if pa <= 20
                       else "Positioning mid-range - no contrarian signal.")))
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
