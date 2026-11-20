#!/usr/bin/env python3
"""Cross-check the digest page: does every number agree with the digest text, and does the
arithmetic hold up when re-derived from the raw series?

Three layers can drift apart:
  1. the digest text (coinbase_premium_daily.py stdout) - the source of truth
  2. the KPI tiles      (build_site.py, parsed out of that text with regexes)
  3. the chart cards    (charts.py, computed from digest_series.json and the text)

A number that appears in two places and disagrees is worse than a missing number: the reader
cannot tell which one to trust. This script exists because exactly that shipped twice (a
crowding gate of 80/20 against the digest's 85/15, and "83th pctile" against "83rd").

Usage: python3 audit_digest.py
Exit code 1 if any HARD check fails.
"""
import hashlib
import json
from datetime import datetime
import re
import statistics
import sys

SITE = "/root/btc-digest-site"
DIGEST = f"{SITE}/latest_digest.txt"
HTML = f"{SITE}/index.html"
SERIES = "/root/.hermes/state/digest_series.json"
datetime_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

fails, warns, oks = [], [], []


def check(name, got, want, tol=None):
    """tol=None -> compare as strings after normalising; else numeric comparison."""
    if want is None or got is None:
        warns.append(f"{name}: missing on one side (got={got!r} want={want!r})")
        return
    if tol is None:
        if str(got).strip() == str(want).strip():
            oks.append(name)
        else:
            fails.append(f"{name}: page says {got!r}, digest says {want!r}")
        return
    try:
        g, w = float(str(got).replace(",", "").replace("$", "")), float(str(want).replace(",", "").replace("$", ""))
    except ValueError:
        fails.append(f"{name}: unparseable got={got!r} want={want!r}")
        return
    if abs(g - w) <= tol:
        oks.append(name)
    else:
        fails.append(f"{name}: page says {g}, digest says {w} (diff {g - w:+.4f}, tol {tol})")


def num(s):
    """Last number in a string: '30-day change -$11.56B' -> -11.56.

    Stripping every non-digit character turned that into '30-11.56' and raised. Take the final
    numeric token instead, so a leading label can never corrupt the value.
    """
    found = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", str(s))
    if not found:
        return None
    try:
        return float(found[-1].replace(",", ""))
    except ValueError:
        return None


raw = open(DIGEST).read()
html = open(HTML).read()
S = json.load(open(SERIES))

# ---------------------------------------------------------------- parse tiles
tiles = {}
for m in re.finditer(r'<span class="k">(.*?)</span><span class="v[^"]*">(.*?)</span>'
                     r'<span class="d[^"]*">(.*?)</span><span class="n">(.*?)</span>', html):
    from html import unescape as _unesc
    label = _unesc(m.group(1))
    tiles[label] = {"value": m.group(2), "delta": _unesc(m.group(3)),
                    "note": _unesc(m.group(4))}

# ------------------------------------------------------- digest source values
d = {
    "spot": re.search(r"spot \$([\d,]+) \(Coinbase\)", raw).group(1),
    "etf5": re.search(r"5d (-?\$[\d,\.]+M)\s+10d", raw).group(1),
    "etf30": re.search(r"30d (-?\$[\d,\.]+M)\s*\n", raw).group(1),
    "prem_live": re.search(r"live ([+-][\d\.]+)%", raw).group(1),
    "prem_avg": re.search(r"30d avg ([+-][\d\.]+)%", raw).group(1),
    "streak": re.search(r"negative streak (\d+)d", raw).group(1),
    "stbl": re.search(r"combined \$([\d\.]+B)", raw).group(1),
    "stbl30": re.search(r"combined \$[\d\.]+B\s+7d (-?\$[\d\.]+B)\s+30d (-?\$[\d\.]+B)", raw).group(2),
    "rsi14": re.search(r"RSI\(14\) ([\d\.]+)", raw).group(1),
    "rsi_pct": re.search(r"RSI14 1y percentile (\d+)%", raw).group(1),
    "fund_ann": re.search(r"30d avg [+-][\d\.]+% /8h\s*->\s*([+-][\d\.]+)% annualised", raw).group(1),
    "oi": re.search(r"OI \$([\d\.]+)bn", raw).group(1),
    "oi_1d": re.search(r"OI \$[\d\.]+bn \(1d ([+-][\d\.]+)", raw).group(1),
    "ls": re.search(r"all-acct L/S ([\d\.]+)", raw).group(1),
    "ls_pct": re.search(r"all-acct L/S [\d\.]+ \([^)]*pctile (\d+)%\)", raw).group(1),
    "ls_med": re.search(r"median ([\d\.]+), crowd lines", raw).group(1),
    "ls_c15": re.search(r"crowd lines ([\d\.]+)/", raw).group(1),
    "ls_c85": re.search(r"crowd lines [\d\.]+/([\d\.]+)", raw).group(1),
    "fng": re.search(r"now (\d+) \(", raw).group(1),
}

