"""Cross-place consistency for the figures that predate the new-sources gate.

The hero tiles and the digest blocks render the same metrics through different code paths. This pulls
every tile, pulls the matching figure out of the block, and compares. It also compares the on-chain
figures against the cached provider files, so "same number" and "right number" are both tested.

Read-only: prints disagreements, changes nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path("/root/btc-digest-site")
ON = Path("/root/btc-bottom/state/onchain")

html = (SITE / "index.html").read_text()
text = re.sub(r"<[^>]+>", " ", html)
text = re.sub(r"\s+", " ", text)

tiles = dict(re.findall(r'<span class="k">([^<]+)</span><span class="v[^"]*">([^<]+)</span>', html))
print("hero tiles found:", ", ".join(tiles))

ok: list[str] = []
bad: list[str] = []


def num(s: str) -> float:
    s = re.sub(r"[^\d.\-+]", "", s)
    return float(s) if s not in ("", "-", "+") else float("nan")


def cmp(label: str, a: str | float | None, b: str | float | None, tol: float) -> None:
    if a is None or b is None:
        bad.append(f"{label}: one side missing ({a} vs {b})")
        return
    x, y = (num(a) if isinstance(a, str) else a), (num(b) if isinstance(b, str) else b)
    if abs(x - y) > tol:
        bad.append(f"{label}: tile/block disagree -> {a} vs {b}")
    else:
        ok.append(f"{label}: tile and block agree ({a} vs {b})")


# ---- tile vs block, one row per metric printed twice
def block(pattern: str):
    m = re.search(pattern, text)
    return m.group(1) if m else None


cmp("ETF 30d flow", tiles.get("ETF flows"), block(r"10d [-+]?\$[\d,]+\.\dM 30d ([-+]?\$[\d,]+\.\dM)"), 0.1)
cmp("US premium live", tiles.get("US premium"), block(r"live (-?\d\.\d{3})% last close"), 0.001)
cmp("Stablecoin total", tiles.get("Stablecoins"), block(r"USDT\+USDC combined \$([\d.]+)B"), 0.05)
cmp("Fear & Greed", tiles.get("Fear &amp; Greed"), block(r"now (\d{1,3}) \("), 0)
cmp("Open interest", tiles.get("Perp open interest"), block(r"OI \$([\d.]+)bn"), 0.01)
cmp("Longs per short", tiles.get("Longs per short"), block(r"all-acct L/S ([\d.]+)"), 0.005)
cmp("RSI(14)", tiles.get("RSI(14)"), block(r"(\d\d\.\d)\s+bottom"), 0.05)

cmp("Funding 30d annualised", tiles.get("Funding rate"),
    block(r"30d avg [-+]?[\d.]+% /8h (?:->|-&gt;) [-+]?([\d.]+)% annualised"), 0.05)
cmp("Spot price header vs blocks",
    (re.search(r'class="spotpx">\$([\d,]+)', html).group(1)
     if re.search(r'class="spotpx">\$([\d,]+)', html) else None),
    block(r"\(spot \$([\d,]+)\)"), 1.0)

# ---- on-chain figures vs the cached provider files
def series(name: str):
    d = json.loads((ON / f"{name}.json").read_text())
    return {r[0][:10]: float(r[1]) for r in d.get("rows") or []}


fng = series("fear_greed")
mv = series("litb_mvrv")
rp = series("litb_realized_price")
px = series("litb_price")
fng_v, mv_v = fng[max(fng)], mv[max(mv)]
rp_v, px_v = rp[max(rp)], px[max(px)]

cmp("Fear & Greed vs provider", tiles.get("Fear &amp; Greed"), fng_v, 0)
settled = block(r"\((1\.\d{3}) settled (\d{4}-\d{2}-\d{2})\)")
cmp("MVRV settled vs price/realised", settled, round(px_v / rp_v, 3), 0.004)
cmp("Realised price vs provider", block(r"realised \$([\d,]+)"), rp_v, 1.0)

print(f"\nprovider: F&G {fng_v:.0f}, MVRV file {mv_v:.4f}, realised ${rp_v:,.0f}, "
      f"price ${px_v:,.0f} -> ratio {px_v / rp_v:.4f}")

# ---- the date labels the numbers are attributed to
labels = re.findall(r"\((1\.\d{3}) settled (\d{4}-\d{2}-\d{2})\)", text)
print("MVRV label on page:", labels)
print(f"provider MVRV file's latest date: {max(mv)} = {mv_v:.4f}")
print(f"provider price/realised latest date: {max(px)} = {px_v:.4f}")

for m in ok:
    print("PASS  " + m)
if bad:
    print()
    for m in bad:
        print("FAIL  " + m)
else:
    print("\nno disagreements among the repeated figures")
