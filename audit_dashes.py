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
# DASH ENTITIES: &mdash; is ASCII in the file but a long dash on screen, so the unicode scan
# cannot see it. This is the hole that let em dashes ship on a page reporting "0 non-ASCII".
ENT = ("&mdash;", "&ndash;", "&horbar;", "&#8212;", "&#8211;", "&#x2014;", "&#x2013;")
ent_total = 0
for f in targets:
    try:
        t = open(f, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for e in ENT:
        n = t.count(e)
        if n:
            ent_total += n
            print(f"  {f}: {n}x {e} (renders as a long dash)")
if ent_total:
    print(f"TOTAL dash entities: {ent_total}")
grand += ent_total

print(f"\nTOTAL long/odd dashes: {grand}")
sys.exit(1 if grand else 0)
