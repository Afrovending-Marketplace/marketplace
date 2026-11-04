from enum import Enum


class Role(str, Enum):
    GUEST = "guest"
    CUSTOMER = "customer"
    VENDOR_APPLICANT = "vendor_applicant"
    VENDOR = "vendor"
    VENDOR_TEAM_MEMBER = "vendor_team_member"
    SUPPORT_ADMIN = "support_admin"
    CONTENT_ADMIN = "content_admin"
    FINANCE_ADMIN = "finance_admin"
    MARKETPLACE_ADMIN = "marketplace_admin"
    SUPER_ADMIN = "super_admin"


ROLE_DESCRIPTIONS = {
    Role.GUEST: "Unauthenticated visitor. Read-only access to public storefront content.",
    Role.CUSTOMER: "Registered shopper. Owns their profile, carts, orders, returns, reviews and tickets.",
    Role.VENDOR_APPLICANT: "Customer who submitted a vendor application. Owns only their application.",
    Role.VENDOR: "Approved vendor owner. Owns their vendor, store, products, inventory and vendor orders.",
    Role.VENDOR_TEAM_MEMBER: "Future: delegated access to one vendor, scoped by vendor-granted permissions.",
    Role.SUPPORT_ADMIN: "Support tickets, customer/order lookups, reviews refund/cancellation requests. No refunds, transfers or commission changes.",
    Role.CONTENT_ADMIN: "Homepage sections, banners and featured products/vendors only. No financial or customer data.",
    Role.FINANCE_ADMIN: "Payments, refunds, disputes, holds, payouts, ledgers and financial exports. Cannot change commission, pricing or roles.",
    Role.MARKETPLACE_ADMIN: "Approves/suspends vendors, moderates catalog and categories, oversees orders and disputes. No commission or role changes.",
    Role.SUPER_ADMIN: "Full platform control incl. admin accounts, commission and plans, settings, audit logs and exports.",
}

ADMIN_ROLES = frozenset({Role.SUPPORT_ADMIN, Role.CONTENT_ADMIN, Role.FINANCE_ADMIN, Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN})
