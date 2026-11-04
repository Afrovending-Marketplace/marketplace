"""Granular admin permissions. Every admin endpoint depends on require_perm(); roles map to least-privilege permission sets."""
from fastapi import Depends, Request

from afrovending.core.errors import APIError
from afrovending.core.models import User
from afrovending.core.roles import ADMIN_ROLES

DASH, CUST_VIEW, CUST_MANAGE = "dashboard.view", "customers.view", "customers.manage"
VENDORS, CATALOG, COMMERCE = "vendors.manage", "catalog.moderate", "commerce.manage"
ORDERS_VIEW, ORDERS_MANAGE = "orders.view", "orders.manage"
FIN_VIEW, FIN_MANAGE, FIN_EXPORT = "finance.view", "finance.manage", "finance.export"
COMMISSION, SETTINGS, ADMINS, AUDIT = "commission.manage", "settings.manage", "admins.manage", "audit.view"
TICKETS, CONTENT, OPS_EXPORT, CUST_EXPORT = "tickets.manage", "content.manage", "ops.export", "customers.export"

ROLE_PERMS = {
    "support_admin": {DASH, CUST_VIEW, ORDERS_VIEW, TICKETS},
    "content_admin": {DASH, CONTENT},
    "finance_admin": {DASH, ORDERS_VIEW, FIN_VIEW, FIN_MANAGE, FIN_EXPORT, TICKETS},
    "marketplace_admin": {DASH, CUST_VIEW, CUST_MANAGE, VENDORS, CATALOG, COMMERCE, ORDERS_VIEW, ORDERS_MANAGE, FIN_VIEW, TICKETS, OPS_EXPORT},
}
ALL = set().union(*ROLE_PERMS.values()) | {COMMISSION, SETTINGS, ADMINS, AUDIT, CUST_EXPORT}
ROLE_PERMS["super_admin"] = ALL
ADMIN_ROLE_VALUES = {r.value for r in ADMIN_ROLES}


def perms_of(roles: list[str]) -> set[str]:
    return set().union(*(ROLE_PERMS.get(r, set()) for r in roles)) if roles else set()


def is_admin(user: User) -> bool:
    return bool(ADMIN_ROLE_VALUES & set(user.roles))


def require_perm(*needed: str):
    """Any one of `needed` suffices. Admin sessions must have passed MFA (authenticator code) first."""
    from afrovending.core.deps import get_current_user

    async def _dep(request: Request, user: User = Depends(get_current_user)) -> User:
        if not perms_of(user.roles) & set(needed):
            raise APIError(403, "forbidden", "You do not have permission to perform this action.")
        if not getattr(request.state, "mfa_verified", False):
            raise APIError(403, "mfa_required", "Confirm your authenticator code to use admin tools.")
        return user

    return _dep
