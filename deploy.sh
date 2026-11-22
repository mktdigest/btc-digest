#!/bin/bash
# Build -> commit -> push -> verify the LIVE page actually contains this change.
# md5 alone lied once (compared against a stale CDN copy), so pass a marker string that only exists
# in the new build. Usage: ./deploy.sh "commit message" 'unique-marker'
set -e
cd /root/btc-digest-site

MSG="${1:-site update}"
MARKER="${2:-}"
# consistency gate: one metric, one number, everywhere it appears
python3 audit_consistency.py || { echo "ABORT: consistency audit failed, nothing pushed"; exit 1; }

python3 build_site.py | tail -1

if git diff --quiet && git diff --cached --quiet; then
  echo "nothing to commit"
else
  git add -A
  git commit -q -m "$MSG"
  git push -q origin HEAD:main
  echo "pushed: $(git log --oneline -1)"
fi

LOCAL=$(md5sum index.html | cut -c1-32)
echo "waiting for GitHub Pages (local md5 ${LOCAL:0:10})..."
for i in $(seq 1 40); do
  sleep 8
  curl -s -H 'Cache-Control: no-cache' -o /tmp/live_page.html \
       "https://mktdigest.github.io/btc-digest/?cb=$(date +%s%N)"
  LIVE=$(md5sum /tmp/live_page.html | cut -c1-32)
  if [ "$LIVE" = "$LOCAL" ]; then
    if [ -z "$MARKER" ] || python3 -c "import sys,re;h=re.sub(r'\\s+',' ',open(sys.argv[1]).read());m=re.sub(r'\\s+',' ',sys.argv[2]);sys.exit(0 if m in h else 1)" /tmp/live_page.html "$MARKER"; then
      echo "LIVE OK after $((i*8))s (md5 ${LIVE:0:10}${MARKER:+, marker found})"
      exit 0
    fi
    echo "  md5 matches but marker '$MARKER' missing - still waiting"
  fi
done
echo "FAILED after 320s: local ${LOCAL:0:10} vs live ${LIVE:0:10}"
exit 1
