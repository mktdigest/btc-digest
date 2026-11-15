"""Chart renderer for the digest page. PIL only - matplotlib is NOT installed here.

Everything is fed from the digest's series dump (digest_series.json) so charts never
re-fetch a rate-limited source. The one exception is stablecoin supply, which comes from
DeFiLlama and has no practical limit.
"""
import json
import math
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont

# ---- palette matches the page -------------------------------------------------
BG = (13, 17, 23)
GRID = (38, 44, 52)
FG = (230, 237, 243)
DIM = (139, 148, 153)
ACC = (88, 166, 255)
UP = (63, 185, 80)
DN = (248, 81, 73)
AMBER = (210, 153, 34)
PUR = (188, 140, 255)
TEAL = (57, 197, 187)

W, H = 880, 268
_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size=12):
    for p in _FONTS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fmt(v):
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.0f}M"
    if a >= 1e3:
        return f"{v / 1e3:.0f}k"
    if a >= 10:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _frame(title, w=W, h=H):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.text((12, 8), title, fill=FG, font=_font(14))
    return img, d


def _grid(d, x0, x1, y0, y1, lo, hi, n=4):
    for i in range(n + 1):
        f = i / n
        y = y1 - (y1 - y0) * f
        d.line([(x0, y), (x1, y)], fill=GRID)
        d.text((x0 - 6, y), _fmt(lo + (hi - lo) * f), fill=DIM, font=_font(10), anchor="rm")


def _xaxis(d, days, x0, x1, y1, ticks=4):
    if not days:
        return
    n = len(days)
    for i in range(ticks + 1):
        idx = min(n - 1, int(i * (n - 1) / ticks))
        x = x0 + (x1 - x0) * (idx / max(1, n - 1))
        d.text((x, y1 + 7), str(days[idx])[5:], fill=DIM, font=_font(9), anchor="ma")


def _mapx(i, n, x0, x1):
    return x0 + (x1 - x0) * (i / max(1, n - 1))


def line_chart(path, series, title, days=None, log=False, hlines=(), pad=(64, 16, 32, 32)):
    """series: list of (values, colour, label). Draws one or more lines."""
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    tf = (lambda v: math.log10(v)) if log else (lambda v: v)
    flat = [v for vals, *_ in series for v in vals
            if v is not None and (v > 0 if log else True)]
    if not flat:
        return False
    lo, hi = min(flat), max(flat)
    if lo == hi:
        lo, hi = lo * 0.99, hi * 1.01
    pad_y = (hi - lo) * 0.08
    lo, hi = lo - pad_y, hi + pad_y
    if not log and min(flat) >= 0 and lo < 0:
        lo = 0.0          # don't draw a negative axis under volume-style data
    tlo, thi = tf(lo), tf(hi)
    _grid(d, x0, x1, y0, y1, lo, hi)

    for v, col in hlines:
        if hi >= v >= lo:
            y = y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo)
            d.line([(x0, y), (x1, y)], fill=col, width=1)

    for vals, col, *rest in series:
        pts = [(_mapx(i, len(vals), x0, x1),
                y1 - (y1 - y0) * (tf(v) - tlo) / (thi - tlo))
               for i, v in enumerate(vals) if v is not None and (v > 0 if log else True)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2, joint="curve")

    # legend, top-right
    lx = x1
    for vals, col, *rest in reversed(series):
        lbl = rest[0] if rest else ""
        if lbl:
            d.text((lx, 10), lbl, fill=col, font=_font(10), anchor="ra")
            lx -= int(d.textlength(lbl, font=_font(10))) + 16
    _xaxis(d, days or [], x0, x1, y1)
    img.save(path)
    return True


def bars_chart(path, values, title, days=None, pad=(64, 16, 32, 32), pos=UP, neg=DN,
               cum=False, unit=""):
    pl, pr, pt, pb = pad
    img, d = _frame(title)
    x0, x1, y0, y1 = pl, W - pr, pt, H - pb
    if not values:
        return False
    vmax = max(abs(min(values)), abs(max(values))) or 1
    _grid(d, x0, x1, y0, y1, -vmax, vmax)
    mid = (y0 + y1) / 2
    n = len(values)
    bw = max(1, (x1 - x0) / n * 0.72)
    for i, v in enumerate(values):
        h = (y1 - y0) / 2 * (abs(v) / vmax)
        x = _mapx(i, n, x0, x1)
        d.line([(x, mid), (x, mid - h if v > 0 else mid + h)],
               fill=pos if v > 0 else neg, width=int(max(1, bw)))
    d.line([(x0, mid), (x1, mid)], fill=GRID)
    if cum:
        run, tot = [], 0.0
        for v in values:
            tot += v
            run.append(tot)
        cmin, cmax = min(run), max(run)
        span = (cmax - cmin) or 1
        pts = [(_mapx(i, n, x0, x1), y1 - (y1 - y0) * 0.9 * ((v - cmin) / span) - (y1 - y0) * 0.05)
               for i, v in enumerate(run)]
        d.line(pts, fill=AMBER, width=2, joint="curve")
        d.text((x1, 10), f"cumulative {_fmt(tot)}{unit}", fill=AMBER, font=_font(10), anchor="ra")
    _xaxis(d, days or [], x0, x1, y1)
    img.save(path)
    return True


