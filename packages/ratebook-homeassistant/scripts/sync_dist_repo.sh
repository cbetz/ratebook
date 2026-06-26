#!/usr/bin/env bash
# Sync the HACS distribution repo (cbetz/ratebook-homeassistant) from this monorepo.
#
# The monorepo is the source of truth. The distribution repo exists only because HACS requires
# `custom_components/<domain>/` at a repository root. This script regenerates the vendored deps
# and mirrors the integration into the dist repo; review + commit + push there afterwards.
#
# Usage:  bash packages/ratebook-homeassistant/scripts/sync_dist_repo.sh [path-to-dist-repo]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONO="$(cd "$HERE/../../.." && pwd)"
DIST="${1:-$MONO/../ratebook-homeassistant}"

if [[ ! -d "$DIST/.git" ]]; then
  echo "error: '$DIST' is not a git repo. Pass the dist-repo path as arg 1." >&2
  exit 1
fi

# 1. Make sure the vendored engine/adapter is current.
python3 "$HERE/sync_vendor.py"

# 2. Mirror the integration to the dist repo root (delete removed files; skip caches).
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
  "$MONO/packages/ratebook-homeassistant/custom_components/ratebook/" \
  "$DIST/custom_components/ratebook/"

echo "Synced integration -> $DIST/custom_components/ratebook"
echo "Next: cd '$DIST' && git add -A && git commit -m 'Sync from monorepo' && git push"
