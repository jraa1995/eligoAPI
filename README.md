# Eligibility & Go/No-Go API

An API for SAM exclusions + entity status + SBA size standard eligibility checks.

## Product Overview
Problem: Every pursuit requires repetitive, manual checks (SAM Exclusions, entity status, size standard against NAICS). It's slow, error-prone, and difficult to audit.

Solution: A unified API that:
- Accepts UEI/CAGE/Legal Name and a NAICS Code
- Checks Exclusions (SAM)
- (Where available) reads SAM Entity status/metadata
- Computes SBA size determination for that NAICS using receipts or employee count
- Returns a boolean "eligible" plus detailed reasons and evidence (source + timestamp)

Primary Users & Flows
- BD Go/No-Go form: one click checks and attaches evidence to the pursuit record
- Teaming partner screen: bulk check partner eligibility across NAICS variants
- Pricing/IGCE: verify size for set-aside strategy alignment

Non-Goals (v0.1)
- Full certifications (HUBZone, WOSB, etc) verification -- roadmap
- Full past performance, responsibility/qualification checks -- roadmap

## Quick Start (Stateful Mock Mode)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ELIG_API_KEY=devkey ELIG_ADMIN_KEY=adminkey ELIG_API_MOCK=1
uvicorn app.main:app --reload
```

### Endpoints
- `GET /v1/health`
- `GET /v1/naics/{code}/size-standard`
- `POST /v1/eligibility/check`
- `POST /v1/eligibility/bulk`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/results`
- `POST /v1/admin/size-standards/import` (admin key)

### Live Mode (SAM lookups)
```bash
unset ELIG_API_MOCK
export SAM_API_KEY=your_sam_key_here
uvicorn app.main:app --reload
```

### Example Size CSV
```csv
naics,title,basis,threshold,unit,effective_fy
541511,Custom Computer Programming Services,receipts,34500000,USD,2025
541512,Computer Systems Design Services,receipts,34500000,USD,2025
336611,Ship Building and Repairing,employees,1300,employees,2025
```