def urpd_chart(path, buckets, spot, title):
    """Horizontal supply ladder: price on Y, share of supply on X."""
    img, d = _frame(title, h=max(H, 380))
    n = len(buckets)
    if not n:
        return False
    pl, pr, pt, pb = 64, 92, 32, 30
    x0, x1, y0, y1 = pl, W - pr, pt, img.height - pb
    lo = min(b["lo"] for b in buckets)
    hi = max(b["hi"] for b in buckets)
    pmax = max(b["pct"] for b in buckets) or 1
    for i in range(5):
        f = i / 4
        y = y1 - (y1 - y0) * f
        d.line([(x0, y), (x1, y)], fill=GRID)
        d.text((x0 - 6, y), _fmt(lo + (hi - lo) * f), fill=DIM, font=_font(10), anchor="rm")
    bh = max(2, (y1 - y0) / n * 0.74)
    for b in buckets:
        mid = (b["lo"] + b["hi"]) / 2
        y = y1 - (y1 - y0) * (mid - lo) / (hi - lo)
        w = (x1 - x0) * (b["pct"] / pmax)
        above = b["lo"] >= spot
        col = DN if above else ACC
        d.line([(x0, y), (x0 + w, y)], fill=col, width=int(bh))
        if b["pct"] >= pmax * 0.35:
            d.text((x0 + w + 5, y), f"{b['pct']:.1f}%", fill=DIM, font=_font(9), anchor="lm")
    if lo <= spot <= hi:
        ys = y1 - (y1 - y0) * (spot - lo) / (hi - lo)
        d.line([(x0, ys), (x1, ys)], fill=AMBER, width=1)
        d.text((x1 + 4, ys), f"spot {_fmt(spot)}", fill=AMBER, font=_font(10), anchor="lm")
    d.text((12, img.height - 20), "bars above spot = overhead supply (resistance);  below = support",
           fill=DIM, font=_font(9))
    img.save(path)
    return True


