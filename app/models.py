from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class Identifier(BaseModel):
    uei: Optional[str] = None
    cage: Optional[str] = None
    legal_name: Optional[str] = None

class SizeBasis(BaseModel):
    kind: Literal["receipts", "employees"]
    value: float

class EligibilityRequest(BaseModel):
    identifier: Identifier
    naics: str = Field(pattern=r"^\d{6}$")
    size_basis: Optional[SizeBasis] = None
    require_active_sam: bool = True
    include_evidence: bool = True

class Reason(BaseModel):
    code: str
    message: str

class Evidence(BaseModel):
    source: str
    fetched_at: str
    reference: str

class SamSummary(BaseModel):
    uei: Optional[str] = None
    cage: Optional[str] = None
    active: Optional[bool] = None

class ExclusionHit(BaseModel):
    name: str
    type: Optional[str] = None
    exclusion_status: Optional[str] = None
    exclusion_end: Optional[str] = None

class Exclusions(BaseModel):
    count: int
    hits: List[ExclusionHit] = []

class SizeResult(BaseModel):
    status: Literal["small", "other_than_small", "unknown"]
    basis: Literal["receipts", "employees", "unknown"]
    value: Optional[float] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    naics: str

class EligibilityResponse(BaseModel):
    eligible: bool
    summary: str
    reasons: List[Reason]
    sam: SamSummary
    exclusions: Exclusions
    size: SizeResult
    evidence: List[Evidence] = []
