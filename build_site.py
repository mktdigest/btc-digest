#!/usr/bin/env python3
"""Build a static, shareable BTC-digest page (GitHub Pages ready).

Runs the daily digest, renders it as HTML cards, embeds the chart, and attaches the
static reference + backtest evidence. Output: index.html + chart.png in this directory.

Usage:  python3 build_site.py
"""
import html
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = "/root/.hermes/scripts"
CHART_DIR = "/root/.hermes/state/charts"
DIGEST = os.path.join(SCRIPTS, "coinbase_premium_daily.py")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--dim:#8b949e;
--accent:#58a6ff;--green:#3fb950;--red:#f85149;--amber:#d29922;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
body{background:var(--bg);color:var(--txt);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased;padding:0 0 80px}
.wrap{max-width:920px;margin:0 auto;padding:0 20px}
header{padding:44px 0 26px;border-bottom:1px solid var(--line);margin-bottom:30px}
h1{font-size:29px;font-weight:650;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:14px;margin-top:8px}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
nav a{color:var(--accent);text-decoration:none;font-size:13px;border:1px solid var(--line);
padding:5px 12px;border-radius:999px;background:var(--card)}
nav a:hover{border-color:var(--accent)}
h2{font-size:20px;font-weight:650;margin:46px 0 6px;padding-top:14px;letter-spacing:-.01em}
h2 .n{color:var(--dim);font-weight:400;font-size:15px;margin-right:8px}
h3{font-size:15px;font-weight:650;margin:0 0 10px;color:var(--accent)}
p{color:#c9d1d9;margin:9px 0}
p.note{color:var(--dim);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:14px 0}
.card pre{font-family:var(--mono);font-size:13px;line-height:1.65;white-space:pre-wrap;word-break:break-word;color:#c9d1d9}
.verdict{color:var(--green);font-weight:600}
.alert{color:var(--amber);font-weight:650}
.watch{color:var(--accent)}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;white-space:nowrap}
th{background:#1c2128;font-weight:650;font-size:13px;color:#c9d1d9}
td.num{font-family:var(--mono);text-align:right}
.neg{color:var(--red);font-weight:600}.pos{color:var(--green);font-weight:600}
img.chart{width:100%;border:1px solid var(--line);border-radius:10px;margin:14px 0;display:block}
.callout{border-left:3px solid var(--amber);background:#1c1a12;border-radius:6px;padding:12px 16px;margin:14px 0}
.callout p{margin:4px 0;color:#e6d7a8}
footer{margin-top:60px;padding-top:22px;border-top:1px solid var(--line);color:var(--dim);font-size:13px}
code{font-family:var(--mono);background:#1c2128;padding:2px 6px;border-radius:4px;font-size:13px}
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
    p = subprocess.run([sys.executable, DIGEST], capture_output=True, text=True, timeout=300)
    out = p.stdout
    if not out.strip():
        raise RuntimeError(f"digest produced no output; stderr={p.stderr[:400]}")
    return out


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


def render_digest(raw):
    lines = [l for l in raw.splitlines() if not l.startswith("MEDIA:")]
    blocks, cur, pre = [], [], []
    for l in lines:
        if re.match(r"^\[[0-9+\]]", l):
            if cur:
                blocks.append(cur)
            cur = [l]
        elif cur:
            cur.append(l)
        else:
            pre.append(l)
    if cur:
        blocks.append(cur)

    out = []
    if any(x.strip() for x in pre):
        out.append('<div class="card"><pre>' + "\n".join(fmt_line(l) for l in pre if l.strip() or True) + "</pre></div>")
    for b in blocks:
        title = b[0]
        body = [l for l in b[1:]]
        while body and not body[-1].strip():
            body.pop()
        if not body:
            continue
        out.append(f'<div class="card"><h3>{esc(title)}</h3><pre>'
                   + "\n".join(fmt_line(l) for l in body) + "</pre></div>")
    return "\n".join(out)


def ev_table(rows):
    h = ['<table><thead><tr><th>Rule / target</th><th>n</th><th>Forward / EV</th><th>Hit rate</th></tr></thead><tbody>']
    for name, n, fwd, win in rows:
        cls = "neg" if fwd.startswith("-") else ("pos" if fwd.startswith("+") else "")
        h.append(f'<tr><td>{name}</td><td class="num">{n}</td>'
                 f'<td class="num {cls}">{fwd}</td><td class="num">{win}</td></tr>')
    h.append("</tbody></table>")
    return "\n".join(h)


def build():
    raw = run_digest()
    blocks_html = render_digest(raw)

    # chart
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    src = os.path.join(CHART_DIR, f"btc_daily_{today}.png")
    chart_html = ""
    if os.path.exists(src):
        shutil.copy(src, os.path.join(HERE, "chart.png"))
        chart_html = '<img class="chart" src="chart.png" alt="BTC daily: price, Balanced Price, all-time anchored VWAP (log scale)">'

    # spot + verdict pulled from the digest for the header
    m = re.search(r"spot \$([\d,]+)", raw)
    spot = m.group(1) if m else "n/a"
    vm = re.search(r"^VERDICT: (.+)$", raw, re.M)
    verdict = vm.group(1) if vm else ""
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Daily Digest</title>
<meta name="description" content="Daily Bitcoin flow, cost-basis and momentum digest with backtested rules.">
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <h1>BTC Daily Digest</h1>
  <div class="sub">Spot <strong>${spot}</strong> &middot; updated {updated} &middot; {esc(verdict)}</div>
  <nav>
    <a href="#digest">Today's digest</a>
    <a href="#chart">Chart</a>
    <a href="#reference">Indicator reference</a>
    <a href="#evidence">Backtest evidence</a>
    <a href="#divergence">Divergence guide</a>
  </nav>
</header>

<h2 id="digest"><span class="n">01</span>Today's digest</h2>
<p class="note">All blocks are settled <strong>daily closes</strong> unless a line says "live".
Flow/cost-basis blocks are as-of the last completed day.</p>
{blocks_html}

<h2 id="chart"><span class="n">02</span>Chart</h2>
<p class="note">BTC price, Balanced Price (deep-cycle floor) and the all-time anchored VWAP, log scale.</p>
{chart_html}

<h2 id="reference"><span class="n">03</span>Indicator reference</h2>
<p class="note">What each block is for, and how to read it.</p>

<div class="card"><h3>[1] Coinbase Premium Index &mdash; US vs global bid</h3>
<p>Live and closing spread between Coinbase (US) and Binance (global) BTC price. <strong>Positive = US buyers paying up</strong>; negative = the US is the missing bid. A negative run of 20+ days is a <em>regime</em>, not noise.</p></div>

<div class="card"><h3>[2] US spot BTC ETF net flow (T+1) &mdash; institutional demand</h3>
<p>Aggregate creations minus redemptions across US spot BTC ETFs. Always read the 5d/30d sums, never a single day.</p></div>

<div class="card"><h3>[3] Coinbase Premium net of Tether &mdash; regime</h3>
<p>The 30-day mean premium with the USDT/USD rate stripped out, so a stablecoin peg wobble can't fake a signal. Answers: is the US discount structural or transient?</p></div>

<div class="card"><h3>[4] Cost basis / URPD &mdash; where supply sits</h3>
<p>Supply by acquisition-price bucket ($2,000 wide). Bars <em>above</em> spot are overhead resistance; at or below spot is support. Includes the short-term-holder split: how much STH supply is underwater.</p></div>

<div class="card"><h3>[5] Valuation floors &mdash; how far is the downside</h3>
<p><strong>Balanced Price</strong> (realized price &minus; transferred price) is where past cycle bottoms have converged (~1.0x). <strong>AVWAP</strong> since 2015 is the market's all-time break-even. Floors, not timing triggers.</p></div>

<div class="card"><h3>[6] Stablecoin supply &mdash; is money coming back?</h3>
<p>Combined USDT + USDC supply. Expansion = capital arriving into crypto; contraction = capital leaving (not "waiting"). Needs <em>both</em> 7d and 30d up to call a return.</p></div>

<div class="card"><h3>[7] RSI &mdash; momentum</h3>
<p>Wilder RSI on <strong>daily closes only</strong>, printed two ways so they never have to be reconciled: <strong>settled</strong> (completed days, stable, what to reason with) and <strong>incl. today's forming candle</strong> (what a live chart shows, drifts all day).</p>
<p class="note">RSI(6) &gt; RSI(14) &gt; RSI(24) = short-term momentum leading. RSI(6) &lt; RSI(24) = deteriorating, bounces being sold into. Never quote an RSI without its timeframe &mdash; the same market reads 62 on 1H and 9 on 1D.</p></div>

<div class="card"><h3>[7b] Divergence &mdash; the only RSI signal with an edge</h3>
<p><strong>Bullish</strong> = a distinct 20-day price low whose RSI14 is <em>higher</em> than at the previous 20-day low. Measured on <strong>closes</strong>, from the trigger day, no look-ahead. Plain divergence has <strong>no edge</strong> (55% vs 53% baseline); only the variant where RSI14 &lt; 35 at the second low tested positive (67%).</p>
<p class="note">A straight-down close can never produce this &mdash; a lower close is a loss day, so RSI falls with price. The RSI must be <em>rebuilt by a bounce that then fails</em>.</p></div>

<div class="card"><h3>[8] Short-fade watch &mdash; when to fade the bounce</h3>
<p>Short trigger: <strong>RSI14 crosses above 40 while price is below MA200</strong> &mdash; a bounce that recovered momentum but is still under the trend line. Take profit fast: EV is only ~+0.12%, near break-even.</p></div>

<div class="card"><h3>[+] Global flow proxy</h3>
<p>Binance taker CVD, <code>2&times;(taker buy vol) &minus; total vol</code>. Net aggressive order flow, not venue-split. Positive = buyers lifting offers.</p></div>

<h2 id="evidence"><span class="n">04</span>Backtest evidence</h2>
<p class="note">BTCUSDT daily. Forward returns measured from the day you could act. Barrier tables are intrabar, adverse-first when both hit the same bar. EV = probability-weighted outcome of the target/stop pair.</p>

<h3>RSI crossovers alone &mdash; coin flips (1000d sample)</h3>
<p>Fires often and loses more often than it wins. Useful for <em>describing</em> momentum, not for triggering entries.</p>
{ev_table(EVIDENCE["rsi_rules"])}

<h3>Divergence &mdash; 9 years, 3378 days</h3>
<p>A textbook bullish divergence by itself did <strong>not</strong> beat simply holding. Only the oversold-constrained variant has an edge, and n=12 is small.</p>
{ev_table(EVIDENCE["divergence"])}
<div class="callout"><p><strong>Correction:</strong> an earlier figure of "62% win" was wrong. It came from a shorter 2024&ndash;2026 sample and a definition that also flagged higher-low/higher-RSI cases, which are not divergences. The numbers above supersede it.</p></div>

<h3>Short-fade &mdash; fade the bounce at resistance</h3>
<p>Better odds than the long side, but the edge is thin. Detected by block [8].</p>
{ev_table(EVIDENCE["short_fade"])}

<h3>Long the bounce &mdash; do not take this leg</h3>
<p>Riding a bounce to +7% before a &minus;5% stop happens only <strong>34%</strong> of the time, and every variant is negative-EV. "Buy the bounce then short" loses money on the first leg.</p>
{ev_table(EVIDENCE["long_bounce"])}

<h2 id="divergence"><span class="n">05</span>Divergence guide</h2>
<p>Price and the RSI stop agreeing. Price keeps going the same way, but the RSI refuses to follow &mdash; the move is running out of force underneath.</p>

<h3>The four types</h3>
<table><thead><tr><th>type</th><th>price</th><th>RSI</th><th>means</th></tr></thead><tbody>
<tr><td>Regular <strong>bullish</strong></td><td>lower low</td><td>HIGHER low</td><td>downtrend losing force &rarr; bounce up</td></tr>
<tr><td>Regular <strong>bearish</strong></td><td>higher high</td><td>LOWER high</td><td>uptrend losing force &rarr; drop</td></tr>
<tr><td>Hidden bullish</td><td>higher low</td><td>lower low</td><td>uptrend healthy &rarr; CONTINUATION up</td></tr>
<tr><td>Hidden bearish</td><td>lower high</td><td>higher high</td><td>downtrend healthy &rarr; CONTINUATION down</td></tr>
</tbody></table>
<p class="note">"Regular" = the reversal kind. "Hidden" = continuation. Getting these backwards is how people buy tops.</p>

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

<footer>
<p>Generated automatically from keyless public APIs (Coinbase, Binance, DeFiLlama, cryptoetf.today, Look Into Bitcoin, BGeometrics). No credentials, no subscription feeds.</p>
<p>Not financial advice. Backtest figures are historical and samples are small where noted.</p>
<p>Last build: {updated}</p>
</footer>
</div></body></html>
"""
    path = os.path.join(HERE, "index.html")
    with open(path, "w") as f:
        f.write(doc)
    print(f"wrote {path} ({len(doc)} bytes); chart={'yes' if chart_html else 'MISSING'}")
    return path


if __name__ == "__main__":
    build()
