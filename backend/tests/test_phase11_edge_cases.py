# Phase 11 edge cases: invalid ids (no 500s), auth required, validation on reviews/messages/notifications/moderation endpoints
import httpx
import pytest

from tests.test_phase03_vendors import BASE, cleanup, verified_client  # noqa: F401

BAD = "notanid"
VALID_MISSING = "0123456789abcdef01234567"


@pytest.fixture(scope="module")
def c():
    return verified_client()


def test_unauthenticated_endpoints_401():
    anon = httpx.Client(base_url=BASE, timeout=30)
    for method, path in (("get", "/notifications"), ("get", "/notifications/unread-count"), ("get", "/reviews/mine"),
                         ("put", f"/reviews/items/{VALID_MISSING}"), ("get", "/admin/reviews"), ("get", "/admin/messages/flagged")):
        r = getattr(anon, method)(path, **({"json": {"rating": 5}} if method == "put" else {}))
        assert r.status_code == 401, (path, r.status_code)


def test_public_reviews_unknown_slug_empty():
    anon = httpx.Client(base_url=BASE, timeout=30)
    r = anon.get("/products/does-not-exist-zzz/reviews")
    assert r.status_code == 200 and r.json()["summary"]["total"] == 0 and r.json()["reviews"] == []
    s = anon.get("/stores/does-not-exist-zzz/seller-ratings")
    assert s.status_code == 200 and s.json()["summary"]["average"] is None


def test_invalid_ids_return_404_not_500(c):
    for method, path, body in (("put", f"/reviews/items/{BAD}", {"rating": 5}), ("put", f"/reviews/items/{VALID_MISSING}", {"rating": 5}),
                               ("put", f"/reviews/sellers/{BAD}", {"rating": 5}), ("get", f"/orders/{BAD}/review-status", None),
                               ("post", f"/notifications/{BAD}/read", None), ("post", f"/notifications/{VALID_MISSING}/read", None),
                               ("get", f"/orders/{BAD}/vendor-orders/{BAD}/messages", None),
                               ("post", f"/orders/{VALID_MISSING}/vendor-orders/{VALID_MISSING}/messages", {"body": "hello"}),
                               ("post", f"/reviews/product/{BAD}/report", {"reason": "spam"})):
        r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (path, r.status_code, r.text[:200])


def test_validation_422(c):
    assert c.put(f"/reviews/items/{VALID_MISSING}", json={"rating": 0}).status_code == 422
    assert c.put(f"/reviews/items/{VALID_MISSING}", json={"rating": 6}).status_code == 422
    assert c.post(f"/reviews/product/{VALID_MISSING}/report", json={"reason": "because"}).status_code == 422
    assert c.put("/notifications/preferences", json={"orders": {"email": True}}).status_code == 422
    assert c.put(f"/vendor/reviews/badkind/{VALID_MISSING}/response", json={"body": "hi there"}).status_code == 422


def test_customer_forbidden_admin_and_vendor_routes(c):
    assert c.get("/admin/reviews").status_code in (401, 403)
    assert c.get("/admin/moderation/rules").status_code in (401, 403)
    assert c.get("/admin/messages/flagged").status_code in (401, 403)
    r = c.get("/vendor/reviews")
    assert r.status_code in (403, 404), r.status_code


def test_notifications_empty_new_user(c):
    d = c.get("/notifications").json()
    assert isinstance(d["data"], list) and d["unread"] == c.get("/notifications/unread-count").json()["unread"]
    p = c.get("/notifications/preferences").json()
    assert set(p["preferences"]) == {"orders", "messages", "reviews", "support", "vendor"}
    assert all(v == {"email": True, "in_app": True} for v in p["preferences"].values())
