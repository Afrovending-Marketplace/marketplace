#!/usr/bin/env bash
# Restore drill: check SHA-256, restore the archive into <DB_NAME>_restore_check, compare counts, then drop the check DB.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
FILE="$1"; CHECK="${DB_NAME}_restore_check"
sha256sum -c "$FILE.sha256" --quiet
mongorestore --uri="$MONGO_URL" --gzip --archive="$FILE" --nsFrom="${DB_NAME}.*" --nsTo="${CHECK}.*" --drop --quiet
python3 - "$FILE" "$CHECK" <<'PY'
import json, os, sys
from pymongo import MongoClient
c = MongoClient(os.environ["MONGO_URL"])
want = json.load(open(sys.argv[1] + ".counts.json"))
got = {k: c[sys.argv[2]][k].estimated_document_count() for k in want}
bad = {k: (want[k], got[k]) for k in want if want[k] != got[k]}
c.drop_database(sys.argv[2])
print(json.dumps({"restore_check": "PASS" if not bad else "FAIL", "collections": len(want), "documents": sum(want.values()), "mismatches": bad}))
sys.exit(1 if bad else 0)
PY
