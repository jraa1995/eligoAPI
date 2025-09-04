import time, uuid, json, asyncio
from fastapi import FastAPI, Depends, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.config import get_settings
from app.models import EligibilityRequest, EligibilityResponse
from app.services import sba as sba_svc, naics as naics_svc
from app.services.evaluator import evaluate
from app.utils.ratelimit import SimpleRateLimiter
from app.db import write_audit, create_job, add_job_items, get_job, list_job_items
from app.services.size_import import import_size_csv
from app.worker import worker_loop

app = FastAPI(title="Eligibility & Go/No-Go API", version="1.1.0")
settings = get_settings()
rl = SimpleRateLimiter(settings.rate_limit_per_minute)
start_time = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def require_key(x_api_key: str = Header(None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    return True

async def require_admin(x_admin_key: str = Header(None)):
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="invalid admin key")
    return True

@app.on_event("startup")
async def startup():
    asyncio.create_task(worker_loop())

@app.middleware("http")
async def apply_ratelimit(request: Request, call_next):
    key = request.headers.get("x-api-key", request.client.host)
    allowed, remaining, reset = rl.allow(key)
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"}, headers={
            "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(reset))
        })
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset))
    return response

@app.get("/v1/health")
async def health():
    return {"status": "ok", "uptime_seconds": int(time.time() - start_time), "mock_mode": settings.mock_mode}

@app.get("/v1/naics/{code}/size-standard", response_model=dict)
async def get_size_standard(code: str):
    if not naics_svc.valid_naics(code):
        raise HTTPException(400, detail="invalid NAICS")
    info = sba_svc.size_standard(code)
    if not info:
        raise HTTPException(404, detail="NAICS not found")
    return {"naics": code, "title": info.get("title") or naics_svc.title_for(code), "basis": info["basis"], "threshold": info["threshold"], "unit": info["unit"], "effective_fy": info.get("fy")}

@app.post("/v1/eligibility/check", response_model=EligibilityResponse)
async def check_eligibility(payload: EligibilityRequest, ok=Depends(require_key), request: Request | None = None):
    try:
        res = await evaluate(payload)
        try:
            write_audit("/v1/eligibility/check", payload.model_dump(), json.loads(res.model_dump_json()))
        except Exception:
            pass
        return res
    except ValueError as ve:
        raise HTTPException(400, detail=str(ve))

# --- Bulk ---
class BulkItem(EligibilityRequest):
    pass

class BulkRequest(BaseModel):
    items: list[BulkItem]
    webhook_url: str | None = None

@app.post("/v1/eligibility/bulk")
async def bulk_start(payload: BulkRequest, ok=Depends(require_key), request: Request | None = None):
    if not payload.items:
        raise HTTPException(400, detail="no items")
    job_id = str(uuid.uuid4())
    requester = request.headers.get("x-api-key") if request else None
    create_job(job_id, len(payload.items), payload.webhook_url, requester)
    add_job_items(job_id, [i.model_dump() for i in payload.items])
    return {"job_id": job_id, "status": "queued", "total": len(payload.items)}

@app.get("/v1/jobs/{job_id}")
async def job_status(job_id: str, ok=Depends(require_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    return {k: job[k] for k in ("id","status","total","done","webhook_url","created_ts")}

@app.get("/v1/jobs/{job_id}/results")
async def job_results(job_id: str, ok=Depends(require_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    items = list_job_items(job_id)
    return {
        "job": {"id": job["id"], "status": job["status"], "total": job["total"], "done": job["done"]},
        "results": [
            {
                "index": it["idx"],
                "status": it["status"],
                "payload": json.loads(it["payload"]),
                "result": (json.loads(it["result"]) if it["result"] else None)
            } for it in items
        ]
    }

# --- Admin: import SBA size standards CSV ---
@app.post("/v1/admin/size-standards/import")
async def import_size_standards(file: UploadFile = File(...), _=Depends(require_admin)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, detail="upload a CSV with headers: naics,title,basis,threshold,unit,effective_fy")
    content = await file.read()
    count = import_size_csv(content)
    return {"imported": count}
