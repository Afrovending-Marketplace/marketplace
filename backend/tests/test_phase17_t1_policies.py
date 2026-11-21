# ruff: noqa: F811
# Iteration 31 (T1): Policy Management — public finalising pages, admin RBAC, draft→review→approve→publish→archive workflow,
# customer/vendor acceptance gates, registration acceptance, v2 material/non-material, production gate (unit), launch checklist items.
# Run serially: pytest tests/test_phase17_t1_policies.py -n 0
import asyncio
import os
import subprocess
import uuid
from datetime import date, timedelta

import httpx
import pytest
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tests.test_phase03_vendors import BASE, _ENV, admin_client, application, mongo  # noqa: E402
from tests.test_phase06_cart import PREFIX, account, live  # noqa: E402
from tests.test_phase07_payments import S, _p6_cleanup, buyer, cleanup7, draft, w  # noqa: E402,F401
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with  # noqa: E402
from tests.test_phase15_t1_refund_cancel import paid, refund  # noqa: E402

SLUGS = ["terms", "privacy", "vendor_agreement", "shipping", "returns", "cookies", "prohibited"]
PATHS = ["/terms", "/privacy", "/vendor-agreement", "/shipping-policy", "/returns-policy", "/cookie-policy", "/prohibited-products"]
LOOP = asyncio.new_event_loop()
P = {}
DUMP = "/tmp/polbak_t17"


def run(coro):
    return LOOP.run_until_complete(coro)


def setup_module():
    subprocess.run(["mongodump", f"--uri={_ENV['MONGO_URL']}", f"--db={_ENV['DB_NAME']}", "--collection=policy_versions", f"--out={DUMP}"], check=True,
                   capture_output=True)


def teardown_module():
    # restore policy data exactly as seeded (same _ids, bodies, history)
    mongo.policy_versions.delete_many({})
    subprocess.run(["mongorestore", f"--uri={_ENV['MONGO_URL']}", f"--nsInclude={_ENV['DB_NAME']}.policy_versions",
                    f"{DUMP}"], check=True, capture_output=True)
    mongo.policy_acceptances.delete_many({})
    mongo.launch_checklist.delete_many({"key": {"$regex": "^policy_"}})
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})
    mongo.notifications.delete_many({"user_id": {"$in": S.get("buyers", [])}})


@pytest.fixture(scope="module")
def sup():
    return admin_client()


@pytest.fixture(scope="module")
def content():
    return admin_with("content_admin")[0]


def vid(slug, status=None):
    q = {"slug": slug, **({"status": status} if status else {})}
    return str(mongo.policy_versions.find_one(q, sort=[("version", -1)])["_id"])


def approve_body(**kw):
    b = {"legal_review_confirmed": True, "reviewer_name": "TEST Counsel", "reviewer_firm": "TEST LLP", "review_date": date.today().isoformat(),
         "review_notes": "TEST", "classification": "material", "change_summary": "TEST first version", "effective_date": date.today().isoformat()}
    b.update(kw)
    return b


def approve_publish(sup, slug, classification="material"):
    v = vid(slug)
    r = sup.post(f"/admin/policies/versions/{v}/approve", json=approve_body(classification=classification))
    assert r.status_code == 200, r.text
    r = sup.post(f"/admin/policies/versions/{v}/publish", json={"confirm": "PUBLISH"})
    assert r.status_code == 200 and r.json()["status"] == "published", r.text
    return r.json()


def registered():
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    c = httpx.Client(base_url=BASE, timeout=60)
    email = f"delivered+p17v{uuid.uuid4().hex[:6]}@resend.dev"
    assert c.post("/auth/register", json={"name": f"{PREFIX}Pol", "email": email, "password": "TestPass12345", "accept_policies": True}).status_code == 201
    u = mongo.users.find_one({"email": email})
    mongo.users.update_one({"_id": u["_id"]}, {"$set": {"email_verified_at": u["created_at"], "status": "active"}})
    return c


# ---------- Public ----------
def test_01_public_finalising_no_body():
    r = httpx.get(f"{BASE}/policies", timeout=30)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [d["slug"] for d in data] == SLUGS and all(d["published"] is None for d in data)
    assert [d["path"] for d in data] == PATHS
    for s in SLUGS:
        d = httpx.get(f"{BASE}/policies/{s}", timeout=30).json()
        assert d["status"] == "finalising" and "body" not in d and "version" not in d, d
    assert httpx.get(f"{BASE}/policies/nope", timeout=30).status_code == 404


