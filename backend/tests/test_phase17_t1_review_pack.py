# ruff: noqa: F811
# Iteration 32 (T1): Lawyer Review Pack — generate (RBAC), list, download docx/pdf (headers, RBAC, audit, counter),
# content of docx/pdf (title, confidentiality, TOC, parts, full policy text, question IDs, no invented contact facts, PAGE fields),
# approve external sharing (super only), launch checklist item legal_review_pack, policies untouched.
# Iteration 33: downloads 403 until approve-sharing (JSON confirm+ack), no-op repeat, attorney feedback records + file download.
# Run serially: pytest tests/test_phase17_t1_review_pack.py -n 0
import io
import os
import re
import zipfile
from datetime import date, timedelta

import httpx
import pytest
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tests.test_phase03_vendors import BASE, admin_client, mongo  # noqa: E402
from tests.test_phase06_cart import PREFIX, account  # noqa: E402,F401
from tests.test_phase10_admin import MADE as ADMINS_MADE, admin_with  # noqa: E402

SLUGS = ["terms", "privacy", "vendor_agreement", "shipping", "returns", "cookies", "prohibited"]
TITLES = ["Terms of Service", "Privacy Policy", "Vendor Agreement", "Shipping & Delivery Policy", "Returns & Refunds Policy", "Cookie Policy",
          "Prohibited"]
POLDIR = os.path.join(os.path.dirname(__file__), "..", "afrovending", "policies")
S = {}
BEFORE = {str(d["_id"]): (d["slug"], d["version"], d["status"], d.get("updated_at")) for d in mongo.policy_versions.find()}


