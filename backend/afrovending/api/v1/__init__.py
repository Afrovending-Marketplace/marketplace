from fastapi import APIRouter

from afrovending.api.v1 import system

router = APIRouter(prefix="/api/v1")
router.include_router(system.router)
