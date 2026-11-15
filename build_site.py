#!/usr/bin/env python3
"""Build the static, shareable BTC-digest page (GitHub Pages ready).

Layout: a glance dashboard (verdict + KPI tiles + the digest in priority sections),
then tabs for Charts / Reference / Evidence / Guide so the page is never one long scroll.

Usage:  python3 build_site.py [path-to-digest.txt]
"""
import html
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import charts as chartmod  # noqa: E402

SCRIPTS = "/root/.hermes/scripts"
CHART_DIR = "/root/.hermes/state/charts"
SERIES_PATH = "/root/.hermes/state/digest_series.json"
DIGEST = os.path.join(SCRIPTS, "coinbase_premium_daily.py")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--dim:#8b949e;
--accent:#58a6ff;--green:#3fb950;--red:#f85149;--amber:#d29922;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
body{background:var(--bg);color:var(--txt);font:18px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased;padding:0 0 70px}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header{padding:36px 0 0}
h1{font-size:38px;font-weight:680;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:17.5px;margin-top:8px}
h2{font-size:26px;font-weight:650;margin:34px 0 6px;letter-spacing:-.01em}
h3{font-size:22px;font-weight:650;margin:0 0 12px;color:var(--accent);line-height:1.35}
h4{font-size:20px;margin:0 0 10px;color:var(--txt)}
p{color:#c9d1d9;margin:9px 0}
p.note{color:var(--dim);font-size:16.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;margin:13px 0}
.card pre{font-family:var(--mono);font-size:16px;line-height:1.75;white-space:pre-wrap;word-break:break-word;color:#c9d1d9}
.verdict{color:var(--green);font-weight:600}
.alert{color:var(--amber);font-weight:650}
.watch{color:var(--accent)}
table{width:100%;border-collapse:collapse;margin:13px 0;font-size:16.5px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:10px 13px;text-align:left;white-space:nowrap}
th{background:#1c2128;font-weight:650;font-size:15px;color:#c9d1d9}
td.num{font-family:var(--mono);text-align:right}
.neg{color:var(--red);font-weight:600}.pos{color:var(--green);font-weight:600}
.warn{color:var(--amber);font-weight:650}
img.chart{width:100%;border:1px solid var(--line);border-radius:10px;margin:13px 0;display:block}
.callout{border-left:3px solid var(--amber);background:#1c1a12;border-radius:6px;padding:11px 15px;margin:13px 0}
.callout p{margin:4px 0;color:#e6d7a8}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:15px}
code{font-family:var(--mono);background:#1c2128;padding:2px 6px;border-radius:4px;font-size:15px}
.hrow{font-family:var(--mono);font-size:15.5px;color:var(--dim);margin:3px 0}
.verdict-card{background:#0d2818;border:1px solid #238636;border-radius:9px;padding:13px 17px;
margin:18px 0 4px;font-size:17px;font-weight:650;color:#7ee787}
h3.sec{font-size:27px;color:#fff;font-weight:700;margin:48px 0 5px;padding-top:22px;
border-top:1px solid var(--line);letter-spacing:-.02em;line-height:1.28}
p.sdesc{color:var(--dim);font-size:17.5px;margin:6px 0 18px;font-style:italic;line-height:1.6}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0 0}
@media(max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:14px 16px}
.kpi .k{display:block;font-size:14px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;font-weight:650}
.kpi .v{display:block;font-size:26px;font-weight:650;font-family:var(--mono);margin-top:6px;line-height:1.15}
.kpi .d{display:block;font-size:16.5px;font-weight:650;font-family:var(--mono);margin-top:4px}
.kpi .n{display:block;font-size:14.5px;color:var(--dim);margin-top:5px;line-height:1.45}
.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:22px 0 0;border-bottom:1px solid var(--line)}
.tabs button{background:none;border:none;border-bottom:2px solid transparent;color:var(--dim);
font:inherit;font-size:17px;padding:11px 18px;cursor:pointer;font-weight:600}
.tabs button:hover{color:var(--txt)}
.tabs button.on{color:var(--accent);border-bottom-color:var(--accent)}
.tab{display:none}.tab.on{display:block}
.cgrid{display:grid;grid-template-columns:1fr;gap:22px;margin-top:18px}
.ccard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px}
.ccard img{width:100%;border-radius:8px;display:block;margin:14px 0}
.ccard p{font-size:16.5px;color:#c9d1d9;margin:10px 0 0}
.ccard.wide{grid-column:1/-1}
.cnow{display:flex;flex-wrap:wrap;gap:9px;margin:4px 0 4px}
.chip{background:#1c2128;border:1px solid var(--line);border-radius:7px;padding:7px 14px;
font-family:var(--mono);font-size:17px;font-weight:650;color:#e6edf3}
.cuse{color:var(--dim);font-size:16.5px}
.cverdict{color:#7ee787;font-weight:650;font-size:17px;margin-top:12px}
@media(max-width:600px){h1{font-size:23px}.wrap{padding:0 15px}th,td{padding:6px 8px;font-size:13px}}
"""

EVIDENCE = {
    "rsi_rules": [
        ("Baseline (any day)", 980, "+1.03%", "49%"),
        ("RSI(6) crosses above RSI(14)", 102, "+1.2%", "46%"),
        ("RSI(14) crosses back above 50", 48, "+0.6%", "46%"),
        ("RSI(6) crosses above RSI(24)", 85, "+2.0%", "47%"),
    ],
    "divergence": [
        ("Baseline (any day)", 3358, "+3.11%", "53%"),
        ("Plain bullish divergence", 31, "+1.08%", "55%"),
        ("Bullish + RSI14&lt;35 at 2nd low", 12, "+7.92%", "67%"),
        ("Bearish divergence", 41, "+5.75%", "54%"),
    ],
    "short_fade": [
        ("TP -3% before SL +5%", 118, "+0.12% EV", "64%"),
        ("TP -5% before SL +5%", 118, "-0.20% EV", "48%"),
        ("TP -7% before SL +5%", 118, "-0.44% EV", "38%"),
        ("TP -7% before SL +7%", 118, "-1.12% EV", "42%"),
        ("TP -10% before SL +7%", 118, "-1.36% EV", "28%"),
    ],
    "long_bounce": [
        ("+3% before -5%", 41, "-1.08% EV", "49%"),
        ("+5% before -5%", 41, "-0.40% EV", "46%"),
        ("+7% (->70K) before -5%", 41, "-0.92% EV", "34%"),
        ("+7% before -7%", 41, "-0.60% EV", "37%"),
        ("+10% before -7%", 41, "-1.15% EV", "15%"),
    ],
}


def run_digest():
    p = subprocess.run([sys.executable, DIGEST], capture_output=True, text=True, timeout=600)
    if not p.stdout.strip():
        raise RuntimeError(f"digest produced no output; stderr={p.stderr[:400]}")
    return p.stdout


def esc(s):
    return html.escape(s)


def fmt_line(line):
    e = esc(line.rstrip())
    st = line.strip()
    if st.startswith("->"):
        return f'<span class="verdict">{e}</span>'
    if st.startswith("watch"):
        return f'<span class="watch">{e}</span>'
    if "**" in line or "ARMED" in line:
        return f'<span class="alert">{e}</span>'
    return e


def render_blocks(lines):
    blocks, cur = [], None
    for l in lines:
        if re.match(r"^\[[0-9+]+[a-z]?\]", l):
            if cur:
                blocks.append(cur)
            cur = [l]
        elif cur is not None:
            if l.strip() == "":
                blocks.append(cur)
                cur = None
            else:
                cur.append(l)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        title, body = b[0], b[1:]
        if not any(x.strip() for x in body):
            continue
        out.append(f'<div class="card"><h3>{esc(title)}</h3><pre>'
                   + "\n".join(fmt_line(l) for l in body) + "</pre></div>")
    return "\n".join(out)


def render_digest(raw):
    lines = [l for l in raw.splitlines() if not l.startswith("MEDIA:")]
    bar = "=" * 70
    head, sections, i = [], [], 0
    while i < len(lines):
        if lines[i].strip() == bar:
            title = lines[i + 1] if i + 1 < len(lines) else ""
            desc, j = [], i + 2
            while j < len(lines) and lines[j].strip() != bar:
                if lines[j].strip():
                    desc.append(lines[j].strip())
                j += 1
            sections.append({"title": title, "desc": desc, "body": []})
            i = j + 1
            continue
        (sections[-1]["body"] if sections else head).append(lines[i])
        i += 1
    out = []
    for l in [x for x in head if x.strip()]:
        if l.startswith("VERDICT:"):
            continue                       # rendered as its own tile in the header
        out.append(f'<div class="hrow">{esc(l)}</div>')
    for s in sections:
        out.append(f'<h3 class="sec">{esc(s["title"])}</h3>')
        for d in s["desc"]:
            out.append(f'<p class="sdesc">{esc(d)}</p>')
        if s["title"].startswith("LEGEND"):
            body = "\n".join(l for l in s["body"] if l.strip())
            out.append(f'<div class="card"><pre>{esc(body)}</pre></div>')
        else:
            out.append(render_blocks(s["body"]))
    return "\n".join(out)


def ev_table(rows):
    h = ['<table><thead><tr><th>Rule / target</th><th>n</th><th>Forward / EV</th><th>Hit rate</th></tr></thead><tbody>']
    for name, n, fwd, win in rows:
        cls = "neg" if fwd.startswith("-") else ("pos" if fwd.startswith("+") else "")
        h.append(f'<tr><td>{name}</td><td class="num">{n}</td>'
                 f'<td class="num {cls}">{fwd}</td><td class="num">{win}</td></tr>')
    h.append("</tbody></table>")
    return "\n".join(h)


def _grab(pat, text, group=1, default=None):
    m = re.search(pat, text, re.M)
    return m.group(group).strip() if m else default


def kpi_tiles(raw):
    """Headline numbers as eight tiles laid out 4 x 2.

    Each tile has four layers: what it is, the headline value, the COMPARISON WINDOW that
    makes the value mean something, and a plain-English implication. The comparison line is
    its own sized element - a signal like "30d -$11.66bn capital leaving" must not hide in
    small grey text. Row 1 is flow, row 2 is positioning/sentiment.
    """
    def tile(k, v, d="", n="", vcls="", dcls=""):
        return (f'<div class="kpi"><span class="k">{esc(k)}</span>'
                f'<span class="v {vcls}">{esc(str(v))}</span>'
                f'<span class="d {dcls or vcls}">{esc(str(d))}</span>'
                f'<span class="n">{esc(n)}</span></div>')

    t = []

    # --- row 1: flow -------------------------------------------------------
    e30 = _grab(r"30d (-?\$[\d,\.]+M)", raw)
    if e30:
        e5 = _grab(r"5d (-?\$[\d,\.]+M)", raw, 1, "n/a")
        t.append(tile("ETF flows", e30, f"5d {e5}", "US spot ETFs, 30-day net",
                      "neg" if e30.startswith("-") else "pos"))

    pv = _grab(r"live ([+-][\d\.]+)%", raw)
    if pv:
        st = _grab(r"negative streak (\d+)d", raw, 1, "")
        pavg = _grab(r"30d avg ([+-][\d\.]+)%\s+negative streak", raw, 1, "")
        t.append(tile("US premium", f"{pv}%", f"{st} days negative" if st else "vs global",
                      f"Coinbase vs Binance. 30d avg {pavg}%" if pavg else "Coinbase vs Binance",
                      "neg" if pv.startswith("-") else "pos"))

    m = re.search(r"combined \$([\d\.]+B)\s+7d ([+-]?\$[\d\.]+B)\s+30d ([+-]?\$[\d\.]+B)", raw)
    if m:
        lvl, d30 = m.group(1), m.group(3)
        t.append(tile("Stablecoins", f"${lvl}", f"30d {d30}",
                      "Capital leaving crypto, not waiting" if d30.startswith("-")
                      else "Capital returning to crypto",
                      "neg" if d30.startswith("-") else "pos"))

    r14 = _grab(r"RSI\(14\) ([\d\.]+)", raw)
    if r14:
        pct = _grab(r"RSI14 1y percentile (\d+)%", raw, 1, "")
        v = float(r14)
        t.append(tile("RSI(14)", r14, f"1y pctile {pct}%" if pct else "daily close",
                      "Oversold - capitulation zone" if v < 30 else
                      ("Overbought - stretched" if v > 70 else "Neutral, no extreme"),
                      "neg" if v < 30 else ("pos" if v > 70 else "")))

    # --- row 2: positioning / sentiment ------------------------------------
    fnd = _grab(r"30d avg ([+-][\d\.]+)% /8h\s*->\s*([+-][\d\.]+)% annualised", raw, 2)
    if fnd:
        t.append(tile("Funding rate", f"{fnd}%", "30d avg, annualised",
                      "Longs pay shorts - crowded longs" if fnd.startswith("+")
                      else "Shorts pay longs - squeeze fuel up",
                      "warn" if fnd.startswith("+") else "pos"))

    oi = _grab(r"OI \$([\d\.]+)bn \(1d ([+-][\d\.]+)", raw, 1)
    if oi:
        d1 = _grab(r"OI \$[\d\.]+bn \(1d ([+-][\d\.]+)", raw, 1, "n/a")
        t.append(tile("Perp open interest", f"${oi}bn", f"1d {d1}bn",
                      "Deleveraging, not new shorts" if str(d1).startswith("-")
                      else "Fresh leverage entering",
                      "neg" if str(d1).startswith("-") else "pos"))

    ls = _grab(r"all-acct L/S ([\d\.]+) \(30d [\d\.]+-[\d\.]+, pctile (\d+)%\)", raw, 1)
    if ls:
        lsp = _grab(r"all-acct L/S [\d\.]+ \(30d [\d\.]+-[\d\.]+, pctile (\d+)%\)", raw, 1, "0")
        crowd_long = int(lsp) >= 80
        crowd_short = int(lsp) <= 20
        t.append(tile("Long/short ratio", ls, f"{lsp}th pctile",
                      "Crowd crowded LONG - squeeze fuel down" if crowd_long else
                      ("Crowd crowded SHORT - squeeze fuel up" if crowd_short
                       else "Positioning mid-range - no signal"),
                      "neg" if crowd_long else ("pos" if crowd_short else "")))

    fng = _grab(r"now (\d+) \(([^)]+)\)", raw)
    if fng:
        cls = _grab(r"now \d+ \(([^)]+)\)", raw, 1, "")
        v = int(fng)
        t.append(tile("Fear & Greed", fng, cls,
                      "Capitulation - bounce fuel up, bad to short" if v <= 20
                      else ("Euphoria - contrarian bearish" if v >= 80 else "No crowd extreme"),
                      "neg" if v <= 20 else ("warn" if v >= 80 else "")))

    return '<div class="kpis">' + "".join(t) + "</div>" if t else ""


# Guide tab: one card per digest block. The NUMBER is looked up from the digest text (see
# ref_section) instead of hardcoded - hardcoding is exactly what let the numbers drift out of
# order. Fields: (display title, stable prefix of the digest's own block title, body HTML).
REF_CARDS = [
    ("Coinbase Premium Index &mdash; US vs global bid", "Coinbase Premium Index",
     '<p>Live and closing spread between Coinbase (US) and Binance (global) BTC price. '
     '<strong>Positive = US buyers paying up</strong>; negative = the US is the missing bid. '
     'A negative run of 20+ days is a <em>regime</em>, not noise.</p>'),

    ("US spot BTC ETF net flow (T+1) &mdash; institutional demand", "US spot BTC ETF net flow",
     '<p>Aggregate creations minus redemptions across US spot BTC ETFs. Always read the '
     '5d/30d sums, never a single day.</p>'),

    ("Coinbase Premium net of Tether &mdash; regime", "Coinbase Premium net of Tether",
     '<p>The 30-day mean premium with the USDT/USD rate stripped out, so a stablecoin peg '
     'wobble cannot fake a signal. Answers: is the US discount structural or transient?</p>'),

    ("Stablecoin supply &mdash; is money coming back?", "Stablecoin supply",
     '<p>Combined USDT + USDC supply. Expansion = capital arriving into crypto; contraction = '
     'capital leaving (not &ldquo;waiting&rdquo;). Needs <em>both</em> the 7d and 30d change '
     'positive to call a return.</p>'),

    ("Spot taker flow by venue &mdash; who is actually buying", "Spot taker flow by venue",
     '<p>Net aggressive buying (taker buy &minus; taker sell) per exchange. A <strong>partial</strong> '
     'rebuild of CoinGlass&rsquo;s per-venue CVD, because only two venues publish history:</p>'
     '<table><thead><tr><th>venue</th><th>what we can get</th></tr></thead><tbody>'
     '<tr><td>Binance</td><td>full history &mdash; 1d / 7d / 30d, exact</td></tr>'
     '<tr><td>OKX</td><td>exact, but only a 48h window</td></tr>'
     '<tr><td>Coinbase</td><td>live tape snapshot only &mdash; no history published</td></tr>'
     '<tr><td>Bybit</td><td>nothing public</td></tr></tbody></table>'
     '<p>The verdict uses the <strong>deep, long-window books</strong> (Binance, OKX) and is '
     'measured <em>relative to volume</em> &mdash; under 3% of gross is called BALANCED, so a '
     'near-flat venue cannot be dressed up as selling.</p>'
     '<p class="note">The Binance perp CVD line is the same idea on futures: '
     '<code>2&times;(taker buy vol) &minus; total vol</code>.</p>'),

    ("Positioning &mdash; Binance futures long/short crowding", "Positioning",
     '<p>Three Binance futures ratios, all <strong>contrarian</strong>:</p>'
     '<table><thead><tr><th>indicator</th><th>what it counts</th></tr></thead><tbody>'
     '<tr><td>all-accounts L/S</td><td>every account, longs &divide; shorts</td></tr>'
     '<tr><td>top-trader accounts</td><td>large accounts, longs &divide; shorts</td></tr>'
     '<tr><td>top-trader positions</td><td>large accounts, by <em>size</em> not headcount</td></tr>'
     '</tbody></table>'
     '<p><strong>High ratio = crowd is long = squeeze fuel DOWN.</strong> Low = crowd short = '
     'squeeze fuel UP. Retail crowded long while top-trader <em>positions</em> fall &rarr; smart '
     'money exiting into retail strength (bearish). OI falling = deleveraging, not new shorts. '
     'A mid-range percentile is no signal.</p>'),

    ("Funding rate &amp; perp basis &mdash; what leverage costs", "Derivatives cost",
     '<p>The 8-hourly payment between longs and shorts, plus the perp&rsquo;s premium to spot '
     'index. <strong>Positive funding = longs pay shorts = leveraged longs are the crowded '
     'side</strong> (bearish tilt &mdash; dips get flushed). Negative funding = shorts pay, '
     'meaning crowded shorts and squeeze fuel <em>up</em>, which is hostile to a short. '
     'Basis near zero means perp and spot agree.</p>'),

    ("Fear &amp; Greed &mdash; how extreme the crowd is", "Sentiment - Fear & Greed",
     '<p>0&ndash;100 composite of volatility, momentum, volume, social and dominance. '
     '<strong>Crowd-state, not price-state:</strong> it says where people are, not where price '
     'goes. Below 20 = capitulation &mdash; contrarian-bullish for a <em>bounce</em>, which is a '
     'warning against shorting into it. Above 80 = euphoria, contrarian-bearish.</p>'),

    ("Cost basis / URPD &mdash; where supply sits", "Cost basis / URPD",
     '<p>Supply by acquisition-price bucket ($2,000 wide). Bars <em>above</em> spot are overhead '
     'resistance; at or below spot is support. Includes the short-term-holder split: how much '
     'STH supply is underwater.</p>'),

    ("Valuation floors &mdash; how far is the downside", "Valuation floors",
     '<p><strong>Balanced Price</strong> (realized price &minus; transferred price) is where past '
     'cycle bottoms have converged (~1.0x). <strong>AVWAP</strong> since 2015 is the market&rsquo;s '
     'all-time break-even. Floors, not timing triggers.</p>'),

    ("RSI &mdash; momentum", "RSI - momentum",
     '<p>Wilder RSI on <strong>daily closes only</strong>, printed two ways so they never have to '
     'be reconciled: <strong>settled</strong> (completed days, stable, what to reason with) and '
     '<strong>incl. today&rsquo;s forming candle</strong> (what a live chart shows, drifts all day).</p>'
     '<p class="note">RSI(6) &gt; RSI(14) &gt; RSI(24) = short-term momentum leading. '
     'RSI(6) &lt; RSI(24) = deteriorating, bounces being sold into. Never quote an RSI without its '
     'timeframe &mdash; the same market reads 62 on 1H and 9 on 1D.</p>'),

    ("Divergence &mdash; the only RSI signal with an edge", "Divergence - 20d price low",
     '<p><strong>Bullish</strong> = a distinct 20-day price low whose RSI14 is <em>higher</em> than '
     'at the previous 20-day low. Measured on <strong>closes</strong>, from the trigger day, no '
     'look-ahead. Plain divergence has <strong>no edge</strong> (55% vs 53% baseline); only the '
     'variant where RSI14 &lt; 35 at the second low tested positive (67%, n=12).</p>'
     '<p class="note">A straight-down close can never produce this &mdash; a lower close is a loss '
     'day, so RSI falls with price. The RSI must be <em>rebuilt by a bounce that then fails</em>.</p>'),

    ("Short-fade watch &mdash; when to fade the bounce", "Short-fade watch",
     '<p>Short trigger: <strong>RSI14 crosses above 40 while price is below MA200</strong> &mdash; a '
     'bounce that recovered momentum but is still under the trend line. Prints MA200/MA50/MA10 and '
     'the exact gap. Take profit fast: EV is only ~+0.12%, near break-even.</p>'),
]


def block_heads(raw):
    """[(number, title)] for every block the digest printed, in printed order."""
    return re.findall(r"^\[(\d+[a-z]?|\+)\]\s+(.+)$", raw, re.M)


def num_of(heads, prefix, default="?"):
    """The number the digest gave the block whose title starts with `prefix`."""
    for n, t in heads:
        if t.startswith(prefix):
            return n
    return default


def ref_section(raw):
    """Guide cards, ordered AND numbered from the digest text - never from this file's order.

    Sorting by the digest's own number means a card can never end up reading [2] before [1]
    just because of where someone appended it in REF_CARDS.
    """
    heads = block_heads(raw)
    numbered = sorted(((num_of(heads, p), t, b) for t, p, b in REF_CARDS),
                      key=lambda r: int(re.sub(r"\D", "", r[0]) or 0))
    return "\n\n".join(f'<div class="card"><h3>[{n}] {t}</h3>\n{b}</div>'
                       for n, t, b in numbered)


def build(raw=None):
    if raw is None:
        raw = run_digest()
    blocks_html = render_digest(raw)
    kpis = kpi_tiles(raw)
    heads = block_heads(raw)   # [(printed number, title)] - inline refs use these, never literals

    spot = _grab(r"spot \$([\d,]+)", raw, 1, "n/a")
    verdict = _grab(r"^VERDICT: (.+)$", raw, 1, "")
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # the deep price/floor/VWAP chart from the digest run
    src = os.path.join(CHART_DIR, f"btc_daily_{datetime.now(timezone.utc):%Y-%m-%d}.png")
    if not os.path.exists(src):
        cands = sorted(f for f in os.listdir(CHART_DIR) if f.startswith("btc_daily_"))
        src = os.path.join(CHART_DIR, cands[-1]) if cands else None
    def card(title, img_src, alt, now, use, verdict, cls=""):
        # normalise: callers pass "wide" or " wide" - concatenating raw gave class="ccardwide"
        cls = f" {cls.strip()}" if cls and cls.strip() else ""
        chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in (now or []))
        return (f'<div class="ccard{cls}"><h4>{esc(title)}</h4>'
                f'<div class="cnow">{chips}</div>'
                f'<img src="{img_src}" alt="{esc(alt)}">'
                f'<p class="cuse"><strong>How to use it:</strong> {esc(use)}</p>'
                + (f'<p class="cverdict">&rarr; {esc(verdict)}</p>' if verdict else "")
                + "</div>")

    bal = _grab(r"Balanced Price \$([\d,]+)", raw)
    balx = _grab(r"Balanced Price \$[\d,]+ \([\d-]+\)\s+-> spot ([\d\.]+)x", raw)
    avw = _grab(r"AVWAP since [\d-]+ \$([\d,]+)", raw)
    avwx = _grab(r"AVWAP since [\d-]+ \$[\d,]+ \(thru [\d-]+\)\s+-> spot ([\d\.]+)x", raw)
    cycle_html = ""
    if src and os.path.exists(src):
        shutil.copy(src, os.path.join(HERE, "chart.png"))
        cyc_now = []
        if bal:
            cyc_now.append(f"Balanced ${bal}")
        if balx:
            cyc_now.append(f"spot {balx}x balanced")
        if avw:
            cyc_now.append(f"AVWAP ${avw}")
        if avwx:
            cyc_now.append(f"spot {avwx}x AVWAP")
        cycle_html = card(
            "Cycle context - price vs Balanced Price and all-time anchored VWAP",
            "chart.png", "BTC price, Balanced Price, anchored VWAP", cyc_now,
            "Balanced Price is where past cycle BOTTOMS converged (about 1.0x). The AVWAP is the "
            "market's all-time break-even. The further spot sits above these, the more downside "
            "exists before deep support is reached. These are floors, not timing triggers - price "
            "can stay far above them for a long time.",
            (f"Spot is {balx}x the Balanced floor and {avwx}x the all-time VWAP. A full retest of "
             f"the floor would be roughly ${bal}." if bal and balx and avwx else ""),
            " wide")

    # indicator charts
    chart_meta = []
    try:
        chart_meta = chartmod.build_all(HERE, SERIES_PATH)
    except Exception as e:
        chart_meta = [{"file": "", "title": f"charts unavailable ({type(e).__name__})", "caption": ""}]

    ccards = [card(c["title"], esc(c["file"]), c["title"], c.get("now"),
                   c.get("use", ""), c.get("verdict", ""), c.get("cls", ""))
              for c in chart_meta if c.get("file")]
    chart_grid = '<div class="cgrid">' + cycle_html + "".join(ccards) + "</div>"

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Daily Digest</title>
<meta name="description" content="Daily Bitcoin flow, positioning and momentum digest with backtested rules.">
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <h1>BTC Daily Digest</h1>
  <div class="sub">Spot <strong>${spot}</strong> &middot; updated {updated}</div>
  <div class="verdict-card">VERDICT: {esc(verdict)}</div>
  {kpis}
  <nav class="tabs">
    <button class="on" data-t="dash">Dashboard</button>
    <button data-t="charts">Charts</button>
    <button data-t="ref">Reference</button>
    <button data-t="ev">Evidence</button>
    <button data-t="guide">Guide</button>
  </nav>
</header>

<section id="dash" class="tab on">
<p class="note">Sections run in order of importance: <strong>flow first</strong> (where the money is going),
then positioning &amp; sentiment, price structure, momentum, and finally the actionable signals.
If the flow section is bearish, everything below it is a bounce to sell. All blocks are settled
<strong>daily closes</strong> unless a line says &ldquo;live&rdquo;.</p>
{blocks_html}
</section>

<section id="charts" class="tab">
<p class="note">Every indicator the digest tracks, charted. Hover-free, static PNGs &mdash; they render anywhere.</p>
{chart_grid}
</section>

<section id="ref" class="tab">
<p class="note">What each block is for, and how to read it. Numbered in the order they appear on the Dashboard, so the legend, the page and this guide always agree.</p>

{ref_section(raw)}
</section>

<section id="ev" class="tab">
<p class="note">BTCUSDT daily. Forward returns measured from the day you could act. Barrier tables are intrabar, adverse-first when both hit the same bar. EV = probability-weighted outcome of the target/stop pair.</p>

<h3>RSI crossovers alone &mdash; coin flips (1000d sample)</h3>
<p>Fires often and loses more often than it wins. Useful for <em>describing</em> momentum, not for triggering entries.</p>
{ev_table(EVIDENCE["rsi_rules"])}

<h3>Divergence &mdash; 9 years, 3378 days</h3>
<p>A textbook bullish divergence by itself did <strong>not</strong> beat simply holding. Only the oversold-constrained variant has an edge, and n=12 is small.</p>
{ev_table(EVIDENCE["divergence"])}
<div class="callout"><p><strong>Correction:</strong> an earlier figure of &ldquo;62% win&rdquo; was wrong. It came from a shorter 2024&ndash;2026 sample and a definition that also flagged higher-low/higher-RSI cases, which are not divergences. The numbers above supersede it.</p></div>

<h3>Short-fade &mdash; fade the bounce at resistance</h3>
<p>Better odds than the long side, but the edge is thin. Detected by block {num_of(heads, "Short-fade watch")}.</p>
{ev_table(EVIDENCE["short_fade"])}

<h3>Long the bounce &mdash; do not take this leg</h3>
<p>Riding a bounce to +7% before a &minus;5% stop happens only <strong>34%</strong> of the time, and every variant is negative-EV. &ldquo;Buy the bounce then short&rdquo; loses money on the first leg.</p>
{ev_table(EVIDENCE["long_bounce"])}
</section>

<section id="guide" class="tab">
<p class="note"><strong>Where the live reading is:</strong> block <strong>{num_of(heads, "Divergence")} &mdash; Divergence</strong> on the
<em>Dashboard</em> tab, inside section <em>4. MOMENTUM</em>. This tab is the guide, not the reading.</p>
<p>Price and the RSI stop agreeing. Price keeps going the same way, but the RSI refuses to follow &mdash; the move is running out of force underneath.</p>

<h3>The four types</h3>
<table><thead><tr><th>type</th><th>price</th><th>RSI</th><th>means</th></tr></thead><tbody>
<tr><td>Regular <strong>bullish</strong></td><td>lower low</td><td>HIGHER low</td><td>downtrend losing force &rarr; bounce up</td></tr>
<tr><td>Regular <strong>bearish</strong></td><td>higher high</td><td>LOWER high</td><td>uptrend losing force &rarr; drop</td></tr>
<tr><td>Hidden bullish</td><td>higher low</td><td>lower low</td><td>uptrend healthy &rarr; CONTINUATION up</td></tr>
<tr><td>Hidden bearish</td><td>lower high</td><td>higher high</td><td>downtrend healthy &rarr; CONTINUATION down</td></tr>
</tbody></table>
<p class="note">&ldquo;Regular&rdquo; = the reversal kind. &ldquo;Hidden&rdquo; = continuation. Getting these backwards is how people buy tops.</p>

<h3>Regular bullish &mdash; step by step</h3>
<p>1. Two clear price lows, the second <strong>lower</strong>. &nbsp; 2. Add RSI(14). &nbsp; 3. RSI at the second (lower) low is <strong>higher</strong> than at the first. &nbsp; 4. Price line slopes <em>down</em>, RSI line slopes <em>up</em>.</p>
<p class="note">Plain reading: sellers keep pushing to new lows but with less force each time. Fewer sellers, same effort, less result.</p>

<h3>What to look out for</h3>
<table><thead><tr><th>Good signs</th><th>Invalidators</th></tr></thead><tbody>
<tr><td>Lows 10+ candles apart, both at obvious swing lows</td><td>Two adjacent candles &mdash; that is noise</td></tr>
<tr><td>RSI oversold (&lt;30, ideal &lt;25) at both lows</td><td>RSI only fractionally higher (18 &rarr; 19)</td></tr>
<tr><td>Second low has a long lower wick / quick snap-back</td><td>Price blows through on rising volume, RSI keeps falling</td></tr>
<tr><td>Volume lighter on the second low (selling drying up)</td><td>Small-timeframe divergence inside a strong trend</td></tr>
<tr><td>Happens at a known level (URPD shelf, MA200)</td><td>You have to squint to see it</td></tr>
</tbody></table>

<div class="callout">
<p><strong>Expectation:</strong> divergence marks a <em>zone</em>, not a moment. Price often makes one final spike before turning &mdash; that spike is the last seller capitulating and it is where stops get hunted. Every variant tested dipped ~5&ndash;6% before it paid.</p>
<p><strong>Never measure from the pivot date.</strong> Look-ahead flatters this to 86% win / +7.95% &mdash; that is how backtests lie.</p>
</div>
</section>

<footer>
<p>Generated automatically from keyless public APIs (Coinbase, Binance, DeFiLlama, cryptoetf.today, Look Into Bitcoin, BGeometrics, alternative.me). No credentials, no subscription feeds.</p>
<p>Not financial advice. Backtest figures are historical and samples are small where noted.</p>
<p>Last build: {updated}</p>
</footer>
<script>
document.querySelectorAll('.tabs button').forEach(function(b){{
  b.addEventListener('click', function(){{
    document.querySelectorAll('.tabs button').forEach(function(x){{x.classList.remove('on');}});
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('on');}});
    b.classList.add('on');
    var el = document.getElementById(b.dataset.t);
    if (el) el.classList.add('on');
  }});
}});
</script>
</div></body></html>
"""
    path = os.path.join(HERE, "index.html")
    with open(path, "w") as f:
        f.write(doc)
    print(f"wrote {path} ({len(doc)} bytes); charts={len(chart_meta)}; kpis={'yes' if kpis else 'no'}")
    return path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            build(fh.read())
    else:
        build()
