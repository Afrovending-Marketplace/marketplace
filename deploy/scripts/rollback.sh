#!/usr/bin/env bash
# Switch back to the previous image release (images are kept locally). Usage: bash deploy/scripts/rollback.sh [release]
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET="${1:-$(cat .previous_release 2>/dev/null)}"
[ -n "$TARGET" ] || { echo "No previous release recorded; pass a release tag (docker images afrovending-backend)"; exit 1; }
docker image inspect "afrovending-backend:$TARGET" "afrovending-web:$TARGET" >/dev/null
sed -i "s/^RELEASE=.*/RELEASE=${TARGET}/" .env
docker compose up -d --no-build --remove-orphans
echo "$TARGET" > .current_release
echo "Rolled back to $TARGET. Database changes are not reverted; restore a backup only if data must be rolled back (see the guide)."
