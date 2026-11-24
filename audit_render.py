#!/usr/bin/env python3
"""Render audit: the class of bugs the number audit could not see.

Why this file exists. The numeric audit compares numbers against sources, so it passed while:
  * the score bands were painted the full height of the 0-100 axis (a geometry bug - correct data,
    meaningless picture);
  * the S2 card once printed "/12.7" because a fitted weight capped it (removed: equal weight now)
    right, the scale it was read against was wrong);
  * PIL raised on every build and build_site swallowed it, shipping a page 47KB smaller with the
    whole Bottom Score tab replaced by "unavailable" (a build bug - both audits were green).

So: four gates that look at the rendered artifact instead of the data.

  1 build integrity   the bottom tab rendered, page size did not collapse, every image resolves
  2 no stray output   module diagnostics never leak into the page as text
  3 label ceiling     a card's printed maximum equals what the signal can reach after its weight
  4 band geometry     every shaded band sits inside the 60-100 zone, one per episode

`--selftest` re-injects the two bugs above and fails unless the gates catch them. An audit that
cannot fail on known-bad code is decoration.
"""
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

SITE = Path("/root/btc-digest-site")
BOTTOM = Path("/root/btc-bottom")
HTML_PATH = SITE / "index.html"
STATE = SITE / "state" / "last_build.json"

errs, oks, warns = [], [], []


def ok(m):
    oks.append(m)


def bad(m):
    errs.append(m)


# ---------------------------------------------------------------- gate 3 (pure, testable)
def check_labels(pairs, weights):
    """pairs: [(key, printed_ceiling)] - every signal is graded 0-20, equal weight, so the ceiling
    a card prints must equal 20."""
    out = []
    for key, printed in pairs:
        want = round(20.0 * weights.get(key, 1.0), 1)
        if abs(printed - want) > 0.05:
            out.append(f"{key}: card claims ceiling /{printed} but its weighted ceiling is /{want}")
    return out


# ---------------------------------------------------------------- gate 4 (pure, testable)
def check_bands(bands, zone_bottom, plot_bottom, n_episodes):
    out = []
    if len(bands) != n_episodes:
        out.append(f"{len(bands)} bands drawn but the series has {n_episodes} stretches of score>=60")
    for b in bands:
        if b["y_bottom"] > zone_bottom + 1:
            out.append(f"band {b.get('day0')}..{b.get('day1')} reaches y={b['y_bottom']}, below the "
                       f"60 line at y={zone_bottom} - a full-height band marks nothing")
        if b["y_top"] > zone_bottom:
            out.append(f"band {b.get('day0')}..{b.get('day1')} starts below the 60 line")
    if zone_bottom >= plot_bottom:
        out.append("the 60 line sits at the bottom of the plot - the zone is inverted")
    return out


# ---------------------------------------------------------------- selftest
def selftest():
    weights = {"S1": 1.0, "S2": 1.0, "S3": 1.0, "S4": 1.0, "S5": 1.0}
    caught = []

    bug1 = check_labels([("S2", 12.7)], weights)                    # the shipped bug, now impossible
    caught.append(("label /12.7 on an equal-weight signal", bool(bug1)))

    good = check_labels([("S2", 20.0)], weights)
    caught.append(("label /12.7 accepted (no false positive)", not good))

    # the shipped band bug: rectangles painted plot-top to plot-bottom
    bug2 = check_bands([{"x0": 0, "x1": 10, "y_top": 40, "y_bottom": 400, "day0": "2022-11-21",
                         "day1": "2022-12-18"}], zone_bottom=184, plot_bottom=400, n_episodes=1)
    caught.append(("band painted full height", bool(bug2)))

    good2 = check_bands([{"x0": 0, "x1": 10, "y_top": 40, "y_bottom": 184, "day0": "a",
                          "day1": "b"}], zone_bottom=184, plot_bottom=400, n_episodes=1)
    caught.append(("clipped band accepted (no false positive)", not good2))

    bug3 = check_bands([{"x0": 0, "x1": 10, "y_top": 40, "y_bottom": 184, "day0": "a",
                         "day1": "b"}], zone_bottom=184, plot_bottom=400, n_episodes=17)
    caught.append(("band count mismatch", bool(bug3)))

    print("SELFTEST - each gate must catch its known bug")
    allgood = True
    for name, passed in caught:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        allgood &= passed
    print("\n" + ("selftest OK - the gates fire on known-bad input"
                  if allgood else "selftest FAILED - a gate does not catch its own bug"))
    return 0 if allgood else 1


