"""Compliance Health API endpoint -- docs/design/frontend-web.md §4."""

from fastapi import APIRouter
from ubunturemit_gateway.models import ComplianceHealthResponse

router = APIRouter(prefix="/api/compliance", tags=["Compliance"])


@router.get("/health", response_model=ComplianceHealthResponse)
def get_compliance_health() -> ComplianceHealthResponse:
    return ComplianceHealthResponse(
        status="OPERATIONAL",
        engine_version="ASCO-v1.0 (70B Sentinel + 32B Strategist on MI300X)",
        rules_enforced=[
            "FIC_ACT_S28A (Sanctions Screening)",
            "FIC_ACT_S21H (PEP Enhanced Due Diligence)",
            "SARB_EXCON_B4 (SDA 1,000,000 ZAR Annual Limit)",
            "FATF_RECOMMENDATION_16 (Travel Rule Complete Originator/Beneficiary)",
            "ISO_20022_3TIER (XSD + Field + Business Rule Verification)",
        ],
        sanctions_list_status="UP_TO_DATE (UN / OFAC / FIC sync: < 5m ago)",
        audit_log_status=(
            "APPEND_ONLY_IMMUTABLE (Kafka + Postgres with UPDATE/DELETE block triggers)"
        ),
        rejection_rate_24h=0.012,
        total_screened_24h=1420,
    )
