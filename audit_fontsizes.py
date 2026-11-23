import re, pathlib, collections

files = ["/root/btc-digest-site/build_site.py", "/root/btc-bottom/render_section.py"]
buckets = collections.defaultdict(list)

for f in files:
    txt = pathlib.Path(f).read_text()
    # CSS sits inside big python strings; just regex selector{...font-size:Npx...}
    for m in re.finditer(r"([^{}\n]{1,120})\{([^}]{0,400}?)\}", txt):
        sel, body = m.group(1).strip(), m.group(2)
        fs = re.search(r"font-size:\s*([\d.]+)px", body)
        if not fs:
            continue
        buckets[float(fs.group(1))].append(f"{sel[-52:]:52s} <- {pathlib.Path(f).name}")

print(f"{len(sum(buckets.values(), []))} font-size declarations\n")
for size in sorted(buckets):
    flag = "  <-- TOO SMALL" if size < 15 else ""
    print(f"{size:5.1f}px  x{len(buckets[size])}{flag}")
    if size < 15:
        for sel in buckets[size]:
            print(f"          {sel}")
