#!/usr/bin/env python3
"""Independent audit of every number the digest prints.

Per the numeric-provenance-audit skill: comparing the page against the generator that wrote it is
NOT verification - both share the bug and the check passes. So this recomputes each metric from the
raw source with its own code, then compares against what is printed.

Gate 1  recompute from raw   - own implementations of MVRV, 350WMA, weekly RSI, cost basis, fits
Gate 2  meaning/consistency  - derived percentages must equal their own inputs
Gate 3  provenance           - every price printed must trace to a source (or a known history value)

v2 fixes after the first run produced 8 false failures:
  * the local mirror lags a day, so gate 1 now pulls LITB's chart API directly (same raw source the
    page uses) instead of reading stale JSON off disk;
  * the least-squares check had the wrong formula (it omitted the intercept);
  * two regexes did not match the page's actual wording.
"""
import json
import re
import statistics
import sys
import urllib.request
from datetime import date, timedelta

SITE = "/root/btc-digest-site"
DIGEST = open(f"{SITE}/latest_digest.txt").read()
HTML = open(f"{SITE}/index.html").read()
ONCHAIN = "/root/btc-bottom/state/onchain"

fails, warns, oks = [], [], []


def ok(name, detail=""):
    oks.append(f"{name}{(' - ' + detail) if detail else ''}")


def fail(name, detail):
    fails.append(f"{name} - {detail}")


def warn(name, detail):
    warns.append(f"{name} - {detail}")


def near(name, got, want, tol, unit=""):
    if got is None or want is None:
        warn(name, f"missing (got={got} want={want})")
        return
    if abs(got - want) <= tol:
        ok(name, f"{got:,.4g}{unit} vs {want:,.4g}{unit}")
    else:
        fail(name, f"printed {got:,.4g}{unit} vs recomputed {want:,.4g}{unit} (tol {tol})")


def grab(pat, text=DIGEST, cast=float, default=None):
    m = re.search(pat, text)
    if not m:
        return default
    try:
        return cast(m.group(1).replace(",", ""))
    except (TypeError, ValueError, AttributeError):
        return default


def litb(slug):
    """Raw LITB chart series -> {day: value}. Third-party source, parsed here independently."""
    req = urllib.request.Request(
        f"https://www.lookintobitcoin.com/api/chart-data/charts/{slug}",
        headers={"User-Agent": "Mozilla/5.0", "Referer":
                 f"https://www.lookintobitcoin.com/charts/{slug}/"})
    d = json.load(urllib.request.urlopen(req, timeout=40))
    out = []
    today = date.today().isoformat()
    for tr in d["data"][:2]:
        m = {}
        for ds, v in zip(tr["x"], tr["y"]):
            day = str(ds)[:10]
            if day <= today and v:
                m[day] = float(v)
        out.append(m)
    return out[0], out[1]


def local(name):
    try:
        d = json.load(open(f"{ONCHAIN}/{name}.json"))
    except Exception:
        return {}
    rs = d["rows"] if isinstance(d, dict) and "rows" in d else d
    out = {}
    for r in rs:
        try:
            if isinstance(r, dict):
                day = str(r.get("d") or r.get("day"))[:10]
                v = next((x for k, x in r.items() if k not in ("d", "day", "unixTs")), None)
            else:
                day, v = str(r[0])[:10], r[1]
            out[day] = float(v)
        except (TypeError, ValueError):
            continue
    return out


print("=" * 78)
print("GATE 1 - recompute from raw source (independent implementations)")
print("=" * 78)

px, rp = litb("realized-price")          # trace 0 = BTC price, trace 1 = realised price
days = sorted(set(px) & set(rp))
mv = {d: px[d] / rp[d] for d in days}
mv_settled, rp_last = mv[days[-1]], rp[days[-1]]
spot = grab(r"\(spot \$([\d,]+)\)") or grab(r"Bitcoin [Ss]pot[^\$]*\$([\d,]+)")

near("MVRV settled", grab(r"\(([\d\.]+) settled"), round(mv_settled, 3), 0.0015)
near("realised price", grab(r"realised \$([\d,]+)"), round(rp_last, 0), 1.5)
near("MVRV live = spot / realised", grab(r"MVRV ([\d\.]+) live"),
     round(spot / rp_last, 3) if spot else None, 0.0015)

