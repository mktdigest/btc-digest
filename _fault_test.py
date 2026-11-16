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
build_ts = re.search(r'<meta name="page-built" content="([^"]+)"', HTML.read_text()).group(1)
assert build_ts != digest_ts, "fixture stale: build stamp equals digest stamp"
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

for f in SITE.glob("*.faultbak"):
    f.unlink()
print()
print(f"{sum(results)}/{len(results)} injected faults caught")
sys.exit(0 if all(results) else 1)
