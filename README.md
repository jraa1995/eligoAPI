# Eligibility & Go/No-Go API

An API that unifies **SAM Exclusions**, **SAM Entity status**, and **SBA size standard** checks to produce a simple **Go/No-Go** decision with audit-friendly evidence.

---

## Product Overview

**Problem.** Every pursuit requires repetitive, manual checks (SAM Exclusions, entity status, size standard against NAICS). It’s slow, error-prone, and hard to audit.

**Solution.** A unified API that:
- Accepts **UEI/CAGE/Legal Name** and a **NAICS** code
- Checks **Exclusions** (SAM.gov)
- Fetches **Entity** registration status (SAM.gov)
- Computes **SBA size determination** for that NAICS using receipts or employee count
- Returns a boolean **`eligible`** plus detailed **`reasons[]`** and **`evidence[]`** (source + timestamp + reference URL in live mode)

**Primary Users & Flows**
- **BD Go/No-Go form:** one-click checks, attach evidence to the pursuit record
- **Teaming partner screen:** bulk check partner eligibility across NAICS variants
- **Pricing/IGCE:** verify size for set-aside strategy alignment

**Non-Goals (v0.1)**
- Full certifications (HUBZone, WOSB, etc.) verification — *roadmap*
- Past performance / responsibility checks — *roadmap*

---

## Architecture (quick)

- **FastAPI** service (`app/main.py`)
- **Evaluator** composes: SAM Exclusions + SAM Entity + SBA size calculation
- **SQLite** persistence (audits, jobs, SBA size table)
- **Background worker** (bulk jobs + optional webhook callback)
- **Adapters** for SAM APIs (mockable with `ELIG_API_MOCK=1`)

---

## Prerequisites

- Python **3.11+**
- `pip`
- (Optional) Docker
- **SAM.gov API key** (for live mode)
- A client API key you control for header `x-api-key`

> We ship a `.gitignore` and `.dockerignore`. Keep **`.env`**, **`venv/`**, and **`eligibility.db`** out of git. If you ever committed secrets, rotate them.

---

## Install

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

---

## Run (Dev / Mock Mode)

Mock mode does **not** call SAM.gov. It returns “no exclusions” and “SAM active” so you can test size logic offline.

**macOS/Linux**
```bash
export ELIG_API_KEY=devkey
export ELIG_ADMIN_KEY=adminkey
export ELIG_API_MOCK=1
uvicorn app.main:app --reload
```

**Windows PowerShell**
```powershell
$env:ELIG_API_KEY="devkey"
$env:ELIG_ADMIN_KEY="adminkey"
$env:ELIG_API_MOCK="1"
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** (Swagger UI).

---

## Run (Live SAM.gov Mode)

Provide your SAM.gov key and **turn off** mock mode.

**macOS/Linux**
```bash
export ELIG_API_KEY=devkey
export ELIG_ADMIN_KEY=adminkey
unset ELIG_API_MOCK
export SAM_API_KEY="YOUR_SAM_KEY_HERE"
uvicorn app.main:app --reload
```

**Windows PowerShell**
```powershell
$env:ELIG_API_KEY="devkey"
$env:ELIG_ADMIN_KEY="adminkey"
Remove-Item Env:\ELIG_API_MOCK -ErrorAction SilentlyContinue
$env:SAM_API_KEY="YOUR_SAM_KEY_HERE"
uvicorn app.main:app --reload
```

> In live mode, responses include **real** Exclusions/Entity results and **evidence.reference** URLs pointing at the SAM queries.

### Optional: .env file

If you prefer a `.env` file (kept out of git), ensure `app/config.py` loads it:

```python
# app/config.py
from dotenv import load_dotenv
load_dotenv()
```

Then create `.env`:
```
ELIG_API_KEY=devkey
ELIG_ADMIN_KEY=adminkey
# ELIG_API_MOCK=1   # leave commented/absent to run live
SAM_API_KEY=YOUR_SAM_KEY_HERE
ELIG_DB=./eligibility.db
ELIG_RATE_LIMIT=60
```

Run:
```bash
uvicorn app.main:app --reload
```

---

## Endpoints

- `GET /v1/health` — liveness
- `GET /v1/naics/{code}/size-standard` — basis & threshold (reads DB; falls back to built-ins)
- `POST /v1/eligibility/check` — **Go/No-Go** for one entity
- `POST /v1/eligibility/bulk` — async job for many entities (optional webhook)
- `GET /v1/jobs/{job_id}` — job status
- `GET /v1/jobs/{job_id}/results` — job results
- `POST /v1/admin/size-standards/import` — **admin**: CSV upsert (`naics,title,basis,threshold,unit,effective_fy`)

---

## Quick Start Data (Size Table)

Use the sample file to seed size thresholds:
```csv
naics,title,basis,threshold,unit,effective_fy
541511,Custom Computer Programming Services,receipts,34500000,USD,2025
541512,Computer Systems Design Services,receipts,34500000,USD,2025
336611,Ship Building and Repairing,employees,1300,employees,2025
```

**Import (Admin)**

- **Windows PowerShell**
```powershell
curl.exe -H "x-admin-key: adminkey" -F "file=@size.csv;type=text/csv" `
  http://127.0.0.1:8000/v1/admin/size-standards/import
# {"imported": 3}
```

- **bash**
```bash
curl -H "x-admin-key: adminkey" -F "file=@size.csv;type=text/csv"   http://127.0.0.1:8000/v1/admin/size-standards/import
```

**Verify**
```bash
curl http://127.0.0.1:8000/v1/naics/541511/size-standard
```

---

## Examples: Eligibility (Single Entity)