# ---------- Production gate unit ----------
def test_02_prod_gate_unit_nothing_published(monkeypatch):
    from afrovending.core import policies as pol
    from afrovending.core.errors import APIError
    run(pol.gate("registration"))  # preview: not gated
    monkeypatch.setattr(type(pol.settings), "is_production", property(lambda s: True))
    for g in ("registration", "vendor", "checkout", "personal_info"):
        with pytest.raises(APIError) as e:
            run(pol.gate(g))
        assert e.value.status_code == 503 and e.value.code == "policies_unavailable", vars(e.value)


def test_03_preview_register_nothing_published():
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    c = httpx.Client(base_url=BASE, timeout=60)
    email = f"delivered+p17a{uuid.uuid4().hex[:6]}@resend.dev"
    r = c.post("/auth/register", json={"name": f"{PREFIX}Pol", "email": email, "password": "TestPass12345", "accept_policies": True})
    assert r.status_code == 201, r.text
    u = mongo.users.find_one({"email": email})
    assert mongo.policy_acceptances.count_documents({"user_id": u["_id"]}) == 0  # nothing published → nothing to record


# ---------- Admin access ----------
def test_04_admin_access(sup, content):
    assert httpx.get(f"{BASE}/admin/policies", timeout=30).status_code == 401
    cust, _ = account()
    assert cust.get("/admin/policies").status_code == 403
    for role in ("support_admin", "finance_admin", "marketplace_admin"):
        c, _ = admin_with(role)
        r = c.get("/admin/policies")
        assert r.status_code == 403, (role, r.status_code, r.text)
        assert c.get(f"/admin/policies/versions/{vid('terms')}").status_code == 403
    r = content.get("/admin/policies")
    assert r.status_code == 200 and r.json()["is_super_admin"] is False and len(r.json()["data"]) == 7
    r = sup.get("/admin/policies")
    assert r.status_code == 200 and r.json()["is_super_admin"] is True
    row = r.json()["data"][0]
    assert row["open"]["status"] == "pending_review" and "body" not in row["open"] and row["published"] is None
    vs = content.get("/admin/policies/terms/versions").json()["data"]
    assert len(vs) == 1 and "body" not in vs[0]
    d = content.get(f"/admin/policies/versions/{vid('terms')}").json()
    assert len(d["body"]) > 200 and d["acceptance_count"] == 0
    assert cust.get("/admin/policies/terms/versions").status_code == 403


# ---------- world (built before anything is published) ----------
def test_05_world_before_publish(w, sup):
    P["buyer"] = buyer()
    P["pid_a"], P["vid_a"] = live(w["a"], w["adm"], f"TEST7 Pol {uuid.uuid4().hex[:4]}", 3000, 20)
    # a draft product for later submit
    sku = f"P{uuid.uuid4().hex[:7]}".upper()
    r = w["a"].post("/vendor/products", json={"title": "TEST7 Pol draft", "description": "Made by hand with care and tradition.", "category_slug": "fashion",
                                              "sku": sku, "price_minor": 1000, "variants": [{"sku": sku, "price_minor": 1000, "initial_stock": 3}]})
    assert r.status_code in (200, 201), r.text
    P["draft_pid"] = r.json()["product"]["id"]
    # a paid vendor order still pending acceptance
    P["paid"] = paid(w, 1)
    # applicant who submitted while nothing was published
    c2, _ = account()
    S.setdefault("buyers", [])
    assert c2.put("/vendor/application", json=application(f"test6-{uuid.uuid4().hex[:6]}")).status_code == 200
    lbl = c2.get("/vendor/policy").json()
    assert lbl["version"] == "vendor_agreement-unpublished+prohibited-unpublished" and lbl["status"] == "pending_legal_review"
    r = c2.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": lbl["version"]})
    assert r.status_code == 200, r.text
    P["app2"] = r.json()["application"]["id"]
    # preview checkout works with nothing published
    assert P["buyer"].get("/account/policy-status").json()["pending"] == []


# ---------- Launch checklist pre ----------
def test_06_launch_items_blocked(sup):
    r = sup.get("/admin/launch/checklist")
    assert r.status_code == 200, r.text
    pitems = [i for i in r.json()["items"] if i["key"].startswith("policy_")]
    assert [i["key"] for i in pitems] == [f"policy_{s}" for s in SLUGS], pitems
    assert all(i.get("mode") == "auto" for i in pitems), pitems[0]
    r = sup.post("/admin/launch/checklist/policy_terms/check")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "blocked" and r.json()["evidence"].startswith("Legal approval: no · Published: no"), r.text


