"""Cross-place consistency audit.

Rule: one metric, one number, wherever it appears. This checks the measures that are now consumed in
more than one place - exchange netflow (page panel + immutable ledger), exchange supply, independent
MVRV, CBBI composite, realised net P/L - by recomputing each from the cached provider files and
comparing against (a) what the page prints and (b) what the ledger recorded for the latest day.

Exit code 1 on any mismatch, so a deploy can refuse to publish.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BOTTOM = Path("/root/btc-bottom")
SITE = Path("/root/btc-digest-site")
ON = BOTTOM / "state" / "onchain"

problems: list[str] = []
oks: list[str] = []


def series(path: str, key: str | None) -> dict[str, float]:
    d = json.loads((ON / path).read_text())
    rows = d.get("rows") if key is None else d["series"][key]
    return {r[0][:10]: float(r[1]) for r in rows}


def recompute() -> dict[str, float]:
    out: dict[str, float] = {}
    cm_in, cm_out = series("cm_metrics.json", "FlowInExUSD"), series("cm_metrics.json", "FlowOutExUSD")
    days = sorted(set(cm_in) & set(cm_out))[-30:]
    out["ex_netflow_30d_bn"] = sum(cm_in[d] - cm_out[d] for d in days) / 1e9

    supply = series("cm_metrics.json", "SplyExNtv")
    out["ex_supply_btc"] = supply[max(supply)]

    cm_mvrv = series("cm_metrics.json", "CapMVRVCur")
    out["cm_mvrv"] = cm_mvrv[max(cm_mvrv)]

    conf = series("cbbi.json", "Confidence")
    out["cbbi_composite"] = conf[max(conf)]

    prof = series("realized_profit.json", None)
    loss = series("realized_loss.json", None)
    pd_days = sorted(set(prof) & set(loss))[-30:]
    out["net_realised_pl_30d_bn"] = sum(prof[d] + loss[d] for d in pd_days) / 1e9
    return out


def main() -> int:
    want = recompute()

    # ---- 1. ledger: latest record for each field must equal the recomputed value
    recs = [json.loads(x) for x in (BOTTOM / "state" / "daily_ledger.jsonl").read_text().splitlines()
            if x.strip()]
    latest = recs[-1]
    ns = latest.get("new_sources") or {}
    tol = {"ex_netflow_30d_bn": 0.02, "ex_supply_btc": 2.0, "cm_mvrv": 0.0002,
           "cbbi_composite": 0.0002, "net_realised_pl_30d_bn": 0.02}
    for k, v in want.items():
        if k not in ns:
            problems.append(f"ledger {latest['day']}: missing field {k}")
            continue
        if abs(ns[k] - v) > tol[k]:
            problems.append(f"ledger {k} {ns[k]} vs recomputed {v:.4f} (tol {tol[k]})")
        else:
            oks.append(f"ledger {k} matches recomputation")

    # ---- 2. page: the printed figures must equal the same values
    html = (SITE / "index.html").read_text()
    checks = [
        ("exchange netflow", rf"Exchange netflow, 30d \(USD\)</b></td><td[^>]*>\s*([+-][\d.]+) bn",
         want["ex_netflow_30d_bn"], 0.15),
        ("exchange supply", r"BTC held on exchanges</b></td><td[^>]*>\s*([\d.]+)M BTC",
         want["ex_supply_btc"] / 1e6, 0.02),
        ("independent MVRV", r"Independent MVRV</b></td><td[^>]*>\s*([\d.]+)", want["cm_mvrv"], 0.002),
        ("CBBI composite", r"Cycle gauge \(CBBI\)</b></td><td[^>]*>\s*([\d.]+)\s*&middot;",
         want["cbbi_composite"], 0.002),
        ("realised net P/L", rf"Realised net profit/loss, 30d</b></td><td[^>]*>\s*([+-][\d.]+) bn",
         want["net_realised_pl_30d_bn"], 0.15),
    ]
    for label, pat, expect, tol_ in checks:
        m = re.search(pat, html)
        if not m:
            problems.append(f"page: could not find the {label} figure")
            continue
        got = float(m.group(1))
        if abs(got - expect) > tol_:
            problems.append(f"page {label} prints {got} but recomputation says {expect:.4f}")
        else:
            oks.append(f"page {label} matches recomputation")

    # ---- 3. the note's cited correlations must match the row values on the same page
    note = re.search(r"Exchange\s+netflow scored\s*([+-][\d.]+)", html)
    row_net = re.search(r"([+-][\d.]+) over [\d,]+ days - too weak", html)
    if note and row_net:
        if abs(float(note.group(1)) - float(row_net.group(1))) > 0.005:
            problems.append(f"note says netflow r {note.group(1)} but the row says {row_net.group(1)}")
        else:
            oks.append("note and row quote the same netflow correlation")
    else:
        problems.append("could not read both netflow correlations (note and row)")

    ncf_note = re.search(r"already feeding S4 is stronger at\s*([+-][\d.]+)", html)
    ncf_row = re.search(r"(?:net capital flow)[^<]*([+-][\d.]+) over", html)
    if ncf_note:
        oks.append(f"note cites S4 input at {ncf_note.group(1)}")

    print()
    for m in oks:
        print("PASS  " + m)
    if problems:
        print()
        for m in problems:
            print("FAIL  " + m)
        print(f"\n{len(oks)} passed, {len(problems)} failures")
        return 1
    print(f"\n{len(oks)} passed, 0 failures - one metric, one number, every place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