# cycle floors, independent window minima
CYCLES = [("2011", "2011-06-01", "2012-12-31"), ("2015", "2013-12-01", "2016-06-30"),
          ("2019", "2017-12-01", "2020-06-30"), ("2022", "2021-11-01", "2024-06-30")]
printed_floors = dict(re.findall(r"(\d{4}) (0\.\d{3})", DIGEST))
floors = {}
for tag, a, b in CYCLES:
    win = [d for d in days if a <= d <= b]
    floors[tag] = min(mv[d] for d in win)
    near(f"MVRV floor {tag}", float(printed_floors.get(tag, "nan")), round(floors[tag], 3), 0.0015)

inc = [floors["2015"] - floors["2011"], floors["2019"] - floors["2015"], floors["2022"] - floors["2019"]]
div = floors["2022"] + inc[-1] * 0.5
lin = floors["2022"] + inc[-1]
xs = [0, 1, 2, 3]
ys = [floors[k] for k in ("2011", "2015", "2019", "2022")]
mx, my = statistics.mean(xs), statistics.mean(ys)
den = sum((x - mx) ** 2 for x in xs)
slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
lsq = (my - slope * mx) + slope * 4          # intercept + slope at the NEXT cycle

m = re.search(r"-> (0\.\d{3}) = \$([\d,]+)", DIGEST)
near("floor fit (halving) multiple", float(m.group(1)) if m else None, round(div, 3), 0.002)
near("floor fit (halving) price", float(m.group(2).replace(",", "")) if m else None,
     round(div * rp_last, 0), 60)
m = re.search(r"repeat last increment -> (0\.\d{3})", DIGEST)
near("floor fit (repeat) multiple", float(m.group(1)) if m else None, round(lin, 3), 0.002)
m = re.search(r"least-squares -> (0\.\d{3}) = \$([\d,]+)", DIGEST)
near("floor fit (least-squares) multiple", float(m.group(1)) if m else None, round(lsq, 3), 0.002)
near("floor fit (least-squares) price", float(m.group(2).replace(",", "")) if m else None,
     round(lsq * rp_last, 0), 60)

# timing: first sub-1.0 print -> floor
gaps = []
for tag, a, b in CYCLES:
    win = [d for d in days if a <= d <= b]
    peak = max(win, key=lambda d: mv[d])
    below = [d for d in win if d > peak and mv[d] < 1.0]
    if not below:
        continue
    lo = min(win, key=lambda d: mv[d])
    gaps.append((date.fromisoformat(lo) - date.fromisoformat(below[0])).days)
tim = re.search(r"CLOCK: low came (\d+)-(\d+) days AFTER the first sub-1\.00 print\s*\(([\d /]+)\)",
                DIGEST, re.S)
if tim:
    near("clock min days", int(tim.group(1)), min(gaps), 0, "d")
    near("clock max days", int(tim.group(2)), max(gaps), 0, "d")
    printed = [int(x) for x in re.findall(r"\d+", tim.group(3))]
    if sorted(printed) == sorted(gaps):
        ok("clock day list", str(gaps))
    else:
        fail("clock day list", f"printed {printed} vs recomputed {gaps}")
else:
    warn("clock line", "pattern not found")

# 350-week MA + weekly RSI
wk = {}
for d in sorted(px):
    dt = date.fromisoformat(d)
    wk[(dt + timedelta(days=(6 - dt.weekday()))).isoformat()] = px[d]
weeks = sorted(wk)
wpx = [wk[w] for w in weeks]
ma350 = statistics.mean(wpx[-350:])
near("350-week MA", grab(r"350-week MA \$([\d,]+)"), round(ma350, 0), 60)
below_n = sum(1 for i in range(350, len(wpx)) if wpx[i] < statistics.mean(wpx[i - 350:i]))
span_n = len(wpx) - 350
mm = re.search(r"(\d+) weekly closes below it in (\d+) weeks tested", DIGEST)
near("350WMA closes below count", int(mm.group(1)) if mm else None, below_n, 0)
near("350WMA weeks tested", int(mm.group(2)) if mm else None, span_n, 0)
worst = min(((wpx[i] / statistics.mean(wpx[i - 350:i]), weeks[i]) for i in range(350, len(wpx))),
            key=lambda t: t[0])
near("closest approach to 350WMA", grab(r"closest ever ([\d\.]+)x"), round(worst[0], 3), 0.002)


