import csv
import io
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from afrovending.api.v1.products import ProductCreateIn, VariantIn, check_variants, create_product, writable_vendor
from afrovending.core.audit import audit
from afrovending.core.catalog import oid, slugify
from afrovending.core.db import db
from afrovending.core.deps import get_current_user
from afrovending.core.errors import APIError
from afrovending.core.models import User, utcnow

router = APIRouter(prefix="/vendor/products/import", tags=["vendor-import"])
COLUMNS = ["handle", "title", "description", "category", "tags", "currency", "product_sku", "low_stock_threshold",
           "option1_name", "option1_value", "option2_name", "option2_value", "option3_name", "option3_value", "sku", "price", "stock"]
REQUIRED = {"handle", "title", "category", "sku", "price"}
MAX_BYTES, MAX_ROWS, MAX_PRODUCTS = 2_000_000, 1000, 200
TEMPLATE_ROWS = [
    ["kente-wrap-dress", "Kente Wrap Dress", "Hand-finished wrap dress in woven kente cloth.", "fashion", "kente;dress", "USD", "KWD", "3",
     "Size", "S", "", "", "", "", "KWD-S", "89.00", "10"],
    ["kente-wrap-dress", "", "", "", "", "", "", "", "Size", "M", "", "", "", "", "KWD-M", "89.00", "8"],
    ["suya-spice-blend", "Suya Spice Blend", "Smoky peanut and chilli suya seasoning.", "food-groceries", "spice", "USD", "SUYA", "5",
     "", "", "", "", "", "", "SUYA-100", "12.00", "40"],
]


def _price(raw: str) -> int:
    value = Decimal(raw.strip().replace(",", "").lstrip("$"))
    if value <= 0 or value != value.quantize(Decimal("0.01")):
        raise InvalidOperation
    return int(value * 100)


def _err(errors: list, row: int, field: str, message: str) -> None:
    errors.append({"row": row, "field": field, "message": message})


def _pydantic(errors: list, row: int, exc: ValidationError) -> None:
    for e in exc.errors():
        _err(errors, row, ".".join(str(p) for p in e["loc"]) or "row", e["msg"].replace("Value error, ", ""))


async def parse(text: str, vendor: dict) -> tuple[list, list]:
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    if missing := REQUIRED - headers:
        raise APIError(422, "validation_error", f"Missing columns: {', '.join(sorted(missing))}. Download the template to see the format.")
    groups: dict[str, list] = {}
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_ROWS:
            raise APIError(422, "validation_error", f"Import up to {MAX_ROWS} rows at a time.")
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if any(row.values()):
            groups.setdefault(slugify(row.get("handle", "")) or f"row-{n}", []).append((n, row))
    if not groups:
        raise APIError(422, "validation_error", "The file has no product rows.")
    if len(groups) > MAX_PRODUCTS:
        raise APIError(422, "validation_error", f"Import up to {MAX_PRODUCTS} products at a time.")
    cats = {c["slug"]: c["slug"] async for c in db.categories.find({"status": "active"})}
    cats.update({c["name"].lower(): c["slug"] async for c in db.categories.find({"status": "active"})})
    all_skus = [r.get("sku", "").upper() for rows in groups.values() for _, r in rows]
    taken = {v["sku"] async for v in db.product_variants.find({"sku": {"$in": all_skus}}, {"sku": 1})}
    vendor_skus = {p["sku"] async for p in db.products.find({"vendor_id": vendor["_id"]}, {"sku": 1})}
    seen, products, errors = set(), [], []
    for handle, rows in groups.items():
        first_n, first = rows[0]
        before = len(errors)
        if not first.get("handle"):
            _err(errors, first_n, "handle", "Handle is required.")
        names = [first.get(f"option{i}_name", "") for i in (1, 2, 3) if first.get(f"option{i}_name")]
        variants = []
        for n, r in rows:
            sku = r.get("sku", "").upper()
            if sku in seen:
                _err(errors, n, "sku", f"SKU {sku} appears more than once in the file.")
            elif sku in taken:
                _err(errors, n, "sku", f"SKU {sku} is already in use.")
            seen.add(sku)
            price = None
            try:
                price = _price(r.get("price", ""))
            except (InvalidOperation, ValueError):
                _err(errors, n, "price", "Price must be a positive amount like 12.50.")
            stock = r.get("stock") or "0"
            if not stock.isdigit():
                _err(errors, n, "stock", "Stock must be a whole number of 0 or more.")
            if price is None or not stock.isdigit():
                continue
            try:
                variants.append(VariantIn(sku=sku, price_minor=price, initial_stock=int(stock),
                                          options={nm: r.get(f"option{i}_value", "") for i, nm in enumerate(names, start=1)}))
            except ValidationError as exc:
                _pydantic(errors, n, exc)
        category = cats.get(first.get("category", "").lower())
        if not category:
            _err(errors, first_n, "category", f"Unknown category '{first.get('category', '')}'.")
        product_sku = (first.get("product_sku") or handle).upper()[:64]
        if product_sku in vendor_skus:
            _err(errors, first_n, "product_sku", f"You already have a product with SKU {product_sku}.")
        payload = None
        try:
            payload = ProductCreateIn(title=first.get("title", ""), description=first.get("description", ""), category_slug=category or "unknown",
                                      tags=[t for t in first.get("tags", "").replace(",", ";").split(";")], sku=product_sku,
                                      price_minor=variants[0].price_minor if variants else 1, currency=first.get("currency") or "USD",
                                      option_names=names, low_stock_threshold=int(first.get("low_stock_threshold") or 5), variants=variants)
            check_variants(payload.option_names, payload.variants)
        except ValidationError as exc:
            _pydantic(errors, first_n, exc)
        except ValueError:
            _err(errors, first_n, "low_stock_threshold", "Low-stock threshold must be a whole number.")
        except APIError as exc:
            _err(errors, first_n, "variants", exc.message)
        ok = len(errors) == before and payload is not None
        products.append({"handle": handle, "title": first.get("title", ""), "rows": [n for n, _ in rows], "variant_count": len(rows),
                         "valid": ok, "payload": payload.model_dump() if ok else None})
    return products, errors


