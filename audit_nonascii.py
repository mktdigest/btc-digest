import pathlib, sys, collections, unicodedata

paths = sys.argv[1:] or ["/root/btc-digest-site/index.html"]
for t in paths:
    p = pathlib.Path(t)
    if not p.exists():
        print(f"MISSING {t}")
        continue
    txt = p.read_text(errors="replace")
    c = collections.Counter(ch for ch in txt if ord(ch) > 127)
    print(f"\n=== {t} ({len(txt):,} chars, {sum(c.values())} non-ASCII) ===")
    for ch, n in c.most_common():
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "?"
        print(f"  U+{ord(ch):04X} {ch!r} x{n:<5} {name}")
