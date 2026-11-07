#!/usr/bin/env bash
# Verified backup of the new marketplace database: gzip archive + SHA-256 + per-collection counts.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
OUT="${BACKUP_DIR:-/app/backups}"; mkdir -p "$OUT"
TS=$(date -u +%Y%m%dT%H%M%SZ); FILE="$OUT/${DB_NAME}-${TS}.archive.gz"
mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --archive="$FILE" --quiet
sha256sum "$FILE" > "$FILE.sha256"
python3 - "$FILE" <<'PY'
import json, os, sys
from pymongo import MongoClient
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
counts = {c: db[c].count_documents({}) for c in sorted(db.list_collection_names())}
json.dump(counts, open(sys.argv[1] + ".counts.json", "w"), indent=1)
print(json.dumps({"backup": sys.argv[1], "collections": len(counts), "documents": sum(counts.values())}))
PY
ls -t "$OUT"/*.archive.gz | tail -n +15 | while read -r old; do rm -f "$old" "$old".sha256 "$old".counts.json "$old".restore.json; done  # keep the newest 14 locally