print(f"parsed {len(tiles)} tiles, {len(cards) if 'cards' in dir() else 0} cards")
print("=" * 78)
print("LAYER 1 — KPI TILES vs DIGEST TEXT")
print("=" * 78)
t = tiles.get("ETF flows", {})
check("tile ETF 30d", t.get("value"), d["etf30"])
check("tile ETF 5d", (t.get("delta") or "").replace("5d ", ""), d["etf5"])

t = tiles.get("US premium", {})
check("tile premium live", t.get("value"), d["prem_live"] + "%")
check("tile premium streak", t.get("delta"), f"{d['streak']} days negative")

t = tiles.get("Stablecoins", {})
check("tile stables level", t.get("value"), "$" + d["stbl"])
check("tile stables 30d", (t.get("delta") or "").replace("30d ", ""), d["stbl30"])

t = tiles.get("RSI(14)", {})
check("tile RSI", t.get("value"), d["rsi14"])
_rp = int(d["rsi_pct"])
check("tile RSI percentile", t.get("delta"),
      (f"bottom {_rp}% of the past year" if _rp <= 50
       else f"top {100 - _rp}% of the past year"))
check("tile RSI note states the same rank", f"{_rp}% of the past year's daily closes were lower"
      in (t.get("note") or ""), True)

t = tiles.get("Funding rate", {})
check("tile funding", t.get("value"), d["fund_ann"] + "%")

t = tiles.get("Perp open interest", {})
check("tile OI", t.get("value"), "$" + d["oi"] + "bn")
check("tile OI 1d", (t.get("delta") or "").replace("1d ", ""), d["oi_1d"] + "bn")

t = tiles.get("Longs per short", {})
check("tile L/S value", t.get("value"), d["ls"])
_lp = int(d["ls_pct"])
check("tile L/S percentile word", t.get("delta"),
      (f"bottom {_lp}% of its own month" if _lp <= 50
       else f"top {100 - _lp}% of its own month"))

t = tiles.get("Fear & Greed", {})
check("tile F&G", t.get("value"), d["fng"])

# ------------------------------------------------------- chart card chips
print()
print("=" * 78)
print("LAYER 2 — CHART CARD CHIPS vs DIGEST TEXT")
print("=" * 78)
cards = {}
for m in re.finditer(r'<h4>(.*?)</h4><div class="cnow">(.*?)</div>', html):
    cards[m.group(1)] = re.findall(r'<span class="chip">(.*?)</span>', m.group(2))


def chip(title, needle):
    for c in cards.get(title, []):
        if needle in c:
            return c
    return None


# The card quotes the last SETTLED close (the series excludes the forming day), so compare it
# to the digest's "last close", not to the live tick. Comparing to live made a correct chip look
# like a bug.
c = chip("US vs global premium - is America paying up?", "last close")
d["prem_close"] = re.search(r"last close ([+-][\d\.]+)%", raw).group(1)
check("card premium last close", c.split()[-1].rstrip("%"), d["prem_close"], tol=1e-9)

c = chip("Momentum score (RSI) - how hard is it moving?", "momentum")
check("card RSI", c.split()[1], d["rsi14"], tol=1e-9)

