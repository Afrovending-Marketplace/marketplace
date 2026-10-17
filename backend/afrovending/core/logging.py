import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
logger = logging.getLogger("afrovending.request")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def register_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method, request.url.path, response.status_code, duration_ms, request_id,
        )
        return response
