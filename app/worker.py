import asyncio, json, hmac, hashlib, httpx
from app.db import fetch_next_job_item, mark_job_item_started, mark_job_item_done, update_job_progress, get_job
from app.models import EligibilityRequest
from app.services.evaluator import evaluate
from app.config import get_settings

settings = get_settings()

async def _send_webhook(job: dict):
    if not job.get("webhook_url"):
        return
    payload = {"job_id": job["id"], "status": job["status"], "total": job["total"], "done": job["done"]}
    headers = {"content-type": "application/json"}
    if settings.webhook_sig_key:
        body = json.dumps(payload).encode()
        sig = hmac.new(settings.webhook_sig_key.encode(), body, hashlib.sha256).hexdigest()
        headers["x-elig-signature"] = sig
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(job["webhook_url"], json=payload, headers=headers)
        except Exception:
            pass  # best-effort

async def worker_loop():
    while True:
        item = fetch_next_job_item()
        if not item:
            await asyncio.sleep(0.5)
            continue
        mark_job_item_started(item["id"])
        try:
            req = EligibilityRequest.model_validate_json(item["payload"])
            res = await evaluate(req)
            mark_job_item_done(item["id"], json.loads(res.model_dump_json()))
            update_job_progress(item["job_id"])  # may mark job complete
            job = get_job(item["job_id"])  # after progress update
            if job and job["status"] == "complete":
                await _send_webhook(job)
        except Exception as e:
            mark_job_item_done(item["id"], {"error": str(e)})
            update_job_progress(item["job_id"])