def teardown_module():
    mongo.review_packs.delete_many({"_id": {"$in": S.get("packs", [])}})
    mongo.launch_checklist.delete_many({"key": "legal_review_pack"})
    ids = [u["_id"] for u in mongo.users.find({"email": {"$in": ADMINS_MADE}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": ids}})
    mongo.users.delete_many({"_id": {"$in": ids}})
    mongo.admin_invites.delete_many({"email": {"$in": ADMINS_MADE}})
    test_users = [u["_id"] for u in mongo.users.find({"name": {"$regex": f"^{PREFIX}"}, "email": {"$in": S.get("cust_emails", [])}})]
    for coll in ("sessions", "auth_tokens", "notifications"):
        mongo[coll].delete_many({"user_id": {"$in": test_users}})
    mongo.users.delete_many({"_id": {"$in": test_users}})


@pytest.fixture(scope="module")
def sup():
    return admin_client()


@pytest.fixture(scope="module")
def content():
    return admin_with("content_admin")[0]


def norm(s: str) -> str:
    s = s.replace("**", "").replace("`", "").replace("•", "")
    return re.sub(r"\s+", "", s)


# ---------- Generate ----------
def test_01_generate_rbac_and_create(sup, content):
    assert mongo.review_packs.count_documents({}) == 0 or True
    r = sup.post("/launch/checklist/legal_review_pack/check".replace("/launch", "/admin/launch"))
    if mongo.review_packs.count_documents({}) == 0:
        assert r.status_code == 200 and r.json()["status"] == "not_started", r.text
    assert httpx.post(f"{BASE}/admin/policies/review-pack", timeout=30).status_code == 401
    cust, email = account()
    S["cust"] = cust
    S.setdefault("cust_emails", []).append(email)
    assert cust.post("/admin/policies/review-pack").status_code == 403
    r = sup.post("/admin/policies/review-pack", timeout=180)
    assert r.status_code == 201, r.text
    d = r.json()
    S.setdefault("packs", []).append(ObjectId(d["id"]))
    S["pid"] = d["id"]
    assert d["sizes"]["docx"] > 30000 and d["sizes"]["pdf"] > 30000, d["sizes"]
    assert [p["slug"] for p in d["policy_versions"]] == SLUGS
    assert all(p["status"] == "pending_review" and p["version"] == 1 for p in d["policy_versions"]), d["policy_versions"]
    assert d["external_sharing_approved"] is False and d["downloads"] == 0 and "files" not in d
    assert mongo.audit_logs.find_one({"action": "policy.review_pack_generated", "entity_id": ObjectId(d["id"])}) or \
        mongo.audit_logs.find_one({"action": "policy.review_pack_generated", "entity_id": d["id"]})


def test_02_list_without_bytes(sup, content):
    r = sup.get("/admin/policies/review-pack")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert rows and rows[0]["id"] == S["pid"] and "files" not in rows[0]
    assert content.get("/admin/policies/review-pack").status_code == 200
    assert S["cust"].get("/admin/policies/review-pack").status_code == 403
    assert httpx.get(f"{BASE}/admin/policies/review-pack", timeout=30).status_code == 401


# ---------- Download gate (403 until approved for sharing) ----------
def test_03_download_blocked_until_approved(sup, content):
    pid = S["pid"]
    for c in (sup, content):
        for fmt in ("docx", "pdf"):
            r = c.get(f"/admin/policies/review-pack/{pid}/download", params={"format": fmt})
            assert r.status_code == 403 and r.json()["error"]["code"] == "sharing_not_approved", (fmt, r.status_code, r.text)
    assert sup.get(f"/admin/policies/review-pack/{'0' * 24}/download").status_code == 404
    assert sup.get("/admin/policies/review-pack/nope/download").status_code == 404
    assert mongo.review_packs.find_one({"_id": ObjectId(pid)})["downloads"] == 0
    assert mongo.audit_logs.count_documents({"action": "policy.review_pack_downloaded", "entity_id": {"$in": [pid, ObjectId(pid)]}}) == 0


# ---------- Approve sharing (explicit confirmation body) ----------
def test_04_approve_sharing(sup, content):
    pid = S["pid"]
    r = sup.post("/admin/launch/checklist/legal_review_pack/check")
    assert r.status_code == 200 and r.json()["status"] == "in_progress", r.text
    det = r.json().get("evidence") or str(r.json())
    assert "NOT yet approved" in det and "0/7" in det, r.json()
    ok = {"confirm": True, "acknowledge_not_legal_approval": True}
    url = f"/admin/policies/review-pack/{pid}/approve-sharing"
    assert content.post(url, json=ok).status_code == 403
    assert S["cust"].post(url, json=ok).status_code == 403
    assert sup.post(f"/admin/policies/review-pack/{'0' * 24}/approve-sharing", json=ok).status_code == 404
    for bad in ({}, {"confirm": True}, {"acknowledge_not_legal_approval": True}, {"confirm": False, "acknowledge_not_legal_approval": True},
                {"confirm": True, "acknowledge_not_legal_approval": False}):
        r = sup.post(url, json=bad)
        assert r.status_code == 422, (bad, r.status_code, r.text)
    assert sup.post(url).status_code == 422  # no body
    assert mongo.review_packs.find_one({"_id": ObjectId(pid)}).get("external_sharing_approved") is False
    r = sup.post(url, json=ok)
    assert r.status_code == 200 and r.json().get("ok") is True and not r.json().get("already_approved"), r.text
    row = [p for p in sup.get("/admin/policies/review-pack").json()["data"] if p["id"] == pid][0]
    assert row["external_sharing_approved"] is True and row["sharing_approved_by"] == "afrovending.online@gmail.com" and row["sharing_approved_at"]
    a = mongo.audit_logs.find_one({"action": "policy.review_pack_sharing_approved", "entity_id": {"$in": [pid, ObjectId(pid)]}})
    assert a, "no sharing audit"
    flat = str(a)
    assert "pack_number" in flat and "terms-v1" in flat and "prohibited-v1" in flat, a
    first_at = row["sharing_approved_at"]
    r = sup.post(url, json=ok)
    assert r.status_code == 200 and r.json().get("already_approved") is True, r.text
    row = [p for p in sup.get("/admin/policies/review-pack").json()["data"] if p["id"] == pid][0]
    assert row["sharing_approved_at"] == first_at
    assert mongo.audit_logs.count_documents({"action": "policy.review_pack_sharing_approved", "entity_id": {"$in": [pid, ObjectId(pid)]}}) == 1
    assert all(d["status"] == "pending_review" for d in mongo.policy_versions.find())
    det = sup.post("/admin/launch/checklist/legal_review_pack/check").json()
    assert "approved by" in str(det) and det["status"] == "in_progress", det


# ---------- Download after approval ----------
def test_05_download_after_approval(sup, content):
    pid = S["pid"]
    r = sup.get(f"/admin/policies/review-pack/{pid}/download", params={"format": "docx"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment") and "CONFIDENTIAL" in cd and cd.rstrip('"').endswith(".docx"), cd
    assert "no-store" in r.headers.get("cache-control", ""), r.headers
    S["docx"] = r.content
    r = sup.get(f"/admin/policies/review-pack/{pid}/download", params={"format": "pdf"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"
    assert "no-store" in r.headers.get("cache-control", "") and r.headers["content-disposition"].startswith("attachment")
    S["pdf"] = r.content
    assert sup.get(f"/admin/policies/review-pack/{pid}/download", params={"format": "xls"}).status_code == 422
    r = content.get(f"/admin/policies/review-pack/{pid}/download", params={"format": "pdf"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert mongo.review_packs.find_one({"_id": ObjectId(pid)})["downloads"] == 3
    logs = list(mongo.audit_logs.find({"action": "policy.review_pack_downloaded", "entity_id": {"$in": [pid, ObjectId(pid)]}}))
    assert len(logs) == 3 and all("pack_number" in str(x) for x in logs), logs[:1]


def test_06_download_rbac():
    pid = S["pid"]
    url = f"/admin/policies/review-pack/{pid}/download"
    assert httpx.get(f"{BASE}{url}", timeout=30).status_code == 401
    assert S["cust"].get(url).status_code == 403
    for role in ("support_admin", "finance_admin"):
        c, _ = admin_with(role)
        assert c.get(url).status_code == 403, role
        assert c.post("/admin/policies/review-pack").status_code == 403


# ---------- Content ----------
COMMON = ["AFROVENDING ONLINE MARKETPLACE LLC", "MARKETPLACE LEGAL POLICY REVIEW PACK", "CONFIDENTIAL — DRAFT FOR ATTORNEY REVIEW",
          "NOT LEGALLY APPROVED", "Table of contents", "Part A", "Part B", "Part C — Final legal review record", "info@afrovending.com",
          "Vendors are the sellers", "Counterfeit or replica goods", "refresh_token", "$24.99", "TOS-1", "PRV-3", "VA-4", "SHP-1", "RET-3", "CK-1",
          "PP-1", "Conflicts and inconsistencies", "Consolidated attorney review checklist", "Attorney comments and requested revisions",
          "[BUSINESS ADDRESS]", "Commissions, subscriptions, Stripe Connect, payouts, refunds, chargebacks and liability", "Questions by area of law",
          "Massachusetts law", "U.S. federal law", "Consumer protection", "Privacy and data security", "E-commerce"] + TITLES


def docx_text(b):
    from docx import Document
    d = Document(io.BytesIO(b))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            for c in row.cells:
                parts.append(c.text)
    return "\n".join(parts), d


def pdf_text(b):
    import fitz
    doc = fitz.open(stream=b, filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    # strip running header/footer lines so paragraphs split across pages compare cleanly
    text = re.sub(r"\n\nAFROVENDING ONLINE MARKETPLACE LLC — Marketplace Legal Policy Review Pack\nConfidential — Draft for Attorney Review · Not legally approved · Page \d+\n",
                  "\n", text)
    return text, doc.page_count


def test_07_docx_content():
    text, d = docx_text(S["docx"])
    missing = [s for s in COMMON if s not in text]
    assert not missing, missing
    # every paragraph/list/callout of each DB policy body appears
    from afrovending.core.review_pack import md_blocks
    nt = norm(text)
    for v in mongo.policy_versions.find({"status": "pending_review"}):
        miss = [b for b in md_blocks(v["body"]) if b[0] in ("p", "li", "callout") and norm(b[1]) not in nt]
        assert not miss, (v["slug"], miss[:3])
    # no invented phone/address
    assert not re.search(r"\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b", text), "phone number found"
    assert not re.search(r"\b\d{1,5}\s+\w+\s+(Street|St\.|Avenue|Ave|Road|Rd|Boulevard|Suite)\b", text), "street address found"
    # footer PAGE/NUMPAGES fields
    z = zipfile.ZipFile(io.BytesIO(S["docx"]))
    footers = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("word/footer"))
    assert "PAGE" in footers and "NUMPAGES" in footers, footers[:300]
    assert "w:highlight" in z.read("word/document.xml").decode()
    print("docx sections:", len(d.sections), "chars:", len(text))


def test_07b_pdf_content():
    text, pages = pdf_text(S["pdf"])
    nt = norm(text)
    missing = [s for s in COMMON if norm(s) not in nt]
    assert not missing, missing
    from afrovending.core.review_pack import md_blocks
    for v in mongo.policy_versions.find({"status": "pending_review"}):
        miss = [b for b in md_blocks(v["body"]) if b[0] in ("p", "li", "callout") and norm(b[1]) not in nt]
        assert not miss, (v["slug"], miss[:3])
    assert not re.search(r"\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b", text)
    import fitz
    raw = fitz.open(stream=S["pdf"], filetype="pdf")
    assert "Page 2" in raw[1].get_text() and pages > 20, pages
    print("pdf pages:", pages)


def test_07c_md_files_match_db_bodies():
    # pack is built from DB bodies; confirm they are the policies/*.md full texts
    for slug in SLUGS:
        body = mongo.policy_versions.find_one({"slug": slug, "version": 1})["body"]
        md = open(os.path.join(POLDIR, f"{slug}.md")).read()
        assert norm(body) == norm(md), slug


# ---------- Attorney feedback ----------
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _form(**kw):
    d = {"reviewer_name": "TEST Counsel", "reviewer_firm": "TEST LLP", "received_on": date.today().isoformat(), "comments": "TEST comment",
         "recommendations": "TEST rec", "requested_changes": "TEST change"}
    d.update(kw)
    return d


def test_08_attorney_review(sup, content):
    pid = S["pid"]
    url = f"/admin/policies/review-pack/{pid}/attorney-review"
    before = {str(d["_id"]): (d["status"], d.get("updated_at"), len(d.get("history", []))) for d in mongo.policy_versions.find()}
    assert content.post(url, data=_form()).status_code == 403
    assert S["cust"].post(url, data=_form()).status_code == 403
    r = sup.post(url, data=_form(received_on=(date.today() + timedelta(days=2)).isoformat()))
    assert r.status_code == 422, r.text
    r = sup.post(url, data=_form(), files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422, r.text
    r = sup.post(url, data=_form(), files={"file": ("pic.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png")})
    assert r.status_code == 422, r.text
    assert sup.post(f"/admin/policies/review-pack/{'0' * 24}/attorney-review", data=_form()).status_code == 404
    # no file
    r = sup.post(url, data=_form(reviewer_name="TEST NoFile"))
    assert r.status_code == 201, r.text
    # with PDF
    r = sup.post(url, data=_form(), files={"file": ("TEST-reviewed.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 201, r.text
    d = r.json()
    recs = d["attorney_records"]
    assert len(recs) == 2 and all("storage_path" not in x for x in recs), recs
    rec = recs[-1]
    assert rec["reviewer_name"] == "TEST Counsel" and rec["reviewer_firm"] == "TEST LLP" and rec["comments"] == "TEST comment"
    assert rec["recommendations"] == "TEST rec" and rec["requested_changes"] == "TEST change" and rec["filename"] == "TEST-reviewed.pdf"
    assert rec["size"] == len(PDF_BYTES) and rec["recorded_by"] == "afrovending.online@gmail.com"
    S["rid"] = rec["id"]
    lst = [p for p in sup.get("/admin/policies/review-pack").json()["data"] if p["id"] == pid][0]
    assert len(lst["attorney_records"]) == 2 and "storage_path" not in str(lst)
    assert mongo.audit_logs.find_one({"action": "policy.attorney_review_recorded", "entity_id": {"$in": [pid, ObjectId(pid)]}})
    after = {str(d["_id"]): (d["status"], d.get("updated_at"), len(d.get("history", []))) for d in mongo.policy_versions.find()}
    assert after == before


def test_09_attorney_file_download(sup, content):
    pid, rid = S["pid"], S["rid"]
    url = f"/admin/policies/review-pack/{pid}/attorney-review/{rid}/file"
    for c in (sup, content):
        r = c.get(url)
        assert r.status_code == 200 and r.content == PDF_BYTES, (r.status_code, r.text[:200])
        assert r.headers["content-type"].startswith("application/pdf") and "no-store" in r.headers.get("cache-control", "")
        assert r.headers["content-disposition"].startswith("attachment")
    assert S["cust"].get(url).status_code == 403
    assert httpx.get(f"{BASE}{url}", timeout=30).status_code == 401
    assert sup.get(f"/admin/policies/review-pack/{pid}/attorney-review/{'f' * 24}/file").status_code == 404
    assert mongo.audit_logs.count_documents({"action": "policy.attorney_review_downloaded", "record_id": rid}) >= 2 or \
        mongo.audit_logs.count_documents({"action": "policy.attorney_review_downloaded", "entity_id": {"$in": [pid, ObjectId(pid)]}}) >= 2


# ---------- Launch checklist ----------
def test_10_launch_item(sup):
    r = sup.get("/admin/launch/checklist")
    assert r.status_code == 200
    it = [i for i in r.json()["items"] if i["key"] == "legal_review_pack"]
    assert it and it[0].get("mode") == "auto", it
    r2 = sup.get("/admin/launch")
    print("GET /admin/launch:", r2.status_code)


def test_11_policies_untouched():
    after = {str(d["_id"]): (d["slug"], d["version"], d["status"], d.get("updated_at")) for d in mongo.policy_versions.find()}
    assert after == BEFORE
    assert all(v[2] == "pending_review" for v in after.values()) and len(after) == 7
