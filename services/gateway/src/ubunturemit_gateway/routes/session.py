"""Session and authenticated institution profile API endpoint."""

from fastapi import APIRouter
from ubunturemit_gateway.models import SessionResponse

router = APIRouter(prefix="/api/session", tags=["Session"])


@router.get("", response_model=SessionResponse)
def get_session() -> SessionResponse:
    return SessionResponse(
        institution_id="INST-ZA-001",
        institution_name="Standard Bank of South Africa",
        country="ZA",
        kyc_tier="TIER_3",
        status="ACTIVE_PARTICIPANT",
    )
