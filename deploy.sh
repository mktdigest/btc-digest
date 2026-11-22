#!/bin/bash
# Build -> commit -> push -> wait for Pages -> prove the live file matches local.
# Every UI change goes through this. Skipping the push is how Ben ended up looking at a stale page
# three times in a row.
set -e
cd /root/btc-digest-site

MSG="${1:-site update}"
python3 build_site.py | tail -1

if git diff --quiet && git diff --cached --quiet; then
  echo "nothing to commit"
else
  git add -A
  git commit -q -m "$MSG"
  git push -q origin HEAD:main
  echo "pushed: $(git log --oneline -1)"
fi

echo "waiting for GitHub Pages..."
LOCAL=$(md5sum index.html | cut -c1-32)
for i in $(seq 1 30); do
  sleep 10
  LIVE=$(curl -s -H 'Cache-Control: no-cache' "https://mktdigest.github.io/btc-digest/?cb=$(date +%s)" | md5sum | cut -c1-32)
  if [ "$LIVE" = "$LOCAL" ]; then
    echo "LIVE MATCHES: ${LOCAL:0:10} (after $((i*10))s)"
    grep -o 'position:sticky' index.html | head -1 | sed 's/^/  /'
    exit 0
  fi
done
echo "STILL STALE after 300s: local ${LOCAL:0:10} vs live ${LIVE:0:10}"
exit 1