# ---------- Workflow on terms ----------
def test_07_lifecycle_terms(sup, content):
    v = vid("terms")
    r = content.put(f"/admin/policies/versions/{v}", json={"body": "x" * 300})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_locked", r.text
    assert content.post(f"/admin/policies/versions/{v}/request-changes", json={"note": "Please fix it"}).status_code == 403
    assert sup.post(f"/admin/policies/versions/{v}/request-changes", json={"note": "abc"}).status_code == 422
    r = sup.post(f"/admin/policies/versions/{v}/request-changes", json={"note": "TEST please revise section 2"})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    body = mongo.policy_versions.find_one({"_id": ObjectId(v)})["body"]
    r = content.put(f"/admin/policies/versions/{v}", json={"body": body + "\n\nTEST edit", "change_summary": "TEST edit"})
    assert r.status_code == 200 and r.json()["body"].endswith("TEST edit")
    r = content.post(f"/admin/policies/versions/{v}/submit", json={"note": ""})
    assert r.status_code == 200 and r.json()["status"] == "pending_review"
    assert content.post(f"/admin/policies/versions/{v}/approve", json=approve_body()).status_code == 403
    r = sup.post(f"/admin/policies/versions/{v}/approve", json=approve_body(legal_review_confirmed=False))
    assert r.status_code == 422, r.text
    r = sup.post(f"/admin/policies/versions/{v}/approve", json=approve_body(review_date=(date.today() + timedelta(days=3)).isoformat()))
    assert r.status_code == 422, r.text
    r = sup.post(f"/admin/policies/versions/{v}/approve", json=approve_body())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved" and d["legal_review"]["confirmed"] is True and d["legal_review"]["reviewer_name"] == "TEST Counsel"
    assert d["requires_reacceptance"] is True and d["classification"] == "material"
    assert content.put(f"/admin/policies/versions/{v}", json={"body": "y" * 300}).status_code == 409
    # public still finalising
    assert httpx.get(f"{BASE}/policies/terms", timeout=30).json()["status"] == "finalising"
    r = sup.post("/admin/launch/checklist/policy_terms/check")
    assert r.json()["status"] == "blocked" and "Legal approval: yes" in r.json()["evidence"], r.text
    assert sup.post(f"/admin/policies/versions/{v}/publish", json={"confirm": "publish"}).status_code == 422
    assert content.post(f"/admin/policies/versions/{v}/publish", json={"confirm": "PUBLISH"}).status_code == 403
    r = sup.post(f"/admin/policies/versions/{v}/publish", json={"confirm": "PUBLISH"})
    assert r.status_code == 200 and r.json()["status"] == "published"
    pub = httpx.get(f"{BASE}/policies/terms", timeout=30).json()
    assert pub["status"] == "published" and pub["version"] == 1 and pub["effective_date"] == date.today().isoformat() and pub["body"].endswith("TEST edit")
    r = sup.post("/admin/launch/checklist/policy_terms/check")
    assert r.json()["status"] == "verified", r.text
    hist = [h["status"] for h in mongo.policy_versions.find_one({"_id": ObjectId(v)})["history"]]
    assert hist == ["draft", "pending_review", "draft", "pending_review", "approved", "published"], hist
    acts = {a["action"] for a in mongo.audit_logs.find({"entity_id": ObjectId(v)})}
    assert {"policy.draft", "policy.draft_edited", "policy.pending_review", "policy.approved", "policy.published"} <= acts, acts


