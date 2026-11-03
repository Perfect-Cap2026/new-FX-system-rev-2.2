import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

REQUESTS = Counter("fip_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("fip_http_request_seconds", "HTTP latency", ["method", "route"])
PROVIDER_CALLS = Counter("fip_provider_calls_total", "Provider calls", ["provider", "kind", "outcome"])
CACHE = Counter("fip_cache_total", "Cache lookups", ["outcome"])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key in ("route", "status", "ms", "symbol", "provider"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            elapsed = time.perf_counter() - start
            REQUESTS.labels(request.method, path, str(status)).inc()
            LATENCY.labels(request.method, path).observe(elapsed)
            logging.getLogger("fip.http").info(
                f"{request.method} {path}",
                extra={"route": path, "status": status, "ms": round(elapsed * 1000, 1)},
            )
