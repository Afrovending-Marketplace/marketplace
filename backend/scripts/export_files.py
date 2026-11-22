"""Export every stored file to a local folder with a SHA-256 manifest, for migrating to another storage provider.

Usage: python scripts/export_files.py /path/to/export   (needs MONGO_URL, DB_NAME and the storage key in the environment)
Generated review packs live inside MongoDB and are covered by database backups.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from afrovending.core.storage import get_object  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "file-export")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
items = [("files", str(d["_id"]), d["storage_path"], d.get("is_private", True)) for d in db.files.find({"is_deleted": False})]
items += [("review_packs.attorney_records", r["id"], r["storage_path"], True) for d in db.review_packs.find({}, {"attorney_records": 1})
          for r in d.get("attorney_records", []) if r.get("storage_path")]
manifest, failed = [], []
for coll, rid, path, private in items:
    try:
        data, ctype = get_object(path)
    except Exception as e:
        failed.append({"collection": coll, "id": rid, "path": path, "error": type(e).__name__})
        continue
    dest = out / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    manifest.append({"collection": coll, "id": rid, "path": path, "content_type": ctype, "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(), "private": bool(private)})
out.mkdir(parents=True, exist_ok=True)
(out / "manifest.json").write_text(json.dumps({"files": manifest, "failed": failed}, indent=1))
print(json.dumps({"exported": len(manifest), "failed": len(failed), "folder": str(out)}))
sys.exit(1 if failed else 0)
