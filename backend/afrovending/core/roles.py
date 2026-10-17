from enum import Enum


class Role(str, Enum):
    GUEST = "guest"
    CUSTOMER = "customer"
    VENDOR_APPLICANT = "vendor_applicant"
    VENDOR = "vendor"
    VENDOR_TEAM_MEMBER = "vendor_team_member"
    SUPPORT_ADMIN = "support_admin"
    MARKETPLACE_ADMIN = "marketplace_admin"
    SUPER_ADMIN = "super_admin"


ROLE_DESCRIPTIONS = {
    Role.GUEST: "Unauthenticated visitor. Read-only access to public storefront content.",
    Role.CUSTOMER: "Registered shopper. Owns their profile, carts, orders, returns, reviews and tickets.",
    Role.VENDOR_APPLICANT: "Customer who submitted a vendor application. Owns only their application.",
    Role.VENDOR: "Approved vendor owner. Owns their vendor, store, products, inventory and vendor orders.",
    Role.VENDOR_TEAM_MEMBER: "Future: delegated access to one vendor, scoped by vendor-granted permissions.",
    Role.SUPPORT_ADMIN: "Reads customer/order data to resolve tickets. Cannot change financial records.",
    Role.MARKETPLACE_ADMIN: "Approves vendors, moderates catalog and reviews, manages categories and orders.",
    Role.SUPER_ADMIN: "Full platform control incl. settings, admin accounts, payouts and refunds.",
}

ADMIN_ROLES = frozenset({Role.SUPPORT_ADMIN, Role.MARKETPLACE_ADMIN, Role.SUPER_ADMIN})
