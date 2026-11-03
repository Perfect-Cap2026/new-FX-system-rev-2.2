import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import RequestContextMiddleware, setup_logging
from app.db import init_db

settings = get_settings()
setup_logging()
log = logging.getLogger("fip")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info(f"FIP started (env={settings.env}, provider={settings.data_provider}, "
             f"llm={'on' if settings.anthropic_api_key else 'off'})")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
              docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "code": "internal"})


app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "provider": settings.data_provider}


@app.get("/metrics", tags=["ops"], include_in_schema=False)
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