def stablecoin_series(days=120):
    """USDT(1) + USDC(2) combined circulating, USD."""
    out = {}
    for cid in (1, 2):
        u = f"https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={cid}"
        raw = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
        for r in json.loads(raw.decode()):
            v = (r.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if v:
                out.setdefault(r["date"], {}).setdefault(cid, v)
    rows = sorted((int(d), v) for d, v in out.items() if len(v) == 2)
    rows = rows[-days:]
    from datetime import datetime, timezone
    labels = [datetime.fromtimestamp(d, timezone.utc).strftime("%Y-%m-%d") for d, _ in rows]
    usdt = [v[1] / 1e9 for _, v in rows]
    usdc = [v[2] / 1e9 for _, v in rows]
    return labels, usdt, usdc


def build_all(outdir, series_path):
    """Render every chart. Returns metadata for the page. Never raises."""
    with open(series_path) as fh:
        S = json.load(fh)
    os.makedirs(outdir, exist_ok=True)
    out = []

    def add(fn, title, caption):
        out.append({"file": fn, "title": title, "caption": caption})

    days = S.get("days", [])
    close = S.get("cb_close", [])
    spot = S.get("spot") or (close[-1] if close else 0)

    # 1. price + MAs
    try:
        def ma(vals, n):
            r = [None] * len(vals)
            for i in range(n - 1, len(vals)):
                r[i] = sum(vals[i - n + 1:i + 1]) / n
            return r
        p = os.path.join(outdir, "c_price.png")
        if line_chart(p, [(close[-400:], FG, "BTC"), (ma(close, 10)[-400:], TEAL, "MA10"),
                          (ma(close, 50)[-400:], ACC, "MA50"), (ma(close, 200)[-400:], PUR, "MA200")],
                      "BTC price vs MA10 / MA50 / MA200  (log)",
                      days=days[-400:], log=True):
            add("c_price.png", "Price vs moving averages",
                "A bounce in a downtrend stalls at the first MA above it. MA200 is the short-fade trigger level.")
    except Exception:
        pass

    # 2. premium
    try:
        prem = S.get("premium", [])
        p = os.path.join(outdir, "c_premium.png")
        m30 = [sum(prem[max(0, i - 29):i + 1]) / len(prem[max(0, i - 29):i + 1]) for i in range(len(prem))]
        if line_chart(p, [(prem[-240:], ACC, "daily"), (m30[-240:], AMBER, "30d mean")],
                      "Coinbase premium % (US vs global bid)", days=days[-240:], hlines=[(0, GRID)]):
            add("c_premium.png", "Coinbase premium",
                "Above 0 = US paying up. A long run below 0 is a regime: the US bid is missing.")
    except Exception:
        pass

    # 3. RSI
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
        p = os.path.join(outdir, "c_rsi.png")
        if line_chart(p, [(rsi(close, 6)[-240:], TEAL, "RSI6"), (rsi(close, 14)[-240:], ACC, "RSI14"),
                          (rsi(close, 24)[-240:], PUR, "RSI24")],
                      "RSI(6 / 14 / 24) on daily closes", days=days[-240:],
                      hlines=[(70, DN), (30, UP)]):
            add("c_rsi.png", "RSI momentum",
                "Red 70 / green 30. Fast below slow = momentum deteriorating, bounces get sold.")
    except Exception:
        pass

    # 4. URPD
    try:
        ub = S.get("urpd", [])
        p = os.path.join(outdir, "c_urpd.png")
        stale = "  - CACHED, bitcoin-data quota" if S.get("urpd_stale") else ""
        if ub and urpd_chart(p, ub, spot, f"URPD - supply by cost basis ({S.get('urpd_day','')}){stale}"):
            add("c_urpd.png", "URPD / cost-basis ladder",
                "Where coins last moved. Clusters above spot are overhead resistance."
                + (" Cached from the last good fetch - bitcoin-data caps at 10 requests/hour."
                   if stale else ""))
    except Exception:
        pass

    # 5. ETF flows
    try:
        ef = S.get("etf_flow", [])
        ed = S.get("etf_days", [])
        p = os.path.join(outdir, "c_etf.png")
        if ef and bars_chart(p, ef[-60:], "US spot BTC ETF net flow, daily ($m)", days=ed[-60:], cum=True, unit="m"):
            add("c_etf.png", "ETF net flows",
                "Green = creations, red = redemptions. The amber line is cumulative - direction matters more than any day.")
    except Exception:
        pass

    # 6. stablecoins
    try:
        sd, usdt, usdc = stablecoin_series(120)
        p = os.path.join(outdir, "c_stables.png")
        if line_chart(p, [(usdt, TEAL, "USDT"), (usdc, ACC, "USDC")],
                      "Stablecoin supply, $bn (is capital coming back?)", days=sd):
            add("c_stables.png", "Stablecoin supply",
                "Expanding = fresh fiat entering crypto. Contracting = capital leaving, not waiting.")
    except Exception:
        pass

    # 7. funding
    try:
        fr = S.get("funding", [])
        p = os.path.join(outdir, "c_funding.png")
        if fr and bars_chart(p, [x * 100 for x in fr], "Perp funding rate, % per 8h (30d)"):
            add("c_funding.png", "Funding rate",
                "Positive = longs pay shorts = leveraged longs crowded (bearish tilt). Negative = the reverse.")
    except Exception:
        pass

    # 8. long/short ratios
    try:
        ra = S.get("ratios_all", [])
        rt = S.get("ratios_topacct", [])
        rp = S.get("ratios_toppos", [])
        p = os.path.join(outdir, "c_ratios.png")
        if line_chart(p, [(ra, ACC, "all accounts"), (rt, PUR, "top acct"), (rp, TEAL, "top positions")],
                      "Binance long/short ratios (contrarian)", hlines=[(1, GRID)]):
            add("c_ratios.png", "Long/short ratios",
                "Above 1 = more longs than shorts. Contrarian: a crowded long book is squeeze fuel down.")
    except Exception:
        pass

    # 9. open interest
    try:
        oi = S.get("oi_bn", [])
        p = os.path.join(outdir, "c_oi.png")
        if oi and line_chart(p, [(oi, AMBER, "OI $bn")],
                             "Binance BTC perp open interest, $bn (30d)"):
            add("c_oi.png", "Open interest",
                "Rising = new positions. Falling = deleveraging (liquidation), not necessarily new shorts.")
    except Exception:
        pass

    # 10. spot vs perp volume
    try:
        def klines(url, lim=60):
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
            add("c_volume.png", "Volume: spot vs perp",
                "Perp volume dwarfing spot means leverage is driving price, and moves are more fragile.")
    except Exception:
        pass

    return out


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    s = sys.argv[2] if len(sys.argv) > 2 else "/root/.hermes/state/digest_series.json"
    for m in build_all(d, s):
        print("rendered", m["file"], "-", m["title"])