def main():
    html = HTML_PATH.read_text()

    # ---- gate 1: build integrity
    if "Bottom score unavailable" in html:
        m = re.search(r"Bottom score unavailable this build \(([^)]+)\)", html)
        bad(f"bottom tab fell back to 'unavailable' - {m.group(1) if m else 'unknown error'}")
    else:
        ok("bottom score tab rendered")

    size = len(html)
    if STATE.exists():
        prev = json.loads(STATE.read_text()).get("size", 0)
        if prev and size < prev * 0.88:
            bad(f"page shrank {prev - size:,} bytes ({size / prev:.0%} of last build) - a section "
                f"probably failed and was silently replaced")
        else:
            ok(f"page size {size:,} vs {prev:,} last build")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"size": size, "md5": hashlib.md5(html.encode()).hexdigest()}))

    imgs = set(re.findall(r'<img src="([^"?]+)', html))
    missing = [i for i in imgs if not (SITE / i).exists()]
    if missing:
        bad(f"referenced images missing from disk: {missing}")
    else:
        ok(f"all {len(imgs)} referenced images exist")

    # ---- gate 2: no stray module output in the page
    strays = [p for p in ("saved state/", "sample 2025-", "sample 2026-", "longs now ", "hours)")
              if p in html and "bitfinex" not in html.split(p)[0][-200:].lower()]
    if strays:
        bad(f"module diagnostics leaked into the page: {strays}")
    else:
        ok("no stray stdout in the page")

    # ---- gate 3: card ceilings vs fitted weights
    weights = {k: 1.0 for k in ("S1", "S2", "S3", "S4", "S5")}
    cards = re.findall(r'class="btitle">(S\d) &middot;.*?bbignum"[^>]*>([\d.]+)'
                       r'<span class="bof">/([\d.]+)</span>', html, re.S)
    if not cards:
        bad("could not parse any card ceilings")
    for key, val, ceil in cards:
        e = check_labels([(key, float(ceil))], weights)
        errs.extend(e)
        if not e and float(val) > float(ceil) + 0.05:
            bad(f"{key}: value {val} exceeds its printed ceiling {ceil}")
    if not errs:
        ok(f"{len(cards)} card ceilings match the equal-weight 20-point scale "
           f"(S2 = {round(20 * weights['S2'], 1)})")

    # ---- gate 4: band geometry, drawn by the real chart code
    sys.path.insert(0, str(BOTTOM))
    import bottom_chart
    import render_section as rs

    ser = rs.model_series()
    sc = [r["score"] for r in ser]
    eps, run = 0, False
    for v in sc:
        if v >= 60 and not run:
            run = True
        elif v < 60 and run:
            eps += 1
            run = False
    if run:
        eps += 1
    # cycle-bottom markers come from our own series now, so this audit never needs an outside file
    import sys as _sys
    _sys.path.insert(0, str(BOTTOM))
    import own_stats
    with tempfile.TemporaryDirectory() as td:
        info = bottom_chart.draw(Path(td) / "probe.png", ser,
                                 [(b["date"], b["price"]) for b in own_stats.cycle_bottoms(ser)])
    if not isinstance(info, dict) or "bands" not in info:
        bad("bottom_chart.draw did not return band geometry - cannot verify the shading")
    else:
        errs.extend(check_bands(info["bands"], info["zone_bottom"], info["plot_bottom"], eps))
        if not errs:
            ok(f"{len(info['bands'])} bands, all inside the 60-100 zone ({eps} episodes)")

    # ---- the sources table must survive a phone ---------------------------------
    # Four columns of prose: on a narrow viewport it has to stack into labelled rows. That only
    # works if every cell carries its own label and no column keeps a pixel width - pixel widths
    # on a fixed-layout table squeezed the prose column to a sliver and towered every row.
    _m = re.search(r'<table class="srcs">.*?</table>', html, re.S)
    if not _m:
        bad("sources table: table.srcs missing - the responsive rules apply to nothing")
    else:
        # every table.srcs must stack, not just the first one found
        _all = re.findall(r"<table class=\"srcs\".*?</table>", html, re.S) or [_m.group(0)]
        _tbl = "".join(_all)
        _nolabel = [t for t in re.findall(r"<td([^>]*)>", _tbl) if "data-label" not in t]
        _pxw = re.findall(r'width:\s*\d+px', _tbl)
        if _nolabel:
            bad(f"sources table: {len(_nolabel)} cells have no data-label, so they cannot stack")
        elif _pxw:
            bad(f"sources table: {len(_pxw)} pixel column widths - use percentages for 390px")
        else:
            ok("sources table stacks on phones (all cells labelled, no pixel widths)")


    # ---- the score gauge must agree with the number above it -------------------------------
    # A marker that sits somewhere other than score/100, or a callout naming a different band
    # than the chip beside the big number, is a rendered lie no numeric audit would catch.
    _num = re.search(r'class="bignum">(\d+)<', html)
    _mk = re.search(r'class="bgmark" style="left:([\d.]+)%"', html)
    _chip = re.search(r'class="bzone2">([A-Z ]+)<', html)
    _call = re.search(r'class="bgnote"[^>]*><b>([A-Z ]+) &middot; ([\d-]+)</b>', html)
    if not (_num and _mk and _chip and _call):
        errs.append("score gauge: bar, marker, zone chip or callout missing")
    else:
        _score, _pos, _chipname, (_callname, _span) = int(_num.group(1)), float(_mk.group(1)), _chip.group(1), (_call.group(1), _call.group(2))
        if abs(_pos - _score) > 0.6:
            errs.append(f"score gauge: marker sits at {_pos}% but the number is {_score}")
        elif _chipname.strip() != _callname.strip():
            errs.append(f"score gauge: chip says {_chipname}, callout says {_callname}")
        elif not (_span.split("-")[0].isdigit() and int(_span.split("-")[0]) <= _score <= int(_span.split("-")[-1])):
            errs.append(f"score gauge: {_score} is outside the band it claims ({_span})")
        else:
            ok(f"score gauge: marker at {_pos}% matches the {_score} above it, band {_span} contains it")

    # ---- report
    print()
    for m in oks:
        print("PASS  " + m)
    for m in warns:
        print("warn  " + m)
    for m in errs:
        print("FAIL  " + m)
    print(f"\n{len(oks)} passed, {len(warns)} warnings, {len(errs)} failures")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