c = chip("Open interest - how much leverage is in the system", "of positions open")
check("card OI", num(c), float(d["oi"]), tol=0.005)

c = chip("Long/short ratios - who is betting which way", "ordinary accounts")
check("card L/S", c.split()[2], d["ls"], tol=1e-9)

c = chip("US spot ETF flows - are institutions buying?", "last 30 days")
check("card ETF 30d", num(c), num(d["etf30"]) / 1000.0, tol=0.006)

c = chip("Stablecoin supply - is cash waiting to buy?", "total stablecoin")
check("card stables", num(c), float(d["stbl"].rstrip("B")), tol=0.05)

# ------------------------------------------------------- arithmetic re-derivation
print()
print("=" * 78)
print("LAYER 3 — ARITHMETIC RE-DERIVED FROM THE RAW SERIES")
print("=" * 78)
close = S.get("cb_close", [])
ra = S.get("ratios_all", [])

# MA200 straight from the closes the digest itself used
ma200 = sum(close[-200:]) / 200
dig_ma200 = num(re.search(r"MA200 ([\d,]+)", raw).group(1))
if dig_ma200:
    check("MA200 vs recomputed", ma200, dig_ma200, tol=1.5)

# L/S crowd lines should be the 15th/85th percentile of the 30-day window.
def _pctl(v, q):
    """Percentile by linear interpolation between order statistics.

    This MUST match the definition in the runner (`_pctl` in coinbase_premium_daily.py). The
    earlier nearest-rank form - sorted[int(0.85 * n)] - snapped to a real sample instead, so on
    2026-11-20 it reported 3.1322 against the digest's interpolated 3.1145 -> printed "3.11".
    That gap equalled the 0.02 tolerance and floating-point dust tipped it into a false FAIL on a
    page that was correct. An audit that flags correct data trains you to ignore it.
    """
    s = sorted(v)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


w = ra[-30:]
p15, p85 = _pctl(w, 15), _pctl(w, 85)
if abs(p85 - float(d["ls_c85"])) > 0.02:
    fails.append(f"L/S crowded-long line: digest prints {d['ls_c85']}, series 85th pctile = {p85:.2f}")
else:
    oks.append("L/S 85th line vs series")
if abs(p15 - float(d["ls_c15"])) > 0.02:
    warns.append(f"L/S crowded-short line: digest prints {d['ls_c15']}, series 15th pctile = {p15:.2f}")
else:
    oks.append("L/S 15th line vs series")
check("L/S median vs series", float(d["ls_med"]) if w else None,
      round(statistics.median(w), 2) if w else None, tol=0.02)

# the tile's stated percentile must match the series. Wording is "top N% of its own month", i.e.
# N is the complement of the percentile rank, so a pad of 1 is still the right tolerance.
m_tail = re.search(r"(top|bottom) (\d+)% of its own month", tiles["Longs per short"]["delta"])
if not m_tail:
    fails.append("L/S tile sub-line no longer readable as 'top/bottom N% of its own month'")
    tile_pct = None
else:
    tile_pct = (100 - int(m_tail.group(2))) if m_tail.group(1) == "top" else int(m_tail.group(2))
real_pct = round(100 * sum(1 for v in w if v <= w[-1]) / len(w))
check("L/S percentile vs recomputed", tile_pct, real_pct, tol=1)

# the note spells the rank out as a day count ("25 of the last 30 daily readings were lower").
# That count is a second, independent rendering of the same fact - if the wording is ever
# re-derived by hand it must still agree with the series.
m_lower = re.search(r"(\d+) of the last 30 daily readings were lower",
                    tiles["Longs per short"].get("note", ""))
if m_lower:
    check("L/S 'N of 30 lower' vs recomputed",
          int(m_lower.group(1)), sum(1 for v in w if v <= w[-1]), tol=0)
else:
    fails.append("L/S tile note no longer states how many of the 30 readings were lower")

# funding: 30d average 8-hourly rate x3 x365
fund = S.get("funding", [])
if fund:
    ann = sum(fund) / len(fund) * 100 * 3 * 365
    check("funding annualised vs recomputed", ann, float(d["fund_ann"]), tol=0.15)

