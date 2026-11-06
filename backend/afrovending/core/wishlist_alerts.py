"""Daily wishlist summary: price drops (>= threshold vs reference price) and back-in-stock items, opted-in shoppers only."""
from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from afrovending.core import email as mail
from afrovending.core.catalog import public_products, visible_vendor_ids
from afrovending.core.config import settings
from afrovending.core.db import db
from afrovending.core.marketing import flags, unsubscribe_token
from afrovending.core.models import utcnow
from afrovending.core.notify import notify

ET = ZoneInfo("America/New_York")


def snapshot(p: dict) -> tuple[int | None, bool]:
    """Lowest price among in-stock active variants (falls back to lowest overall); real selling price only."""
    vs = p.get("variants") or []
    live = [v["price_minor"] for v in vs if v.get("in_stock")]
    allp = [v["price_minor"] for v in vs]
    return (min(live) if live else (min(allp) if allp else None)), bool(live)


def drop_bps(ref: int, cur: int) -> Decimal:
    return (Decimal(ref - cur) * Decimal(10000) / Decimal(ref)).quantize(Decimal("0.01")) if ref else Decimal(0)


def _money(m: int) -> str:
    return f"${Decimal(m) / Decimal(100):.2f}"


def _email(name: str, items: list[dict], uid) -> tuple[str, str]:
    rows = ""
    for it in items:
        img = f'<img src="{escape(it["image"])}" width="64" height="64" alt="" style="border-radius:8px;object-fit:cover">' if it.get("image") else ""
        line = (f'{_money(it["old"])} → <b>{_money(it["new"])}</b> ({it["pct"]}% off)' if it["kind"] == "price_drop" else f'Back in stock · {_money(it["new"])}')
        rows += (f'<tr><td style="padding:6px">{img}</td><td style="padding:6px"><a href="{escape(it["url"])}">{escape(it["title"])}</a><br>{line}</td></tr>')
    unsub = f"{settings.frontend_url}/unsubscribe?token={unsubscribe_token(uid)}"
    body = (f"<p>Hi {escape(name)},</p><p>Good news about items on your AfroVending wishlist:</p><table>{rows}</table>"
            + mail._button(f"{settings.frontend_url}/account/wishlist", "View your wishlist")
            + f'<p style="font-size:12px;color:#777">You get this because you opted in to AfroVending marketing emails. <a href="{escape(unsub)}">Unsubscribe</a> '
              f'or turn off wishlist alerts in your account.</p>')
    return "Wishlist update: price drops and restocks", mail._layout("Your wishlist update", body)


async def run_wishlist_alerts(now: datetime | None = None) -> dict:
    cfg = (await flags())["wishlist_alerts"]
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    now = now or utcnow()
    day = now.astimezone(ET).date().isoformat()
    vids = await visible_vendor_ids()
    sent = 0
    for uid in await db.wishlists.distinct("user_id"):
        u = await db.users.find_one({"_id": uid})
        wants = (u or {}).get("wishlist_alerts") or {"price_drop": True, "back_in_stock": True}
        rows = await db.wishlists.find({"user_id": uid}).to_list(300)
        docs = {d["_id"]: d for d in await db.products.find({"_id": {"$in": [r["product_id"] for r in rows]}, "status": "active", "vendor_id": {"$in": vids}}).to_list(300)}
        pubs = {p["slug"]: p for p in await public_products(list(docs.values()))} if docs else {}
        items = []
        for r in rows:
            d = docs.get(r["product_id"])
            p = pubs.get(d["slug"]) if d else None
            if not p:
                continue
            cur, stock = snapshot(p)
            ref, ref_stock = r.get("ref_price_minor"), r.get("ref_in_stock")
            upd = {"ref_in_stock": stock}
            if ref is None or cur is None or cur > ref:
                upd["ref_price_minor"] = cur
            kind = None
            if stock and ref is not None and cur is not None and cur < ref and drop_bps(ref, cur) >= cfg["threshold_bps"] and wants.get("price_drop", True):
                kind, upd["ref_price_minor"] = "price_drop", cur
            elif stock and ref_stock is False and wants.get("back_in_stock", True):
                kind = "back_in_stock"
            await db.wishlists.update_one({"_id": r["_id"]}, {"$set": upd})
            if not kind or not u or not u.get("marketing_opt_in") or u.get("status") != "active":
                continue
            key = f"{kind}:{r['product_id']}:{ref}:{cur}:{day if kind == 'back_in_stock' else ''}"
            try:
                await db.wishlist_alerts.insert_one({"user_id": uid, "key": key, "product_id": r["product_id"], "kind": kind, "old_minor": ref, "new_minor": cur,
                                                     "pct": float(drop_bps(ref, cur) / 100) if kind == "price_drop" else None, "digest_day": day, "created_at": now})
            except DuplicateKeyError:
                continue
            img = (p.get("images") or [None])[0]
            img = f"{settings.frontend_url}{img}" if isinstance(img, str) and img.startswith("/") else img
            items.append({"kind": kind, "title": p["title"], "old": ref, "new": cur, "pct": f"{drop_bps(ref, cur) / 100:.0f}" if kind == "price_drop" else None,
                          "url": f"{settings.frontend_url}/products/{p['slug']}", "image": img if isinstance(img, str) else None})
        if not items:
            continue
        try:
            dig = (await db.wishlist_digests.insert_one({"user_id": uid, "day": day, "status": "sending", "items": len(items), "created_at": now})).inserted_id
        except DuplicateKeyError:
            continue
        items = items[:cfg["max_items"]]
        subject, html = _email(u.get("name") or "there", items, uid)
        ok = await mail.try_send(to=u["email"], subject=subject, html=html)
        await db.wishlist_digests.update_one({"_id": dig}, {"$set": {"status": "sent" if ok else "failed", "sent_at": utcnow()}})
        await notify(uid, "orders", "Wishlist update", f"{len(items)} item(s) on your wishlist dropped in price or came back in stock.", "/account/wishlist",
                     email=False)
        sent += ok
    return {"sent": sent, "day": day}
