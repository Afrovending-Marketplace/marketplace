from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from afrovending.api.v1 import router as v1_router
from afrovending.core.config import APP_NAME, APP_VERSION, settings
from afrovending.core.db import client, db
from afrovending.core.errors import register_error_handlers
from afrovending.core.logging import configure_logging, register_request_logging
from afrovending.migrations.runner import run_migrations
from afrovending.migrations.seed import seed_admin
from fastapi import Request
from afrovending.core.errors import error_response

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_migrations(db)
    await seed_admin(db)
    yield
    client.close()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

register_error_handlers(app)


@app.middleware("http")
async def _origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if (request.method in ("POST", "PUT", "PATCH", "DELETE") and origin and request.url.path.startswith("/api/")
            and origin.rstrip("/") not in settings.cors_origins):
        return error_response(request, 403, "forbidden", "Request origin not allowed.")
    return await call_next(request)


register_request_logging(app)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.get("/api")
async def api_root():
    return {"service": APP_NAME, "versions": ["v1"], "current": "/api/v1"}


app.include_router(v1_router)
