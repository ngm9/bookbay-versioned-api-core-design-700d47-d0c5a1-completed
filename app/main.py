import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import application_metadata, configure_logging
from app.db import Base, engine
from app.routes_misc import router as misc_router
from app.routes_v1 import router as v1_router

configure_logging()
logger = logging.getLogger("bookbay.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true":
        Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


app = FastAPI(**application_metadata(), lifespan=lifespan)


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("request_failed request_id=%s method=%s path=%s elapsed_ms=%s", request_id, request.method, request.url.path, elapsed_ms)
        raise
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = str(elapsed_ms)
    logger.info("request_complete request_id=%s method=%s path=%s status=%s elapsed_ms=%s", request_id, request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.include_router(v1_router)
app.include_router(misc_router)
