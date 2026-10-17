from fastapi import APIRouter

from afrovending.api.v1 import account, admin, auth, contact, system

router = APIRouter(prefix="/api/v1")
for module in (system, auth, account, admin, contact):
    router.include_router(module.router)
