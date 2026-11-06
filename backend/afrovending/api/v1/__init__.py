from fastapi import APIRouter

from afrovending.api.v1 import (account, admin, admin_catalog, admin_commerce, admin_ops, admin_payments, admin_team, admin_vendors, auth, cart, catalog,
                                checkout, contact, cron, files, fulfillment, marketing, messages, mfa, notifications, payments, product_import, products, reviews,
                                seo, statements,
                                support, system, vendor_dashboard, vendor_payments, vendors)

router = APIRouter(prefix="/api/v1")
for module in (system, auth, account, admin, admin_vendors, admin_catalog, contact, files, vendors, product_import, products, catalog, cron, cart, checkout, admin_commerce,
               payments, vendor_payments, admin_payments, fulfillment, statements, vendor_dashboard, mfa, admin_team, support, admin_ops, reviews, messages, notifications, marketing, seo):
    router.include_router(module.router)