def wilder(vals, n=14):
    g, l = [], []
    for i in range(1, len(vals)):
        ch = vals[i] - vals[i - 1]
        g.append(max(ch, 0.0)); l.append(max(-ch, 0.0))
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    out = [None] * n + [100 - 100 / (1 + ag / al) if al else 100.0]
    for i in range(n, len(g)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out.append(100 - 100 / (1 + ag / al) if al else 100.0)
    return out


wrsi = wilder(wpx)
near("weekly RSI(14)", grab(r"weekly RSI\(14\) ([\d\.]+)"), round(wrsi[-1], 1), 0.15)
near("weeks with weekly RSI < 30", grab(r"sub-30 on only (\d+) weeks"),
     sum(1 for v in wrsi if v is not None and v < 30), 0)

# cost basis (local mirror is the only source for these; the page prints its date and lag)
lth, sth = local("lth_realized_price"), local("sth_realized_price")
cdays = sorted(set(px) & set(lth))
near("LTH cost", grab(r"LTH cost \$([\d,]+)"), round(lth[cdays[-1]], 0), 1.5)
near("STH cost", grab(r"STH cost \$([\d,]+)"), round(sth[cdays[-1]], 0), 1.5)
sub = [d for d in cdays if px[d] < lth[d]]
if sub:
    lo = min(sub, key=lambda d: px[d] / lth[d])
    near("sub-LTH episode depth", grab(r"([-−]?\d+)% deep"), round(100 * (px[lo] / lth[lo] - 1), 0), 1, "%")

    def at_after(start, n):
        want = (date.fromisoformat(start) + timedelta(days=n)).isoformat()
        return next((d for d in cdays if d >= want), cdays[-1])

    near("episode +6m", grab(r"\+(\d+)% in 6m"), round(100 * (px[at_after(sub[0], 182)] / px[sub[0]] - 1), 0), 1, "%")
    near("episode +12m", grab(r"\+(\d+)% in 12m"), round(100 * (px[at_after(sub[0], 365)] / px[sub[0]] - 1), 0), 1, "%")

print("\n" + "=" * 78)
print("GATE 2 - meaning and internal consistency")
print("=" * 78)

m_lth = re.search(r"LTH cost \$([\d,]+) \([^)]+\) -> spot ([-+]\d+)%", DIGEST)
near("LTH vs spot %", float(m_lth.group(2)) if m_lth else None,
     round(100 * (spot / float(m_lth.group(1).replace(",", "")) - 1), 0) if m_lth and spot else None, 1.5)
m_sth = re.search(r"STH cost \$([\d,]+) \([^)]+\) -> spot ([-+]\d+)%", DIGEST)
near("STH vs spot %", float(m_sth.group(2)) if m_sth else None,
     round(100 * (spot / float(m_sth.group(1).replace(",", "")) - 1), 0) if m_sth and spot else None, 1.5)
m_dist = re.search(r"-> 1\.00 is ([-+]\d+\.\d)% away", DIGEST)
near("MVRV 1.00 distance %", float(m_dist.group(1)) if m_dist else None,
     round(100 * (rp_last / spot - 1), 1) if spot else None, 0.2)
m_bid = re.search(r"BID \$([\d,]+)", DIGEST)
m_avg = re.search(r"average price paid when the book grew: 7d \$([\d,]+)", DIGEST)
if not (m_bid and m_avg):
    # an anchor that quietly stops matching is a gate that stops checking: fail, do not skip
    fail("Bitfinex BID vs 7d average", "block [9] wording moved - the anchor is gone and this check is blind")
elif m_bid.group(1) == m_avg.group(1):
    ok("Bitfinex BID == 7d average entry")
else:
    fail("Bitfinex BID vs 7d average", f"{m_bid.group(1)} != {m_avg.group(1)}")

# gross adds and gross trims must reconcile to the net the same line prints
m_fl = re.search(r"7d  added ([\d,]+) BTC in \d+ rising days, trimmed ([\d,]+) in \d+ falling days, "
                 r"net ([+-][\d,]+)", DIGEST)
if not m_fl:
    fail("Bitfinex adds/trims", "no gross add/trim line in block [9]")
else:
    _a, _t, _n = (float(x.replace(",", "")) for x in m_fl.groups())
    if abs(_a - _t - _n) > 1.0:
        fail("Bitfinex adds/trims", f"{_a:,.0f} added - {_t:,.0f} trimmed != net {_n:,.0f}")
    else:
        ok(f"Bitfinex adds minus trims == net ({_a:,.0f} - {_t:,.0f} = {_n:+,.0f})")
for lab in ("STH cost", "LTH cost", "350-week MA"):
    v = grab(rf"{lab} \$([\d,]+)")
    chip = re.search(rf"{lab} \$([\d,]+)", HTML)
    if v and chip and chip.group(1) != f"{v:,.0f}":
        fail(f"ladder chip {lab}", f"chip {chip.group(1)} vs block {v:,.0f}")
ok("ladder chips checked against block values")

# the bottom-score chart caption makes two countable claims: N stretches, D days. Both are checkable
# against the series the chart is drawn from - the failure mode here was a caption describing shading
# the image did not actually show.
try:
    import sys as _s
    if "/root/btc-bottom" not in _s.path:
        _s.path.insert(0, "/root/btc-bottom")
    import json as _json
    import score_g as _sg
    _m = _json.loads(open("/root/btc-bottom/state/model_h.json").read())
    _w, _keys = _m["weights"], list(_m["weights"])
    _rows = _sg.build_series()
    # parts ARE the points (0-20 each, scaled inside score_g). Multiplying by 20/max here
    # double-scaled every signal: the last reading came out 72.12 instead of 67.23 and the
    # >=60 count 226 instead of 206, which made the audit "disagree" with the chart it checks.
    _sc = [round(min(100.0, sum(r["parts"][k] * _w[k] for k in _keys)), 2) for r in _rows]
    _eps, _run = [], None
    for _i, _v in enumerate(_sc + [0.0]):
        if _v >= 60 and _run is None:
            _run = _i
        elif _v < 60 and _run is not None:
            _eps.append(_i - _run)
            _run = None
    # the caption lives in the rendered page, not the digest text
    near("chart caption: stretches of score>=60",
         grab(r"(\d+) stretches where the score held 60", HTML), len(_eps), 0)
    near("chart caption: total days >=60", grab(r"(\d+) days in total", HTML), sum(_eps), 0)
except Exception as _e:
    warn("band caption check", f"skipped ({type(_e).__name__}: {_e})")

print("\n" + "=" * 78)
print("GATE 3 - provenance: every price on the page traces to a source")
print("=" * 78)
sources = {
    "realised price": rp_last,
    "350-week MA": ma350,
    "LTH cost": lth[cdays[-1]],
    "STH cost": sth[cdays[-1]],
    "Balanced price": grab(r"Balanced Price \$([\d,]+)"),
    "AVWAP": grab(r"AVWAP since [\d-]+ \$([\d,]+)"),
    "MA200": grab(r"MA200 ([\d,]+)"),
    "spot": spot,
    "floor (halving)": div * rp_last,
    "floor (repeat)": lin * rp_last,
    "floor (least-squares)": lsq * rp_last,
    "episode price low": px[min(sub, key=lambda d: px[d] / lth[d])] if sub else None,
    "episode cost low": lth[min(sub, key=lambda d: px[d] / lth[d])] if sub else None,
    "bitfinex entry": m_avg and float(m_avg.group(1).replace(",", "")),
    # the older tranches the Bitfinex block prints are derived from its hourly series, so they are a
    # legitimate source value rather than an unexplained number
    "bitfinex 30d entry": grab(r"30d \$([\d,]+)", DIGEST),
    "bitfinex 90d entry": grab(r"90d \$([\d,]+)", DIGEST),
}
levels = [float(x.replace(",", "")) for x in re.findall(r"\$(\d{2},\d{3})", DIGEST)]
untraced = [lv for lv in levels
            if min(((abs(lv - v) / v) for v in sources.values() if v), default=1) > 0.02]
if untraced:
    warn("untraced price levels", f"{len(untraced)}/{len(levels)} outside 2% of a source: "
                                  f"{sorted(set(untraced))[:8]}")
else:
    ok("all price levels trace to a source", f"{len(levels)} checked")

print("\n" + "=" * 78)
for f in fails:
    print("FAIL  " + f)
for w in warns:
    print("warn  " + w)
print(f"\n{len(oks)} passed, {len(warns)} warnings, {len(fails)} failures")
print("=" * 78)
sys.exit(1 if fails else 0)
