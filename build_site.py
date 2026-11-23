#!/usr/bin/env python3
"""Build the static, shareable BTC-digest page (GitHub Pages ready).

Layout: a glance dashboard (verdict + KPI tiles + the digest in priority sections),
then tabs for Charts / Reference / Evidence / Guide so the page is never one long scroll.

Usage:  python3 build_site.py [path-to-digest.txt]
"""
import hashlib
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
:root{
--s1:10px;--s2:16px;--s3:24px;--s4:36px;--s5:52px;--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--dim:#8b949e;
--accent:#58a6ff;--green:#3fb950;--red:#f85149;--amber:#d29922;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
body{background:var(--bg);color:var(--txt);font:18px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased;padding:0 0 70px}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header{padding:36px 0 0}
h1{font-size:38px;font-weight:680;letter-spacing:-.02em}
/* Spot is the number that matters - give it the top of the page at display size. The big figure
   IS the Coinbase print, so Coinbase is not repeated below; the strip shows the other venues and
   the Coinbase/Binance spread, which is new information rather than an echo. */
.spotlbl{font-size:15px;font-weight:700;letter-spacing:.13em;color:var(--dim);text-transform:uppercase}
.spotlbl .upd{font-weight:400;letter-spacing:0;text-transform:none;margin-left:14px;font-size:14.5px}
.spotpx{font-size:clamp(46px,11vw,78px);font-weight:750;letter-spacing:-.035em;line-height:1.04;
margin:8px 0 2px;color:#fff;font-variant-numeric:tabular-nums}
.spotrow{display:flex;flex-wrap:wrap;gap:8px 28px;font-size:17px;color:var(--txt);margin-top:10px;
font-variant-numeric:tabular-nums}
.spotrow b{color:var(--dim);font-weight:600;margin-right:9px}
h2{font-size:26px;font-weight:650;margin:34px 0 6px;letter-spacing:-.01em}
h3{font-size:22px;font-weight:650;margin:0 0 12px;color:var(--accent);line-height:1.35}
h4{font-size:20px;margin:0 0 10px;color:var(--txt)}
p{color:#c9d1d9;margin:9px 0}
p.note{color:var(--dim);font-size:15.5px;line-height:1.6;margin:var(--s2) 0 0}
h3.cardh{font-size:20px;margin:0 0 var(--s2);color:#fff}
h4.sub{font-size:15px;text-transform:uppercase;letter-spacing:.05em;color:#8b949e;
margin:var(--s3) 0 var(--s1);font-weight:700}
ol.steps{margin:var(--s2) 0 0;padding-left:22px;color:#c3ccd6;line-height:1.75;font-size:16px}
ol.steps li{margin:0 0 var(--s1)}
p.bnote{color:#9aa7b4;font-size:15.5px;line-height:1.65;margin:var(--s2) 0 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin:var(--s3) 0}
.card pre{font-family:var(--mono);font-size:15px;line-height:1.75;white-space:pre-wrap;word-break:break-word;color:#c9d1d9}
.card{padding:22px 24px}
.card h3{font-size:17px;line-height:1.4;margin:0 0 4px}
.bbody{margin:15px 0 0;font-size:15.5px;line-height:1.68;color:#cdd6e0}
.blead{margin:0 0 var(--s2);padding:0 0 0 12px;border-left:2px solid #2c3644;color:#9aa7b4;font-size:14.5px;line-height:1.6}
.frow{display:grid;grid-template-columns:minmax(112px,168px) 1fr;gap:4px 16px;padding:8px 0;border-top:1px solid rgba(255,255,255,.055)}
.frow:first-of-type{border-top:0}
.fk{color:#8b949e;font-size:13px;line-height:1.55;letter-spacing:.01em}
.fv{color:#e6edf3;line-height:1.6}
.bline{margin:0 0 var(--s2)}
.bline:last-of-type{margin-bottom:0}
.bsec{margin:var(--s2) 0 0;padding:13px 15px;background:rgba(255,255,255,.022);border:1px solid rgba(255,255,255,.05);border-radius:8px}
.bsec p{margin:5px 0 0;line-height:1.62}
.bseck{font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#8b949e}
.vbox{margin:var(--s2) 0 0;padding:13px 15px;border-radius:8px;border-left:3px solid;background:rgba(255,255,255,.028)}
.vtext{margin:6px 0 0;font-size:15px;line-height:1.6;color:#dfe6ee}
.vbox.bear{border-color:#f85149}.vbox.bull{border-color:#3fb950}
.vbox.warn{border-color:#d29922}.vbox.flat{border-color:#6e7681}
.verdict{color:var(--dim);font-weight:600}
.vline{display:block;font-weight:650}
.vbox .stag{margin:0 0 2px}
.vline .stag,.key .stag{display:inline-block;font-size:13px;font-weight:700;letter-spacing:.06em;
padding:2px 8px;border-radius:5px;margin-right:9px;vertical-align:1px}
.vline.bear{color:#ff8a80}.vline.bear .stag,.key .stag.bear{background:#3d1418;color:#ff8a80;border:1px solid #6e2126}
.vline.bull{color:#7ee787}.vline.bull .stag,.key .stag.bull{background:#0d2818;color:#7ee787;border:1px solid #238636}
.vline.warn{color:#e3b341}.vline.warn .stag,.key .stag.warn{background:#2b2210;color:#e3b341;border:1px solid #6b5320}
.vline.flat{color:#8b949e}.vline.flat .stag,.key .stag.flat{background:#1c2128;color:#8b949e;border:1px solid var(--line)}
.sbadge{display:inline-block;font-size:15px;font-weight:700;letter-spacing:.03em;
padding:4px 12px;border-radius:7px;margin-left:10px;vertical-align:3px;white-space:nowrap}
.sbadge.bear{background:#3d1418;color:#ff8a80;border:1px solid #6e2126}
.sbadge.bull{background:#0d2818;color:#7ee787;border:1px solid #238636}
.sbadge.warn{background:#2b2210;color:#e3b341;border:1px solid #6b5320}
.sbadge.flat{background:#1c2128;color:#8b949e;border:1px solid var(--line)}
.key{margin:16px 0 2px;font-size:16px;color:var(--dim);line-height:2.1}
.keys{display:grid;gap:12px;margin:18px 0 6px}
.keyrow{display:grid;grid-template-columns:110px 1fr;gap:16px;align-items:center;
font-size:15px;color:#a9b4c0;line-height:1.55}
@media(max-width:640px){.keyrow{grid-template-columns:1fr}}
.alert{color:var(--amber);font-weight:650}
.watch{color:var(--accent)}
table{width:100%;border-collapse:collapse;margin:var(--s2) 0;font-size:16px;display:table;table-layout:fixed}
th,td{overflow-wrap:break-word;vertical-align:top}
th,td{border:1px solid var(--line);padding:11px 14px;text-align:left;white-space:normal;vertical-align:top}
@media(max-width:720px){table{display:block;overflow-x:auto;font-size:15px}th,td{white-space:nowrap;padding:8px 10px}}
th{background:#1c2128;font-weight:650;font-size:15px;color:#c9d1d9}
td.num{font-family:var(--mono);text-align:right}
.neg{color:var(--red);font-weight:600}.pos{color:var(--green);font-weight:600}
.warn{color:var(--amber);font-weight:650}
img.chart{width:100%;border:1px solid var(--line);border-radius:10px;margin:13px 0;display:block}
.bfields{margin:9px 0 0;font-size:12.5px;color:var(--dim);line-height:1.45}
.bfields b{color:var(--tx)}
.bchart{margin:var(--s3) 0 0}
.bchart img{width:100%;border:1px solid var(--line);border-radius:8px;display:block}
.bchart figcaption{margin-top:6px;font-size:12px;color:var(--dim)}
.legcard{padding:8px 22px}
.legrow{display:grid;grid-template-columns:46px 1fr;gap:2px 14px;padding:17px 0;
border-top:1px solid rgba(255,255,255,.07)}
.legrow:first-child{border-top:0}
.legnum{grid-row:1/span 2;display:flex;align-items:flex-start;justify-content:center;
width:30px;height:30px;border-radius:8px;background:#1b2430;border:1px solid #2c3846;
color:var(--accent);font-size:14px;font-weight:700;line-height:28px;text-align:center}
.legtxt h4{margin:2px 0 6px;font-size:16px;color:#e6edf3;letter-spacing:.01em}
.legtxt p{margin:0;font-size:15px;line-height:1.68;color:#a9b4c0;max-width:none}
.gloss{margin:0 0 12px;font-size:15.5px;line-height:1.6;color:#b6c2ce}
details.more{margin-top:10px}
details.more summary{cursor:pointer;font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:#7d8896;list-style:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary:after{content:" +";color:#5d6a78}
details.more[open] summary:after{content:" \2212"}
details.more p{margin:8px 0 0;font-size:15px;line-height:1.68;color:#a9b4c0}
.callout{border-left:3px solid var(--amber);background:#1c1a12;border-radius:6px;padding:11px 15px;margin:13px 0}
.callout p{margin:4px 0;color:#e6d7a8}
footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:15px}
code{font-family:var(--mono);background:#1c2128;padding:2px 6px;border-radius:4px;font-size:15px}
.hrow{font-family:var(--mono);font-size:15.5px;color:var(--dim);margin:4px 0}
.tab .hrow:last-of-type{margin-bottom:var(--s3)}
.verdict-card{border-radius:9px;padding:13px 17px;margin:18px 0 4px;font-size:17px;font-weight:650;
display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.verdict-card.bear{background:#2a1013;border:1px solid #6e2126;color:#ff8a80}
.verdict-card.bull{background:#0d2818;border:1px solid #238636;color:#7ee787}
.verdict-card.warn{background:#2b2210;border:1px solid #6b5320;color:#e3b341}
.verdict-card.flat{background:#161b22;border:1px solid var(--line);color:#c3ccd6}
.verdict-card .stag{flex:0 0 auto}
h3.sec{font-size:27px;color:#fff;font-weight:700;margin:var(--s5) 0 var(--s2);padding-top:var(--s3);
border-top:1px solid var(--line);letter-spacing:-.02em;line-height:1.28}
p.sdesc{color:var(--dim);font-size:17.5px;margin:0 0 var(--s3);font-style:italic;line-height:1.6}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:var(--s3) 0 0}
@media(max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:14px 16px}
.kpi .k{display:block;font-size:14px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em;font-weight:650}
.kpi .v{display:block;font-size:26px;font-weight:650;font-family:var(--mono);margin-top:6px;line-height:1.15}
.kpi .d{display:block;font-size:16.5px;font-weight:650;font-family:var(--mono);margin-top:4px}
.kpi .n{display:block;font-size:14.5px;color:var(--dim);margin-top:5px;line-height:1.45}
.tabbar{position:sticky;top:0;z-index:80;max-width:none;background:rgba(13,17,23,.94);
backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
border:0;padding:14px 20px;margin:var(--s3) -20px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;align-items:center;
margin:0 auto;padding:8px;background:#11161d;border:1px solid var(--line);border-radius:14px;
width:fit-content;max-width:100%}
section[id]{scroll-margin-top:92px}
.tab > :first-child{margin-top:0}
.tabs button{background:#161c25;border:1px solid #222b36;color:#a9b4c0;
font:inherit;font-size:16px;padding:12px 22px;cursor:pointer;font-weight:650;
border-radius:9px;transition:background .12s,color .12s,border-color .12s;letter-spacing:.01em}
.tabs button:hover{color:#e6edf3;background:#1d2530;border-color:#2f3a47}

@media(max-width:600px){
.tabbar{padding:8px 10px;margin-left:-15px;margin-right:-15px}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;width:100%;max-width:none;padding:6px}
.tabs button{padding:10px 4px;font-size:13.5px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;border-radius:8px}
}
.tabs button.on{color:#0b0f14;background:var(--accent);border-color:var(--accent);
box-shadow:0 2px 10px rgba(88,166,255,.25)}
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


STANCE_LABEL = {"bear": "BEARISH", "bull": "BULLISH", "warn": "CAUTION", "flat": "NO SIGNAL"}


def fmt_line(line):
    st = line.strip()
    # Verdict lines carry an explicit stance tag written by the digest. Colour comes from THAT,
    # never from the wording - "EXTREME FEAR" is contrarian-bullish but a warning against
    # shorting, and "oversold" is a bounce zone inside a deteriorating trend.
    m = re.match(r"^->\s*\[(bear|bull|warn|flat)\]\s*(.*)$", st)
    if m:
        stance, body = m.group(1), m.group(2)
        return (f'<span class="vline {stance}">'
                f'<b class="stag">{STANCE_LABEL[stance]}</b>{esc(body)}</span>')
    e = esc(line.rstrip())
    if st.startswith("->"):
        # untagged verdict: show it neutrally rather than defaulting to green, which made
        # bearish news read as good news. Every block should be tagged; grey here means a gap.
        return f'<span class="verdict">{e}</span>'
    if st.startswith("watch"):
        return f'<span class="watch">{e}</span>'
    if "**" in line or "ARMED" in line:
        return f'<span class="alert">{e}</span>'
    return e

LEAD_LABELS = ("ONE LINE", "WHAT THIS IS", "WHAT IT IS")
SECTION_LABELS = ("HISTORY", "LIMITS", "GAP", "CLOCK", "FLOOR PRICE")


# Wrapped input means many lines end mid-sentence - but so do complete data rows. Join only when the
# text actually dangles: the previous line ends on a connector/comma/dash, or this line STARTS on one
# ("at. 1.00 = break-even ..." belongs above; "cycle floors, our own ..." does not).
DANGLING_END = {"and", "or", "the", "a", "an", "of", "to", "in", "with", "that", "but", "than", "as",
                "for", "from", "by", "at", "is", "are", "was", "were", "\u2014", "=", "+"}
DANGLING_START = {"at", "and", "or", "but", "then", "is", "are", "was", "were", "to", "of", "in",
                  "with", "than", "as", "for", "from", "by", "a", "an", "the"}


def _is_continuation(prev, line):
    if prev.rstrip().endswith((".", "!", "?")):
        return False
    if prev.rstrip()[-1:] in ",;-\u2014":
        return True
    if re.split(r"\s+", prev.strip())[-1].rstrip(",.;:").lower() in DANGLING_END:
        return True
    return re.split(r"\s+", line.strip())[0].rstrip(",.;:").lower() in DANGLING_START


def render_body(lines):
    """Simple, reliable reflow.

    - Lead line (ONE LINE / WHAT THIS IS) becomes a muted intro paragraph.
    - Remaining text is joined on lines that do not end a sentence.
    - Verdict line becomes a styled callout box.
    - Sections (HISTORY, LIMITS, etc.) get their own small heading.
    """
    items = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^->\s*\[(bear|bull|warn|flat)\]\s*(.+)$", line)
        if m:
            items.append(("verdict", m.group(1), m.group(2)))
            continue
        head = re.match(r"^([A-Z][A-Z ()]{2,22}):\s*(.+)$", line)
        if head and head.group(1) in LEAD_LABELS:
            items.append(("lead", "", head.group(2)))
            continue
        if head and head.group(1) in SECTION_LABELS:
            items.append(("sec", head.group(1), head.group(2)))
            continue
        if items and items[-1][0] in ("text", "lead", "sec") and _is_continuation(items[-1][2], line):
            items[-1] = (items[-1][0], items[-1][1], (items[-1][2] + " " + line).strip())
            continue
        items.append(("text", "", line))

    out = []
    for kind, label, text in items:
        t = esc(text)
        if kind == "verdict":
            out.append(f'<div class="vbox {label}"><span class="stag">{STANCE_LABEL[label]}</span>'
                       f'<p class="vtext">{t}</p></div>')
        elif kind == "lead":
            out.append(f'<p class="blead">{t}</p>')
        elif kind == "sec":
            out.append(f'<div class="bsec"><span class="bseck">{esc(label.title())}</span>'
                       f'<p>{t}</p></div>')
        else:
            out.append(f'<p class="bline">{t}</p>')
    return '<div class="bbody">' + "".join(out) + "</div>"


BLOCK_CHARTS = {
    "1":  ("c_etf.png", "Daily net ETF flow, $M - bars in, bars out"),
    "2":  ("c_premium.png", "Coinbase premium over Binance, % - the US bid line"),
    "4":  ("c_stables.png", "USDT + USDC supply, $B - the dry-powder line"),
    "6":  ("c_ratios.png", "Long/short ratios and open interest - crowd positioning"),
    "7":  ("c_funding.png", "Funding rate, annualised % - what leverage costs"),
    "10": ("c_urpd.png", "Supply by cost-basis band - the shelves price sits on"),
    "11": ("chart.png", "Price vs Balanced Price and the all-time anchored VWAP"),
    "12": ("c_mvrv.png", "MVRV with 1.00 marked - the shaded band is holders underwater"),
    "13": ("c_cost.png", "Price vs LTH and STH cost basis - who paid what"),
    "14": ("c_rsi.png", "RSI, daily - the oversold line is 30"),
}

BLOCK_FIELDS = {
    "1":  "latest = yesterday's net creation (T+1 = published a day late); 5d/10d/30d = running sums",
    "2":  "live = now, last close = settled; 30d avg = the trend; streak = days one sign; 1y low = the extreme",
    "3":  "the premium with USDT noise removed; percentile vs the past year; streak = days in this regime",
    "4":  "supply in $B; 1d/7d/30d = the change over that window; combined = stablecoin dry powder",
    "5":  "net aggressive buying per venue; % of vol = its size against that venue's total volume",
    "6":  "L/S = accounts long per short; pctile = rank in its own 30d; OI = open interest in $bn",
    "7":  "rate per 8h and the annualised equivalent; basis = perp vs index; positive = longs pay shorts",
    "8":  "0-100 crowd index: <20 capitulation, >80 euphoria; percentile = rank within the 30d window",
    "9":  "longs = BTC held in margin longs; avg price = volume-weighted entry of the adds; premium = vs Binance",
    "10": "supply by cost-basis band, as % of total; the band at spot is the shelf that matters",
    "11": "spot as a multiple of each floor; 1.0x Balanced = where past cycle bottoms landed",
    "12": "market value / realised value: 1.00 = break-even for the average holder; floors = cycle lows",
    "13": "average price each age cohort paid; gap = how far the long-term base sits under recent buyers",
    "14": "0-100 momentum, <30 oversold; the 'forming' line drifts until the daily close",
    "15": "a new 20d price low versus RSI14 at that low; needs a failed rally, not just a drop",
    "16": "moving averages (200/50/10-day); armed = the conditions that make fading positive-EV",
}


def split_entry(text: str) -> tuple[str, str]:
    """Split one legend entry into (title, rest).

    Two shapes exist in the digest: "<Title: sentence...>" where a short lead-in is followed by a colon,
    and "<Plain sentence>. <More sentences...>" with no colon at all. The earlier parser demanded the
    first shape and a title under 40 characters, so every plain-sentence entry was silently dropped.
    """
    colon = text.find(":")
    dot = text.find(". ")
    if 0 < colon <= 45 and (dot == -1 or colon < dot):
        return text[:colon].strip(), text[colon + 1:].strip()
    if dot != -1 and dot <= 90:
        return text[:dot].strip(), text[dot + 2:].strip()
    return text.strip(), ""


def render_legend(body_lines):
    """LEGEND entries as numbered rows, not one pre block.

    Each entry is "[N] Title: sentence..." with wrapped continuation lines. Parse, then render a
    badge + title + paragraph so sixteen explanations read as sixteen things rather than as a wall.
    """
    entries = []
    for raw in body_lines:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\[(\d+)\]\s*(.+)$", line)
        if m:
            title, detail = split_entry(m.group(2).strip())
            entries.append([m.group(1), title, detail])
        elif entries:
            entries[-1][2] = (entries[-1][2] + " " + line).strip()
    rows = "".join(
        f'<div class="legrow"><span class="legnum">{n}</span>'
        f'<div class="legtxt"><h4>{esc(t)}</h4>' + (f'<p>{esc(d)}</p>' if d else '') + '</div></div>'
        for n, t, d in entries)
    return f'<div class="card legcard">{rows}</div>'


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
        num = (re.match(r"\[(\d+[a-z]?)\]", title) or [None, ""])[1]
        # split the trailing verdict off the body: it is a callout, not a line of text
        body_txt, verdict_line = [], None
        for ln in body:
            if re.match(r"^\s*->\s*\[(bear|bull|warn|flat)\]", ln) and ln.strip():
                verdict_line = ln
            else:
                body_txt.append(ln)
        extra = ""
        fields = BLOCK_FIELDS.get(num)
        if fields:
            extra += f'<p class="bfields"><b>Fields:</b> {esc(fields)}</p>'
        ch = BLOCK_CHARTS.get(num)
        if ch and os.path.exists(os.path.join(HERE, ch[0])):
            # hash the bytes into the URL: GitHub Pages caches assets hard, and a changed PNG under
            # the same name served the OLD plot for a day ("am still looking at the old chart")
            ver = "1"
            try:
                with open(os.path.join(HERE, ch[0]), "rb") as fh:
                    ver = hashlib.md5(fh.read()).hexdigest()[:10]
            except Exception:
                pass
            extra += (f'<figure class="bchart"><img src="{ch[0]}?v={ver}" alt="{esc(ch[1])}" '
                      f'loading="lazy"><figcaption>{esc(ch[1])}</figcaption></figure>')
        body_html = render_body(body_txt)
        if verdict_line:
            body_html += render_body([verdict_line])
        ent = _LEGEND["map"].get(num)
        gloss = f'<p class="gloss">{esc(ent[0])}</p>' if ent and ent[0] else ""
        more = (f'<details class="more"><summary>More detail</summary><p>{esc(ent[1])}</p></details>'
                if ent and ent[1] else "")
        if num:
            _LEGEND["seen"].add(num)
        out.append(f'<div class="card"><h3>{esc(title)}</h3>{gloss}{body_html}{extra}{more}</div>')
    return "\n".join(out)


def section_stance(body_lines):
    """Net stance of a whole section, from the stance tags its blocks carry.

    This is the cue the section header was missing. "If flow is bearish, everything below is a
    bounce to sell" was an instruction with no way to check it - you had to total up five blocks
    by hand. Now the header says it outright.
    """
    tags = re.findall(r"->\s*\[(bear|bull|warn|flat)\]", "\n".join(body_lines))
    if not tags:
        return None
    nb, nu, nw = tags.count("bear"), tags.count("bull"), tags.count("warn")
    tally = " / ".join(f"{n} {word}" for n, word in
                       ((nb, "bearish"), (nu, "bullish"), (nw, "caution")) if n)
    if nb > nu:
        return "bear", f"NET BEARISH - {tally}"
    if nu > nb:
        return "bull", f"NET BULLISH - {tally}"
    if nb or nw:
        return "warn", f"MIXED - {tally}"
    return "flat", "NO SIGNAL - nothing directional"


_LEGEND = {"html": "", "map": {}, "seen": set()}


def _ensure_diagrams():
    """Regenerate the two explanatory images if missing, so a fresh clone still builds."""
    import subprocess
    d = os.path.dirname(os.path.abspath(__file__))
    for f in ("img_divergence_types.png", "img_evidence_divergence.png"):
        if not os.path.exists(os.path.join(d, f)):
            subprocess.run([sys.executable, os.path.join(d, "diagrams.py")], check=False)
            break


def _stamp():
    """Build time + a hash of the digest the page was built from.

    The git hash was misleading: the page is built before the commit exists, so it always named the
    previous commit. The digest hash changes exactly when the content does, which is the question
    being asked ("am I looking at the old page?").
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_digest.txt"), "rb") as f:
            d = hashlib.md5(f.read()).hexdigest()[:6]
    except Exception:
        d = "nofile"
    return f'build {ts}Z &middot; digest {d}'


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
    # Parse the LEGEND section first: each block will carry its own gloss and collapsible detail,
    # so the reader never leaves the number to find out what the number means.
    legend_raw = []
    for sec in sections:
        if sec["title"].startswith("LEGEND"):
            for raw in sec["body"]:
                line = raw.strip()
                if not line:
                    continue
                m = re.match(r"^\[(\d+[a-z]?)\]\s*(.+)$", line)
                if m:
                    legend_raw.append([m.group(1), m.group(2)])
                elif legend_raw:
                    # legend entries wrap across physical lines; dropping the continuation cut every
                    # "more detail" off at the first line break
                    legend_raw[-1][1] += " " + line
    legend = {}
    for n, txt in legend_raw:
        t, d = split_entry(" ".join(txt.split()))
        legend[n] = (t, d)
    _LEGEND["map"] = legend
    _LEGEND["seen"] = set()

    out = []
    for l in [x for x in head if x.strip()]:
        if l.startswith("VERDICT:"):
            continue                       # rendered as its own tile in the header
        if l.startswith("BTC daily read") or l.startswith("spot "):
            continue                       # promoted into the big spot block at the top
        out.append(f'<div class="hrow">{esc(l)}</div>')
    for s in sections:
        if s["title"].startswith("LEGEND"):
            # handled before the section header is emitted: the glossary itself is gone, and an
            # empty heading with nothing under it is worse than no heading
            pass
        else:
            st = section_stance(s["body"])
            badge = f' <span class="sbadge {st[0]}">{esc(st[1])}</span>' if st else ""
            out.append(f'<h3 class="sec">{esc(s["title"])}{badge}</h3>')
            for d in s["desc"]:
                out.append(f'<p class="sdesc">{esc(d)}</p>')
        if s["title"].startswith("LEGEND"):
            # every entry that has a block on this page now lives under that block, so only the
            # leftovers ([+], [7b]) need a home here
            leftovers = [(n, t, d) for n, (t, d) in _LEGEND["map"].items()
                         if n not in _LEGEND["seen"]]
            if leftovers:
                rows = "".join(
                    f'<div class="legrow"><span class="legnum">{n}</span>'
                    f'<div class="legtxt"><h4>{esc(t)}</h4>'
                    + (f'<p>{esc(d)}</p>' if d else '') + '</div></div>'
                    for n, t, d in leftovers)
                out.append(f'<h3 class="sec">Other readings</h3>'
                           f'<p class="sdesc">These appear in the digest but not as their own block.</p>'
                           f'<div class="card legcard">{rows}</div>')
            continue
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


VERDICT_WORDS = (
    ("bear", ("absent", "leaving", "negative", "below", "draining", "sell", "bearish", "risk-off",
              "underwater", "losing", "contraction", "outflow", "weak")),
    ("bull", ("returning", "arriving", "positive", "above", "inflow", "bid present", "bullish",
              "improving", "strong", "buying")),
    ("warn", ("mixed", "caution", "conflict", "two-sided", "stretched")),
)


def verdict_stance(text):
    """Colour the verdict by what it says, not by what colour the last build happened to use."""
    t = (text or "").lower()
    m = re.match(r"^\s*\[(bearish|bullish|caution|no signal)\]", t)
    if m:
        return {"bearish": "bear", "bullish": "bull", "caution": "warn", "no signal": "flat"}[m.group(1)]
    for cls, words in VERDICT_WORDS:
        if any(w in t for w in words):
            return cls
    return "flat"


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
        # Plain-language sub-line. "1y pctile 83%" assumed the reader knows the measure and what a
        # percentile is. The side matters: an RSI of 24 sits in the BOTTOM 4% of the year, and a
        # naive "top (100-pct)%" printed that as "top 96%", which reads as a high reading. Name
        # the smaller side, then spell the rank out as a percentage of days in the note.
        sub = ("bottom %s%% of the past year" % pct if int(pct) <= 50
               else "top %d%% of the past year" % (100 - int(pct))) if pct else "daily close"
        state = ("Oversold - capitulation zone" if v < 30 else
                 ("Overbought - stretched" if v > 70 else "Neutral, no extreme"))
        note = (f"14-day RSI. {pct}% of the past year's daily closes were lower. {state}."
                if pct else state)
        t.append(tile("RSI(14)", r14, sub, note,
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

    ls = re.search(r"all-acct L/S ([\d\.]+) \(30d ([\d\.]+)-([\d\.]+), median ([\d\.]+), "
                   r"crowd lines ([\d\.]+)/([\d\.]+), pctile (\d+)%\)", raw)
    if ls:
        lsv, lo, hi, med, c15, c85 = ls.group(1, 2, 3, 4, 5, 6)
        lsp = int(ls.group(7))
        # Thresholds MUST match the digest's own verdict gates (p85 / p15). These were 80/20 here
        # while the block text used 85/15, so at an 82nd-pctile reading the tile said "mid-range,
        # no signal" while the block directly beneath it said "crowded LONG".
        crowd_long, crowd_short = lsp >= 85, lsp <= 15
        # Written for a first-time reader: the sub-line says the rank in plain words and names
        # what is being ranked ("of its own month") instead of "higher than 83% of the last 30
        # days", which read like a count of days rather than a rank within 30 daily readings.
        # The note defines the measure BEFORE the percentile, spells the rank out as a count,
        # and says where the normal band comes from (p15-p85 = the middle 70% of the month).
        if crowd_long:
            note = f"Above the normal band ({c15}-{c85}): crowded long, squeeze risk is down."
        elif crowd_short:
            note = f"Below the normal band ({c15}-{c85}): crowded short, squeeze risk is up."
        else:
            note = f"Inside the normal band ({c15}-{c85}): no crowding signal either way."
        # Same side rule as the RSI tile: name the smaller tail, so a 10th-pctile reading says
        # "bottom 10% of its own month" instead of a technically-true-but-useless "top 90%".
        sub = (f"bottom {lsp}% of its own month" if lsp <= 50
               else f"top {100 - lsp}% of its own month")
        t.append(tile("Longs per short", lsv,
                      sub,
                      note,
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

    ("Holder cost basis &mdash; what long-term and recent buyers actually paid", "Holder cost basis",
     '<p><strong>What it is.</strong> Every coin carries the price of the last time it moved. Split '
     'the supply by how long it has sat still &mdash; <strong>155 days</strong> is the standard line '
     '&mdash; and you get two average purchase prices: <strong>LTH</strong> (long-term holders, coins '
     'last moved over 155 days ago) and <strong>STH</strong> (short-term holders, moved within 155 '
     'days). These are cost bases, not forecasts: they say what each group paid.</p>'
     '<p><strong>Why the split matters.</strong> The two groups behave completely differently. A '
     'recent buyer sitting 20% underwater is a seller the moment price returns to their entry &mdash; '
     'that is the overhead supply. A long-term holder sitting in profit has no reason to sell into a '
     'decline at all. So the same price fall produces selling from one group and nothing from the '
     'other, which is why price can drop on falling volume.</p>'
     '<p><strong>How to read the levels.</strong> Price at or below the <strong>STH cost</strong> '
     'means recent buyers are underwater and rallies meet their break-even orders first. Price above '
     'the <strong>LTH cost</strong> means the patient base is still in profit and not forced to sell '
     '&mdash; that is what makes the LTH line the floor with actual holders behind it, rather than a '
     'line drawn on a chart.</p>'
     '<p><strong>The gap is the useful bit.</strong> When LTH cost sits far below STH cost, the crowd '
     'sits on top of a much lower long-term base: the recent cohort is the fragile one, and its '
     'break-even prices are what every rally has to chew through.</p>'
     '<p class="note"><strong>Limits, stated on the block itself.</strong> The free tier only carries '
     'this pair from November 2022 &mdash; 1,445 days &mdash; so the block refuses to make a '
     'cycle-spanning claim. In that window price closed below the LTH cost basis exactly once '
     '(Nov 2022&ndash;Jan 2023, reaching 23% below it), and six and twelve months after the start of '
     'that episode price was up 65% and 131%. That is one observation: it is the only direct evidence '
     'available, and it is not a statistic. Cost basis is a slow-moving average &mdash; a level to '
     'lean on, never a trigger.</p>'),

    ("MVRV &mdash; market value vs realised value", "MVRV",
     '<p><strong>What it is.</strong> Every coin has a last-moved price, and the sum of those is the '
     '<em>realised cap</em> &mdash; the <strong>average price the whole market actually paid</strong>. '
     'Divide market cap by realised cap and you get MVRV. So <code>1.00</code> means the market is '
     'exactly at break-even, and <code>0.80</code> means the average holder is down 20%.</p>'
     '<p><strong>Why it matters.</strong> Below 1.00 the average holder is under water &mdash; which in '
     'BTC history has only happened near cycle bottoms. That is why it reads bear-market cheapness '
     'better than any single price level: it says nothing about where price goes next week, but it '
     'does say whether the market is being handed to buyers at cost or below it.</p>'
     '<p><strong>Two ways the level can be read, and they disagree.</strong> The floor multiple rises '
     'each cycle &mdash; but by less each time (+0.177, +0.127, +0.063). If that keeps halving, the '
     'next floor is ~0.79; if the last increment simply repeats, ~0.82. Against today&rsquo;s realised '
     'price that is a <strong>zone of roughly $42k&ndash;$44k</strong>, and a straight-line fit on the '
     'same four floors instead gives ~0.91 / $48k. Both are printed on the block on purpose: any single '
     'number for this is a guess dressed as a forecast.</p>'
     '<p><strong>The structural caveat.</strong> The <em>multiple</em> is the stable thing, not the '
     'dollars. In capitulation, coins change hands at lower prices, so realised cap falls and the '
     'dollar floor drops with it. Expect the floor price to move down as the bottom approaches.</p>'
     '<p><strong>The clock.</strong> The more usable part is timing. Across four cycles the MVRV low '
     'came <strong>26&ndash;149 days after</strong> the first sub-1.00 print, and MVRV then stayed '
     'below 1.00 for <strong>7&ndash;16 months</strong>. It does not bottom on the cross &mdash; it '
     'grinds. So the trigger is not a price target, it is the first close with MVRV below 1.00: that '
     'starts the clock.</p>'
     '<p class="note"><strong>Limits.</strong> Four completed observations, all from one asset with a '
     'structural adoption trend underneath it &mdash; the rising floors are partly just that. The '
     'series is Look Into Bitcoin, keyless, and the block recomputes the floors on every run rather '
     'than quoting them.</p>'),

    ("Bitfinex margin longs &mdash; the price the leveraged bid is paying", "Bitfinex margin longs",
     '<p><strong>What it is.</strong> Bitfinex publishes, hourly, how much BTC is held in '
     '<em>margin longs</em> &mdash; positions where someone borrowed dollars to buy BTC. It is '
     'leveraged money: it must be repaid, it gets liquidated on dips, and it tends to sell into '
     'rallies to take profit. Rising longs means someone is betting on higher prices with borrowed '
     'money on that one venue.</p>'
     '<p><strong>The number worth acting on is not the size.</strong> It is the '
     '<strong>average price of the additions</strong>: every hour the position grew, weighted by that '
     'hour&rsquo;s price. That is where those buyers are actually long from, and it turns the series '
     'into price levels:</p>'
     '<table><thead><tr><th>window</th><th>what the level tells you</th></tr></thead><tbody>'
     '<tr><td>7-day entry</td><td>the <strong>live bid</strong> &mdash; what the newest leveraged buyers '
     'paid. They defend it, and it triggers selling if it breaks.</td></tr>'
     '<tr><td>30-day entry</td><td><strong>overhead supply</strong> &mdash; if spot is below it, the '
     'average buyer is under water and bounces run into people exiting at break-even.</td></tr>'
     '<tr><td>90-day entry</td><td>the deeper trapped cohort &mdash; the ceiling a real recovery has to '
     'chew through.</td></tr></tbody></table>'
     '<p><strong>How to read the history line.</strong> For earlier surges of comparable size, we '
     'measure the highest and lowest price over the following 30 days, then compare that with a random '
     'hour from the same period. The baseline is the whole point: on its own, &ldquo;best +2.4%, worst '
     '&minus;20.4%&rdquo; proves nothing. Against &ldquo;+6.1% / &minus;7.0% for a random hour&rdquo; it '
     'says the surges produced smaller bounces and deeper dips &mdash; the buying was early, not smart.</p>'
     '<p class="note"><strong>Limits.</strong> One aggregate long book &mdash; no account sizes, so '
     '&ldquo;whales&rdquo; is an inference from the venue, not an observation. The sample is 417 days '
     'of a single regime and only 10 episodes, so this is context for the flow and positioning blocks, '
     'never a trigger on its own.</p>'),

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
     '<p><strong>VWAP</strong> = volume-weighted average price. The average price BTC traded at, '
     'where a price that traded heavy volume counts for more than a price that traded almost '
     'nothing. It answers &ldquo;what did buyers actually pay?&rdquo; A simple average counts every '
     'candle equally; VWAP counts the ones with real money behind them.</p>'
     '<p><strong>AVWAP</strong> = anchored VWAP &mdash; the same calculation started from a chosen '
     'date instead of the whole history. Anchored at 2015-07-20 (Coinbase&rsquo;s first BTC-USD '
     'candle) it is the break-even price of every Coinbase buyer since the exchange opened. Above '
     'it the average buyer is in profit; below it, underwater.</p>'
     '<p><strong>Balanced Price</strong> (realized price &minus; transferred price) is where past '
     'cycle bottoms have converged (~1.0x). Both are deep floors, not timing triggers.</p>'
     '<p><strong>The 350-week MA</strong> is the long-term trend line with a perfect record: in '
     '<strong>499 weeks</strong> since it existed, there has not been <strong>one weekly close '
     'below it</strong>, and the closest approach was <strong>1.046x in January 2023</strong>. That '
     'makes it a hard reference rather than a fitted guess &mdash; the difference between &ldquo;price '
     'has always bounced around here&rdquo; and &ldquo;price has never once settled below here.&rdquo; '
     'It is not a magnet: 2023 bottomed 4.6% above it and turned. Treat it as the line where the '
     'long-term trend would actually break, not as a bounce trigger.</p>'),

    ("RSI &mdash; momentum", "RSI - momentum",
     '<p>Wilder RSI on <strong>daily closes only</strong>, printed two ways so they never have to '
     'be reconciled: <strong>settled</strong> (completed days, stable, what to reason with) and '
     '<strong>incl. today&rsquo;s forming candle</strong> (what a live chart shows, drifts all day).</p>'
     '<p><strong>Weekly RSI</strong> is printed underneath for context, because it answers a '
     'different question: daily RSI fires dozens of times a cycle, weekly RSI below 30 has happened '
     'in only <strong>8 weeks in 16 years</strong> &mdash; January 2015, June 2022 and February '
     '2026. It is a bottom marker, not a trade signal: the last three prints were followed within '
     'six months by a best case of +47%, +28% and +20% and a worst case of 0%, &minus;13% and '
     '&minus;11%.</p>'
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
        # NEVER run the digest from here. Two reasons, both learned the hard way:
        #   1. it doubles every API call - bitcoin-data.com allows 10/hour, and the wrapper
        #      already ran the digest once for this build;
        #   2. the page would then be built from a DIFFERENT run than latest_digest.txt, so the
        #      cached text and the page disagree (premium -0.122% on the page vs -0.112% in the
        #      cache) and there is no way to tell which is current.
        # Read the text the wrapper just captured instead.
        with open(os.path.join(HERE, "latest_digest.txt")) as fh:
            raw = fh.read()
    # Provenance stamps. The audit verifies these, so a page can never be built from a digest
    # other than latest_digest.txt (that is how the page once showed premium -0.122% while the
    # cache said -0.112%), and so "data as of" can never silently become the build clock.
    digest_md5 = hashlib.md5(raw.encode()).hexdigest()[:12]
    built_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    blocks_html = render_digest(raw)
    _ensure_diagrams()
    kpis = kpi_tiles(raw)
    heads = block_heads(raw)   # [(printed number, title)] - inline refs use these, never literals

    spot = _grab(r"spot \$([\d,]+)", raw, 1, "n/a")
    bnpx = _grab(r"\(Coinbase\)\s*\$([\d,]+)", raw, 1, "")
    usdt = _grab(r"USDT/USD\s+([\d.]+)", raw, 1, "")
    verdict = _grab(r"^VERDICT: (.+)$", raw, 1, "")
    verdict_cls = verdict_stance(verdict)
    verdict_tag = {"bear": "BEARISH", "bull": "BULLISH", "warn": "CAUTION",
                   "flat": "NO SIGNAL"}[verdict_cls]
    # The digest stamps its own run time; the page must quote THAT as the data time. Using the
    # build clock made a page built from a 40-minute-old digest claim to be up to the minute.
    digest_ts = _grab(r"BTC daily read\s*\|\s*([\d\-]+ [\d:]+ UTC)", raw, 1, "")
    updated = digest_ts or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    built_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Secondary venues for the header strip. The big figure IS the Coinbase print, so repeating it
    # would be the same duplication we just deleted - the spread is the genuinely new number
    # (how far the US print sits from the global one).
    bits = []
    if bnpx:
        bits.append(f'<span><b>Binance</b>${bnpx}</span>')
    try:
        cbv, bnv = float(spot.replace(",", "")), float(bnpx.replace(",", ""))
        d = cbv - bnv
        bits.append(f'<span><b>Coinbase &minus; Binance</b>{d:+,.0f} ({d / cbv * 100:+.2f}%)</span>')
    except Exception:
        pass
    if usdt:
        bits.append(f'<span><b>USDT/USD</b>{usdt}</span>')
    spot_extra = "".join(bits)

    # the deep price/floor/VWAP chart from the digest run
    src = os.path.join(CHART_DIR, f"btc_daily_{datetime.now(timezone.utc):%Y-%m-%d}.png")
    if not os.path.exists(src):
        cands = sorted(f for f in os.listdir(CHART_DIR) if f.startswith("btc_daily_"))
        src = os.path.join(CHART_DIR, cands[-1]) if cands else None
    def card(title, img_src, alt, now, use, verdict, cls=""):
        # normalise: callers pass "wide" or " wide" - concatenating raw gave class="ccardwide"
        cls = f" {cls.strip()}" if cls and cls.strip() else ""
        chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in (now or []))
        # Cache-buster on the image URL. GitHub Pages serves assets with a long max-age and the
        # browser keeps the OLD PNG when only the bytes change under the same filename - that
        # shipped a corrected caption on top of the previous chart and the reader saw the old
        # plot ("am still looking at the old chart"). Hash the bytes so a new image is a new URL.
        ver = f"{datetime.now(timezone.utc):%Y%m%d%H%M}"
        try:
            with open(os.path.join(HERE, img_src), "rb") as fh:
                ver = hashlib.md5(fh.read()).hexdigest()[:10]
        except Exception:
            pass
        sep = "&" if "?" in img_src else "?"
        return (f'<div class="ccard{cls}"><h4>{esc(title)}</h4>'
                f'<div class="cnow">{chips}</div>'
                f'<img src="{img_src}{sep}v={ver}" alt="{esc(alt)}">'
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
            "VWAP = volume-weighted average price: the average price BTC changed hands at, where a "
            "price that traded heavy volume counts for more than one that traded almost nothing. "
            "It answers 'what did buyers actually pay?' AVWAP is the same sum anchored to a chosen "
            "start date - here 2015-07-20, Coinbase's first BTC-USD candle - so it is the "
            "break-even of EVERY Coinbase buyer since the exchange opened. Above it, the average "
            "buyer is in profit; below it, underwater. Balanced Price is where past cycle BOTTOMS "
            "converged (~1.0x). Both are deep floors, not timing triggers - price can sit far "
            "above them for a long time, as it does now (2.2x AVWAP, 1.7x Balanced).",
            (f"Spot is {balx}x the Balanced floor and {avwx}x the all-time VWAP. A full retest of "
             f"the floor would be roughly ${bal}." if bal and balx and avwx else ""),
            " wide")

    # indicator charts
    chart_meta = []
    try:
        chart_meta = chartmod.build_all(HERE, SERIES_PATH, digest_text=raw)
    except Exception as e:
        chart_meta = [{"file": "", "title": f"charts unavailable ({type(e).__name__})", "caption": ""}]

    ccards = [card(c["title"], esc(c["file"]), c["title"], c.get("now"),
                   c.get("use", ""), c.get("verdict", ""), c.get("cls", ""))
              for c in chart_meta if c.get("file")]
    chart_grid = '<div class="cgrid">' + cycle_html + "".join(ccards) + "</div>"

    # The levels ladder goes on the DASHBOARD, above the blocks: it is the one picture that shows
    # all of block [11]-[13] at once, and page one was the wall of text being complained about.
    ladder_html = ""
    for m in chart_meta:
        if m.get("file") == "c_levels.png":
            # the ladder is a map, not a verdict: its "nearest floor" line goes into the caption.
            # Left as a -> line it reads as an untagged stance and trips the page audit.
            use_txt = m.get("use", "")
            if m.get("verdict"):
                use_txt += " Nearest floor: " + m["verdict"].replace("nearest floor ", "") + "."
            ladder_html = card(m["title"], esc(m["file"]), m["title"], m.get("now"),
                               use_txt, "", " wide")
            break

    # Bottom score tab, built by the engine in /root/btc-bottom. If it fails, say so on the page
    # rather than shipping a silent hole where a headline number should be.
    try:
        import sys as _sys
        if "/root/btc-bottom" not in _sys.path:
            _sys.path.insert(0, "/root/btc-bottom")
        import render_section as _bottom
        bottom_html = _bottom.render(HERE, verdict=verdict)
    except Exception as _e:
        bottom_html = (f'<p class="note">Bottom score unavailable this build '
                       f'({type(_e).__name__}: {_e}). The rest of the digest is unaffected.</p>')

    build_stamp = _stamp()
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Daily Digest</title>
<meta name="digest-md5" content="{digest_md5}">
<meta name="page-built" content="{built_stamp}">
<meta name="description" content="Daily Bitcoin flow, positioning and momentum digest with backtested rules.">
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <h1>BTC Daily Digest</h1>
  <div class="spotlbl">Bitcoin spot &middot; Coinbase<span class="upd">updated {updated} &middot; {build_stamp}</span></div>
  <div class="spotpx">${spot}</div>
  <div class="spotrow">{spot_extra}</div>
  <div class="verdict-card {verdict_cls}"><span class="stag {verdict_cls}">{verdict_tag}</span><span>{esc(verdict)}</span></div>
  {kpis}
</header>

<div class="tabbar">
  <nav class="tabs">
    <button class="on" data-t="dash">Dashboard</button>
    <button data-t="bottom">Bottom Score</button>
    <button data-t="charts">Charts</button>
    <button data-t="ref">Reference</button>
    <button data-t="ev">Evidence</button>
    <button data-t="guide">Guide</button>
  </nav>
</div>

<section id="dash" class="tab on">
{ladder_html}
{blocks_html}
</section>

<section id="bottom" class="tab">
{bottom_html}
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

<div class="card">
<h3 class="cardh">How these numbers were measured</h3>
<p class="bline">BTCUSDT daily. Forward returns are measured from the day you could actually act.
Barrier tables are intrabar, and when both sides are touched in the same bar the adverse one is counted
first. EV is the probability-weighted outcome of the target and stop pair.</p>
</div>

<div class="card">
<h3 class="cardh">RSI crossovers alone are coin flips</h3>
<p class="bline">Sample: 1000 days. These fire often and lose more often than they win, so they are useful
for describing momentum, not for triggering entries.</p>
{ev_table(EVIDENCE["rsi_rules"])}
</div>

<div class="card">
<h3 class="cardh">Divergence over nine years</h3>
<p class="bline">Sample: 3378 days. A textbook bullish divergence on its own did not beat simply holding.
Only the oversold-constrained variant has an edge, and that sample is only 12 events.</p>
{ev_table(EVIDENCE["divergence"])}
<figure class="bchart"><img src="img_evidence_divergence.png?v=0e195436"
alt="Win rate of each divergence variant against the 53 percent baseline" loading="lazy">
<figcaption>The table above, drawn. Only the oversold version clears the baseline bar.</figcaption></figure>
<div class="callout"><p><strong>Correction:</strong> an earlier figure of "62% win" was wrong. It came
from a shorter 2024 to 2026 sample and a definition that also flagged higher-low, higher-RSI cases, which
are not divergences. The numbers above replace it.</p></div>
</div>

<div class="card">
<h3 class="cardh">Short-fade: selling the bounce at resistance</h3>
<p class="bline">Better odds than the long side, but the edge is thin. Detected by block
{num_of(heads, "Short-fade watch")}.</p>
{ev_table(EVIDENCE["short_fade"])}
</div>

<div class="card">
<h3 class="cardh">Long the bounce: do not take this leg</h3>
<p class="bline">Riding a bounce to +7% before a minus 5% stop happens only 34% of the time, and every
variant is negative EV. Buying the bounce and then shorting loses money on the first leg.</p>
{ev_table(EVIDENCE["long_bounce"])}
</div>

</section>

<section id="guide" class="tab">

<div class="card">
<h3 class="cardh">How to read this page</h3>
<p class="bline">Sections are ordered by importance: flow first (where the money is going), then
positioning and sentiment, then price structure, momentum, and finally the trading signals. If flow is
bearish, everything below it is a bounce to sell.</p>
<p class="bline">Each section header carries a tally, and every block ends with a coloured tag. The colour
is the stance, not the tone of the wording:</p>
<div class="keys">
  <div class="keyrow"><span class="stag bear">BEARISH</span><span>Money or demand is leaving, or the crowd is leaning the wrong way.</span></div>
  <div class="keyrow"><span class="stag bull">BULLISH</span><span>Money or demand is arriving.</span></div>
  <div class="keyrow"><span class="stag warn">CAUTION</span><span>Contrarian or bounce risk. Act carefully, if at all.</span></div>
  <div class="keyrow"><span class="stag flat">NO SIGNAL</span><span>Nothing directional. Do not force a trade.</span></div>
</div>
<p class="bnote">All blocks use settled daily closes unless a line says "live".</p>
</div>

<div class="card">
<h3 class="cardh">Divergence</h3>
<p class="bline">Price and the RSI stop agreeing. Price keeps going the same way, but the RSI refuses to
follow, so the move is running out of force underneath.</p>
<p class="bnote"><strong>Live reading:</strong> block {num_of(heads, "Divergence")} &mdash; Divergence, on
the Dashboard tab inside section 4. Momentum. This tab explains how to read it; it does not show today's
value.</p>
<h4 class="sub">The four types</h4>
<table><thead><tr><th>Type</th><th>Price</th><th>RSI</th><th>What it means</th></tr></thead><tbody>
<tr><td>Regular <strong>bullish</strong></td><td>lower low</td><td>higher low</td><td>Downtrend losing force, so a bounce is likely</td></tr>
<tr><td>Regular <strong>bearish</strong></td><td>higher high</td><td>lower high</td><td>Uptrend losing force, so a drop is likely</td></tr>
<tr><td>Hidden bullish</td><td>higher low</td><td>lower low</td><td>Uptrend is healthy, so the rise continues</td></tr>
<tr><td>Hidden bearish</td><td>lower high</td><td>higher high</td><td>Downtrend is healthy, so the fall continues</td></tr>
</tbody></table>
<figure class="bchart"><img src="img_divergence_types.png?v=77688c56"
alt="The four divergence types drawn out: regular and hidden, bullish and bearish" loading="lazy">
<figcaption>The same four types as lines. Price is the top line, RSI the bottom one, and the circles mark
the two pivots that disagree.</figcaption></figure>
<p class="bnote">Regular means reversal, hidden means continuation. Getting these two backwards is how
people buy tops.</p>
</div>

<div class="card">
<h3 class="cardh">Regular bullish, step by step</h3>
<ol class="steps">
<li>Two clear price lows, the second one lower than the first.</li>
<li>Add RSI(14) to the same chart.</li>
<li>The RSI at the second, lower price low is higher than it was at the first.</li>
<li>The price line slopes down while the RSI line slopes up.</li>
</ol>
<p class="bnote">In plain words: sellers keep pushing price to new lows, but with less force each time.
Same effort, less result.</p>
</div>

<div class="card">
<h3 class="cardh">What to look out for</h3>
<table><thead><tr><th>Good signs</th><th>Invalidators</th></tr></thead><tbody>
<tr><td>Lows 10 or more candles apart, both at obvious swing lows</td><td>Two adjacent candles, which is noise</td></tr>
<tr><td>RSI oversold at both lows, below 30 and ideally below 25</td><td>RSI only fractionally higher, for example 18 to 19</td></tr>
<tr><td>Second low has a long lower wick or a quick snap back</td><td>Price blows through on rising volume while RSI keeps falling</td></tr>
<tr><td>Volume lighter on the second low, so selling is drying up</td><td>Small-timeframe divergence inside a strong trend</td></tr>
<tr><td>Happens at a known level such as a URPD shelf or the 200-day average</td><td>You have to squint to see it</td></tr>
</tbody></table>
</div>

<div class="card">
<h3 class="cardh">Expectation and limits</h3>
<p class="bline">A divergence marks a zone, not a moment. Price often makes one final spike before it
turns, and that spike is the last seller capitulating, which is also where stops get hunted. Every variant
tested dipped roughly 5 to 6% before it paid.</p>
<p class="bnote"><strong>Never measure from the pivot date.</strong> Doing that flatters the result to an
86% win rate and +7.95%, which is how backtests lie.</p>
</div>

</section>

<footer>
<p>Generated automatically from keyless public APIs (Coinbase, Binance, DeFiLlama, cryptoetf.today, Look Into Bitcoin, BGeometrics, alternative.me). No credentials, no subscription feeds.</p>
<p>Not financial advice. Backtest figures are historical and samples are small where noted.</p>
<p>Data as of {updated} &middot; page built {built_ts}</p>
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
