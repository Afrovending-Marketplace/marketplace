#!/usr/bin/env bash
# Nightly (06:00 UTC): verified mongodump -> restore drill -> AES-256 encrypted copy to DigitalOcean Spaces (off the Droplet).
set -euo pipefail
export BACKUP_DIR=/backups

run_once() {
  cd /srv/backend
  bash scripts/backup_db.sh
  latest=$(ls -t /backups/*.archive.gz | head -1)
  bash scripts/restore_verify.sh "$latest"
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -in "$latest" -out "$latest.enc"
  rclone copy "$latest.enc" "spaces:${SPACES_BUCKET}/db/" && rclone copy "$latest.sha256" "spaces:${SPACES_BUCKET}/db/"
  rclone copy "$latest.restore.json" "spaces:${SPACES_BUCKET}/db/"
  rm -f "$latest.enc"
  rclone delete "spaces:${SPACES_BUCKET}/db/" --min-age 35d
  echo "backup ok: $latest"
}

if [ "${1:-}" = "loop" ]; then
  while true; do
    now=$(date -u +%s); next=$(date -u -d "tomorrow 06:00" +%s)
    [ "$(date -u +%H)" -lt 6 ] && next=$(date -u -d "today 06:00" +%s)
    sleep $((next - now))
    run_once || echo "BACKUP FAILED at $(date -u)" >&2
  done
else
  run_once
fi
