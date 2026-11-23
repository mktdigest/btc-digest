import pathlib, re, sys, collections

DASHES = {
    "\u2014": "em dash",
    "\u2013": "en dash",
    "\u2015": "horizontal bar",
    "\u2012": "figure dash",
    "\u2212": "minus sign",
    "\u2010": "hyphen (unicode)",
    "\u2011": "non-breaking hyphen",
    "\ufe58": "small em dash",
    "\u30fc": "katakana prolonged",
}

targets = sys.argv[1:] or ["/root/btc-digest-site/index.html"]
grand = 0
for t in targets:
    p = pathlib.Path(t)
    if not p.exists():
        print(f"MISSING {t}")
        continue
    txt = p.read_text(errors="replace")
    print(f"\n=== {t} ({len(txt):,} chars) ===")
    for ch, name in DASHES.items():
        n = txt.count(ch)
        if not n:
            continue
        grand += n
        print(f"  {name:20s} U+{ord(ch):04X}  x{n}")
        # show up to 3 contexts
        for m in list(re.finditer(re.escape(ch), txt))[:3]:
            a, b = max(0, m.start() - 42), min(len(txt), m.end() + 42)
            snip = txt[a:b].replace("\n", " ")
            print(f"      ...{snip}...")
print(f"\nTOTAL long/odd dashes: {grand}")
sys.exit(1 if grand else 0)
