# app/services/sam.py
"""
SAM.gov adapters used by the Eligibility & Go/No-Go API.

Exposed coroutines:
- fetch_exclusions(identifier) -> { count:int, hits:list[...], evidence:{...} }
- fetch_entity_summary(identifier) -> { uei:str|None, cage:str|None, active:bool|None, evidence:{...} }

`identifier` may include any of: { "uei", "cage", "legal_name" }.
In mock mode (ELIG_API_MOCK=1) both functions return deterministic fake data.

These functions are intentionally tolerant to upstream schema quirks and 404s.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from app.config import get_settings

settings = get_settings()


# ---------- Utilities ----------

def _now_iso() -> str:
    """UTC timestamp in RFC3339 basic format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _base_headers() -> Dict[str, str]:
    return {"Accept": "application/json"}


def _exclusions_params(identifier: Dict[str, str]) -> Dict[str, str]:
    """
    Build query params for Exclusions API.
    Docs occasionally expect different keys; we include the common ones.
    """
    p: Dict[str, str] = {"api_key": settings.sam_api_key or ""}
    if identifier.get("uei"):
        p["uei"] = identifier["uei"]
    if identifier.get("cage"):
        p["cageCode"] = identifier["cage"]
    if identifier.get("legal_name"):
        p["name"] = identifier["legal_name"]
    return p


def _entity_params(identifier: Dict[str, str]) -> Dict[str, str]:
    """
    Build query params for Entity API (registration status).
    """
    p: Dict[str, str] = {
        "api_key": settings.sam_api_key or "",
        "includes": "coreData,registration",
    }
    if identifier.get("uei"):
        p["uei"] = identifier["uei"]
    if identifier.get("cage"):
        p["cageCode"] = identifier["cage"]
    if identifier.get("legal_name"):
        p["legalBusinessName"] = identifier["legal_name"]
    return p


# ---------- Public API ----------

async def fetch_exclusions(identifier: Dict[str, str]) -> Dict[str, Any]:
    """
    Query SAM Exclusions API.

    Returns:
      {
        "count": <int>,
        "hits": [
          {"name": str, "type": str|None, "exclusion_status": str|None, "exclusion_end": str|None},
          ...
        ],
        "evidence": {"source": "sam_exclusions_api", "reference": str, "fetched_at": str}
      }
    """
    if settings.mock_mode:
        return {
            "count": 0,
            "hits": [],
            "evidence": {
                "source": "sam_exclusions_api",
                "reference": "mock",
                "fetched_at": _now_iso(),
            },
        }

    url = settings.sam_exclusions_base
    params = _exclusions_params(identifier)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=_base_headers(), params=params)
            # Treat 404 as "no exclusions found" for robustness
            if r.status_code == 404:
                return {
                    "count": 0,
                    "hits": [],
                    "evidence": {
                        "source": "sam_exclusions_api",
                        "reference": str(r.request.url),
                        "fetched_at": _now_iso(),
                    },
                }
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        # Bubble up to be handled as a 424/500 by the calling layer
        raise

    # Normalize results
    embedded = data.get("_embedded", {}) if isinstance(data, dict) else {}
    raw_hits: List[Dict[str, Any]] = embedded.get("exclusions", []) or []

    hits: List[Dict[str, Any]] = []
    for item in raw_hits:
        hits.append(
            {
                "name": item.get("name"),
                "type": item.get("exclusionType"),
                "exclusion_status": item.get("exclusionStatus"),
                "exclusion_end": item.get("exclusionEndDate"),
            }
        )

    return {
        "count": len(hits),
        "hits": hits,
        "evidence": {
            "source": "sam_exclusions_api",
            "reference": str(r.request.url),
            "fetched_at": _now_iso(),
        },
    }


async def fetch_entity_summary(identifier: Dict[str, str]) -> Dict[str, Any]:
    """
    Query SAM Entity API for registration status.

    Returns:
      {
        "uei": str|None,
        "cage": str|None,
        "active": bool|None,  # None when unknown
        "evidence": {"source": "sam_entity_api", "reference": str, "fetched_at": str}
      }
    """
    if settings.mock_mode:
        return {
            "uei": identifier.get("uei", "MOCKUEI123456"),
            "cage": identifier.get("cage", "MOCK1"),
            "active": True,
            "evidence": {
                "source": "sam_entity_api",
                "reference": "mock",
                "fetched_at": _now_iso(),
            },
        }

    url = settings.sam_entity_base
    params = _entity_params(identifier)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=_base_headers(), params=params)
            # If entity not found, return unknown status
            if r.status_code == 404:
                return {
                    "uei": identifier.get("uei"),
                    "cage": identifier.get("cage"),
                    "active": None,
                    "evidence": {
                        "source": "sam_entity_api",
                        "reference": str(r.request.url),
                        "fetched_at": _now_iso(),
                    },
                }
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        # Bubble up (caller will convert to 424/500)
        raise

    embedded = data.get("_embedded", {}) if isinstance(data, dict) else {}
    entities = embedded.get("entities", []) or []

    if not entities:
        return {
            "uei": identifier.get("uei"),
            "cage": identifier.get("cage"),
            "active": None,
            "evidence": {
                "source": "sam_entity_api",
                "reference": str(r.request.url),
                "fetched_at": _now_iso(),
            },
        }

    e = entities[0] or {}
    entity_block = e.get("entity", {}) or {}
    reg_block = e.get("registration", {}) or {}

    active = (reg_block.get("status") == "Active")
    uei = entity_block.get("uei")
    cage = entity_block.get("cageCode")

    return {
        "uei": uei,
        "cage": cage,
        "active": active,
        "evidence": {
            "source": "sam_entity_api",
            "reference": str(r.request.url),
            "fetched_at": _now_iso(),
        },
    }
