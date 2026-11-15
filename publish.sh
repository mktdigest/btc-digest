#!/usr/bin/env bash
# Rebuild and push the digest page. Usage: ./publish.sh [remote-url]
set -euo pipefail
cd "$(dirname "$0")"
python3 build_site.py
git add -A
git commit -q -m "digest: $(date -u +%Y-%m-%dT%H:%MZ)" || echo "nothing to commit"
if [ $# -ge 1 ]; then git remote remove origin 2>/dev/null || true; git remote add origin "$1"; fi
git push -u origin HEAD:main
echo "pushed. enable Pages: Settings -> Pages -> Deploy from branch -> main / (root)"