# stablecoin combined = USDT + USDC. The card's three chips must quote the digest VERBATIM:
# charts.py used to sum a LIVE DeFiLlama fetch at build time, so a rebuild hours after the digest
# printed $244.6B under a text that said $244.7B. Exact string match, not a tolerance, because
# these are the same fact rendered twice.
stbl_chips = cards.get("Stablecoin supply - is cash waiting to buy?", [])
if len(stbl_chips) >= 3:
    d30 = num(stbl_chips[2])
    check("stables 7d+30d sign agreement", (d30 < 0) == (num(stbl_chips[1]) < 0), True, tol=None)
    m_dig = re.search(r"USDT\+USDC combined \$([\d\.,]+B)\s+7d\s+(-?\+?\$[\d\.,]+B)\s+"
                      r"30d\s+(-?\+?\$[\d\.,]+B)", raw)
    if m_dig:
        for i, (label, printed) in enumerate(zip(("total", "7d", "30d"), m_dig.groups())):
            m_chip = re.search(r"[-+]?\$?[\d\.,]+B", stbl_chips[i])
            got = (m_chip.group(0) if m_chip else "").replace("$", "")
            check(f"stables card {label} quotes digest", got, printed.replace("$", ""))
    else:
        fails.append("stables: digest's combined line unparseable - card cannot be verified")

# RSI percentile claim vs the series
def rsi_series(vals, n=14):
    if len(vals) < n + 1:
        return []
    r, g, l = [None] * n, 0.0, 0.0
    for i in range(1, n + 1):
        ch = vals[i] - vals[i - 1]
        g += max(ch, 0); l += max(-ch, 0)
    g /= n; l /= n
    out = [100 - 100 / (1 + (g / l if l else 1e9))]
    for i in range(n + 1, len(vals)):
        ch = vals[i] - vals[i - 1]
        g = (g * (n - 1) + max(ch, 0)) / n
        l = (l * (n - 1) + max(-ch, 0)) / n
        out.append(100 - 100 / (1 + (g / l if l else 1e9)))
    return out

r = rsi_series(close)
if r:
    year = r[-365:]
    pct = round(100 * sum(1 for x in year if x <= r[-1]) / len(year))
    check("RSI 1y percentile vs recomputed", int(d["rsi_pct"]), pct, tol=2)

# ------------------------------------------------------- internal contradictions
print()
print("=" * 78)
print("LAYER 4 — INTERNAL CONTRADICTIONS (same stat stated twice)")
print("=" * 78)
# the F&G block prints its percentile twice, via _ord() (truncates) and .0f (rounds)
fng_lines = re.findall(r"current = (\d+)\w\w percentile of the 30d window", raw)
fng_verdict = re.findall(r"EXTREME FEAR \(pctile (\d+)\)", raw)
if fng_lines and fng_verdict:
    check("F&G percentile: block line vs verdict", fng_lines[0], fng_verdict[0])

# every block's stance tag must exist and be one of the four
tags = re.findall(r"-> \[(\w+)\]", raw)
bad = [t for t in tags if t not in ("bear", "bull", "warn", "flat")]
if bad:
    fails.append(f"unknown stance tag(s): {bad}")
else:
    oks.append(f"all {len(tags)} stance tags valid")

# a bare "->" with no tag would silently render grey
untagged = len(re.findall(r"^\s*-> (?!\[)", raw, re.M))
check("untagged verdict lines", untagged, 0, tol=0)

