# BTC Daily Digest

A shareable, self-contained page showing the daily Bitcoin flow / cost-basis / momentum digest
plus the indicator reference and the backtest evidence behind each rule.

- `index.html` — the page (generated, do not hand-edit)
- `chart.png` — the daily chart, embedded in the page
- `build_site.py` — regenerates `index.html` from the live digest

## Rebuild

    python3 build_site.py

Data comes from keyless public APIs (Coinbase, Binance, DeFiLlama, cryptoetf.today,
Look Into Bitcoin, BGeometrics). No credentials, no subscription feeds.

Not financial advice.
