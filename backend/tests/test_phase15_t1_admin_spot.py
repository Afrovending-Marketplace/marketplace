# Iteration 27 admin permission spot checks per scoped role (reuses phase10 admin_with + teardown)
import pytest

from tests.test_phase10_admin import MADE, admin_with, teardown_module  # noqa: F401

# endpoint -> roles that must be allowed (super_admin always allowed); everyone else must get 403
MATRIX = {
    ("GET", "/admin/payments/ledger"): {"finance_admin", "marketplace_admin"},  # marketplace has finance.view (read-only) by design
    ("GET", "/admin/payments/refunds"): {"finance_admin", "marketplace_admin"},
    ("GET", "/admin/audit-logs"): set(),
    ("POST", "/admin/team/invites"): set(),
    ("GET", "/admin/vendor-applications"): {"marketplace_admin"},
    ("GET", "/admin/privacy-requests"): {"marketplace_admin"},
}


@pytest.fixture(scope="module")
def admins():
    return {r: admin_with(r)[0] for r in ("marketplace_admin", "finance_admin", "support_admin", "content_admin")}


def test_scoped_matrix(admins):
    bad = []
    for (m, path), allowed in MATRIX.items():
        for role, c in admins.items():
            body = {"email": "nobody@example.com", "role": "support_admin"} if m == "POST" else None
            code = c.request(m, path, json=body).status_code
            ok = (code != 403) if role in allowed else (code == 403)
            print(role, m, path, code)
            if not ok:
                bad.append((role, m, path, code))
    assert not bad, bad


def test_support_and_content_cannot_refund_or_moderate(admins):
    fake = "0" * 24
    for role in ("support_admin", "content_admin"):
        c = admins[role]
        assert c.post(f"/admin/payments/vendor-orders/{fake}/refunds", json={"lines": [], "reason": "x"},
                      headers={"Idempotency-Key": "t1-xxxxxxxxxx"}).status_code == 403
        assert c.post(f"/admin/products/{fake}/moderate", json={"decision": "approve"}).status_code == 403
        assert c.put("/admin/payments/config", json={}).status_code == 403


def test_marketplace_cannot_refund(admins):
    r = admins["marketplace_admin"].post(f"/admin/payments/vendor-orders/{'0' * 24}/refunds", json={"lines": [], "reason": "x"},
                                         headers={"Idempotency-Key": "t1-xxxxxxxxxx"})
    assert r.status_code == 403