@router.get("/template")
async def template(_: User = Depends(get_current_user)):
    buf = io.StringIO()
    csv.writer(buf).writerows([COLUMNS, *TEMPLATE_ROWS])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="afrovending-products-template.csv"'})


@router.post("/preview")
async def preview(request: Request, file: UploadFile = File(...), user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    data = await file.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise APIError(422, "validation_error", "CSV must be under 2 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise APIError(422, "validation_error", "Save the file as UTF-8 CSV and try again.")
    products, errors = await parse(text, vendor)
    now = utcnow()
    batch_id = (await db.product_imports.insert_one({"vendor_id": vendor["_id"], "user_id": ObjectId(user.id), "status": "previewed",
                                                     "filename": (file.filename or "import.csv")[:200], "products": products, "errors": errors,
                                                     "created_at": now, "expires_at": now + timedelta(hours=24)})).inserted_id
    await audit("product.import_previewed", "product_imports", request=request, actor=user, entity_id=str(batch_id), rows=sum(p["variant_count"] for p in products))
    return {"batch_id": str(batch_id), "products": [{k: v for k, v in p.items() if k != "payload"} for p in products], "errors": errors,
            "valid_count": sum(p["valid"] for p in products), "invalid_count": sum(not p["valid"] for p in products)}


@router.post("/{batch_id}/commit")
async def commit(batch_id: str, request: Request, user: User = Depends(get_current_user)):
    vendor = await writable_vendor(user)
    batch = await db.product_imports.find_one_and_update({"_id": oid(batch_id), "vendor_id": vendor["_id"], "status": "previewed"}, {"$set": {"status": "committing"}})
    if not batch:
        raise APIError(404, "not_found", "Import preview not found or already used. Upload the file again.")
    created, failed = [], []
    for p in batch["products"]:
        if not p["valid"]:
            continue
        try:
            doc = await create_product(vendor, user.id, ProductCreateIn(**p["payload"]), reason="import")
            created.append({"id": str(doc["_id"]), "title": doc["title"]})
        except APIError as exc:
            failed.append({"handle": p["handle"], "message": exc.message})
    await db.product_imports.update_one({"_id": batch["_id"]}, {"$set": {"status": "committed", "committed_at": utcnow(), "created_count": len(created)}})
    await audit("product.import_committed", "product_imports", request=request, actor=user, entity_id=batch_id, created=len(created), failed=len(failed))
    return {"created": created, "failed": failed, "skipped_invalid": sum(not p["valid"] for p in batch["products"])}
