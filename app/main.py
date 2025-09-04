# app/main.py
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress

from fastapi import (
    FastAPI,
    Depends,
    Header,
    HTTPException,
    Request,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.models import EligibilityRequest, EligibilityResponse
from app.services import sba as sba_svc, naics as naics_svc
from app.services.evaluator import evaluate
from app.utils.ratelimit import SimpleRateLimiter
from app.db import (
    write_audit,
    create_job,
    add_job_items,
    get_job,
    list_job_items,
)
from app.services.size_import import import_size_csv
from app.worker import worker_loop


# ------------------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------------------

settings = get_settings()
rl = SimpleRateLimiter(settings.rate_limit_per_minute)
start_time = time.time()


async def require_key(x_api_key: str | None = Header(default=None)) -> bool:
    """Simple API key guard."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    return True


async def require_admin(x_admin_key: str | None = Header(default=None)) -> bool:
    """Admin-only routes (e.g., size standard import)."""
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="invalid admin key")
    return True


# Use lifespan instead of deprecated on_event startup/shutdown
async def _lifespan(app: FastAPI):
    # Start background worker
    worker_task = asyncio.create_task(worker_loop())
    try:
        yield
    finally:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(
    title="Eligibility & Go/No-Go API",
    version="1.2.0",
    lifespan=_lifespan,
)

# CORS (tighten origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------------------

@app.middleware("http")
async def apply_ratelimit(request: Request, call_next):
    """Simple token-bucket rate limiter; emits standard headers."""
    key = request.headers.get("x-api-key", request.client.host if request.client else "anonymous")
    allowed, remaining, reset = rl.allow(key)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded"},
            headers={
                "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset)),
            },
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset))
    return response


# ------------------------------------------------------------------------------
# Error Handlers (optional but production-friendly)
# ------------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    # Avoid leaking internals; log server-side in real deployments
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/v1/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - start_time),
        "mock_mode": settings.mock_mode,
    }


@app.get("/v1/naics/{code}/size-standard", response_model=dict, tags=["size"])
async def get_size_standard(code: str):
    if not naics_svc.valid_naics(code):
        raise HTTPException(400, detail="invalid NAICS")
    info = sba_svc.size_standard(code)
    if not info:
        raise HTTPException(404, detail="NAICS not found")
    return {
        "naics": code,
        "title": info.get("title") or naics_svc.title_for(code),
        "basis": info["basis"],
        "threshold": info["threshold"],
        "unit": info["unit"],
        "effective_fy": info.get("fy"),
    }


@app.post("/v1/eligibility/check", response_model=EligibilityResponse, tags=["eligibility"])
async def check_eligibility(
    payload: EligibilityRequest,
    ok: bool = Depends(require_key),  # defaults last
):
    """Synchronous eligibility check."""
    try:
        res = await evaluate(payload)
        # Best-effort audit; failures ignored
        try:
            write_audit(
                "/v1/eligibility/check",
                payload.model_dump(),
                json.loads(res.model_dump_json()),
            )
        except Exception:
            pass
        return res
    except ValueError as ve:
        raise HTTPException(400, detail=str(ve))


class BulkRequest(BaseModel):
    items: list[EligibilityRequest]
    webhook_url: str | None = None


@app.post("/v1/eligibility/bulk", tags=["eligibility"])
async def bulk_start(
    payload: BulkRequest,
    request: Request,                   # non-defaults first
    ok: bool = Depends(require_key),    # defaults after
):
    """Start a bulk job; results can be polled or sent via optional webhook."""
    if not payload.items:
        raise HTTPException(400, detail="no items")
    job_id = str(uuid.uuid4())
    requester = request.headers.get("x-api-key")
    create_job(job_id, len(payload.items), payload.webhook_url, requester)
    add_job_items(job_id, [i.model_dump() for i in payload.items])
    return {"job_id": job_id, "status": "queued", "total": len(payload.items)}


@app.get("/v1/jobs/{job_id}", tags=["jobs"])
async def job_status(job_id: str, ok: bool = Depends(require_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    return {k: job[k] for k in ("id", "status", "total", "done", "webhook_url", "created_ts")}


@app.get("/v1/jobs/{job_id}/results", tags=["jobs"])
async def job_results(job_id: str, ok: bool = Depends(require_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    items = list_job_items(job_id)
    return {
        "job": {
            "id": job["id"],
            "status": job["status"],
            "total": job["total"],
            "done": job["done"],
        },
        "results": [
            {
                "index": it["idx"],
                "status": it["status"],
                "payload": json.loads(it["payload"]),
                "result": (json.loads(it["result"]) if it["result"] else None),
            }
            for it in items
        ],
    }


@app.post("/v1/admin/size-standards/import", tags=["admin"])
async def import_size_standards(
    file: UploadFile = File(...),
    _admin_ok: bool = Depends(require_admin),
):
    """Admin: upsert SBA size standards via CSV (naics,title,basis,threshold,unit,effective_fy)."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            400,
            detail="upload a CSV with headers: naics,title,basis,threshold,unit,effective_fy",
        )
    content = await file.read()
    count = import_size_csv(content)
    return {"imported": count}
