import re, pathlib

FILES = ["/root/btc-digest-site/build_site.py", "/root/btc-bottom/render_section.py"]


def bump(size: float) -> float:
    """Readability floor. Decorative micro-labels stop at 14.5; anything a reader must
    actually read goes to 15+. Body copy lands at 16.5-17. Hierarchy is preserved because
    the mapping is monotonic: a bigger input never produces a smaller output."""
    if size <= 12.5:
        return 14.5
    if size <= 13.0:
        return 15.0
    if size <= 14.0:
        return 15.5
    if size <= 14.5:
        return 16.0
    if size <= 15.0:
        return 16.0
    if size <= 15.5:
        return 16.5
    if size <= 16.5:
        return 17.0
    return size  # 17px and up already reads fine, leave headers alone


changed = []
for f in FILES:
    p = pathlib.Path(f)
    s = p.read_text()

    def rep(m):
        old = float(m.group(1))
        new = bump(old)
        if new != old:
            changed.append((p.name, old, new))
        fmt = f"{new:g}"
        return f"font-size:{fmt}px"

    s2 = re.sub(r"font-size:\s*([\d.]+)px", rep, s)
    p.write_text(s2)

from collections import Counter
c = Counter((o, n) for _, o, n in changed)
print(f"{len(changed)} declarations raised")
for (o, n), k in sorted(c.items()):
    print(f"  {o:5g}px -> {n:5g}px   x{k}")
