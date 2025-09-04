from app.models import EligibilityRequest, EligibilityResponse, Reason, Evidence, SamSummary, Exclusions, SizeResult
from app.services import sam as sam_svc
from app.services import sba as sba_svc
from app.services import naics as naics_svc

async def evaluate(payload: EligibilityRequest) -> EligibilityResponse:
    # Validate NAICS
    if not naics_svc.valid_naics(payload.naics):
        raise ValueError("invalid NAICS")

    reasons = []
    evidence = []

    # Exclusions
    excl = await sam_svc.fetch_exclusions(payload.identifier.model_dump(exclude_none=True))
    if excl.get("evidence"): evidence.append(excl["evidence"])
    if excl["count"] > 0:
        reasons.append(Reason(code="HAS_EXCLUSIONS", message=f"{excl['count']} exclusion(s) found"))
    else:
        reasons.append(Reason(code="NO_EXCLUSIONS", message="No active exclusions found."))

    # Entity summary
    entity = await sam_svc.fetch_entity_summary(payload.identifier.model_dump(exclude_none=True))
    if entity.get("evidence"): evidence.append(entity["evidence"])
    sam_active = entity.get("active")
    if payload.require_active_sam:
        if sam_active is True:
            reasons.append(Reason(code="SAM_ACTIVE", message="Entity has an active registration."))
        elif sam_active is False:
            reasons.append(Reason(code="SAM_INACTIVE", message="Entity registration not active."))
        else:
            reasons.append(Reason(code="SAM_UNKNOWN", message="Could not verify SAM registration status."))

    # Size determination
    basis_kind = payload.size_basis.kind if payload.size_basis else None
    basis_val = payload.size_basis.value if payload.size_basis else None
    size = sba_svc.compute_size_status(payload.naics, basis_kind, basis_val)
    size_status = size["status"]
    if size_status == "small":
        reasons.append(Reason(code="SIZE_SMALL", message="Meets small business threshold."))
    elif size_status == "other_than_small":
        reasons.append(Reason(code="SIZE_OTS", message="Exceeds small business threshold."))
    else:
        reasons.append(Reason(code="SIZE_UNKNOWN", message="Size basis missing or mismatched for this NAICS."))

    # Eligible logic
    has_excl = excl["count"] > 0
    sam_ok = (sam_active is True) if payload.require_active_sam else True
    size_ok = (size_status in ("small", "unknown"))  # unknown allowed but flagged

    eligible = (not has_excl) and sam_ok and size_ok

    summary_bits = []
    summary_bits.append("No exclusions" if not has_excl else "Has exclusions")
    if payload.require_active_sam:
        summary_bits.append("active SAM" if sam_ok else "SAM not active/unknown")
    if size_status == "small":
        summary_bits.append(f"size SMALL for {payload.naics} (threshold: {size['threshold']})")
    elif size_status == "other_than_small":
        summary_bits.append(f"size OTS for {payload.naics} (threshold: {size['threshold']})")
    else:
        summary_bits.append("size evidence required")

    return EligibilityResponse(
        eligible=eligible,
        summary="; ".join(summary_bits),
        reasons=reasons,
        sam=SamSummary(uei=entity.get("uei"), cage=entity.get("cage"), active=entity.get("active")),
        exclusions=Exclusions(count=excl["count"], hits=excl["hits"]),
        size=SizeResult(**size),
        evidence=[Evidence(**e) for e in evidence]
    )
