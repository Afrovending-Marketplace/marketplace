from fastapi import APIRouter

from afrovending.api.v1 import account, admin, admin_vendors, auth, contact, files, system, vendors

router = APIRouter(prefix="/api/v1")
for module in (system, auth, account, admin, admin_vendors, contact, files, vendors):
    router.include_router(module.router)
