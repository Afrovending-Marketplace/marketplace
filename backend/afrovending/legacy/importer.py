"""Legacy AfroVending import: validate -> map -> idempotent upsert into a STAGING database.

Never sends email, never creates payments/ledger/payouts, never copies passwords or card data, never grants admin roles.
Usage: python -m afrovending.legacy.importer --source DIR [--target-db NAME] [--dry-run] [--publish-active] [--fetch-images --images-dir DIR]
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bson import ObjectId
from email_validator import EmailNotValidError, validate_email
from pymongo import MongoClient

from afrovending.core.config import settings

SOURCE = "legacy_afrovending"
SPECS = {
    "categories": (["legacy_id", "name"], ["slug", "parent_legacy_id", "map_to_slug"]),
    "customers": (["legacy_id", "email", "name"], ["phone", "email_verified", "status", "created_at", "marketing_opt_in"]),
    "vendors": (["legacy_id", "owner_email", "store_name"], ["owner_name", "slug", "description", "phone", "city", "region", "country", "status", "created_at", "logo_url", "banner_url"]),
    "products": (["legacy_id", "vendor_legacy_id", "category_legacy_id", "title"], ["slug", "description", "status", "tags", "image_urls", "created_at", "sku", "price", "stock"]),
    "variants": (["legacy_id", "product_legacy_id", "sku", "price"], ["option_names", "option_values", "stock", "status"]),
    "addresses": (["legacy_id", "customer_legacy_id", "full_name", "line1", "city", "country"], ["label", "line2", "region", "postal_code", "phone", "is_default"]),
    "orders": (["legacy_id", "order_number", "customer_legacy_id", "total", "placed_at"], ["vendor_legacy_id", "status", "currency", "subtotal", "shipping", "tax", "discount"]),
    "order_items": (["order_legacy_id", "title", "quantity", "unit_price"], ["product_legacy_id", "variant_legacy_id", "sku"]),
    "wishlists": (["customer_legacy_id", "product_legacy_id"], ["created_at"]),
    "redirects": (["from_path", "to_path"], []),
}
STATIC_REDIRECTS = {"/about-us": "/about", "/contact-us": "/contact", "/faqs": "/faq", "/privacy-policy": "/privacy", "/become-a-vendor": "/sell",
                    "/stores": "/vendors", "/category": "/categories", "/checkout": "/cart"}
LIVE = {"active", "published", "approved", "enabled", "1", "true", "yes"}
SKU_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")


def slugify(s: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:80]


def minor(v) -> int:
    d = Decimal(str(v).replace("$", "").replace(",", "").strip())
    if d < 0:
        raise InvalidOperation
    return int((d * 100).quantize(Decimal("1")))


def when(v):
    v = (v or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(v.replace("Z", "+0000"), fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def truthy(v) -> bool:
    return str(v or "").strip().lower() in LIVE


def norm(v):
    """Compare like Mongo stores: naive UTC datetimes at millisecond precision."""
    if isinstance(v, datetime):
        v = v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v
        return v.replace(microsecond=v.microsecond // 1000 * 1000)
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def load(src: Path, name: str) -> list[dict] | None:
    for ext in ("csv", "json"):
        f = src / f"{name}.{ext}"
        if f.exists():
            if ext == "json":
                rows = json.loads(f.read_text("utf-8-sig"))
            else:
                with f.open(newline="", encoding="utf-8-sig") as fh:
                    rows = list(csv.DictReader(fh))
            return [{k.strip(): ("" if v is None else str(v).strip()) for k, v in r.items() if k} for r in rows]
    return None


class Run:
    def __init__(self, db, dry: bool, publish: bool):
        self.db, self.dry, self.publish, self.now = db, dry, publish, datetime.now(timezone.utc)
        self.rep = {"mode": "dry-run" if dry else "import", "target_db": db.name, "started_at": self.now.isoformat(), "entities": {},
                    "errors": [], "warnings": [], "reconciliation": [], "missing_files": [], "unmapped_legacy_paths": []}
        self.cats, self.users, self.cust, self.vendors, self.products, self.variants = {}, {}, {}, {}, {}, {}
        self.paths = set()

    def stat(self, entity: str, k: str, n: int = 1):
        self.rep["entities"].setdefault(entity, defaultdict(int))[k] += n

    def err(self, entity, row, field, msg):
        self.rep["errors"].append({"file": entity, "row": row, "field": field, "message": msg})
        self.stat(entity, "errors")

    def mig(self, legacy_id, **extra):
        return {"source": SOURCE, "legacy_id": str(legacy_id), **extra}

    def upsert(self, coll: str, flt: dict, doc: dict, entity: str):
        cur = self.db[coll].find_one(flt)
        if not cur:
            self.stat(entity, "created")
            if self.dry:
                return ObjectId()
            doc.setdefault("created_at", self.now)
            return self.db[coll].insert_one({**doc, "updated_at": self.now}).inserted_id
        changed = {k: v for k, v in doc.items() if k != "created_at" and norm(cur.get(k)) != norm(v)}
        self.stat(entity, "updated" if changed else "unchanged")
        if changed and not self.dry:
            self.db[coll].update_one({"_id": cur["_id"]}, {"$set": {**changed, "updated_at": self.now}})
        return cur["_id"]

    def rows(self, src: Path, name: str):
        data = load(src, name)
        if data is None:
            self.rep["missing_files"].append(f"{name}.csv")
            return []
        req, opt = SPECS[name]
        cols = set(data[0]) if data else set()
        miss = [c for c in req if c not in cols]
        if data and miss:
            self.err(name, 0, ",".join(miss), "Required column missing; file skipped.")
            return []
        unknown = cols - set(req) - set(opt)
        if unknown:
            self.rep["warnings"].append({"file": name, "message": f"Ignored columns: {', '.join(sorted(unknown))}"})
        out = []
        for i, r in enumerate(data, start=2):
            self.stat(name, "rows")
            blank = [c for c in req if not r.get(c)]
            if blank:
                self.err(name, i, ",".join(blank), "Required value is empty.")
                continue
            out.append((i, r))
        return out

    # ---------- steps ----------
    def categories(self, src):
        rows = self.rows(src, "categories")
        rows.sort(key=lambda x: bool(x[1].get("parent_legacy_id")))
        for i, r in rows:
            slug = slugify(r.get("map_to_slug") or r.get("slug") or r["name"])
            existing = self.db.categories.find_one({"slug": slug})
            if existing and not (existing.get("migration") or {}).get("legacy_id") == r["legacy_id"]:
                self.cats[r["legacy_id"]] = (existing["_id"], slug)
                self.stat("categories", "mapped_to_existing")
            else:
                parent = self.cats.get(r.get("parent_legacy_id") or "")
                doc = {"slug": slug, "name": r["name"][:80], "blurb": "", "sort_order": 100, "parent_id": parent[0] if parent else None,
                       "image": None, "status": "active", "migration": self.mig(r["legacy_id"])}
                self.cats[r["legacy_id"]] = (self.upsert("categories", {"migration.legacy_id": r["legacy_id"], "migration.source": SOURCE}, doc, "categories"), slug)
            self.stat("categories", "valid")
            if r.get("slug"):
                self.redirect(f"/category/{r['slug']}", f"/categories/{slug}")

    def _email(self, entity, i, raw):
        try:
            return validate_email(raw, check_deliverability=False).normalized.lower()
        except EmailNotValidError as e:
            self.rep["reconciliation"].append({"type": "invalid_email", "file": entity, "row": i, "value": raw[:80], "detail": str(e)[:120]})
            self.stat(entity, "skipped")
            return None

    def account(self, email, name, phone, verified, created, legacy_key, entity, i):
        rec = self.users.get(email)
        if rec:
            prefix = legacy_key.split(":")[0] + ":"
            same = [k for k in rec["legacy"] if k.startswith(prefix)]
            if same and prefix == "customer:":
                self.rep["reconciliation"].append({"type": "duplicate_email", "file": entity, "row": i, "email": email,
                                                   "detail": f"Same email as {same[0]}; merged into one account (review)."})
        else:
            rec = self.users[email] = {"email": email, "name": name, "phone": phone, "verified": verified, "created": created, "legacy": {}, "roles": {"customer"}}
        rec["legacy"].setdefault(legacy_key, legacy_key)
        return rec

    def accounts(self, src):
        for i, r in self.rows(src, "customers"):
            email = self._email("customers", i, r["email"])
            if email:
                rec = self.account(email, r["name"], r.get("phone"), truthy(r.get("email_verified")), when(r.get("created_at")), f"customer:{r['legacy_id']}", "customers", i)
                rec["legacy"][f"customer:{r['legacy_id']}"] = r["legacy_id"]
                rec["consent"] = r.get("marketing_opt_in", "")
                self.cust[r["legacy_id"]] = email
                self.stat("customers", "valid")
        self.vendor_rows = []
        for i, r in self.rows(src, "vendors"):
            email = self._email("vendors", i, r["owner_email"])
            if email:
                rec = self.account(email, r.get("owner_name") or r["store_name"], r.get("phone"), True, when(r.get("created_at")), f"vendor:{r['legacy_id']}", "vendors", i)
                rec["legacy"][f"vendor:{r['legacy_id']}"] = r["legacy_id"]
                rec["roles"].add("vendor")
                self.vendor_rows.append((i, r, email))
        for email, rec in self.users.items():
            cur = self.db.users.find_one({"email": email})
            if cur and not (cur.get("migration") or {}).get("source") == SOURCE:
                admin = any(x.endswith("admin") for x in cur.get("roles", []))
                self.rep["reconciliation"].append({"type": "admin_email_conflict" if admin else "existing_account", "email": email,
                                                   "detail": "Matches an administrator; legacy records NOT attached." if admin else
                                                   "Matches an account created on the new site; linked by email, password untouched."})
                if admin:
                    rec["blocked"] = True
                    continue
                rec["id"] = cur["_id"]
                if not self.dry:
                    self.db.users.update_one({"_id": cur["_id"]}, {"$set": {"migration_link": {"source": SOURCE, "legacy_ids": rec["legacy"]}},
                                                                   "$addToSet": {"roles": {"$each": sorted(rec["roles"])}}})
                self.stat("accounts", "linked_existing")
                continue
            prev = (cur or {}).get("migration") or {}
            doc = {"email": email, "name": (rec["name"] or email.split("@")[0])[:100], "phone": rec["phone"] or None,
                   "roles": sorted(set(cur.get("roles", [])) | rec["roles"]) if cur else sorted(rec["roles"]),
                   "status": (cur or {}).get("status", "active"), "email_verified_at": (cur or {}).get("email_verified_at") or ((rec["created"] or self.now) if rec["verified"] else None),
                   "migration": {"source": SOURCE, "legacy_ids": rec["legacy"], "activation_required": prev.get("activation_required", True),
                                 "legacy_marketing_consent": rec.get("consent", ""), **{k: prev[k] for k in ("activated_at", "activation_sent_at") if k in prev}}}
            if not cur:
                doc.update(password_hash=None, auth_providers=[], marketing_opt_in=False, created_at=rec["created"] or self.now)
            rec["id"] = self.upsert("users", {"email": email}, doc, "accounts")
        self.stat("accounts", "total", len(self.users))

    def vendors_step(self):
        for i, r, email in self.vendor_rows:
            rec = self.users[email]
            if rec.get("blocked"):
                self.err("vendors", i, "owner_email", "Owner email belongs to an administrator; vendor not imported (manual review).")
                continue
            slug = self.free_slug("vendors", slugify(r.get("slug") or r["store_name"]), r["legacy_id"])
            active = truthy(r.get("status") or "active")
            flt = {"migration.legacy_id": r["legacy_id"], "migration.source": SOURCE}
            doc = {"owner_user_id": rec["id"], "application_id": None, "slug": slug, "name": r["store_name"][:120], "status": "active" if active else "suspended",
                   "approved_at": when(r.get("created_at")) or self.now, "migration": self.mig(r["legacy_id"])}
            vid = self.upsert("vendors", flt, doc, "vendors")
            loc = ", ".join(x for x in (r.get("city"), r.get("region"), r.get("country")) if x)
            store = {"vendor_id": vid, "owner_user_id": rec["id"], "slug": slug, "display_name": r["store_name"][:120], "tagline": "", "description": r.get("description", "")[:2000],
                     "location": loc, "categories": [], "logo_file_id": None, "banner_file_id": None,
                     "status": "published" if (self.publish and active) else "draft", "migration": self.mig(r["legacy_id"])}
            self.upsert("vendor_stores", {"vendor_id": vid}, store, "vendor_stores")
            self.vendors[r["legacy_id"]] = (vid, rec["id"], active)
            self.stat("vendors", "valid")
            if r.get("slug"):
                self.redirect(f"/store/{r['slug']}", f"/store/{slug}")

    def free_slug(self, coll, base, legacy_id):
        base = base or "item"
        slug, n = base, 2
        while True:
            hit = self.db[coll].find_one({"slug": slug}, {"migration": 1})
            if not hit or (hit.get("migration") or {}).get("legacy_id") == legacy_id:
                taken = self.rep.setdefault("_slugs", {}).setdefault(coll, {})
                if taken.get(slug, legacy_id) == legacy_id:
                    taken[slug] = legacy_id
                    return slug
            slug, n = f"{base}-{n}", n + 1

    def catalog(self, src):
        products = self.rows(src, "products")
        var_rows = defaultdict(list)
        for i, r in self.rows(src, "variants"):
            var_rows[r["product_legacy_id"]].append((i, r))
        for i, r in products:
            v = self.vendors.get(r["vendor_legacy_id"])
            c = self.cats.get(r["category_legacy_id"])
            if not v:
                self.err("products", i, "vendor_legacy_id", f"Unknown or skipped vendor {r['vendor_legacy_id']}.")
                continue
            if not c:
                self.err("products", i, "category_legacy_id", f"Unknown category {r['category_legacy_id']}; add it to categories.csv or map_to_slug.")
                continue
            vrows = var_rows.pop(r["legacy_id"], None)
            if not vrows and r.get("sku") and r.get("price"):
                vrows = [(i, {"legacy_id": f"{r['legacy_id']}-default", "sku": r["sku"], "price": r["price"], "stock": r.get("stock", "0")})]
            variants = []
            for vi, vr in vrows or []:
                if not SKU_RE.match(vr["sku"]):
                    self.err("variants", vi, "sku", f"SKU '{vr['sku'][:40]}' must be 2-64 letters, numbers, dots, dashes or underscores.")
                    continue
                try:
                    price = minor(vr["price"])
                    stock = int(Decimal(vr.get("stock") or "0"))
                    if price < 1 or stock < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    self.err("variants", vi, "price/stock", "Price must be > 0 and stock a whole number >= 0.")
                    continue
                other = self.db.product_variants.find_one({"sku": vr["sku"]}, {"migration": 1})
                if (other and (other.get("migration") or {}).get("legacy_id") != vr["legacy_id"]) or vr["sku"] in self.rep.setdefault("_skus", {}) and self.rep["_skus"][vr["sku"]] != vr["legacy_id"]:
                    self.err("variants", vi, "sku", f"Duplicate SKU {vr['sku']}.")
                    continue
                self.rep["_skus"][vr["sku"]] = vr["legacy_id"]
                names = [x.strip() for x in (vr.get("option_names") or "").split("|") if x.strip()][:3]
                vals = [x.strip() for x in (vr.get("option_values") or "").split("|") if x.strip()][:3]
                variants.append({"legacy_id": vr["legacy_id"], "sku": vr["sku"], "price": price, "stock": stock, "options": dict(zip(names, vals)),
                                 "active": (vr.get("status") or "active").lower() not in ("inactive", "disabled", "0", "false")})
                self.stat("variants", "valid")
            live = [x for x in variants if x["active"]]
            if not live:
                self.err("products", i, "variants", "No valid active variant (needs sku + price); product skipped.")
                continue
            slug = self.free_slug("products", slugify(r.get("slug") or r["title"]), r["legacy_id"])
            publish = self.publish and truthy(r.get("status") or "active") and v[2]
            prices = [x["price"] for x in live]
            status = "active" if publish else "draft"
            doc = {"title": r["title"][:140], "description": r.get("description", "")[:5000], "category_slug": c[1], "category_id": c[0],
                   "tags": [t.strip().lower()[:30] for t in (r.get("tags") or "").split("|") if t.strip()][:15], "sku": live[0]["sku"], "price_minor": live[0]["price"],
                   "currency": "USD", "option_names": list(live[0]["options"].keys()), "low_stock_threshold": 5, "vendor_id": v[0], "owner_user_id": v[1],
                   "slug": slug, "status": status, "ever_active": publish, "moderation_note": "",
                   "history": [{"status": status, "note": "Imported from legacy AfroVending site", "at": when(r.get("created_at")) or self.now, "by": None}],
                   "price_min_minor": min(prices), "price_max_minor": max(prices), "in_stock": any(x["stock"] > 0 for x in live),
                   "migration": self.mig(r["legacy_id"], legacy_status=r.get("status", ""))}
            if when(r.get("created_at")):
                doc["created_at"] = when(r["created_at"])
            pid = self.upsert("products", {"migration.legacy_id": r["legacy_id"], "migration.source": SOURCE}, doc, "products")
            self.products[r["legacy_id"]] = (pid, v[0], slug, min(prices), doc["in_stock"])
            self.stat("products", "valid")
            for n, x in enumerate(variants):
                vdoc = {"sku": x["sku"], "options": x["options"], "label": " / ".join(x["options"].values()) or "Default", "price_minor": x["price"],
                        "status": "active" if x["active"] else "inactive", "sort_order": n, "product_id": pid, "vendor_id": v[0], "migration": self.mig(x["legacy_id"])}
                vid = self.upsert("product_variants", {"migration.legacy_id": x["legacy_id"], "migration.source": SOURCE}, vdoc, "product_variants")
                self.variants[x["legacy_id"]] = (vid, x["sku"])
                inv = {"variant_id": vid, "product_id": pid, "vendor_id": v[0], "quantity_on_hand": x["stock"], "migration_opening_stock": x["stock"]}
                cur = self.db.inventory.find_one({"variant_id": vid})
                if not cur:
                    inv["quantity_reserved"] = 0
                self.upsert("inventory", {"variant_id": vid}, inv, "inventory")
            for n, url in enumerate([u.strip() for u in (r.get("image_urls") or "").split("|") if u.strip()][:8]):
                if not (url.startswith(("http://", "https://", "/"))):
                    self.err("products", i, "image_urls", f"Image '{url[:60]}' must be an http(s) URL or a /path inside the images folder.")
                    continue
                self.upsert("legacy_image_queue", {"product_id": pid, "url": url}, {"product_id": pid, "vendor_id": v[0], "owner_user_id": v[1], "url": url,
                                                                                   "sort": n, "status": (self.db.legacy_image_queue.find_one({"product_id": pid, "url": url}) or {}).get("status", "pending")}, "images")
            if r.get("slug"):
                self.redirect(f"/product/{r['slug']}", f"/products/{slug}")
        for pl, vrows in var_rows.items():
            for vi, _ in vrows:
                self.err("variants", vi, "product_legacy_id", f"Unknown or skipped product {pl}.")

    def addresses(self, src):
        for i, r in self.rows(src, "addresses"):
            rec = self.users.get(self.cust.get(r["customer_legacy_id"], ""))
            if not rec or "id" not in rec:
                self.err("addresses", i, "customer_legacy_id", "Unknown or skipped customer.")
                continue
            doc = {"user_id": rec["id"], "label": r.get("label", "")[:40], "full_name": r["full_name"][:100], "line1": r["line1"][:200], "line2": r.get("line2", "")[:200],
                   "city": r["city"][:100], "region": r.get("region", "")[:100], "postal_code": r.get("postal_code", "")[:20], "country": r["country"][:2].upper() if len(r["country"]) == 2 else r["country"][:60],
                   "phone": r.get("phone", "")[:30], "is_default": truthy(r.get("is_default")), "migration": self.mig(r["legacy_id"])}
            self.upsert("addresses", {"migration.legacy_id": r["legacy_id"], "migration.source": SOURCE}, doc, "addresses")
            self.stat("addresses", "valid")

    def orders(self, src):
        items = defaultdict(list)
        for i, r in self.rows(src, "order_items"):
            items[r["order_legacy_id"]].append((i, r))
        seen = {}
        for i, r in self.rows(src, "orders"):
            if r["order_number"] in seen:
                self.err("orders", i, "order_number", f"Duplicate order number (also row {seen[r['order_number']]}).")
                continue
            seen[r["order_number"]] = i
            try:
                amt = {k: minor(r[k]) if r.get(k) else 0 for k in ("subtotal", "shipping", "tax", "discount", "total")}
            except InvalidOperation:
                self.err("orders", i, "amounts", "Amounts must be decimal numbers >= 0.")
                continue
            lines = []
            for li, it in items.pop(r["legacy_id"], []):
                try:
                    q, up = int(it["quantity"]), minor(it["unit_price"])
                except (InvalidOperation, ValueError):
                    self.err("order_items", li, "quantity/unit_price", "Invalid quantity or price.")
                    continue
                p = self.products.get(it.get("product_legacy_id", ""))
                lines.append({"title": it["title"][:200], "sku": it.get("sku", ""), "quantity": q, "unit_price_minor": up, "line_total_minor": q * up,
                              "product_id": p[0] if p else None, "legacy_product_id": it.get("product_legacy_id", ""),
                              "variant_id": (self.variants.get(it.get("variant_legacy_id", "")) or (None,))[0]})
            if r.get("subtotal") and lines and sum(x["line_total_minor"] for x in lines) != amt["subtotal"]:
                self.rep["warnings"].append({"file": "orders", "row": i, "message": f"Items add up to {sum(x['line_total_minor'] for x in lines)} cents, subtotal says {amt['subtotal']}."})
            if r.get("subtotal") and amt["subtotal"] + amt["shipping"] + amt["tax"] - amt["discount"] != amt["total"]:
                self.rep["warnings"].append({"file": "orders", "row": i, "message": "subtotal + shipping + tax - discount does not equal total."})
            rec = self.users.get(self.cust.get(r["customer_legacy_id"], ""))
            if not rec:
                self.rep["warnings"].append({"file": "orders", "row": i, "message": f"Customer {r['customer_legacy_id']} not imported; order kept without an owner (guest/history only)."})
            v = self.vendors.get(r.get("vendor_legacy_id", ""))
            doc = {"order_number": r["order_number"], "user_id": (rec or {}).get("id"), "customer_legacy_id": r["customer_legacy_id"], "vendor_id": v[0] if v else None,
                   "status": (r.get("status") or "unknown").lower()[:40], "currency": (r.get("currency") or "USD").upper()[:3], **{f"{k}_minor": a for k, a in amt.items()},
                   "items": lines, "placed_at": when(r["placed_at"]), "migration": self.mig(r["legacy_id"]), "read_only": True}
            self.upsert("legacy_orders", {"migration.legacy_id": r["legacy_id"], "migration.source": SOURCE}, doc, "legacy_orders")
            self.stat("orders", "valid")
        for ol, rows in items.items():
            for li, _ in rows:
                self.err("order_items", li, "order_legacy_id", f"Unknown order {ol}.")

    def wishlists(self, src):
        for i, r in self.rows(src, "wishlists"):
            rec = self.users.get(self.cust.get(r["customer_legacy_id"], ""))
            p = self.products.get(r["product_legacy_id"])
            if not rec or "id" not in rec or not p:
                self.err("wishlists", i, "customer/product", "Unknown customer or product.")
                continue
            self.upsert("wishlists", {"user_id": rec["id"], "product_id": p[0]}, {"user_id": rec["id"], "product_id": p[0], "ref_price_minor": p[3], "ref_in_stock": p[4]}, "wishlists")
            self.stat("wishlists", "valid")

    def redirect(self, frm: str, to: str):
        frm = "/" + frm.strip("/")
        self.paths.add(frm)
        if frm != to:
            self.upsert("legacy_redirects", {"from_path": frm}, {"from_path": frm, "to_path": to, "status": 301, "source": SOURCE}, "redirects")

    def redirects(self, src):
        for frm, to in STATIC_REDIRECTS.items():
            self.redirect(frm, to)
        for i, r in self.rows(src, "redirects"):
            if not r["from_path"].startswith("/") or not r["to_path"].startswith("/"):
                self.err("redirects", i, "from_path/to_path", "Paths must start with '/' (same-site only).")
                continue
            self.redirect(r["from_path"], r["to_path"])
        urls = src / "legacy_urls.txt"
        if urls.exists():
            known = {d["from_path"] for d in self.db.legacy_redirects.find({}, {"from_path": 1})} | set(STATIC_REDIRECTS) | self.paths
            for line in urls.read_text().splitlines():
                path = "/" + re.sub(r"^https?://[^/]+", "", line.strip()).split("?")[0].strip("/")
                if path not in ("/", "/cart", "/login", "/register", "/forgot-password", "/shop") and path not in known and not path.startswith("/product-tag/"):
                    self.rep["unmapped_legacy_paths"].append(path)

    def verify(self):
        if self.dry:
            return
        m = {"migration.source": SOURCE}
        self.rep["verification"] = {
            "products_without_vendor": self.db.products.count_documents({**m, "vendor_id": {"$nin": [v[0] for v in self.vendors.values()]}}),
            "variants_without_inventory": sum(1 for vid, _ in self.variants.values() if not self.db.inventory.find_one({"variant_id": vid})),
            "products_owner_mismatch": sum(1 for pid, vid, *_ in self.products.values()
                                           if (self.db.products.find_one({"_id": pid}) or {}).get("owner_user_id") != (self.db.vendors.find_one({"_id": vid}) or {}).get("owner_user_id")),
            "price_mismatch": sum(1 for pid, _, _, low, _ in self.products.values() if (self.db.products.find_one({"_id": pid}) or {}).get("price_min_minor") != low),
            "images_pending": self.db.legacy_image_queue.count_documents({"status": "pending"}),
            "admin_roles_on_migrated_accounts": self.db.users.count_documents({**m, "roles": {"$regex": "admin$"}}),
            "migrated_accounts_with_password": self.db.users.count_documents({**m, "password_hash": {"$ne": None}, "migration.activation_required": True}),
        }

    def activation_readiness(self):
        recon = defaultdict(int)
        for x in self.rep["reconciliation"]:
            recon[x["type"]] += 1
        roles = [r["roles"] for r in self.users.values() if not r.get("blocked")]
        self.rep["activation_readiness"] = {"accounts": len(roles), "customers_only": sum(1 for r in roles if r == {"customer"}),
                                            "vendors": sum(1 for r in roles if "vendor" in r), "valid_emails": len(roles), "needs_review": dict(recon),
                                            "emails_sent": 0, "note": "No email is sent by the importer. Activation emails need owner approval (admin migration API)."}


def ensure_indexes(db):
    for coll, keys, kw in (("users", [("email", 1)], {"unique": True}), ("products", [("slug", 1)], {"unique": True}), ("product_variants", [("sku", 1)], {"unique": True}),
                           ("vendors", [("slug", 1)], {"unique": True}), ("inventory", [("variant_id", 1)], {"unique": True}),
                           ("legacy_orders", [("migration.legacy_id", 1)], {"unique": True}), ("legacy_redirects", [("from_path", 1)], {"unique": True}),
                           ("legacy_image_queue", [("product_id", 1), ("url", 1)], {"unique": True}), ("wishlists", [("user_id", 1), ("product_id", 1)], {"unique": True})):
        try:
            db[coll].create_index(keys, **kw)
        except Exception:  # existing index with another spec on the live schema
            pass


def fetch_images(db, images_dir: Path | None, limit: int = 500) -> dict:
    """Download/optimize/store queued product images (idempotent: done rows are skipped)."""
    import requests

    from afrovending.core.images import optimize
    from afrovending.core.storage import APP_PREFIX, put_object
    out = defaultdict(int)
    for q in db.legacy_image_queue.find({"status": {"$in": ["pending", "failed"]}, "attempts": {"$not": {"$gte": 3}}}).limit(limit):
        try:
            local = images_dir / q["url"].split("://", 1)[-1].split("/", 1)[-1] if images_dir else None
            if local and local.exists():
                data = local.read_bytes()
            elif q["url"].startswith("http"):
                resp = requests.get(q["url"], timeout=30)
                resp.raise_for_status()
                data = resp.content
            else:
                raise FileNotFoundError(q["url"])
            res = optimize(data)
            ids, now = {}, datetime.now(timezone.utc)
            for kind in ("main", "thumb"):
                stored = put_object(f"{APP_PREFIX}/public/product-media/{q['vendor_id']}/legacy-{q['_id']}-{kind}.webp", res[kind], "image/webp")
                ids[kind] = db.files.insert_one({"owner_user_id": q["owner_user_id"], "purpose": f"product_{kind}", "storage_path": stored["path"],
                                                 "original_filename": q["url"].rsplit("/", 1)[-1][:200], "content_type": "image/webp", "size": len(res[kind]),
                                                 "is_private": False, "is_deleted": False, "application_id": None, "created_at": now}).inserted_id
            p = db.products.find_one({"_id": q["product_id"]}, {"title": 1})
            db.product_images.insert_one({"product_id": q["product_id"], "vendor_id": q["vendor_id"], "file_id": ids["main"], "thumb_file_id": ids["thumb"],
                                          "alt": (p or {}).get("title", "")[:200], "sort_order": q["sort"], "width": res["width"], "height": res["height"],
                                          "original_size": len(data), "size": len(res["main"]), "created_at": now, "migration": {"source": SOURCE, "url": q["url"]}})
            db.legacy_image_queue.update_one({"_id": q["_id"]}, {"$set": {"status": "done", "done_at": now}})
            out["done"] += 1
        except Exception as e:
            db.legacy_image_queue.update_one({"_id": q["_id"]}, {"$set": {"status": "failed", "error": str(e)[:200]}, "$inc": {"attempts": 1}})
            out["failed"] += 1
    return dict(out)


def run(source: str, target_db: str, dry: bool = False, publish: bool = False, allow_live: bool = False, client=None) -> dict:
    if target_db == settings.db_name and not allow_live:
        raise SystemExit(f"Refusing to write into the app database '{target_db}' without --allow-live-db (requires owner approval).")
    db = (client or MongoClient(settings.mongo_url))[target_db]
    if not dry:
        ensure_indexes(db)
    r, src = Run(db, dry, publish), Path(source)
    r.categories(src)
    r.accounts(src)
    r.vendors_step()
    r.catalog(src)
    r.addresses(src)
    r.orders(src)
    r.wishlists(src)
    r.redirects(src)
    r.verify()
    r.activation_readiness()
    rep = r.rep
    rep.pop("_slugs", None)
    rep.pop("_skus", None)
    rep["entities"] = {k: dict(v) for k, v in rep["entities"].items()}
    rep["finished_at"] = datetime.now(timezone.utc).isoformat()
    if not dry:
        db.migration_runs.insert_one({**json.loads(json.dumps(rep, default=str)), "kind": "legacy_import"})
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target-db", default=f"{settings.db_name}_migration_staging")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish-active", action="store_true", help="Publish stores/products that were live on the old site (default: import as draft).")
    ap.add_argument("--allow-live-db", action="store_true")
    ap.add_argument("--fetch-images", action="store_true")
    ap.add_argument("--images-dir")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    rep = run(a.source, a.target_db, a.dry_run, a.publish_active, a.allow_live_db)
    if a.fetch_images and not a.dry_run:
        rep["images"] = fetch_images(MongoClient(settings.mongo_url)[a.target_db], Path(a.images_dir) if a.images_dir else None)
    out = Path(a.report or f"/app/migration/reports/{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{rep['mode']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps({"report": str(out), "entities": rep["entities"], "errors": len(rep["errors"]), "warnings": len(rep["warnings"]),
                      "reconciliation": len(rep["reconciliation"]), "verification": rep.get("verification")}, indent=1, default=str))
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