### PowerShell (recommended)
```powershell
$payload = @{
  identifier = @{ uei = "YOUR-UEI" }  # or cage / legal_name
  naics = "541511"
  size_basis = @{ kind = "receipts"; value = 34500000 }  # <= threshold => SMALL
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/eligibility/check" `
  -Headers @{ "x-api-key" = "devkey" } `
  -ContentType "application/json" -Body $payload
```

### curl (bash)
```bash
curl -H "x-api-key: devkey" -H "content-type: application/json"   --data-raw '{ "identifier": { "uei": "YOUR-UEI" }, "naics": "541511",
                "size_basis": { "kind": "receipts", "value": 34500000 } }'   http://127.0.0.1:8000/v1/eligibility/check
```

**Response (shape)**

```json
{
  "eligible": true,
  "summary": "No exclusions; active SAM; size SMALL for 541511 (threshold: 34500000)",
  "reasons": [
    {"code":"NO_EXCLUSIONS","message":"No active exclusions found."},
    {"code":"SAM_ACTIVE","message":"Entity has an active registration."},
    {"code":"SIZE_SMALL","message":"Meets small business threshold."}
  ],
  "sam": {"uei":"...", "cage":"...", "active":true},
  "exclusions": {"count":0, "hits":[]},
  "size": {"status":"small","basis":"receipts","threshold":34500000,"unit":"USD","naics":"541511"},
  "evidence": [
    {"source":"sam_exclusions_api","reference":"<live-url-or-mock>","fetched_at":"..."},
    {"source":"sam_entity_api","reference":"<live-url-or-mock>","fetched_at":"..."}
  ]
}
```

**Flip outcomes quickly**

- **No-Go**: set `size_basis.value` above threshold
- **Unknown size**: omit `size_basis` (eligible remains `true` in v0.1 but flagged)

> Want unknown size to be a hard No-Go? In `app/services/evaluator.py` change:
> ```python
> size_ok = (size_status == "small")
> ```

---

## Examples: Bulk Screening

Start a job:
```powershell
$body = @{
  webhook_url = $null
  items = @(
    @{ identifier = @{ uei = "UEI-ALPHA" };   naics = "541511"; size_basis = @{ kind = "receipts"; value = 34000000 } },
    @{ identifier = @{ uei = "UEI-BRAVO" };   naics = "541511"; size_basis = @{ kind = "receipts"; value = 36000000 } },
    @{ identifier = @{ uei = "UEI-CHARLIE" }; naics = "336611"; size_basis = @{ kind = "employees"; value = 1299 } }
  )
} | ConvertTo-Json -Depth 6

$job = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/v1/eligibility/bulk" `
  -Headers @{ "x-api-key" = "devkey" } `
  -ContentType "application/json" -Body $body

Invoke-RestMethod -Headers @{ "x-api-key" = "devkey" } `
  -Uri ("http://127.0.0.1:8000/v1/jobs/" + $job.job_id)

Invoke-RestMethod -Headers @{ "x-api-key" = "devkey" } `
  -Uri ("http://127.0.0.1:8000/v1/jobs/" + $job.job_id + "/results")
```

---

## Docker

**Build**
```bash
docker build -t elig-api:latest .
```

**Run (mock)**
```bash
docker run --rm -p 8080:8080   -e ELIG_API_KEY=devkey   -e ELIG_ADMIN_KEY=adminkey   -e ELIG_API_MOCK=1   elig-api:latest
# http://127.0.0.1:8080/docs
```

**Run (live)**
```bash
docker run --rm -p 8080:8080   -e ELIG_API_KEY=devkey   -e ELIG_ADMIN_KEY=adminkey   -e SAM_API_KEY=YOUR_SAM_KEY_HERE   -e ELIG_API_MOCK=0   elig-api:latest
```

---

## Auth & Config

**Headers**
- Client requests: `x-api-key: <ELIG_API_KEY>`
- Admin import: `x-admin-key: <ELIG_ADMIN_KEY>`

**Environment variables**
- `ELIG_API_KEY` — client auth key
- `ELIG_ADMIN_KEY` — admin auth key
- `ELIG_API_MOCK` — `1` to mock SAM; unset/`0` for live
- `SAM_API_KEY` — **required in live mode**
- `ELIG_DB` — SQLite path (default `./eligibility.db`)
- `ELIG_RATE_LIMIT` — requests/min per key (default `60`)
- `ELIG_WEBHOOK_SIG` — HMAC secret for webhook signatures (optional)

---

## Persistence

SQLite DB (created on first run, path `ELIG_DB`) with tables:
- `audits` — request/response snapshots for `/v1/eligibility/check`
- `jobs`, `job_items` — bulk processing state
- `size_standards` — SBA size thresholds (populate via admin CSV)

---

## Security & Repo Hygiene

- Keep the repo **private**; enforce **MFA/SSO**.
- Do **not** commit `.env`, `eligibility.db`, or `venv/`.
- Enable GitHub **secret scanning / push protection**.
- Rotate credentials if leaked. Purge with `git filter-repo` if necessary.
- Run behind TLS + WAF; restrict admin routes by IP if possible.

---

## Troubleshooting

- **PowerShell “Bad hostname” / `-d` treated as command**  
  Use **backticks** for line breaks or prefer `Invoke-RestMethod`. `^` is for `cmd.exe`, not PowerShell.

- **JSON decode error**  
  Ensure payload uses straight double quotes (`"`) and send via `Invoke-RestMethod` or a here-string.

- **401 Unauthorized**  
  Missing/incorrect `x-api-key` or `x-admin-key`.

- **429 Rate limit exceeded**  
  Per-key limit (header `X-RateLimit-*`). Configure via `ELIG_RATE_LIMIT`.

- **Live SAM errors (403/401)**  
  Verify `SAM_API_KEY` is set and `ELIG_API_MOCK` is disabled.

---

## License

Proprietary — internal use only unless otherwise specified.
