import time
from typing import Any, Dict
import httpx
from app.config import get_settings

settings = get_settings()

async def fetch_exclusions(identifier: Dict[str, str]) -> Dict[str, Any]:
    if settings.mock_mode:
        return {"count": 0, "hits": [], "evidence": {"source": "sam_exclusions_api", "reference": "mock", "fetched_at": time.strftime('%Y-%m-%dT%H:%M:%SZ")}}
    headers = {"Accept": "application/json"}
    params = {"api_key": settings.sam_api_key}
    if identifier.get("uei"): params["uei"] = identifier["uei"]
    if identifier.get("cage"): params["cageCode"] = identifier["cage"]
    if identifier.get("legal_name"): params["name"] = identifier["legal_name"]
    url = settings.sam_exclusions_base
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        hits = []
        for item in data.get("_embedded", {}).get("exclusions", []):
            hits.append({
                "name": item.get("name"),
                "type": item.get("exclusionType"),
                "exclusion_status": item.get("exclusionStatus"),
                "exclusion_end": item.get("exclusionEndDate"),
            })
        return {
            "count": len(hits),
            "hits": hits,
            "evidence": {
                "source": "sam_exclusions_api",
                "reference": str(r.request.url),
                "fetched_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
        }

async def fetch_entity_summary(identifier: Dict[str, str]) -> Dict[str, Any]:
    if settings.mock_mode:
        return {"uei": identifier.get("uei", "MOCKUEI123456"), "cage": identifier.get("cage", "MOCK1"), "active": True, "evidence": {"source": "sam_entity_api", "reference": "mock", "fetched_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')}}
    headers = {"Accept": "application/json"}
    params = {"api_key": settings.sam_api_key, "includes": "coreData,registration"}
    if identifier.get("uei"): params["uei"] = identifier["uei"]
    if identifier.get("cage"): params["cageCode"] = identifier["cage"]
    if identifier.get("legal_name"): params["legalBusinessName"] = identifier["legal_name"]
    url = settings.sam_entity_base
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        entities = data.get("_embedded", {}).get("entities", [])
        if not entities:
            return {"uei": identifier.get("uei"), "cage": identifier.get("cage"), "active": None, "evidence": {"source": "sam_entity_api", "reference": str(r.request.url), "fetched_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')}}
        e = entities[0]
        active = e.get("registration", {}).get("status") == "Active"
        uei = e.get("entity", {}).get("uei")
        cage = (e.get("entity", {}).get("cageCode") if e.get("entity") else None)
        return {"uei": uei, "cage": cage, "active": active, "evidence": {"source": "sam_entity_api", "reference": str(r.request.url), "fetched_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')}}
