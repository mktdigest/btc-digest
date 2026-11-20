"""Fault injection: prove each LAYER 5 guard actually bites.

A check that cannot fail is theatre. Each fault below is the exact bug class that shipped
on 2026-11-16; every one must turn the audit red, then be restored.

Run:  python3 _fault_test.py     (exit 0 = every injected fault was caught)
"""
import pathlib
import re
import shutil
import subprocess
import sys

SITE = pathlib.Path("/root/btc-digest-site")
HTML, BS = SITE / "index.html", SITE / "build_site.py"
DIGEST = SITE / "latest_digest.txt"


def run_audit():
    r = subprocess.run([sys.executable, "audit_digest.py"], cwd=SITE,
                       capture_output=True, text=True)
    fails = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith("FAIL")]
    return r.returncode, fails


def replace_in(path, old, new):
    s = path.read_text()
    assert old in s, f"anchor missing in {path.name}: {old[:50]!r}"
    path.write_text(s.replace(old, new, 1))


def trial(name, path, mutate):
    backup = path.with_suffix(path.suffix + ".faultbak")
    shutil.copy(path, backup)
    try:
        mutate(path)
        code, fails = run_audit()
        caught = code != 0
        print(f"{'CAUGHT ' if caught else 'MISSED!'} {name}")
        for f in fails[:2]:
            print(f"         -> {f}")
        return caught
    finally:
        shutil.copy(backup, path)
        backup.unlink()


results = []

# A. page claims to be built from a different digest than the cache (stale/mixed page)
results.append(trial(
    "page claims a different digest run",
    HTML,
    lambda p: replace_in(p, '<meta name="digest-md5" content="',
                         '<meta name="digest-md5" content="deadbeef0000'),
))

# B. build clock presented as data time - the header lie that shipped
digest_ts = re.search(r"BTC daily read\s*\|\s*([\d\-]+ [\d:]+ UTC)",
                      (SITE / "latest_digest.txt").read_text()).group(1)
# A deliberately wrong "data as of" stamp: the digest's own stamp shifted by +7 minutes. Deriving
# it beats borrowing page-built, which is legitimately IDENTICAL to the digest stamp when the cron
# builds in the same minute the digest stamps (08:30 SGT = 00:30 UTC).
_d, _hm = digest_ts.split(" ", 1)          # "2026-11-20 00:30 UTC" -> date, "00:30 UTC"
_h, _mi = (int(x) for x in _hm.split(" ")[0].split(":"))
build_ts = f"{_d} {(_h + (_mi + 7) // 60) % 24:02d}:{(_mi + 7) % 60:02d} UTC"
assert build_ts != digest_ts, "fixture stale: generated stamp equals the digest stamp"
results.append(trial(
    "header shows build time instead of data time",
    HTML,
    lambda p: replace_in(p, "updated " + digest_ts, "updated " + build_ts),
))

# C. builder secretly fetches again -> page can come from a different run than the cache
results.append(trial(
    "builder calls run_digest() again",
    BS,
    lambda p: replace_in(p, "    blocks_html = render_digest(raw)",
                         "    run_digest()\n    blocks_html = render_digest(raw)"),
))

# D. build stamp stripped -> staleness becomes invisible
results.append(trial(
    "page-built meta stripped",
    HTML,
    lambda p: replace_in(p, '<meta name="page-built" content="', '<meta name="x-built" content="'),
))

# E. provenance meta removed entirely -> must be a hard fail, not a silent warn
results.append(trial(
    "digest-md5 meta removed",
    HTML,
    lambda p: replace_in(p, '<meta name="digest-md5" content="', '<meta name="x-digest" content="'),
))

# F. data-time unreadable -> staleness invisible
results.append(trial(
    "header timestamp removed",
    HTML,
    lambda p: replace_in(p, "updated " + digest_ts, "updated (unknown)"),
))

# G. arithmetic layer: the printed 85th percentile no longer matches the series. Values move
# daily, so derive the anchor from today's digest instead of hardcoding 3.11.
_dig = DIGEST.read_text()
_m = re.search(r"crowd lines ([\d\.]+)/([\d\.]+)", _dig)
assert _m, "fixture stale: no crowd lines in the digest"
_c15, _c85 = _m.group(1), _m.group(2)
_bogus = f"{float(_c85) + 0.20:.2f}"
results.append(trial(
    "crowd-line 85th percentile disagrees with the series",
    DIGEST,
    lambda p: replace_in(p, f"crowd lines {_c15}/{_c85}", f"crowd lines {_c15}/{_bogus}"),
))

for f in SITE.glob("*.faultbak"):
    f.unlink()
print()
print(f"{sum(results)}/{len(results)} injected faults caught")
sys.exit(0 if all(results) else 1)
