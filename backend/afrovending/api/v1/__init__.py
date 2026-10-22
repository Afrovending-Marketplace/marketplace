from fastapi import APIRouter

from afrovending.api.v1 import (account, admin, admin_catalog, admin_commerce, admin_vendors, auth, cart, catalog, checkout, contact, cron, files,
                                product_import, products, system, vendors)

router = APIRouter(prefix="/api/v1")
for module in (system, auth, account, admin, admin_vendors, admin_catalog, contact, files, vendors, product_import, products, catalog, cron, cart, checkout, admin_commerce):
    router.include_router(module.router)
