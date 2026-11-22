#!/usr/bin/env bash
# Deploy a reviewed git commit: backup -> build versioned images -> start -> health check. Usage: bash deploy/scripts/deploy.sh <git-commit-or-tag>
set -euo pipefail
cd "$(dirname "$0")/.."
REF="${1:?pass the reviewed git commit or tag to deploy}"
git -C .. fetch --all --tags && git -C .. checkout --detach "$REF"
RELEASE=$(git -C .. rev-parse --short HEAD)
PREV=$(cat .current_release 2>/dev/null || echo "")
sed -i "s/^RELEASE=.*/RELEASE=${RELEASE}/" .env

if [ -n "$PREV" ]; then
  echo "== Pre-deploy database backup + restore drill"
  docker compose run --rm backup /usr/local/bin/nightly.sh
fi

echo "== Building release $RELEASE"
docker compose build backend
docker compose build web backup

echo "== Starting release $RELEASE (migrations run on backend start-up)"
docker compose up -d --remove-orphans

for i in $(seq 1 30); do
  if curl -fsS "https://$(grep ^SITE_DOMAIN= .env | cut -d= -f2)/api/v1/health" >/dev/null 2>&1; then
    echo "$PREV" > .previous_release; echo "$RELEASE" > .current_release
    echo "== Release $RELEASE is healthy"; exit 0
  fi
  sleep 5
done
echo "!! Health check failed for $RELEASE. Roll back with: bash deploy/scripts/rollback.sh" >&2
exit 1
