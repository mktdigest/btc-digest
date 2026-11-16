"""Fix the four reconciliation bugs the audit found.

1. build_site.py re-ran the whole digest when called without an argument, so the page could be
   built from a DIFFERENT run than latest_digest.txt. That is how the page ended up showing
   premium -0.122% / spot $64,144 while the cached digest said -0.112% / $64,072.
2. The header's "updated <time>" was the BUILD clock, not the digest's own timestamp, so a
   stale page still claimed to be fresh. Data time and build time are different facts.
3. Fear & Greed printed its percentile twice: _ord() truncates (6.67 -> 6) while f"{:.0f}"
   rounds (6.67 -> 7), so one block said "6th percentile" and "pctile 7" two lines apart.
4. The premium chart card labelled the last settled close "right now".
"""
import pathlib

BS = pathlib.Path("/root/btc-digest-site/build_site.py")
CH = pathlib.Path("/root/btc-digest-site/charts.py")
DG = pathlib.Path("/root/.hermes/scripts/coinbase_premium_daily.py")
n = 0


def sub(path, old, new, label):
    global n
    s = path.read_text()
    c = s.count(old)
    assert c == 1, f"{label}: expected 1 match, found {c}"
    path.write_text(s.replace(old, new))
    n += 1
    print("  ok ", label)


# ── 1. never run the digest from the page builder ──────────────────────────────
sub(BS, '''def build(raw=None):
    if raw is None:
        raw = run_digest()''',
    '''def build(raw=None):
    if raw is None:
        # NEVER run the digest from here. Two reasons, both learned the hard way:
        #   1. it doubles every API call - bitcoin-data.com allows 10/hour, and the wrapper
        #      already ran the digest once for this build;
        #   2. the page would then be built from a DIFFERENT run than latest_digest.txt, so the
        #      cached text and the page disagree (premium -0.122% on the page vs -0.112% in the
        #      cache) and there is no way to tell which is current.
        # Read the text the wrapper just captured instead.
        with open(os.path.join(HERE, "latest_digest.txt")) as fh:
            raw = fh.read()''', "build() reads the cache, never runs the digest")

# ── 2. data time vs build time ────────────────────────────────────────────────
sub(BS, '''    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")''',
    '''    # The digest stamps its own run time; the page must quote THAT as the data time. Using the
    # build clock made a page built from a 40-minute-old digest claim to be up to the minute.
    digest_ts = _grab(r"BTC daily read\\s*\\|\\s*([\\d\\-]+ [\\d:]+ UTC)", raw, 1, "")
    updated = digest_ts or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    built_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")''',
    "digest timestamp for the header")

sub(BS, '''<p>Last build: {updated}</p>''',
    '''<p>Data as of {updated} &middot; page built {built_ts}</p>''', "footer states both times")

# ── 3. one rounded percentile, used everywhere in the block ───────────────────
sub(DG, '''    pct = sum(1 for v in vals if v <= now) / len(vals) * 100

    out = [f"    now {now} ({cls})   yesterday {yday}   30d range {min(vals)}-{max(vals)}",
           f"    30d avg {statistics.mean(vals):.0f}   (current = {_ord(pct)} percentile of the 30d window)"]''',
    '''    pct = sum(1 for v in vals if v <= now) / len(vals) * 100
    # Round ONCE and print that integer everywhere. _ord() truncates and "%.0f" rounds, so a
    # 6.67 percentile printed as "6th percentile" on the data line and "pctile 7" in the verdict
    # two lines below - the same statistic, two different numbers, on the same block.
    pi = int(round(pct))

    out = [f"    now {now} ({cls})   yesterday {yday}   30d range {min(vals)}-{max(vals)}",
           f"    30d avg {statistics.mean(vals):.0f}   (current = {_ord(pi)} percentile of the 30d window)"]''',
    "F&G: one rounded percentile")

sub(DG, '''        verdict = (f"EXTREME FEAR (pctile {pct:.0f}): crowd capitulating - contrarian-bullish for a "''',
    '''        verdict = (f"EXTREME FEAR (pctile {pi}): crowd capitulating - contrarian-bullish for a "''',
    "F&G fear verdict uses pi")
sub(DG, '''        verdict = f"EXTREME GREED (pctile {pct:.0f}): crowd euphoric - contrarian-bearish"''',
    '''        verdict = f"EXTREME GREED (pctile {pi}): crowd euphoric - contrarian-bearish"''',
    "F&G greed verdict uses pi")
sub(DG, '''        verdict = f"neutral sentiment (pctile {pct:.0f}): no crowd extreme"''',
    '''        verdict = f"neutral sentiment (pctile {pi}): no crowd extreme"''',
    "F&G neutral verdict uses pi")

# ── 4. the premium card is quoting the last CLOSE, not a live tick ────────────
sub(CH, '''                [f"right now {prem[-1]:+.3f}%", f"30-day average {m30[-1]:+.3f}%",
                 f"below zero for {streak} days straight"],''',
    '''                # prem[-1] is the last SETTLED daily close - the series excludes the forming
                # day. Calling it "right now" (as this chip did) claimed a live tick that it is
                # not, and disagreed with the digest's live line on the same screen.
                [f"last close {prem[-1]:+.3f}%", f"30-day average {m30[-1]:+.3f}%",
                 f"below zero for {streak} days straight"],''', "premium chip: last close, not live")

print(f"\n{n} fixes applied")