# ---------- Customer acceptance ----------
def test_08_customer_acceptance(sup):
    approve_publish(sup, "privacy")
    b = P["buyer"]
    pend = b.get("/account/policy-status").json()["pending"]
    assert [p["slug"] for p in pend] == ["terms", "privacy"], pend
    assert b.post("/cart/items", json={"variant_id": P["vid_a"], "quantity": 1}).status_code == 200
    assert b.get("/cart").status_code == 200
    r = b.post("/checkout/start", headers={"Idempotency-Key": f"t17-{uuid.uuid4().hex}"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "policy_acceptance_required", r.text
    ids = [p["version_id"] for p in pend]
    assert b.post("/account/policy-acceptances", json={"version_ids": ids, "accept": False}).status_code == 422
    assert b.post("/account/policy-acceptances", json={"version_ids": ids[:1], "accept": True}).status_code == 409
    r = b.post("/account/policy-acceptances", json={"version_ids": ids, "accept": True}, headers={"user-agent": "TEST-UA"})
    assert r.status_code == 200 and r.json()["pending"] == [], r.text
    uid = S["buyers"][-1] if False else mongo.users.find_one({"_id": {"$in": S["buyers"]}, "email": {"$exists": True}}, sort=[("_id", -1)])
    rows = list(mongo.policy_acceptances.find({"version_id": {"$in": [ObjectId(i) for i in ids]}, "context": "reacceptance"}))
    assert len(rows) == 2
    for row in rows:
        assert {"user_id", "slug", "version", "version_id", "accepted_at", "ip", "user_agent", "context"} <= set(row)
        assert row["version"] == 1 and row["user_agent"] == "TEST-UA"
    assert uid
    r = b.post("/checkout/start", headers={"Idempotency-Key": f"t17-{uuid.uuid4().hex}"})
    assert r.status_code != 409 or r.json()["error"]["code"] not in ("policy_acceptance_required",), r.text
    print("checkout after accept:", r.status_code, r.text[:200])


def test_09_register_while_published():
    mongo.rate_limits.delete_many({"key": {"$regex": "^register:"}})
    email = f"delivered+p17b{uuid.uuid4().hex[:6]}@resend.dev"
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/auth/register", json={"name": f"{PREFIX}Pol", "email": email, "password": "TestPass12345"})
    assert r.status_code == 422, r.text
    r = c.post("/auth/register", json={"name": f"{PREFIX}Pol", "email": email, "password": "TestPass12345", "accept_policies": True})
    assert r.status_code == 201, r.text
    u = mongo.users.find_one({"email": email})
    rows = list(mongo.policy_acceptances.find({"user_id": u["_id"]}))
    assert sorted(r_["slug"] for r_ in rows) == ["privacy", "terms"] and all(r_["context"] == "registration" for r_ in rows)
    assert c.get("/account/policy-status").json()["pending"] == []


def test_10_prod_gate_unit_passes_after_publish(monkeypatch):
    from afrovending.core import policies as pol
    from afrovending.core.errors import APIError
    monkeypatch.setattr(type(pol.settings), "is_production", property(lambda s: True))
    run(pol.gate("registration"))
    run(pol.gate("personal_info"))
    with pytest.raises(APIError):
        run(pol.gate("checkout"))  # shipping/returns not published


# ---------- Vendor side ----------
def test_11_vendor_gates(w, sup):
    approve_publish(sup, "vendor_agreement")
    approve_publish(sup, "prohibited")
    a = w["a"]
    lbl = a.get("/vendor/policy").json()
    assert lbl["version"] == "vendor_agreement-v1+prohibited-v1" and lbl["status"] == "published", lbl
    pend = [p["slug"] for p in a.get("/account/policy-status").json()["pending"]]
    assert pend == ["terms", "privacy", "vendor_agreement", "prohibited"], pend
    r = a.post(f"/vendor/products/{P['draft_pid']}/submit")
    assert r.status_code == 409 and r.json()["error"]["code"] == "policy_acceptance_required", r.text
    _, o, vo, item, _ = P["paid"]
    r = a.post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "policy_acceptance_required", r.text
    # buyer (accepted) can't check out vendor A's items
    b = P["buyer"]
    r = b.post("/checkout/start", headers={"Idempotency-Key": f"t17-{uuid.uuid4().hex}"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "vendor_unavailable", r.text
    # existing order refunds still work
    r = refund(w, vo, item, 1)
    assert r.status_code in (200, 201), r.text
    # applicant who accepted "unpublished" can't be approved
    r = sup.post(f"/admin/vendor-applications/{P['app2']}/decision", json={"decision": "approve"})
    assert r.status_code == 409, r.text
    # new applicant must accept the current label
    c3 = registered()
    assert c3.put("/vendor/application", json=application(f"test6-{uuid.uuid4().hex[:6]}")).status_code == 200
    assert c3.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": "vendor_agreement-unpublished+prohibited-unpublished"}).status_code == 422
    assert c3.post("/vendor/application/submit", json={"accept_policy": False, "policy_version": lbl["version"]}).status_code == 422
    r = c3.post("/vendor/application/submit", json={"accept_policy": True, "policy_version": lbl["version"]})
    assert r.status_code == 200, r.text
    uid = mongo.vendor_applications.find_one({"_id": ObjectId(r.json()["application"]["id"])})["user_id"]
    rows = list(mongo.policy_acceptances.find({"user_id": uid, "context": "vendor_application"}))
    assert sorted(x["slug"] for x in rows) == ["prohibited", "vendor_agreement"]
    r = sup.post(f"/admin/vendor-applications/{r.json()['application']['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 200, r.text
    # vendor A accepts → can accept orders / submit products again
    ids = [p["version_id"] for p in a.get("/account/policy-status").json()["pending"]]
    assert a.post("/account/policy-acceptances", json={"version_ids": ids, "accept": True}).json()["pending"] == []
    r = a.post(f"/vendor/products/{P['draft_pid']}/submit")
    assert r.status_code != 409 or r.json()["error"]["code"] != "policy_acceptance_required", r.text
    r = a.post(f"/vendor/orders/{vo['_id']}/status", json={"to": "accepted"})
    assert r.status_code == 200 or r.json()["error"]["code"] != "policy_acceptance_required", r.text


def test_12_unit_assert_vendors_ready():
    from afrovending.core import policies as pol
    vids = S["vendor_ids"]
    run(pol.assert_vendors_ready([vids[0]]))  # vendor A accepted
    from afrovending.core.errors import APIError
    with pytest.raises(APIError) as e:
        run(pol.assert_vendors_ready([vids[1]]))  # vendor B didn't
    assert e.value.code == "vendor_unavailable"


# ---------- v2 non-material / material ----------
def test_13_v2_non_material_then_material(sup, content):
    b = P["buyer"]
    v1 = vid("terms", "published")
    r = content.post("/admin/policies/terms/versions", json={"change_summary": "TEST v2"})
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["body"] == mongo.policy_versions.find_one({"_id": ObjectId(v1)})["body"]
    assert content.post("/admin/policies/terms/versions", json={}).status_code == 409
    assert httpx.get(f"{BASE}/policies/terms", timeout=30).json()["version"] == 1
    assert content.put(f"/admin/policies/versions/{v2['id']}", json={"body": v2["body"] + "\nTEST v2 typo fix"}).status_code == 200
    assert content.post(f"/admin/policies/versions/{v2['id']}/submit", json={}).status_code == 200
    assert httpx.get(f"{BASE}/policies/terms", timeout=30).json()["version"] == 1
    d = approve_publish(sup, "terms", "non_material")
    assert d["version"] == 2 and d["requires_reacceptance"] is False
    assert mongo.policy_versions.find_one({"_id": ObjectId(v1)})["status"] == "archived"
    assert httpx.get(f"{BASE}/policies/terms", timeout=30).json()["version"] == 2
    # iteration 33: public change log lists every published version, newest first, no review/body data
    pub = httpx.get(f"{BASE}/policies/terms", timeout=30).json()
    ch = pub["changes"]
    assert [(c["version"], c["current"], c["material"]) for c in ch] == [(2, True, False), (1, False, True)], ch
    for c in ch:
        assert set(c) == {"version", "effective_date", "published_at", "change_summary", "material", "current"}, c
        assert c["published_at"] and c["effective_date"]
    assert ch[0]["change_summary"] == "TEST first version"
    assert "legal_review" not in str(pub) and "TEST Counsel" not in str(pub)
    for s_ in ("shipping", "returns", "cookies"):
        d = httpx.get(f"{BASE}/policies/{s_}", timeout=30).json()
        assert d["status"] == "finalising" and "changes" not in d and "body" not in d, d
    assert b.get("/account/policy-status").json()["pending"] == []
    r = content.post("/admin/policies/terms/versions", json={"change_summary": "TEST v3"})
    v3 = r.json()["id"]
    content.post(f"/admin/policies/versions/{v3}/submit", json={})
    approve_publish(sup, "terms", "material")
    pend = b.get("/account/policy-status").json()["pending"]
    assert [(p["slug"], p["version"]) for p in pend] == [("terms", 3)], pend
    ch = httpx.get(f"{BASE}/policies/terms", timeout=30).json()["changes"]
    assert [(c["version"], c["current"], c["material"]) for c in ch] == [(3, True, True), (2, False, False), (1, False, True)], ch


def test_14_archive_needs_reason(sup, content):
    v = vid("cookies")
    assert sup.post(f"/admin/policies/versions/{v}/archive", json={"reason": ""}).status_code == 422
    assert content.post(f"/admin/policies/versions/{v}/archive", json={"reason": "TEST obsolete"}).status_code == 403
    r = sup.post(f"/admin/policies/versions/{v}/archive", json={"reason": "TEST obsolete"})
    assert r.status_code == 200 and r.json()["status"] == "archived"
    assert mongo.audit_logs.find_one({"entity_id": ObjectId(v), "action": "policy.archived"})