# ── section tallies: "NET BEARISH - 1 bearish / 2 caution" must match the tags below it
secs = re.split(r"^(\d+)\.\s+([A-Z][A-Z &\-]+?)\s{2,}", raw, flags=re.M)
for i in range(1, len(secs) - 2, 3):
    num, name, body = secs[i], secs[i + 1].strip(), secs[i + 2]
    head = body.split("\n", 1)[0]
    tally = re.search(r"(NET (?:BEARISH|BULLISH)|MIXED|NO SIGNAL)\s*-\s*(.+)", head)
    if not tally:
        warns.append(f"section {num} {name}: no tally in header ({head[:60]!r})")
        continue
    counts = {k: int(v) for v, k in re.findall(r"(\d+)\s+(bearish|bullish|caution)", tally.group(2))}
    actual = {}
    for t in re.findall(r"-> \[(bear|bull|warn|flat)\]", body):
        actual[{"bear": "bearish", "bull": "bullish", "warn": "caution"}.get(t, "flat")] = \
            actual.get({"bear": "bearish", "bull": "bullish", "warn": "caution"}.get(t, "flat"), 0) + 1
    if counts != {k: v for k, v in actual.items() if k != "flat"}:
        fails.append(f"section {num} {name}: header says {counts}, tags say {actual}")
    else:
        oks.append(f"section {num} tally {counts} matches its tags")

# ── LAYER 5 — provenance, data time, and "did the builder fetch behind our back"
print()
print("=" * 78)
print("LAYER 5 — PROVENANCE / DETERMINISM GUARDS")
print("=" * 78)

digest_md5_now = hashlib.md5(raw.encode()).hexdigest()[:12]
meta_md5 = re.search(r'<meta name="digest-md5" content="([0-9a-f]+)">', html)
if meta_md5 is None:
    # A missing meta is worse than a wrong one: nothing on the page says which run built it,
    # so every number below could belong to a different digest. Hard fail, not a warn.
    fails.append("page has no digest-md5 meta - cannot prove which digest run built it")
else:
    check("page built from the cached digest", meta_md5.group(1), digest_md5_now)

# Data time must be the DIGEST's stamp, never the build clock.
page_data_ts = re.search(r'updated ([\d\-]+ [\d:]+ UTC)', html)
digest_ts = re.search(r"BTC daily read\s*\|\s*([\d\-]+ [\d:]+ UTC)", raw)
if page_data_ts is None or digest_ts is None:
    fails.append("data-time unreadable (page=%s digest=%s) - staleness would be invisible"
                 % (bool(page_data_ts), bool(digest_ts)))
else:
    check("header data-time = digest timestamp", page_data_ts.group(1), digest_ts.group(1))

page_built = re.search(r'<meta name="page-built" content="([^"]+)">', html)
if page_built and digest_ts:
    oks.append("page build stamp present: " + page_built.group(1))
else:
    fails.append("page build stamp missing - staleness would be invisible")

# Static guard: the builder must never call run_digest() again. One occurrence is the
# definition; a second means someone restored the implicit fetch.
src = open(f"{SITE}/build_site.py").read()
calls = len(re.findall(r"run_digest\s*\(", src))
if calls <= 1:
    oks.append("builder does not call run_digest() (no hidden fetch)")
else:
    fails.append(f"build_site.py calls run_digest() {calls - 1}x - the builder is fetching "
                 f"again, so the page can come from a different run than the cache")

# A settled figure must not move between the 08:30 and 21:00 builds of the same UTC day.
try:
    snap = json.load(open("/root/.hermes/state/btc_digest_snapshot.json"))
    if snap.get("ts", "")[:10] == datetime_now[:10]:
        for k, label in (("rsi14", "RSI14 settled"), ("streak", "premium streak")):
            if str(snap.get(k)) != str(d.get(k)):
                warns.append(f"{label} moved intraday ({snap.get(k)} -> {d.get(k)}); "
                             f"settled figures should only change when the UTC day rolls")
        if str(snap.get("ls")) != str(d["ls"]):
            warns.append(f"long/short ratio moved intraday ({snap.get('ls')} -> {d['ls']}) "
                         f"- fine if positioning genuinely re-printed, check it is not a "
                         f"different series (all-acct vs top-trader)")
except Exception:
    pass

print()
for o in oks:
    print(f"  PASS  {o}")
for w in warns:
    print(f"  WARN  {w}")
for f in fails:
    print(f"  FAIL  {f}")
print()
print(f"{len(oks)} passed, {len(warns)} warnings, {len(fails)} failures")
sys.exit(1 if fails else 0)
